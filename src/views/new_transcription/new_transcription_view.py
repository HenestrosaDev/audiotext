import contextlib
import logging
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog
from typing import Any

import customtkinter as ctk

import utils.constants as c
from models.transcription_settings import TranscriptionSettings
from utils.enums import AudioSource
from utils.env_keys import EnvKeys
from utils.folder_watcher import list_supported_files
from utils.i18n import _
from utils.media import MediaInfo, probe_media
from utils.time_format import format_duration
from utils.validators import is_valid_url, is_youtube_url
from views.localization import Text, localize
from views.settings.settings_form import FormMode, SettingsForm
from views.style import icons, theme
from views.widgets.bindings import bind_wraplength
from views.widgets.stepper import Stepper

logger = logging.getLogger(__name__)

SOURCE_STEP = 0
SETTINGS_STEP = 1

StartCallback = Callable[[AudioSource, str, TranscriptionSettings], None]


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


class NewTranscriptionView(ctk.CTkFrame):  # type: ignore[misc]
    """
    Guides the user through a new transcription of a file, a URL or a folder:
    first the source, then the settings. Once started, the transcription is shown
    in the history, where its progress is followed (the last step).
    """

    def __init__(
        self,
        master: Any,
        source: AudioSource,
        on_start: StartCallback,
        on_set_api_key: Callable[[EnvKeys, str], None],
        on_model_change: Callable[[], None],
        is_busy: Callable[[], bool],
        run_on_ui_thread: Callable[..., None],
        initial_settings: TranscriptionSettings | None = None,
    ) -> None:
        """
        :param initial_settings: The settings to start from (e.g. those of a
                                 transcription that failed), instead of the
                                 configured ones.
        """
        super().__init__(master, fg_color="transparent")
        assert source in (AudioSource.FILE, AudioSource.YOUTUBE, AudioSource.DIRECTORY)

        self.source = source
        self._on_start = on_start
        self._on_set_api_key = on_set_api_key
        self._on_model_change = on_model_change
        self._is_busy = is_busy
        self._run_on_ui_thread = run_on_ui_thread
        self._initial_settings = initial_settings
        self._step = SOURCE_STEP
        self._selected: str = ""
        # Increases with each selection, so stale background results are ignored
        self._selection_number = 0

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._init_header()
        self.frm_source = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_source.grid_columnconfigure(0, weight=1)
        self.frm_source.grid_rowconfigure(0, weight=1)
        if source == AudioSource.YOUTUBE:
            self._init_url_step()
        else:
            self._init_path_step()

        self.frm_settings: SettingsForm | None = None
        self._init_footer()
        self._show_step(SOURCE_STEP)

    # WIDGETS

    def _init_header(self) -> None:
        # The icon, the title, the subtitle and the first step of each source
        titles: dict[AudioSource, tuple[str, Text, Text, Text]] = {
            AudioSource.FILE: (
                "file",
                lambda: _("Transcribe a file"),
                lambda: _(
                    "Audio and video files: MP3, WAV, M4A, MP4, MOV, MKV and more."
                ),
                lambda: _("Choose a file"),
            ),
            AudioSource.YOUTUBE: (
                "link",
                lambda: _("Transcribe from a URL"),
                lambda: _(
                    "A YouTube video or a direct link to an audio or video file."
                ),
                lambda: _("Enter the URL"),
            ),
            AudioSource.DIRECTORY: (
                "folder",
                lambda: _("Transcribe a folder"),
                lambda: _(
                    "All the audio and video files of a folder, or the new ones as they're added."
                ),
                lambda: _("Choose a folder"),
            ),
        }
        icon_name, title, subtitle, source_step = titles[self.source]

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=32, pady=(26, 0), sticky=ctk.EW)
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            header,
            text="",
            image=icons.icon(icon_name, 22, theme.ICON_ON_ACCENT),
            width=40,
            height=40,
            corner_radius=10,
            fg_color=theme.ACCENT,
        ).grid(row=0, column=0, rowspan=2, padx=(0, 14))
        localize(
            ctk.CTkLabel(header, font=theme.font(22, "bold"), anchor=ctk.W), text=title
        ).grid(row=0, column=1, sticky=ctk.W)
        localize(
            ctk.CTkLabel(
                header, font=theme.font(13), text_color=theme.HINT_TEXT, anchor=ctk.W
            ),
            text=subtitle,
        ).grid(row=1, column=1, sticky=ctk.W)

        self.stepper = Stepper(
            self, [source_step, lambda: _("Settings"), lambda: _("Transcribe")]
        )
        self.stepper.grid(row=1, column=0, padx=32, pady=(22, 18), sticky=ctk.EW)

    def _card(self, master: Any) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            master,
            fg_color=theme.CARD_BG,
            border_color=theme.CARD_BORDER,
            border_width=1,
            corner_radius=14,
        )

    def _init_path_step(self) -> None:
        is_file = self.source == AudioSource.FILE

        # Drop zone, shown until a file or folder is chosen
        self.frm_drop_zone = self._card(self.frm_source)
        self.frm_drop_zone.grid_columnconfigure(0, weight=1)
        self.frm_drop_zone.grid_rowconfigure((0, 5), weight=1)
        ctk.CTkLabel(
            self.frm_drop_zone,
            text="",
            image=icons.icon("import", 46, theme.ICON_MUTED),
        ).grid(row=1, column=0, pady=(0, 10))
        localize(
            ctk.CTkLabel(self.frm_drop_zone, font=theme.font(17, "bold")),
            text=lambda: (
                _("Drop an audio or video file here")
                if is_file
                else _("Drop a folder here")
            ),
        ).grid(row=2, column=0)
        localize(
            ctk.CTkLabel(
                self.frm_drop_zone, font=theme.font(13), text_color=theme.HINT_TEXT
            ),
            text=lambda: _("or"),
        ).grid(row=3, column=0, pady=6)
        localize(
            ctk.CTkButton(
                self.frm_drop_zone,
                height=36,
                font=theme.font(14),
                command=self.trigger_browse,
            ),
            text=lambda: (
                (_("Choose a file…") if is_file else _("Choose a folder…"))
                + f"   {theme.SHORTCUT_MODIFIER_LABEL}O"
            ),
        ).grid(row=4, column=0)

        # Summary of the chosen file or folder
        self.frm_summary = self._card(self.frm_source)
        self.frm_summary.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            self.frm_summary,
            text="",
            image=icons.icon("file" if is_file else "folder", 30, theme.ACCENT_TEXT),
            width=56,
            height=56,
            corner_radius=12,
            fg_color=theme.SUBTLE_BG,
        ).grid(row=0, column=0, rowspan=3, padx=20, pady=20)
        self.lbl_summary_name = ctk.CTkLabel(
            self.frm_summary, text="", font=theme.font(16, "bold"), anchor=ctk.W
        )
        self.lbl_summary_name.grid(row=0, column=1, sticky=ctk.SW, pady=(20, 0))
        self.lbl_summary_path = ctk.CTkLabel(
            self.frm_summary,
            text="",
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
        )
        self.lbl_summary_path.grid(row=1, column=1, sticky=ctk.W)
        self.lbl_summary_details = ctk.CTkLabel(
            self.frm_summary, text="", font=theme.font(13), anchor=ctk.W
        )
        self.lbl_summary_details.grid(row=2, column=1, sticky=ctk.NW, pady=(0, 20))
        localize(
            ctk.CTkButton(
                self.frm_summary,
                width=90,
                command=self.trigger_browse,
                **theme.SECONDARY_BUTTON,
            ),
            text=lambda: _("Change…"),
        ).grid(row=0, column=2, rowspan=3, padx=20)

        self.frm_drop_zone.grid(row=0, column=0, sticky=ctk.NSEW)

    def _init_url_step(self) -> None:
        card = self._card(self.frm_source)
        card.grid(row=0, column=0, sticky="new")
        card.grid_columnconfigure(0, weight=1)

        localize(
            ctk.CTkLabel(card, font=theme.font(15, "bold")), text=lambda: _("URL")
        ).grid(row=0, column=0, padx=22, pady=(20, 6), sticky=ctk.W)
        self._url_variable = ctk.StringVar(self)
        self._url_variable.trace_add("write", lambda *_args: self._on_url_change())
        self.ent_url = ctk.CTkEntry(
            card,
            textvariable=self._url_variable,
            height=40,
            font=theme.font(14),
            placeholder_text="https://www.youtube.com/watch?v=…",
        )
        self.ent_url.grid(row=1, column=0, padx=(22, 8), sticky=ctk.EW)
        self.ent_url.bind("<Return>", lambda _event: self.trigger_primary())
        localize(
            ctk.CTkButton(
                card,
                width=80,
                height=40,
                command=self._on_paste,
                **theme.SECONDARY_BUTTON,
            ),
            text=lambda: _("Paste"),
        ).grid(row=1, column=1, padx=(0, 22))

        self.lbl_url_status = ctk.CTkLabel(
            card, text="", font=theme.font(12), anchor=ctk.W
        )
        self.lbl_url_status.grid(
            row=2, column=0, columnspan=2, padx=22, pady=(6, 0), sticky=ctk.W
        )
        localize(
            ctk.CTkLabel(
                card, font=theme.font(12), text_color=theme.HINT_TEXT, anchor=ctk.W
            ),
            text=lambda: _(
                "Examples: https://youtu.be/dQw4w9WgXcQ · "
                "https://example.com/podcast/episode-12.mp3"
            ),
        ).grid(row=3, column=0, columnspan=2, padx=22, pady=(2, 20), sticky=ctk.W)

    def _init_footer(self) -> None:
        ctk.CTkFrame(self, height=1, fg_color=theme.DIVIDER).grid(
            row=3, column=0, sticky=ctk.EW
        )
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, padx=32, pady=14, sticky=ctk.EW)
        footer.grid_columnconfigure(1, weight=1)

        self.btn_back = localize(
            ctk.CTkButton(
                footer,
                image=icons.icon("chevron_left", 12),
                compound=ctk.LEFT,
                width=90,
                height=36,
                command=lambda: self._show_step(SOURCE_STEP),
                **theme.SECONDARY_BUTTON,
            ),
            text=lambda: _("Back"),
        )
        self.btn_back.grid(row=0, column=0)

        self.lbl_footer = ctk.CTkLabel(
            footer,
            text="",
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            anchor=ctk.E,
            justify=ctk.RIGHT,
        )
        self.lbl_footer.grid(row=0, column=1, padx=14, sticky=ctk.EW)
        bind_wraplength(self.lbl_footer, margin=10)

        self.btn_primary = ctk.CTkButton(
            footer,
            height=36,
            width=170,
            font=theme.font(14, "bold"),
            command=self.trigger_primary,
        )
        self.btn_primary.grid(row=0, column=2)

    # PUBLIC METHODS

    def set_source(self, value: str, should_advance: bool = False) -> None:
        """
        Sets the file, folder or URL to transcribe.

        :param should_advance: Whether to go to the settings (e.g. when a file is
                               dropped on the window).
        """
        if self.source == AudioSource.YOUTUBE:
            self._url_variable.set(value)
        else:
            self._set_path(value)

        if should_advance and self._is_source_valid():
            self._show_step(SETTINGS_STEP)

    def trigger_primary(self) -> None:
        if self._step == SOURCE_STEP:
            if self._is_source_valid():
                self._show_step(SETTINGS_STEP)
            elif self.source == AudioSource.YOUTUBE:
                self._on_url_change(is_submitting=True)
            else:
                self.trigger_browse()
        else:
            self._start()

    def trigger_browse(self) -> None:
        if self.source == AudioSource.FILE:
            path = filedialog.askopenfilename(
                title=_("Select a file"),
                filetypes=[
                    (_("All supported files"), c.SUPPORTED_FILE_EXTENSIONS),
                    (_("Audio files"), c.AUDIO_FILE_EXTENSIONS),
                    (_("Video files"), c.VIDEO_FILE_EXTENSIONS),
                ],
            )
        elif self.source == AudioSource.DIRECTORY:
            path = filedialog.askdirectory(title=_("Select a folder"))
        else:
            self.ent_url.focus_set()
            return

        if path:
            self.set_source(path, should_advance=False)

    def focus_input(self) -> None:
        if self.source == AudioSource.YOUTUBE and self._step == SOURCE_STEP:
            self.ent_url.focus_set()

    def refresh_api_keys(self) -> None:
        if self.frm_settings:
            self.frm_settings.refresh_api_keys()

    # STEPS

    def _show_step(self, step: int) -> None:
        self._step = step
        self.stepper.set_current(step)

        if step == SOURCE_STEP:
            if self.frm_settings:
                self.frm_settings.grid_remove()
            self.frm_source.grid(
                row=2, column=0, padx=32, pady=(0, 20), sticky=ctk.NSEW
            )
            self.btn_back.grid_remove()
            localize(self.btn_primary, text=lambda: _("Continue"))
            self.btn_primary.configure(
                image=icons.icon("chevron_right", 12, theme.ICON_ON_ACCENT),
                compound=ctk.RIGHT,
                fg_color=theme.ACCENT,
                hover_color=theme.ACCENT_HOVER,
            )
            self.lbl_footer.configure(text="", text_color=theme.HINT_TEXT)
            self._refresh_continue_button()
            self.after(50, self.focus_input)
        else:
            self.frm_source.grid_remove()
            if self.frm_settings is None:
                self.frm_settings = SettingsForm(
                    self,
                    mode={
                        AudioSource.FILE: FormMode.FILE,
                        AudioSource.YOUTUBE: FormMode.URL,
                        AudioSource.DIRECTORY: FormMode.FOLDER,
                    }[self.source],
                    on_set_api_key=self._on_set_api_key,
                    on_model_change=self._on_model_change,
                    initial=self._initial_settings,
                )
            self.frm_settings.grid(
                row=2, column=0, padx=(26, 14), pady=(0, 10), sticky=ctk.NSEW
            )
            self.btn_back.grid()
            is_busy = self._is_busy()
            localize(
                self.btn_primary,
                text=lambda: _("Add to queue") if is_busy else _("Start transcription"),
            )
            self.btn_primary.configure(
                image=icons.icon("play", 12, theme.ICON_ON_ACCENT),
                compound=ctk.LEFT,
                state=ctk.NORMAL,
                **theme.PRIMARY_BUTTON,
            )
            self.lbl_footer.configure(text_color=theme.HINT_TEXT)
            if is_busy:
                localize(
                    self.lbl_footer,
                    text=lambda: _(
                        "It will start when the current transcription finishes."
                    ),
                )
            else:
                self.lbl_footer.configure(text=self._source_description())

    def _source_description(self) -> str:
        if self.source == AudioSource.YOUTUBE:
            return self._selected
        return Path(self._selected).name

    def _start(self) -> None:
        assert self.frm_settings
        if error := self.frm_settings.validate():
            self.lbl_footer.configure(text=error, text_color=theme.ERROR_TEXT)
            return

        settings = self.frm_settings.get_settings()
        self._on_start(self.source, self._selected, settings)

    # SOURCE

    def _is_source_valid(self) -> bool:
        if self.source == AudioSource.YOUTUBE:
            return is_valid_url(self._selected)
        if self.source == AudioSource.FILE:
            path = Path(self._selected)
            return path.is_file() and path.suffix.lower() in c.SUPPORTED_FILE_EXTENSIONS
        return bool(self._selected) and Path(self._selected).is_dir()

    def _refresh_continue_button(self) -> None:
        if self._step == SOURCE_STEP:
            is_valid = self._is_source_valid()
            # Without a file, the button opens the file dialog
            is_enabled = is_valid or self.source != AudioSource.YOUTUBE
            self.btn_primary.configure(state=ctk.NORMAL if is_enabled else ctk.DISABLED)

    def _set_path(self, value: str) -> None:
        path = Path(value)
        is_file = self.source == AudioSource.FILE

        if is_file and not (
            path.is_file() and path.suffix.lower() in c.SUPPORTED_FILE_EXTENSIONS
        ):
            self.lbl_footer.configure(text_color=theme.ERROR_TEXT)
            localize(
                self.lbl_footer,
                text=lambda: _(
                    "“{name}” is not a supported audio or video file."
                ).format(name=path.name),
            )
            return
        if not is_file and not path.is_dir():
            self.lbl_footer.configure(text_color=theme.ERROR_TEXT)
            localize(self.lbl_footer, text=lambda: _("Please select a valid folder."))
            return

        self._selected = str(path)
        self._selection_number += 1
        self.lbl_footer.configure(text="")

        self.frm_drop_zone.grid_remove()
        self.frm_summary.grid(row=0, column=0, sticky="new")
        self.lbl_summary_name.configure(text=path.name or str(path))
        self.lbl_summary_path.configure(text=str(path.parent))
        self.lbl_summary_details.configure(text_color=theme.HINT_TEXT)
        localize(self.lbl_summary_details, text=lambda: _("Reading…"))
        self._refresh_continue_button()

        selection_number = self._selection_number
        target = self._describe_file if is_file else self._describe_folder
        threading.Thread(
            target=target, args=(path, selection_number), daemon=True
        ).start()

    def _describe_file(self, path: Path, selection_number: int) -> None:
        info: MediaInfo | None = None
        try:
            info = probe_media(path)
        except OSError:
            logger.warning("Could not read %s", path, exc_info=True)
        size: int | None = None
        with contextlib.suppress(OSError):
            size = path.stat().st_size

        def describe() -> str:
            parts = []
            if info is not None:
                parts.append(_("Video") if info.has_video else _("Audio"))
                if info.duration:
                    parts.append(format_duration(info.duration))
            if size is not None:
                parts.append(format_size(size))
            return " · ".join(parts)

        self._show_details(describe, selection_number)

    def _describe_folder(self, path: Path, selection_number: int) -> None:
        try:
            count = len(list_supported_files(path))
        except OSError as e:
            error = str(e)
            self._show_details(lambda: error, selection_number, is_error=True)
            return

        def describe() -> str:
            if count == 0:
                return _("No audio or video files found (subfolders included).")
            if count == 1:
                return _("1 audio or video file (subfolders included)")
            return _("{count} audio and video files (subfolders included)").format(
                count=count
            )

        self._show_details(describe, selection_number, is_error=count == 0)

    def _show_details(
        self, text: Text, selection_number: int, is_error: bool = False
    ) -> None:
        """
        :param text: The details, translated when they're shown, since they're
                     read in a background thread.
        """

        def show() -> None:
            if selection_number == self._selection_number and self.winfo_exists():
                self.lbl_summary_details.configure(
                    text_color=theme.ERROR_TEXT if is_error else theme.TEXT
                )
                localize(self.lbl_summary_details, text=text)

        # Tkinter widgets must be updated from the main thread
        self._run_on_ui_thread(show)

    def _on_url_change(self, is_submitting: bool = False) -> None:
        value = self._url_variable.get().strip()
        self._selected = value

        if not value:
            self.lbl_url_status.configure(text="")
        elif is_valid_url(value):
            is_youtube = is_youtube_url(value)
            self.lbl_url_status.configure(text_color=theme.SUCCESS_TEXT)
            localize(
                self.lbl_url_status,
                text=lambda: (
                    "✓ " + (_("YouTube video") if is_youtube else _("Link to a file"))
                ),
            )
        elif is_submitting or len(value) > 12:
            self.lbl_url_status.configure(text_color=theme.ERROR_TEXT)
            localize(
                self.lbl_url_status,
                text=lambda: _("Enter a URL that starts with http:// or https://"),
            )
        else:
            self.lbl_url_status.configure(text="")

        self._refresh_continue_button()

    def _on_paste(self) -> None:
        try:
            text = self.clipboard_get()
        except tk.TclError:  # The clipboard is empty or doesn't contain text
            return
        self._url_variable.set(text.strip())
        self.ent_url.icursor(ctk.END)
