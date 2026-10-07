import gc
import logging
import multiprocessing
import re
import sys
import tkinter as tk
from typing import Any

import customtkinter as ctk

import utils.config_manager as cm
import utils.constants as c
import utils.i18n as i18n
import utils.path_helper as ph
from controllers.history_controller import HistoryController
from controllers.main_controller import MainController
from controllers.transcription_queue import TranscriptionQueue
from interfaces.summarizer import Summarizer
from interfaces.translator import Translator
from models.config.config_system import ConfigSystem
from models.config.config_whisperx import ConfigWhisperX
from utils.enums import ComputeType
from utils.env_keys import migrate_env_file
from utils.history_store import HistoryStore
from utils.system import hide_console_windows
from views.main_window.main_window import MainWindow
from views.style import theme

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    DnDWrapper: Any = TkinterDnD.DnDWrapper
except ImportError:  # Drag and drop is optional
    DnDWrapper = object

WINDOW_SIZE = (1280, 820)
WINDOW_MIN_SIZE = (960, 600)
# Pixels of the window that must be on the screen to restore its position
VISIBLE_WINDOW_MARGIN = 100
# Time the window must stay still before its size and position are stored
WINDOW_GEOMETRY_SAVE_DELAY_MS = 500
# How often the garbage is collected on the Tkinter thread
GC_INTERVAL_MS = 250

# Command on macOS, Control on Windows and Linux
SHORTCUT_MODIFIER = theme.SHORTCUT_MODIFIER

logger = logging.getLogger(__name__)


def parse_geometry(geometry: str) -> tuple[int, int, int, int] | None:
    """
    Parses a Tk geometry like "1280x820+100+50".

    :return: The width, height, x and y, or None if the geometry isn't valid.
    """
    match = re.fullmatch(r"(\d+)x(\d+)([+-]-?\d+)([+-]-?\d+)", geometry.strip())
    if not match:
        return None

    width, height = int(match[1]), int(match[2])
    if width < WINDOW_MIN_SIZE[0] or height < WINDOW_MIN_SIZE[1]:
        return None

    # Tk writes "+-10" for a negative position
    x, y = (int(value.replace("+-", "-")) for value in (match[3], match[4]))
    return width, height, x, y


def is_on_screen(
    window: tuple[int, int, int, int], screen_size: tuple[int, int]
) -> bool:
    """
    Whether a part of the window big enough to drag it would be visible. Tk only
    knows the size of the main screen, so the windows on the other screens are
    accepted if they are close enough: up to two screens to the left or to the
    right, and one screen above or below. The screens to the left of or above the
    main screen have negative coordinates.

    :param window: The width, height, x and y of the window.
    :param screen_size: The width and height of the main screen.
    """
    width, height, x, y = window
    screen_width, screen_height = screen_size
    return bool(
        -screen_width * 2 + VISIBLE_WINDOW_MARGIN < x + width
        and x < screen_width * 3 - VISIBLE_WINDOW_MARGIN
        and -screen_height + VISIBLE_WINDOW_MARGIN < y + height
        and y < screen_height * 2 - VISIBLE_WINDOW_MARGIN
    )


def configure_whisperx_device() -> None:
    """
    Stores in the configuration whether a GPU is available. If not, WhisperX is
    configured to run on the CPU with a compute type the CPU supports.
    """
    # Imported here to avoid the "No ffmpeg exe could be found" error
    import torch

    can_use_gpu = torch.cuda.is_available()

    cm.ConfigManager.modify_value(
        section=ConfigWhisperX.Key.SECTION,
        key=ConfigWhisperX.Key.CAN_USE_GPU,
        new_value=str(can_use_gpu),
    )

    if not can_use_gpu:
        cm.ConfigManager.modify_value(
            section=ConfigWhisperX.Key.SECTION,
            key=ConfigWhisperX.Key.COMPUTE_TYPE,
            new_value=ComputeType.INT8.value,
        )
        cm.ConfigManager.modify_value(
            section=ConfigWhisperX.Key.SECTION,
            key=ConfigWhisperX.Key.USE_CPU,
            new_value="True",
        )


class App(ctk.CTk, DnDWrapper):  # type: ignore[misc]
    def __init__(
        self,
        summarizer: Summarizer | None = None,
        translator: Translator | None = None,
    ) -> None:
        """
        :param summarizer: Summarizes the entries of the history. By default, with
                           the configured language model.
        :param translator: Translates the entries of the history. By default, with
                           the provider chosen by the user.
        """
        super().__init__()

        config_system = cm.ConfigManager.get_config_system()
        i18n.set_language(config_system.ui_language)

        # Modes: "System", "Dark", "Light"
        ctk.set_appearance_mode(config_system.appearance_mode)
        # Themes: "blue" (standard), "green", "dark-blue"
        ctk.set_default_color_theme("blue")

        self.title(c.APP_NAME)
        self._set_icon()

        self.minsize(*WINDOW_MIN_SIZE)
        self._restore_window_geometry(config_system)

        configure_whisperx_device()
        # Previous versions stored the API keys in a plain-text file
        migrate_env_file()

        config_dir = ph.get_user_config_dir()
        self._history_store = HistoryStore(
            config_dir / "history.json", config_dir / "media"
        )

        store = self._history_store
        self._view = MainWindow(
            self,
            store,
            create_history=lambda view: HistoryController(
                store, view, summarizer=summarizer, translator=translator
            ),
            create_jobs=lambda view: TranscriptionQueue(
                store, view, create_runner=lambda queue: MainController(queue, view)
            ),
        )
        self._view.pack(fill="both", expand=True)
        if config_system.check_for_updates:
            self._view.check_for_updates()

        self._bind_shortcuts()
        self._enable_drag_and_drop()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if sys.platform == "darwin":
            # Command + Q and the Quit item of the menu don't close the window
            self.createcommand("::tk::mac::Quit", self._on_close)

        # Python collects the garbage in whichever thread is allocating memory.
        # The Tkinter objects found in it (variables, fonts and images of destroyed
        # widgets) are deleted in Tcl when finalized, which crashes the app if it
        # happens in a background thread (e.g. while WhisperX is being loaded). So
        # the garbage is only collected on the Tkinter thread
        gc.disable()
        self._collect_garbage()

    # WINDOW GEOMETRY

    def _restore_window_geometry(self, config_system: ConfigSystem) -> None:
        """
        Opens the window with the size and position it had when it was closed, or
        centered with the default size the first time.
        """
        geometry = parse_geometry(config_system.window_geometry)
        screen_size = (self.winfo_screenwidth(), self.winfo_screenheight())
        if geometry and is_on_screen(geometry, screen_size):
            width, height, x, y = geometry
            # Tk reads "-10" as a distance to the right edge, and "+-10" as negative
            self._normal_geometry = f"{width}x{height}+{x}+{y}"
            self.geometry(self._normal_geometry)
        else:
            width, height = WINDOW_SIZE
            self.geometry(f"{width}x{height}")
            self.eval("tk::PlaceWindow . center")
            # Known once the window is shown
            self._normal_geometry = ""

        if config_system.is_window_maximized:
            self.after(0, self._maximize)

        # The size and position are stored while the window is used, so they
        # aren't lost if the app isn't closed with the close button
        self._saved_window_state = (
            self._normal_geometry,
            config_system.is_window_maximized,
        )
        self._save_window_state_job: str | None = None
        self.bind("<Configure>", self._on_configure, add="+")

    def _maximize(self) -> None:
        try:
            if sys.platform.startswith("linux"):
                self.attributes("-zoomed", True)
            else:
                self.state("zoomed")
        except tk.TclError:
            logger.debug("Could not maximize the window")

    def _is_maximized(self) -> bool:
        try:
            # The green button of macOS makes the window full screen instead
            if self.attributes("-fullscreen"):
                return True
            if sys.platform.startswith("linux"):
                return bool(self.attributes("-zoomed"))
            return bool(self.state() == "zoomed")
        except tk.TclError:
            return False

    def _on_configure(self, event: Any) -> None:
        # The event is also received for every widget of the window
        if event.widget is not self:
            return

        # The window sends an event for every step while it's moved or resized.
        # Also, when it's maximized, it sends the events before its state changes,
        # so the maximized size would be taken as the normal one
        if self._save_window_state_job:
            self.after_cancel(self._save_window_state_job)
        self._save_window_state_job = self.after(
            WINDOW_GEOMETRY_SAVE_DELAY_MS, self._save_window_state
        )

    def _save_window_state(self) -> None:
        """
        Stores the size and position the window has without being maximized, and
        whether it's maximized, to open it the same way the next time.
        """
        self._save_window_state_job = None
        # Minimized or hidden
        if self.state() in ("iconic", "withdrawn"):
            return

        is_maximized = self._is_maximized()
        if not is_maximized:
            self._normal_geometry = self.geometry()

        window_state = (self._normal_geometry, is_maximized)
        if window_state == self._saved_window_state:
            return

        try:
            if self._normal_geometry:
                cm.ConfigManager.modify_value(
                    ConfigSystem.Key.SECTION,
                    ConfigSystem.Key.WINDOW_GEOMETRY,
                    self._normal_geometry,
                )
            cm.ConfigManager.modify_value(
                ConfigSystem.Key.SECTION,
                ConfigSystem.Key.IS_WINDOW_MAXIMIZED,
                str(is_maximized),
            )
        except OSError:
            logger.exception("Could not save the size and position of the window")
        else:
            self._saved_window_state = window_state

    def _on_close(self) -> None:
        if self._save_window_state_job:
            self.after_cancel(self._save_window_state_job)
        self._save_window_state()
        self.destroy()

    def _bind_shortcuts(self) -> None:
        shortcuts = {
            f"<{SHORTCUT_MODIFIER}-Return>": self._view.trigger_main_action,
            f"<{SHORTCUT_MODIFIER}-s>": self._view.trigger_save,
            f"<{SHORTCUT_MODIFIER}-o>": self._view.trigger_browse,
            f"<{SHORTCUT_MODIFIER}-f>": self._view.trigger_search,
            "<Escape>": self._view.trigger_cancel,
        }

        for sequence, action in shortcuts.items():
            self.bind(sequence, lambda _event, action=action: action())

        # Playback and navigation of the list, ignored while typing
        for sequence in ("<space>", "<Left>", "<Right>", "<Up>", "<Down>"):
            self.bind_all(sequence, self._view.handle_key, add="+")

    def _enable_drag_and_drop(self) -> None:
        if DnDWrapper is object:
            return

        try:
            TkinterDnD._require(self)
        except (RuntimeError, tk.TclError):
            logger.warning("Drag and drop is not available on this system")
            return

        self.drop_target_register(DND_FILES)
        self.dnd_bind(
            "<<Drop>>",
            lambda event: self._view.on_files_dropped(
                list(self.tk.splitlist(event.data))
            ),
        )

    def _collect_garbage(self) -> None:
        """Runs the collections that Python would run automatically."""
        threshold0, threshold1, threshold2 = gc.get_threshold()
        count0, count1, count2 = gc.get_count()
        if count0 > threshold0:
            if count1 > threshold1:
                gc.collect(2 if count2 > threshold2 else 1)
            else:
                gc.collect(0)
        self.after(GC_INTERVAL_MS, self._collect_garbage)

    def _set_icon(self) -> None:
        try:
            self.wm_iconbitmap(ph.ROOT_PATH / "res/windows/icon.ico")
        except tk.TclError:
            # `.ico` files are not supported on some platforms (e.g. Linux)
            logger.debug("Could not set the window icon")


if __name__ == "__main__":
    # The bundled app is also run for the helper processes of multiprocessing (e.g.
    # the resource tracker used by PyTorch), which would otherwise open another window
    multiprocessing.freeze_support()
    hide_console_windows()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    app = App()
    app.mainloop()
