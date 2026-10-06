import logging
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from tkinter import messagebox
from typing import Any

import customtkinter as ctk

import utils.constants as c
from controllers.history_controller import HistoryController
from controllers.transcription_queue import TranscriptionQueue
from models.config.config_system import ConfigSystem
from models.history import EntryStatus, HistoryEntry
from models.transcript_segment import TranscriptSegment
from models.transcription_settings import TranscriptionSettings
from utils.config_manager import ConfigManager
from utils.enums import AudioSource
from utils.env_keys import EnvKeys
from utils.history_store import HistoryStore
from utils.i18n import _
from utils.update_checker import Release, UpdateCheckError, get_available_update
from views.entries.folder_view import FolderView
from views.entries.status_view import StatusView
from views.history.formatting import format_full_date
from views.history.history_sidebar import HistorySidebar
from views.main_window.top_bar import TopBar
from views.main_window.welcome_view import WelcomeView
from views.new_transcription.microphone_view import MicrophoneView, MicState
from views.new_transcription.new_transcription_view import NewTranscriptionView
from views.settings.preferences_dialog import PreferencesDialog, api_key_labels
from views.style import theme
from views.transcript.transcript_view import TranscriptView
from views.ui_thread_queue import UiThreadQueue
from views.widgets.splitter import Splitter
from views.widgets.text_dialog import TextDialog

logger = logging.getLogger(__name__)

# Width kept for the content when the sidebar is widened
CONTENT_MIN_WIDTH = 420

EntryView = TranscriptView | StatusView | FolderView


class Page(Enum):
    WELCOME = auto()
    NEW = auto()
    MIC = auto()
    ENTRY = auto()


def entry_view_class(entry: HistoryEntry) -> type[EntryView]:
    if entry.is_folder:
        return FolderView
    if entry.status == EntryStatus.DONE:
        return TranscriptView
    return StatusView


class MainWindow(ctk.CTkFrame):  # type: ignore[misc]
    """
    The window of the app: the top bar to start a transcription from each kind
    of source, the history of transcriptions on the left and, on the right, the
    selected transcription or the steps to create a new one.

    It shows the changes made by the controllers of the history and of the queue
    of transcriptions (see `TranscriptionQueueView`), and passes them the actions
    of the sidebar and of the views of the entries, asking the user for what they
    need first (e.g. a name or a confirmation).
    """

    def __init__(
        self,
        parent: Any,
        store: HistoryStore,
        history: HistoryController,
        jobs: TranscriptionQueue,
        on_ui_language_change: Callable[[str], None],
    ) -> None:
        super().__init__(parent, corner_radius=0, fg_color=theme.WINDOW_BG)
        self._store = store
        self._history = history
        self._jobs = jobs
        self._on_ui_language_change = on_ui_language_change

        self._page = Page.WELCOME
        self._new_views: dict[AudioSource, NewTranscriptionView] = {}
        # The steps opened from an entry that didn't finish, to change its settings
        self._back_view: NewTranscriptionView | None = None
        self._mic_view: MicrophoneView | None = None
        self._welcome_view: WelcomeView | None = None
        self._entry_view: Any = None
        self._entry_view_id: str | None = None
        self._preferences: PreferencesDialog | None = None
        self._available_update: Release | None = None

        # The callbacks of the background threads of the views, which aren't run
        # once the window is destroyed
        self._ui_queue = UiThreadQueue(self)

        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.top_bar = TopBar(
            self,
            on_toggle_sidebar=self.toggle_sidebar,
            on_source=self.show_source,
            on_preferences=self.show_preferences,
        )
        self.top_bar.grid(row=0, column=0, columnspan=3, sticky=ctk.EW)

        config_system = ConfigManager.get_config_system()
        self.sidebar = HistorySidebar(
            self, store, self, width=config_system.sidebar_width
        )
        self.sidebar.grid(row=1, column=0, sticky=ctk.NS)
        # The divider of the sidebar is dragged to resize it
        self._sidebar_divider = Splitter(
            self,
            is_vertical=True,
            on_drag=self._on_sidebar_drag,
            on_release=self._on_sidebar_drag_end,
            on_reset=lambda: self._resize_sidebar(theme.SIDEBAR_WIDTH),
            thickness=6,
            has_line=True,
        )
        self._sidebar_divider.grid(row=1, column=1, sticky=ctk.NS)
        if config_system.is_sidebar_collapsed:
            self.sidebar.grid_remove()
            self._sidebar_divider.grid_remove()

        self.frm_content = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.frm_content.grid(row=1, column=2, sticky=ctk.NSEW)
        self.frm_content.grid_columnconfigure(0, weight=1)
        self.frm_content.grid_rowconfigure(0, weight=1)

        self.show_welcome()

    def destroy(self) -> None:
        self._ui_queue.stop()
        super().destroy()

    # SESSION (the window is rebuilt when the interface language changes)

    def get_session_state(self) -> dict[str, Any]:
        source = next(
            (s for s, v in self._new_views.items() if v.winfo_ismapped()), None
        )
        return {
            "page": self._page,
            "entry_id": self._entry_view_id,
            "source": source,
            "update": self._available_update,
        }

    def restore_session_state(self, state: dict[str, Any]) -> None:
        if state["update"]:
            self.show_update(state["update"])
        if state["page"] == Page.ENTRY and state["entry_id"]:
            self.select_entry(state["entry_id"])
        elif state["page"] == Page.MIC:
            self.show_source(AudioSource.MIC)
        elif state["page"] == Page.NEW and state["source"]:
            self.show_source(state["source"])

    # PAGES

    def _hide_pages(self) -> None:
        for widget in self.frm_content.winfo_children():
            widget.grid_remove()

    def _show_page(self, page: Page, widget: Any) -> None:
        self._hide_pages()
        self._page = page
        widget.grid(row=0, column=0, sticky=ctk.NSEW)

        if page != Page.ENTRY:
            self.sidebar.set_selected(None)
            self._destroy_entry_view()

    def show_welcome(self) -> None:
        if self._welcome_view is None:
            self._welcome_view = WelcomeView(self.frm_content, self.show_source)
        self._show_page(Page.WELCOME, self._welcome_view)
        self.top_bar.set_active_source(None)

    def show_source(self, source: AudioSource) -> None:
        """Shows the steps to transcribe from a kind of source."""
        if source == AudioSource.MIC:
            if self._mic_view is None:
                self._mic_view = MicrophoneView(
                    self.frm_content,
                    on_start=self._start_recording,
                    on_stop=self._jobs.stop_recording,
                    on_open_entry=self._open_last_recording,
                    on_set_api_key=self._on_set_api_key,
                    on_model_change=self._request_model_preload,
                    is_busy=self._jobs.is_busy,
                    run_on_ui_thread=self.run_on_ui_thread,
                )
            self._show_page(Page.MIC, self._mic_view)
        else:
            view = self._new_views.get(source)
            if view is None:
                view = NewTranscriptionView(
                    self.frm_content,
                    source,
                    on_start=self._start_transcription,
                    on_set_api_key=self._on_set_api_key,
                    on_model_change=self._request_model_preload,
                    is_busy=self._jobs.is_busy,
                    run_on_ui_thread=self.run_on_ui_thread,
                )
                self._new_views[source] = view
            self._show_page(Page.NEW, view)
            view.focus_input()

        self.top_bar.set_active_source(source)

    def go_back_to_settings(self, entry_id: str) -> None:
        """
        Opens the settings of an entry that didn't finish (e.g. it failed because
        of a missing token), so they can be changed before transcribing it again.
        """
        entry = self._store.get(entry_id)
        if entry is None or entry.status.is_active or entry.parent_id:
            return
        kind = AudioSource(entry.kind)
        if kind == AudioSource.MIC:
            return
        source = AudioSource.DIRECTORY if kind == AudioSource.WATCH else kind

        self._close_back_view()

        def on_start(
            source: AudioSource, value: str, settings: TranscriptionSettings
        ) -> None:
            self._close_back_view()
            self._jobs.restart(entry_id, source, value, settings)

        view = NewTranscriptionView(
            self.frm_content,
            source,
            on_start=on_start,
            on_set_api_key=self._on_set_api_key,
            on_model_change=self._request_model_preload,
            is_busy=self._jobs.is_busy,
            run_on_ui_thread=self.run_on_ui_thread,
            initial_settings=TranscriptionSettings.from_dict(entry.settings),
        )
        self._back_view = view
        self._show_page(Page.NEW, view)
        self.top_bar.set_active_source(source)
        view.set_source(entry.source, should_advance=True)

    def _shown_new_view(self) -> NewTranscriptionView | None:
        views = (*self._new_views.values(), self._back_view)
        return next((v for v in views if v and v.winfo_ismapped()), None)

    def _close_back_view(self) -> None:
        if self._back_view is not None:
            self._back_view.destroy()
            self._back_view = None

    def select_entry(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None:
            return

        self._hide_pages()
        self._page = Page.ENTRY
        self.top_bar.set_active_source(None)
        if entry.is_folder:
            self.sidebar.expand_folder(entry.id)
        self.sidebar.set_selected(entry_id)

        if self._entry_view_id != entry_id or self._entry_view is None:
            self._show_entry_view(entry)
        else:
            self._entry_view.grid(row=0, column=0, sticky=ctk.NSEW)

    def _show_entry_view(self, entry: HistoryEntry) -> None:
        self._destroy_entry_view()
        view_class = entry_view_class(entry)

        view: EntryView
        if view_class is TranscriptView:
            view = TranscriptView(self.frm_content, entry, self, self.run_on_ui_thread)
        elif view_class is FolderView:
            view = FolderView(self.frm_content, entry, self._store, self)
        else:
            view = StatusView(self.frm_content, entry, self)

        self._entry_view = view
        self._entry_view_id = entry.id
        view.grid(row=0, column=0, sticky=ctk.NSEW)

    def _destroy_entry_view(self) -> None:
        if self._entry_view is not None:
            self._entry_view.destroy()
        self._entry_view = None
        self._entry_view_id = None

    def on_entry_changed(self, entry_id: str, is_structural: bool = False) -> None:
        """
        Updates the views after an entry changes.

        :param is_structural: Whether the change affects the order or the
                              sections of the list (e.g. pinning or adding).
        """
        if is_structural:
            self.sidebar.refresh()
        else:
            self.sidebar.update_entry(entry_id)
        self.refresh_entry_view(entry_id)

    def refresh_entry_view(self, entry_id: str) -> None:
        """Shows the changes of an entry (or of a file of it) in its view."""
        shown_id = self._entry_view_id
        if shown_id is None or self._entry_view is None:
            return

        shown = self._store.get(shown_id)
        if shown is None:
            if self._page == Page.ENTRY:
                self.show_welcome()
            else:
                self._destroy_entry_view()
            return

        changed = self._store.get(entry_id)
        is_related = entry_id == shown_id or (
            changed is not None and changed.parent_id == shown_id
        )
        if not is_related:
            return

        if not isinstance(self._entry_view, entry_view_class(shown)):
            was_visible = self._entry_view.winfo_ismapped()
            self._show_entry_view(shown)
            if not was_visible:
                self._entry_view.grid_remove()
        else:
            self._entry_view.update_entry(shown)

    def refresh_progress(self, entry_id: str) -> None:
        self.sidebar.update_progress(entry_id)
        if self._entry_view_id == entry_id and hasattr(
            self._entry_view, "update_progress"
        ):
            self._entry_view.update_progress()

    def show_status(self, message: str, is_error: bool = False) -> None:
        self.top_bar.show_status(message, is_error=is_error)

    # SIDEBAR

    def refresh_sidebar(self) -> None:
        self.sidebar.refresh()

    def toggle_sidebar(self) -> None:
        is_visible = self.sidebar.winfo_ismapped()
        if is_visible:
            self.sidebar.grid_remove()
            self._sidebar_divider.grid_remove()
        else:
            self.sidebar.grid()
            self._sidebar_divider.grid()
        ConfigManager.modify_value(
            ConfigSystem.Key.SECTION,
            ConfigSystem.Key.IS_SIDEBAR_COLLAPSED,
            str(is_visible),
        )

    def _on_sidebar_drag(self, pointer_x: int) -> None:
        width = self.sidebar._reverse_widget_scaling(
            pointer_x - self.sidebar.winfo_rootx()
        )
        self._resize_sidebar(width, is_final=False)

    def _on_sidebar_drag_end(self) -> None:
        self._resize_sidebar(self.sidebar.width)

    def _resize_sidebar(self, width: float, is_final: bool = True) -> None:
        max_width = (
            self.sidebar._reverse_widget_scaling(self.winfo_width()) - CONTENT_MIN_WIDTH
        )
        width = self.sidebar.set_width(round(min(width, max_width)), is_final=is_final)
        if is_final:
            ConfigManager.modify_value(
                ConfigSystem.Key.SECTION, ConfigSystem.Key.SIDEBAR_WIDTH, str(width)
            )

    # THREADS

    def run_on_ui_thread(self, callback: Callable[..., Any], *args: Any) -> None:
        """
        Schedules a callback to be run on the Tkinter thread. Tkinter is not
        thread-safe, so background threads must use this method to update the UI.
        """
        self._ui_queue.put(callback, *args)

    # TRANSCRIPTIONS

    def _start_transcription(
        self, source: AudioSource, value: str, settings: TranscriptionSettings
    ) -> None:
        # The next transcription from this source starts from the first step
        if view := self._new_views.pop(source, None):
            view.destroy()
        self._jobs.start(source, value, settings)

    def retry_entry(self, entry_id: str) -> None:
        self._jobs.retry_entry(entry_id)

    def cancel_entry(self, entry_id: str) -> None:
        self._jobs.cancel_entry(entry_id)

    def get_progress(self, entry_id: str) -> float | None:
        return self._jobs.get_progress(entry_id)

    def get_progress_message(self, entry_id: str) -> tuple[str, float | None]:
        return self._jobs.get_progress_message(entry_id)

    def get_queue_position(self, entry_id: str) -> int | None:
        return self._jobs.get_queue_position(entry_id)

    # MICROPHONE

    def _start_recording(
        self, settings: TranscriptionSettings, device_index: int | None
    ) -> None:
        if self._mic_view is None:
            return
        title = _("Recording · {date}").format(
            date=format_full_date(datetime.now().astimezone())
        )
        if self._jobs.start_recording(title, settings, device_index):
            self._mic_view.set_state(MicState.RECORDING)

    def _open_last_recording(self) -> None:
        if self._jobs.last_mic_entry_id:
            self.select_entry(self._jobs.last_mic_entry_id)

    def is_recording(self) -> bool:
        return self._mic_view is not None and self._mic_view.state == MicState.RECORDING

    def on_recording_progress(self, elapsed_seconds: float, level: float) -> None:
        if self._mic_view:
            self._mic_view.on_recording_progress(elapsed_seconds, level)

    def on_stop_recording_from_mic(self) -> None:
        if self._mic_view and self._mic_view.state == MicState.RECORDING:
            self._mic_view.set_state(
                MicState.TRANSCRIBING, _("Processing the recording…")
            )

    def on_live_text(self, text: str) -> None:
        if self._mic_view:
            self._mic_view.show_live_text(text)

    def on_live_status(self, message: str) -> None:
        if self._mic_view:
            self._mic_view.show_live_status(message)

    def on_mic_progress(self, message: str) -> None:
        if self._mic_view:
            self._mic_view.show_progress(message)

    def on_mic_text(self, text: str) -> None:
        if self._mic_view:
            self._mic_view.show_text(text)

    def on_mic_finished(self, error: str | None) -> None:
        if self._mic_view is None:
            return
        if error is None:
            self._mic_view.set_state(MicState.DONE)
        else:
            self._mic_view.set_state(MicState.FAILED, error)

    # ENTRIES

    def rename_entry(self, entry_id: str, title: str) -> None:
        self._history.rename_entry(entry_id, title)

    def rename_entry_dialog(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None:
            return
        title = TextDialog(
            self,
            _("Rename"),
            _("Name of the transcription:"),
            entry.title,
            allow_empty=False,
        ).get_input()
        if title:
            self._history.rename_entry(entry_id, title)

    def edit_note(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None:
            return
        note = TextDialog(
            self,
            _("Note"),
            _("A note about “{title}”:").format(title=entry.title),
            entry.note,
            is_multiline=True,
        ).get_input()
        if note is not None:
            self._history.set_note(entry_id, note)

    def delete_note(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None or not entry.note:
            return
        if messagebox.askyesno(
            _("Delete note"),
            _("Delete the note of “{title}”?").format(title=entry.title),
            icon=messagebox.WARNING,
            parent=self.winfo_toplevel(),
        ):
            self._history.set_note(entry_id, "")

    def edit_tag(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None:
            return
        tag = TextDialog(
            self,
            _("Tag"),
            _("Tag of “{title}”. Leave it empty to show the kind of source.").format(
                title=entry.title
            ),
            entry.tag,
            suggestions=self._store.tags(),
        ).get_input()
        if tag is not None:
            self._history.set_tag(entry_id, tag)

    def toggle_pin(self, entry_id: str) -> None:
        self._history.toggle_pin(entry_id)

    def reveal_entry(self, entry_id: str) -> None:
        self._history.reveal_entry(entry_id)

    def open_folder(self, folder: Path) -> None:
        self._history.open_folder(folder)

    def delete_entry(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None:
            return

        message = _("Delete “{title}” from the history?").format(title=entry.title)
        if entry.is_folder:
            message += "\n\n" + _("The transcriptions of its files are deleted too.")
        message += "\n\n" + _("Your audio, video and saved files are not deleted.")
        if not messagebox.askyesno(
            _("Delete transcription"), message, parent=self.winfo_toplevel()
        ):
            return

        if entry.status.is_active:
            self._jobs.cancel_entry(entry_id)
        self._history.delete_entry(entry_id)

    # TRANSCRIPT

    def save_text(self, entry_id: str, text: str) -> None:
        self._history.save_text(entry_id, text)

    def update_transcript(
        self, entry_id: str, segments: list[TranscriptSegment], text: str
    ) -> None:
        self._history.update_transcript(entry_id, segments, text)

    def summarize_entry(self, entry_id: str) -> None:
        self._history.summarize_entry(entry_id)

    def is_summarizing(self, entry_id: str) -> bool:
        return self._history.is_summarizing(entry_id)

    def get_summary_error(self, entry_id: str) -> str:
        return self._history.get_summary_error(entry_id)

    def translate_entry(
        self, entry_id: str, language: str, provider: str, model: str = ""
    ) -> None:
        self._history.translate_entry(entry_id, language, provider, model)

    def start_manual_translation(self, entry_id: str, language: str) -> None:
        self._history.start_manual_translation(entry_id, language)

    def is_translating(self, entry_id: str) -> bool:
        return self._history.is_translating(entry_id)

    def get_translation_error(self, entry_id: str) -> str:
        return self._history.get_translation_error(entry_id)

    def save_translation_text(self, entry_id: str, text: str) -> None:
        self._history.save_translation_text(entry_id, text)

    def update_translation(
        self, entry_id: str, segments: list[TranscriptSegment], text: str
    ) -> None:
        self._history.update_translation(entry_id, segments, text)

    def remove_translation(self, entry_id: str) -> None:
        self._history.remove_translation(entry_id)

    # GROUPS

    def move_to_group(self, entry_id: str, group_id: str | None) -> None:
        self._history.move_to_group(entry_id, group_id)

    def move_to_new_group(self, entry_id: str) -> None:
        if group_id := self.create_group():
            self._history.move_to_group(entry_id, group_id)

    def create_group(self) -> str | None:
        name = TextDialog(
            self,
            _("New group"),
            _("Name of the group:"),
            ok_text=_("Create"),
            allow_empty=False,
        ).get_input()
        return self._history.create_group(name) if name else None

    def rename_group(self, group_id: str) -> None:
        group = self._store.get_group(group_id)
        if group is None:
            return
        name = TextDialog(
            self,
            _("Rename group"),
            _("Name of the group:"),
            group.name,
            allow_empty=False,
        ).get_input()
        if name:
            self._history.rename_group(group_id, name)

    def delete_group(self, group_id: str) -> None:
        group = self._store.get_group(group_id)
        if group is None:
            return
        if messagebox.askyesno(
            _("Delete group"),
            _(
                "Delete the group “{name}”? Its transcriptions are kept, without a group."
            ).format(name=group.name),
            parent=self.winfo_toplevel(),
        ):
            self._history.delete_group(group_id)

    # APP SHORTCUTS AND DRAG AND DROP

    def trigger_main_action(self) -> None:
        if self._page == Page.NEW:
            if view := self._shown_new_view():
                view.trigger_primary()
        elif self._page == Page.MIC and self._mic_view:
            self._mic_view.trigger_primary()

    def trigger_save(self) -> None:
        if isinstance(self._entry_view, TranscriptView) and self._page == Page.ENTRY:
            self._entry_view.show_export_menu()

    def trigger_browse(self) -> None:
        # Browse in the source being shown (e.g. a folder), or a file otherwise
        view = self._shown_new_view() if self._page == Page.NEW else None
        if view:
            view.trigger_browse()
            return

        self.show_source(AudioSource.FILE)
        self._new_views[AudioSource.FILE].trigger_browse()

    def trigger_cancel(self) -> None:
        if (
            self._page == Page.MIC
            and self._mic_view
            and self._mic_view.state == MicState.RECORDING
        ):
            self._jobs.stop_recording()

    def trigger_search(self) -> None:
        if self._page == Page.ENTRY and isinstance(self._entry_view, TranscriptView):
            self._entry_view.focus_search()
        else:
            if not self.sidebar.winfo_ismapped():
                self.toggle_sidebar()
            self.sidebar.focus_search()

    def handle_key(self, event: Any) -> str | None:
        """
        Handles the keys of the playback and of the list, unless the user is
        typing.

        :return: "break" if the key was handled.
        """
        widget = event.widget
        if isinstance(widget, tk.Entry):
            return None
        view = self._entry_view if self._page == Page.ENTRY else None
        if isinstance(widget, tk.Text) and not (
            isinstance(view, TranscriptView) and view.is_transcript_widget(widget)
        ):
            return None

        if event.keysym in ("Up", "Down"):
            self._select_relative(-1 if event.keysym == "Up" else 1)
            return "break"
        if isinstance(view, TranscriptView) and view.handle_key(event.keysym):
            return "break"
        return None

    def _select_relative(self, step: int) -> None:
        ids = self.sidebar.visible_entry_ids
        if not ids:
            return
        current = self._entry_view_id if self._page == Page.ENTRY else None
        idx = ids.index(current) + step if current in ids else 0
        if 0 <= idx < len(ids):
            self.select_entry(ids[idx])

    def on_files_dropped(self, paths: list[str]) -> None:
        if not paths:
            return
        path = Path(paths[0])
        if path.is_dir():
            source = AudioSource.DIRECTORY
        elif path.suffix.lower() in c.SUPPORTED_FILE_EXTENSIONS:
            source = AudioSource.FILE
        else:
            self.show_status(
                _("“{name}” is not a supported audio or video file.").format(
                    name=path.name
                ),
                is_error=True,
            )
            return

        self.show_source(source)
        self._new_views[source].set_source(str(path), should_advance=True)

        if len(paths) > 1:
            self.show_status(
                _(
                    "Only one file can be added at a time. To transcribe several files, drop the folder that contains them."
                )
            )

    # UPDATES

    def check_for_updates(
        self, on_result: Callable[[Release | None, bool], None] | None = None
    ) -> None:
        """
        Checks in the background whether a new version is available, showing it
        in the top bar if so.

        :param on_result: Called on the Tkinter thread with the new version, if
                          any, and whether the check failed.
        """

        def check() -> None:
            try:
                release, has_error = get_available_update(), False
            except UpdateCheckError:
                logger.warning("Could not check for updates", exc_info=True)
                release, has_error = None, True
            self.run_on_ui_thread(
                self._on_update_checked, release, has_error, on_result
            )

        threading.Thread(target=check, daemon=True).start()

    def _on_update_checked(
        self,
        release: Release | None,
        has_error: bool,
        on_result: Callable[[Release | None, bool], None] | None,
    ) -> None:
        if release:
            self.show_update(release)
        if on_result:
            on_result(release, has_error)

    def show_update(self, release: Release) -> None:
        self._available_update = release
        self.top_bar.show_update(
            release.version, on_click=lambda: webbrowser.open(release.url)
        )

    # PREFERENCES

    def show_preferences(self, tab: str | None = None) -> None:
        """:param tab: The tab to show, e.g. `AI_TAB`."""
        if self._preferences is not None and self._preferences.winfo_exists():
            if tab:
                self._preferences.show_tab(tab)
            self._preferences.lift()
            self._preferences.focus_force()
            return
        self._preferences = PreferencesDialog(
            self,
            on_set_api_key=self._on_set_api_key,
            on_ui_language_change=lambda language: self.after(
                10, lambda: self._on_ui_language_change(language)
            ),
            on_model_change=self._request_model_preload,
            can_change_language=not self._jobs.is_busy(),
            initial_tab=tab,
            on_ai_change=self._refresh_shown_entry,
            on_check_for_updates=self.check_for_updates,
            on_date_format_change=self._on_date_format_change,
        )

    def _refresh_shown_entry(self) -> None:
        if self._entry_view_id:
            self.refresh_entry_view(self._entry_view_id)

    def _on_date_format_change(self) -> None:
        self.sidebar.refresh()
        self._refresh_shown_entry()

    def set_api_key(self, env_key: EnvKeys) -> None:
        """Asks for an API key, e.g. the one of the provider of the summaries."""
        self._on_set_api_key(env_key, api_key_labels()[env_key][0])

    def _on_set_api_key(self, env_key: EnvKeys, title: str) -> None:
        old_value = env_key.get_value(default="")
        new_value = TextDialog(
            self,
            title,
            _(
                "Type in the API key. It's kept in the credential store of your "
                "system. Leave it empty to remove it."
            ),
            old_value,
            ok_text=_("OK"),
            is_secret=True,
        ).get_input()

        if new_value is not None and new_value != old_value:
            env_key.set_value(new_value)
            self.show_status(
                _("API key saved.") if new_value else _("API key removed.")
            )

        for view in (*self._new_views.values(), self._back_view, self._mic_view):
            if view is not None:
                view.refresh_api_keys()
        # The summary and the translation need the key of their provider
        self._refresh_shown_entry()

    def _request_model_preload(self) -> None:
        self._jobs.preload_model()
