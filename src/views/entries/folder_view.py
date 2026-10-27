import logging
import queue
import threading
import tkinter as tk
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Literal

import customtkinter as ctk

from models.history import EntryStatus, HistoryEntry
from models.transcription_settings import SettingsChange, changed_options
from utils.enums import AudioSource
from utils.exporters import COLLECTION_FORMATS, ExportDocument, export_collection
from utils.history_store import HistoryStore, sanitize_file_name
from utils.i18n import C_, L_, P_, _
from utils.time_format import format_duration
from views.entries.delegates import EntryActions, TranscriptAction
from views.entries.entry_header import EntryHeader
from views.entries.progress_card import ProgressCard
from views.history.formatting import (
    folder_actions,
    format_size,
    reveal_label,
    status_icon,
    status_label,
)
from views.localization import localize, on_language_change
from views.style import icons, theme
from views.transcript.transcript_view import sorted_export_labels
from views.widgets.bindings import bind_recursive, bind_wraplength
from views.widgets.localized_options import LocalizedOptions
from views.widgets.option_menu import CTkOptionMenu
from views.widgets.scrollable_frame import CTkScrollableFrame
from views.widgets.search_entry import SearchEntry
from views.widgets.tooltip import Tooltip

logger = logging.getLogger(__name__)

# The files shown at first, and each time more are asked for, since building the
# rows of a folder with hundreds of files takes a while
PAGE_SIZE = 200

# The statuses the files are filtered by
ALL_FILTER = "all"
DONE_FILTER = "done"
FAILED_FILTER = "failed"
PENDING_FILTER = "pending"

# What the files are sorted by, besides their path
NAME_SORT = "name"
STATUS_SORT = "status"
DURATION_SORT = "duration"
SIZE_SORT = "size"

# The status filter and the sorting chosen for each folder, kept while the app
# is open, so the folder is shown as it was left
list_state: dict[str, tuple[str, str]] = {}

# The order of the statuses when sorting by them, the ones to look at first
STATUS_ORDER = [
    EntryStatus.FAILED,
    EntryStatus.PROCESSING,
    EntryStatus.QUEUED,
    EntryStatus.WATCHING,
    EntryStatus.INTERRUPTED,
    EntryStatus.CANCELLED,
    EntryStatus.DONE,
]


def file_duration(entry: HistoryEntry) -> float | None:
    """The duration of a transcribed file, known from its last segment."""
    return max((segment.end for segment in entry.segments), default=None)


def file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


# Characters shown before a search match in the preview of a transcription
PREVIEW_CONTEXT = 30


def text_preview(text: str, query: str = "") -> str:
    """
    The start of a transcription, in a single line, or the part around the
    first match of the search, so it's seen why the file was found.
    """
    text = " ".join(text.split())
    start = text.casefold().find(query.casefold()) if query else -1
    if start <= PREVIEW_CONTEXT:
        return text[:300]
    # From the start of a word
    begin = text.rfind(" ", 0, start - PREVIEW_CONTEXT) + 1
    return "…" + text[begin : begin + 300]


def matches_filter(entry: HistoryEntry, status_filter: str) -> bool:
    if status_filter == DONE_FILTER:
        return entry.status == EntryStatus.DONE
    if status_filter == FAILED_FILTER:
        return entry.status == EntryStatus.FAILED
    if status_filter == PENDING_FILTER:
        return entry.status not in (EntryStatus.DONE, EntryStatus.FAILED)
    return True


def sort_files(
    files: list[HistoryEntry], sort: str, sizes: dict[str, int | None]
) -> list[HistoryEntry]:
    """
    Sorts the files of a folder, which are sorted by their path otherwise. The
    longest and the largest ones go first, and the ones without a duration or a
    size last.

    :param sizes: The size of each file, by its path.
    """
    if sort == STATUS_SORT:
        return sorted(files, key=lambda entry: STATUS_ORDER.index(entry.status))
    if sort == DURATION_SORT:
        return sorted(files, key=lambda entry: -(file_duration(entry) or -1))
    if sort == SIZE_SORT:
        return sorted(files, key=lambda entry: -(sizes.get(entry.source) or -1))
    return files


def wrap_when_narrow(container: ctk.CTkFrame, left: Any, right: Any) -> None:
    """
    Shows a widget on the right of another one, or below it if they don't fit
    side by side (e.g. in a narrow window, or with longer translations).
    """
    if not right.winfo_manager():
        return
    width = container.winfo_width()
    is_narrow = width > 1 and (
        left.winfo_reqwidth() + right.winfo_reqwidth() + 16 > width
    )
    if is_narrow:
        right.grid_configure(row=1, column=0, columnspan=2, pady=(8, 0), sticky=ctk.W)
    else:
        right.grid_configure(row=0, column=1, columnspan=1, pady=0, sticky=ctk.E)


def change_label(change: SettingsChange) -> str:
    return {
        SettingsChange.METHOD: _("Engine"),
        SettingsChange.MODEL: _("Model"),
        SettingsChange.LANGUAGE: _("Language"),
        SettingsChange.WORD_TIMINGS: _("Word-level timings"),
        SettingsChange.SPEAKERS: _("Identify speakers"),
        SettingsChange.SPEECH_ISOLATION: _("Reduce background noise"),
        SettingsChange.CONTEXT: _("Context"),
    }[change]


class FileRow(ctk.CTkFrame):  # type: ignore[misc]
    """
    A file of a folder: its status, name, the start of its transcription (or why
    it failed), and its duration and size. It opens its transcription when
    clicked, and its actions from its menu.
    """

    def __init__(self, master: Any, view: "FolderView", entry: HistoryEntry) -> None:
        super().__init__(
            master, fg_color="transparent", corner_radius=8, cursor="hand2"
        )
        self.entry_id = entry.id
        self._name = ""
        self._detail = ""
        self.grid_columnconfigure(1, weight=1)

        self.lbl_icon = ctk.CTkLabel(self, text="", width=18)
        self.lbl_icon.grid(row=0, column=0, padx=(10, 10), pady=8, sticky=ctk.N)

        # Its width is given by the row, not by its texts, which are shortened to
        # it: otherwise each shortened text would resize it, and so on
        self.frm_text = ctk.CTkFrame(self, fg_color="transparent", width=1, height=38)
        self.frm_text.grid_propagate(False)
        self.frm_text.grid(row=0, column=1, pady=6, sticky=ctk.EW)
        self.frm_text.grid_columnconfigure(0, weight=1)
        self.lbl_name = ctk.CTkLabel(
            self.frm_text, text="", font=theme.font(13), anchor=ctk.W, height=20
        )
        self.lbl_name.grid(row=0, column=0, sticky=ctk.EW)
        self.lbl_detail = ctk.CTkLabel(
            self.frm_text, text="", font=theme.font(12), anchor=ctk.W, height=18
        )
        self.lbl_detail.grid(row=1, column=0, sticky=ctk.EW)
        tk.Misc.bind(self.frm_text, "<Configure>", lambda _event: self._fit(), add="+")

        self.lbl_meta = ctk.CTkLabel(
            self,
            text="",
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            compound=ctk.LEFT,
        )
        self.lbl_meta.grid(row=0, column=2, padx=(12, 4))

        self._is_selected = False
        self._is_hovered = False
        bind_recursive(self, "<Button-1>", lambda _event: view.open_file(self.entry_id))
        # Several files are selected like in the file manager
        bind_recursive(
            self,
            f"<{theme.SHORTCUT_MODIFIER}-Button-1>",
            lambda _event: view.select_file(self.entry_id, is_toggle=True),
        )
        bind_recursive(
            self,
            "<Shift-Button-1>",
            lambda _event: view.select_file(self.entry_id, is_range=True),
        )
        # After binding the click, so clicking it doesn't open the file too
        btn_more = ctk.CTkButton(
            self,
            text="",
            image=icons.icon("more", 15, theme.ICON_MUTED),
            width=28,
            height=28,
            fg_color="transparent",
            hover_color=theme.CARD_BORDER,
        )
        btn_more.configure(command=lambda: view.show_file_menu(self.entry_id, btn_more))
        btn_more.grid(row=0, column=3, padx=(0, 8))
        self.btn_more = btn_more
        for sequence in theme.CONTEXT_MENU_EVENTS:
            bind_recursive(
                self, sequence, lambda event: view.show_file_menu(self.entry_id, event)
            )
        bind_recursive(self, "<Enter>", lambda _event: self._set_hovered(True))
        bind_recursive(self, "<Leave>", lambda _event: self._set_hovered(False))

    def update_entry(
        self,
        entry: HistoryEntry,
        name: str,
        size: int | None,
        is_outdated: bool,
        is_missing: bool = False,
        is_selected: bool = False,
        query: str = "",
    ) -> None:
        """
        :param name: The path of the file in its folder.
        :param query: The search, whose match is shown in the preview.
        :param is_outdated: Whether it was transcribed with other settings than
                            the current ones of its folder.
        :param is_missing: Whether the file was moved or deleted.
        """
        status = entry.status
        self._name = name
        self._is_selected = is_selected
        self._set_hovered(self._is_hovered)

        if is_missing:
            self.lbl_icon.configure(
                image=icons.icon("alert_circle", 15, theme.ICON_MUTED)
            )
        else:
            self.lbl_icon.configure(image=status_icon(status, 15))
        if is_missing:
            self._detail = _("File not found")
            color = theme.HINT_TEXT
        elif status == EntryStatus.FAILED:
            self._detail = entry.error or status_label(status)
            color = theme.ERROR_TEXT
        elif status == EntryStatus.DONE:
            self._detail = text_preview(entry.text, query) or _("No speech found")
            color = theme.HINT_TEXT
        else:
            self._detail = status_label(status)
            color = theme.HINT_TEXT
        self.lbl_detail.configure(text_color=color)

        meta = []
        if (duration := file_duration(entry)) is not None:
            meta.append(format_duration(duration))
        if size is not None:
            meta.append(format_size(size))
        self.lbl_meta.configure(
            text=(" " if is_outdated and meta else "") + " · ".join(meta),
            image=icons.icon("warning", 12, theme.STATUS_CANCELLED)
            if is_outdated
            else None,
        )
        self._fit()

    @property
    def detail(self) -> str:
        """The start of its transcription, why it failed, or its status."""
        return self._detail

    def _fit(self) -> None:
        width = self.frm_text.winfo_width()
        # Until it's laid out, they're shortened to a common width
        available = width - 8 if width > 1 else 360
        self.lbl_name.configure(
            text=theme.fit_text(self._name, theme.font(13), available)
        )
        self.lbl_detail.configure(
            text=theme.fit_text(self._detail, theme.font(12), available)
        )

    def _set_hovered(self, is_hovered: bool) -> None:
        self._is_hovered = is_hovered
        if self._is_selected:
            color: Any = theme.ROW_SELECTED
        else:
            color = theme.ROW_HOVER if is_hovered else "transparent"
        self.configure(fg_color=color)


class FolderView(ctk.CTkFrame):  # type: ignore[misc]
    """
    A folder transcription: its progress, its actions, and the list of its files,
    which can be searched, filtered and sorted, and which open their
    transcription when clicked.
    """

    def __init__(
        self,
        master: Any,
        entry: HistoryEntry,
        store: HistoryStore,
        actions: EntryActions,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.entry_id = entry.id
        self._store = store
        self._actions = actions
        self._entry = entry
        self._children: list[HistoryEntry] = []
        self._rows: dict[str, FileRow] = {}
        # The sizes of the files, by path, read once
        self._sizes: dict[str, int | None] = {}
        self._shown_count = PAGE_SIZE
        self._failed_ids: list[str] = []
        self._outdated_ids: list[str] = []
        self._missing_ids: set[str] = set()
        # The files selected, in the order they were, and the one the range of
        # the next one selected with Shift starts from
        self._selected: list[str] = []
        self._anchor_id: str | None = None
        # The files skipped because they already had a transcription, counted
        # in the background each time the folder is shown or done (see
        # `_count_skipped`), and whether it was being transcribed
        self._skipped_count: int | None = None
        self._skipped_results: queue.SimpleQueue[int] = queue.SimpleQueue()
        self._was_active = entry.status.is_active
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        self.header = EntryHeader(
            self,
            entry,
            actions.prompts,
            files=actions.files,
            on_edit_settings=actions.window.go_back_to_settings,
        )
        self.header.grid(row=0, column=0, padx=28, pady=(22, 0), sticky=ctk.EW)

        # Row 1 is the progress card, only shown while the folder is transcribed
        self.card: ProgressCard | None = None
        self._init_summary()
        self._init_outdated()
        self._init_toolbar()

        self.frm_files = CTkScrollableFrame(
            self,
            fg_color=theme.CARD_BG,
            border_color=theme.CARD_BORDER,
            border_width=1,
            corner_radius=12,
        )
        self.frm_files.grid(row=5, column=0, padx=28, pady=(0, 20), sticky=ctk.NSEW)
        self.frm_files.grid_columnconfigure(0, weight=1)
        self.lbl_empty = ctk.CTkLabel(
            self.frm_files, text="", font=theme.font(13), text_color=theme.HINT_TEXT
        )
        self.btn_show_more = localize(
            ctk.CTkButton(
                self.frm_files, width=0, command=self._show_more, **theme.GHOST_BUTTON
            ),
            text=L_("Show more"),
        )

        self._refresh(entry)
        self._count_skipped()
        # The summary and the list of the files are built again
        on_language_change(self, lambda: self._refresh(self._entry))

    def _init_summary(self) -> None:
        self.frm_summary = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_summary.grid(row=2, column=0, padx=28, pady=(16, 0), sticky=ctk.EW)
        self.frm_summary.grid_columnconfigure(0, weight=1)
        self.lbl_summary = ctk.CTkLabel(
            self.frm_summary, text="", font=theme.font(13), anchor=ctk.W
        )
        self.lbl_summary.grid(row=0, column=0, sticky=ctk.W)

        self.frm_buttons = ctk.CTkFrame(self.frm_summary, fg_color="transparent")
        self.frm_buttons.grid(row=0, column=1, sticky=ctk.E)
        tk.Misc.bind(
            self.frm_summary,
            "<Configure>",
            lambda _event: self._wrap_rows(),
            add="+",
        )
        # Failed files are transcribed again even while the folder is, after the
        # file being transcribed
        self.btn_retry_failed = localize(
            ctk.CTkButton(
                self.frm_buttons,
                width=0,
                image=icons.icon("refresh", 14, theme.ICON_MUTED),
                compound=ctk.LEFT,
                command=self._retry_failed,
                **theme.SECONDARY_BUTTON,
            ),
            text=L_("Retry failed"),
        )
        self.btn_rescan = ctk.CTkButton(
            self.frm_buttons,
            width=0,
            image=icons.icon("refresh", 14, theme.ICON_MUTED),
            compound=ctk.LEFT,
            command=lambda: self._actions.jobs.retry_entry(self.entry_id),
            **theme.SECONDARY_BUTTON,
        )
        Tooltip(
            self.btn_rescan,
            L_("Transcribes the files without a transcription, like the new ones."),
        )
        self.btn_more = ctk.CTkButton(
            self.frm_buttons,
            text="",
            image=icons.icon("more", 16),
            width=32,
            command=self._show_folder_menu,
            **theme.SECONDARY_BUTTON,
        )
        self.btn_more.grid(row=0, column=2, padx=(8, 0))

    def _init_outdated(self) -> None:
        """Tells which files were transcribed with other settings."""
        self.frm_outdated = ctk.CTkFrame(
            self,
            fg_color=theme.NOTE_BG,
            border_color=theme.NOTE_BORDER,
            border_width=1,
            corner_radius=10,
        )
        self.frm_outdated.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            self.frm_outdated,
            text="",
            image=icons.icon("warning", 15, theme.STATUS_CANCELLED),
        ).grid(row=0, column=0, padx=(12, 8), pady=10)
        self.lbl_outdated = ctk.CTkLabel(
            self.frm_outdated,
            text="",
            font=theme.font(13),
            anchor=ctk.W,
            justify=ctk.LEFT,
        )
        self.lbl_outdated.grid(row=0, column=1, pady=10, sticky=ctk.EW)
        bind_wraplength(self.lbl_outdated, margin=10, minimum=200)
        localize(
            ctk.CTkButton(
                self.frm_outdated,
                width=0,
                command=self._retranscribe_outdated,
                **theme.SECONDARY_BUTTON,
            ),
            text=L_("Re-transcribe them"),
        ).grid(row=0, column=2, padx=12, pady=10)

    def _init_toolbar(self) -> None:
        self.frm_toolbar = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_toolbar.grid(row=4, column=0, padx=28, pady=(18, 6), sticky=ctk.EW)
        self.frm_toolbar.grid_columnconfigure(1, weight=1)
        self.lbl_files = localize(
            ctk.CTkLabel(self.frm_toolbar, font=theme.font(15, "bold"), anchor=ctk.W),
            text=L_("Files"),
        )
        self.lbl_files.grid(row=0, column=0, sticky=ctk.W)

        self.frm_controls = ctk.CTkFrame(self.frm_toolbar, fg_color="transparent")
        self.frm_controls.grid(row=0, column=1, sticky=ctk.E)
        tk.Misc.bind(
            self.frm_toolbar,
            "<Configure>",
            lambda _event: self._wrap_rows(),
            add="+",
        )
        self.query = ctk.StringVar(self)
        self.query.trace_add("write", lambda *_args: self._on_list_change())
        self.ent_search = SearchEntry(
            self.frm_controls, self.query, L_("Search"), height=28, width=170
        )
        self.ent_search.grid(row=0, column=0, padx=(0, 8))

        self.seg_status = ctk.CTkSegmentedButton(
            self.frm_controls, values=[""], height=28
        )
        self.status_filter = LocalizedOptions(
            self.seg_status,
            lambda: {
                ALL_FILTER: _("All"),
                DONE_FILTER: C_("files", "Done"),
                FAILED_FILTER: C_("files", "Failed"),
                PENDING_FILTER: _("Pending"),
            },
            list_state.get(self.entry_id, (ALL_FILTER, NAME_SORT))[0],
            command=lambda _value: self._on_list_change(),
        )
        self.seg_status.grid(row=0, column=1, padx=(0, 8))

        self.opt_sort = CTkOptionMenu(
            self.frm_controls, values=[""], width=150, height=28, dynamic_resizing=False
        )
        self.sort = LocalizedOptions(
            self.opt_sort,
            lambda: {
                NAME_SORT: _("Sort by name"),
                STATUS_SORT: _("Sort by status"),
                DURATION_SORT: _("Sort by duration"),
                SIZE_SORT: _("Sort by size"),
            },
            list_state.get(self.entry_id, (ALL_FILTER, NAME_SORT))[1],
            command=lambda _value: self._on_list_change(),
        )
        self.opt_sort.grid(row=0, column=2)

        # The actions on the files selected, below the controls
        self.frm_selection = ctk.CTkFrame(
            self.frm_toolbar, fg_color=theme.ROW_SELECTED, corner_radius=8
        )
        self.frm_selection.grid_columnconfigure(0, weight=1)
        self.lbl_selection = ctk.CTkLabel(
            self.frm_selection, text="", font=theme.font(13), anchor=ctk.W
        )
        self.lbl_selection.grid(row=0, column=0, padx=(12, 8), pady=6, sticky=ctk.W)
        for column, (text, command) in enumerate(
            (
                (L_("Re-transcribe"), self._retranscribe_selected),
                (L_("Export…"), lambda: self._show_export_menu(selected=True)),
                (L_("Remove from history…"), self._remove_selected),
            ),
            start=1,
        ):
            button = localize(
                ctk.CTkButton(
                    self.frm_selection,
                    width=0,
                    height=26,
                    command=command,
                    **theme.SECONDARY_BUTTON,
                ),
                text=text,
            )
            button.grid(row=0, column=column, padx=(0, 6), pady=6)
            if column == 2:
                self.btn_export_selected = button
        # An icon, so the bar fits in narrow windows with longer translations
        self.btn_clear_selection = ctk.CTkButton(
            self.frm_selection,
            text="",
            image=icons.icon("x_circle", 15, theme.ICON_MUTED),
            width=26,
            height=26,
            fg_color="transparent",
            hover_color=theme.CARD_BORDER,
            command=self.clear_selection,
        )
        self.btn_clear_selection.grid(row=0, column=4, padx=(0, 8), pady=6)
        Tooltip(self.btn_clear_selection, L_("Clear selection"))

    # ENTRY

    def update_entry(self, entry: HistoryEntry) -> None:
        self.header.update_entry(entry)
        self._refresh(entry)

    def update_progress(self) -> None:
        if self.card:
            self.card.update_progress()

    def _refresh(self, entry: HistoryEntry) -> None:
        self._entry = entry
        children = self._store.children(entry.id)
        self._children = children
        # Read again, since the files may have changed meanwhile
        self._sizes.clear()
        self._missing_ids = {
            child.id for child in children if not Path(child.source).exists()
        }
        child_ids = {child.id for child in children}
        self._selected = [id_ for id_ in self._selected if id_ in child_ids]

        if entry.status.is_active or entry.status in (
            EntryStatus.FAILED,
            EntryStatus.INTERRUPTED,
        ):
            if self.card is None:
                self.card = ProgressCard(self, entry, self._actions)
                self.card.grid(row=1, column=0, padx=28, pady=(16, 0), sticky=ctk.EW)
            self.card.update_entry(entry)
        elif self.card is not None:
            self.card.destroy()
            self.card = None

        done = [child for child in children if child.status == EntryStatus.DONE]
        failed = [child for child in children if child.status == EntryStatus.FAILED]
        parts = [
            P_("{count} file", "{count} files", len(children)).format(
                count=len(children)
            ),
            _("{count} done").format(count=len(done)),
        ]
        if failed:
            parts.append(_("{count} failed").format(count=len(failed)))
        if missing := len(self._missing_ids):
            parts.append(
                P_("{count} missing", "{count} missing", missing).format(count=missing)
            )
        # The files that already had a transcription aren't in the list
        skipped = (
            self._skipped_count
            if self._skipped_count is not None
            else entry.skipped_files
        )
        if skipped:
            parts.append(
                P_(
                    "{count} skipped, already transcribed",
                    "{count} skipped, already transcribed",
                    skipped,
                ).format(count=skipped)
            )
        self.lbl_summary.configure(text=" · ".join(parts))

        self._refresh_buttons(entry, failed)
        self._refresh_outdated(entry, done)
        # The files may have changed meanwhile
        if self._was_active and not entry.status.is_active:
            self._count_skipped()
        self._was_active = entry.status.is_active
        self._render_files()
        # Their texts, and so their widths, may have changed
        self.after_idle(self._wrap_rows)

    def _wrap_rows(self) -> None:
        if self.winfo_exists():
            wrap_when_narrow(self.frm_summary, self.lbl_summary, self.frm_buttons)
            wrap_when_narrow(self.frm_toolbar, self.lbl_files, self.frm_controls)

    def _refresh_buttons(self, entry: HistoryEntry, failed: list[HistoryEntry]) -> None:
        self._failed_ids = [child.id for child in failed]
        if failed:
            self.btn_retry_failed.grid(row=0, column=0, padx=(8, 0))
        else:
            self.btn_retry_failed.grid_remove()

        if entry.status.is_active:
            self.btn_rescan.grid_remove()
        else:
            self.btn_rescan.configure(
                text=_("Resume watching")
                if entry.kind == AudioSource.WATCH.value
                else _("Rescan folder")
            )
            self.btn_rescan.grid(row=0, column=1, padx=(8, 0))

    def _refresh_outdated(self, entry: HistoryEntry, done: list[HistoryEntry]) -> None:
        """Tells which settings changed since some files were transcribed."""
        changes: set[SettingsChange] = set()
        self._outdated_ids = []
        for child in done:
            if child_changes := changed_options(child.settings, entry.settings):
                self._outdated_ids.append(child.id)
                changes.update(child_changes)

        if not self._outdated_ids:
            self.frm_outdated.grid_remove()
            return

        count = len(self._outdated_ids)
        changed = ", ".join(
            change_label(change) for change in SettingsChange if change in changes
        )
        self.lbl_outdated.configure(
            text=P_(
                "{count} file was transcribed with other settings. Changed: "
                "{settings}.",
                "{count} files were transcribed with other settings. Changed: "
                "{settings}.",
                count,
            ).format(count=count, settings=changed)
        )
        self.frm_outdated.grid(row=3, column=0, padx=28, pady=(12, 0), sticky=ctk.EW)

    def _count_skipped(self) -> None:
        """Counts the files skipped in the background, since it reads the folder."""
        counter = self._actions.files.skipped_files_counter(self.entry_id)
        if counter is None or self._entry.status.is_active:
            return
        results = self._skipped_results

        def count() -> None:
            try:
                results.put(counter())
            except OSError:
                logger.warning("Could not count the skipped files", exc_info=True)
                # So it stops waiting for the count
                results.put(-1)

        threading.Thread(target=count, daemon=True).start()
        self.after(100, self._show_skipped_count)

    def _show_skipped_count(self) -> None:
        if not self.winfo_exists():
            return
        try:
            count = self._skipped_results.get_nowait()
        except queue.Empty:
            self.after(100, self._show_skipped_count)
            return
        if count >= 0 and count != self._skipped_count:
            self._skipped_count = count
            self._refresh(self._entry)

    # FILES

    @property
    def rows(self) -> list[FileRow]:
        """The rows of the files shown, in order."""
        return sorted(
            (row for row in self._rows.values() if row.winfo_manager()),
            key=lambda row: int(row.grid_info()["row"]),
        )

    def _on_list_change(self) -> None:
        self._shown_count = PAGE_SIZE
        list_state[self.entry_id] = (self.status_filter.get(), self.sort.get())
        self._render_files()

    def _show_more(self) -> None:
        self._shown_count += PAGE_SIZE
        self._render_files()

    def _file_name(self, entry: HistoryEntry) -> str:
        """The path of a file in its folder, or the title it was renamed to."""
        path = Path(entry.source)
        folder = self._entry.source_path
        try:
            name = str(path.relative_to(folder)) if folder else path.name
        except ValueError:
            name = path.name
        return entry.title if entry.title != path.name else name

    def _size(self, entry: HistoryEntry) -> int | None:
        if entry.source not in self._sizes:
            self._sizes[entry.source] = file_size(Path(entry.source))
        return self._sizes[entry.source]

    def _visible_files(self) -> list[HistoryEntry]:
        query = self.query.get().strip()
        status_filter = self.status_filter.get()
        files = [
            child
            for child in self._children
            if matches_filter(child, status_filter)
            and (not query or child.matches(query))
        ]
        sort = self.sort.get()
        if sort == SIZE_SORT:
            for child in files:
                self._size(child)
        return sort_files(files, sort, self._sizes)

    def _render_files(self) -> None:
        children = self._children
        child_ids = {child.id for child in children}
        for entry_id in [id_ for id_ in self._rows if id_ not in child_ids]:
            self._rows.pop(entry_id).destroy()

        # Searching, filtering and sorting only help with several files
        if len(children) > 1:
            self.frm_controls.grid()
        else:
            self.frm_controls.grid_remove()

        visible = self._visible_files()
        shown = visible[: self._shown_count]
        shown_ids = {child.id for child in shown}
        for entry_id, row in self._rows.items():
            if entry_id not in shown_ids:
                row.grid_remove()

        outdated = set(self._outdated_ids)
        for idx, child in enumerate(shown):
            file_row = self._rows.get(child.id)
            if file_row is None:
                file_row = self._rows[child.id] = FileRow(self.frm_files, self, child)
            file_row.update_entry(
                child,
                self._file_name(child),
                self._size(child),
                child.id in outdated,
                is_missing=child.id in self._missing_ids,
                is_selected=child.id in self._selected,
                query=self.query.get().strip(),
            )
            file_row.grid(
                row=idx, column=0, padx=6, pady=(6 if idx == 0 else 0, 0), sticky=ctk.EW
            )

        if len(visible) > len(shown):
            self.btn_show_more.grid(row=len(shown), column=0, pady=8)
        else:
            self.btn_show_more.grid_remove()
        self._refresh_selection()

        if shown:
            self.lbl_empty.grid_remove()
            return
        if children:
            empty_text = _("No results")
        elif self._entry.status == EntryStatus.WATCHING:
            empty_text = _("Waiting for new files…")
        else:
            empty_text = _("No files")
        self.lbl_empty.configure(text=empty_text)
        self.lbl_empty.grid(row=0, column=0, padx=16, pady=24)

    def open_file(self, entry_id: str) -> None:
        if self._selected:
            # A click outside the selection clears it, like in the file manager
            self.clear_selection()
            return
        self._actions.window.select_entry(entry_id)

    # SELECTION

    @property
    def selected_ids(self) -> list[str]:
        return list(self._selected)

    def select_file(
        self, entry_id: str, is_toggle: bool = False, is_range: bool = False
    ) -> str:
        """
        Selects a file, keeping the ones selected.

        :param is_toggle: Whether to unselect it if it's selected.
        :param is_range: Whether to also select the files shown between it and
                         the last one selected.
        """
        shown = [row.entry_id for row in self.rows]
        if is_range and self._anchor_id in shown and entry_id in shown:
            start, end = sorted((shown.index(self._anchor_id), shown.index(entry_id)))
            for id_ in shown[start : end + 1]:
                if id_ not in self._selected:
                    self._selected.append(id_)
        elif is_toggle and entry_id in self._selected:
            self._selected.remove(entry_id)
        elif entry_id not in self._selected:
            self._selected.append(entry_id)
        self._anchor_id = entry_id
        self._render_files()
        return "break"

    def select_all(self) -> None:
        """Selects the files shown (e.g. the ones the search found)."""
        self._selected = [row.entry_id for row in self.rows]
        self._render_files()

    def open_selected(self) -> None:
        """Opens the file selected, if there is only one."""
        if len(self._selected) == 1:
            entry_id = self._selected[0]
            self.clear_selection()
            self._actions.window.select_entry(entry_id)

    def clear_selection(self) -> None:
        self._selected.clear()
        self._anchor_id = None
        self._render_files()

    def _refresh_selection(self) -> None:
        count = len(self._selected)
        if not count:
            self.frm_selection.grid_remove()
            return
        self.lbl_selection.configure(
            text=P_("{count} selected", "{count} selected", count).format(count=count)
        )
        has_text = any(
            entry.status == EntryStatus.DONE and entry.text.strip()
            for entry in self._selected_entries()
        )
        self.btn_export_selected.configure(
            state=ctk.NORMAL if has_text else ctk.DISABLED
        )
        self.frm_selection.grid(
            row=2, column=0, columnspan=2, pady=(8, 0), sticky=ctk.EW
        )

    def _selected_entries(self) -> list[HistoryEntry]:
        return [
            entry for entry_id in self._selected if (entry := self._store.get(entry_id))
        ]

    # MENUS

    def show_file_menu(self, entry_id: str, anchor: Any) -> str:
        """:param anchor: The button of the row, or the event of a right click."""
        entry = self._store.get(entry_id)
        if entry is None:
            return "break"
        if entry_id in self._selected and len(self._selected) > 1:
            self._show_selection_menu(anchor)
            return "break"
        actions = self._actions
        source_path = entry.source_path
        has_text = entry.status == EntryStatus.DONE and bool(entry.text.strip())
        text_state: Literal["normal", "disabled"] = (
            tk.NORMAL if has_text else tk.DISABLED
        )

        menu = tk.Menu(self, tearoff=False)
        menu.add_command(
            label=_("Open transcript"),
            command=lambda: actions.window.select_entry(entry_id),
            state=tk.NORMAL if entry.status == EntryStatus.DONE else tk.DISABLED,
        )
        menu.add_command(
            label=reveal_label(),
            command=lambda: actions.files.reveal_entry(entry_id),
            state=tk.NORMAL if source_path and source_path.exists() else tk.DISABLED,
        )
        menu.add_separator()
        menu.add_command(
            label=_("Copy text"),
            command=lambda: self._copy_text(entry_id),
            state=text_state,
        )
        for label, action in (
            (_("Export…"), TranscriptAction.EXPORT),
            (_("Summarize…"), TranscriptAction.SUMMARIZE),
            (_("Translate…"), TranscriptAction.TRANSLATE),
        ):
            menu.add_command(
                label=label,
                command=partial(actions.window.open_transcript, entry_id, action),
                state=text_state,
            )
        menu.add_separator()
        is_missing = entry_id in self._missing_ids
        menu.add_command(
            label=_("Re-transcribe this file"),
            command=lambda: actions.jobs.retranscribe_files([entry_id]),
            state=tk.DISABLED if entry.status.is_active or is_missing else tk.NORMAL,
        )
        # The files that were moved or deleted can't be transcribed again
        if is_missing:
            menu.add_command(
                label=_("Remove from history…"),
                command=lambda: actions.prompts.confirm_remove_entries([entry_id]),
            )
        self._popup(menu, anchor)
        return "break"

    def _show_selection_menu(self, anchor: Any) -> None:
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label=_("Re-transcribe"), command=self._retranscribe_selected)
        menu.add_command(
            label=_("Export…"),
            command=lambda: self._show_export_menu(selected=True),
            state=self.btn_export_selected.cget("state"),
        )
        menu.add_separator()
        menu.add_command(label=_("Remove from history…"), command=self._remove_selected)
        menu.add_command(label=_("Clear selection"), command=self.clear_selection)
        self._popup(menu, anchor)

    def _show_folder_menu(self) -> None:
        entry = self._entry
        actions = self._actions
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(
            label=_("Re-transcribe all…"),
            command=self._confirm_retranscribe_all,
            state=tk.DISABLED if entry.status.is_active else tk.NORMAL,
        )
        has_text = any(
            child.status == EntryStatus.DONE and child.text.strip()
            for child in self._children
        )
        menu.add_command(
            label=_("Export all…"),
            command=lambda: self._show_export_menu(selected=False),
            state=tk.NORMAL if has_text else tk.DISABLED,
        )
        if self._missing_ids:
            menu.add_command(
                label=_("Remove missing files from list…"),
                command=lambda: actions.prompts.confirm_remove_entries(
                    sorted(self._missing_ids)
                ),
            )
        if folders := folder_actions(entry.source_path, entry.transcripts_dir):
            menu.add_separator()
            for label, folder in folders:
                menu.add_command(
                    label=label, command=partial(actions.files.open_folder, folder)
                )
        menu.add_separator()
        menu.add_command(
            label=_("Remove from history…"),
            command=lambda: actions.prompts.confirm_delete_entry(entry.id),
        )
        self._popup(menu, self.btn_more)

    @staticmethod
    def _popup(menu: tk.Menu, anchor: Any) -> None:
        if isinstance(anchor, tk.Event):
            x, y = anchor.x_root, anchor.y_root
        else:
            x = anchor.winfo_rootx()
            y = anchor.winfo_rooty() + anchor.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    # ACTIONS

    def _copy_text(self, entry_id: str) -> None:
        if entry := self._store.get(entry_id):
            self.clipboard_clear()
            self.clipboard_append(entry.text)
            self._actions.window.show_status(_("Copied to the clipboard."))

    def _retranscribe_selected(self) -> None:
        ids = [
            entry.id
            for entry in self._selected_entries()
            if not entry.status.is_active and entry.id not in self._missing_ids
        ]
        if ids:
            self._actions.jobs.retranscribe_files(ids)
        self.clear_selection()

    def _remove_selected(self) -> None:
        if self._selected:
            self._actions.prompts.confirm_remove_entries(list(self._selected))

    def _show_export_menu(self, selected: bool) -> None:
        """
        The formats to export the transcriptions of the folder (or of the files
        selected) to, in a single file.
        """
        menu = tk.Menu(self, tearoff=False)
        for file_type, label in sorted_export_labels(COLLECTION_FORMATS):
            menu.add_command(
                label=label, command=partial(self._export, file_type, selected)
            )
        anchor = self.btn_export_selected if selected else self.btn_more
        self._popup(menu, anchor)

    def _export(self, file_type: str, selected: bool) -> None:
        entries = self._selected_entries() if selected else self._children
        documents = [
            ExportDocument(
                title=self._file_name(entry),
                text=entry.text,
                segments=entry.segments,
                is_text_edited=entry.is_text_edited,
            )
            for entry in entries
            if entry.status == EntryStatus.DONE and entry.text.strip()
        ]
        if not documents:
            return
        folder = self._entry.transcripts_dir or self._entry.source_path
        selected_path = filedialog.asksaveasfilename(
            title=_("Export transcription"),
            initialdir=str(folder) if folder else str(Path.home()),
            initialfile=f"{sanitize_file_name(self._entry.title)}.{file_type}",
            defaultextension=f".{file_type}",
            filetypes=[(f".{file_type}", f"*.{file_type}"), (_("All files"), "*.*")],
        )
        if not selected_path:
            return
        try:
            path = export_collection(
                Path(selected_path), file_type, self._entry.title, documents
            )
        except (OSError, ValueError) as e:
            self._actions.window.show_status(
                _("Could not export: {error}").format(error=e), is_error=True
            )
            return
        self._actions.window.show_status(_("Exported to {path}").format(path=path))

    def _retry_failed(self) -> None:
        if self._failed_ids:
            self._actions.jobs.retranscribe_files(list(self._failed_ids))

    def _retranscribe_outdated(self) -> None:
        if self._outdated_ids:
            self._actions.jobs.retranscribe_files(list(self._outdated_ids))

    def _confirm_retranscribe_all(self) -> None:
        if messagebox.askyesno(
            _("Re-transcribe all"),
            _(
                "Transcribe all the files of “{title}” again? The files saved for "
                "them will be replaced."
            ).format(title=self._entry.title),
            icon=messagebox.WARNING,
            parent=self.winfo_toplevel(),
        ):
            self._actions.jobs.retranscribe_folder(self.entry_id)
