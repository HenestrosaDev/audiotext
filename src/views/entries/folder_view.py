from pathlib import Path
from typing import Any

import customtkinter as ctk

from models.history import EntryStatus, HistoryEntry
from utils.history_store import HistoryStore
from utils.i18n import _
from views.entries.delegates import EntryActions
from views.entries.entry_header import EntryHeader
from views.entries.progress_card import ProgressCard
from views.history.formatting import format_entry_date, status_icon, status_label
from views.localization import localize, on_language_change
from views.style import theme
from views.widgets.scrollable_frame import CTkScrollableFrame


class FolderView(ctk.CTkFrame):  # type: ignore[misc]
    """
    A folder transcription: its progress and the list of its files, which open
    their transcription when clicked.
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
        self._rows: dict[str, tuple[ctk.CTkLabel, ctk.CTkLabel]] = {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self.header = EntryHeader(self, entry, actions.prompts)
        self.header.grid(row=0, column=0, padx=28, pady=(22, 0), sticky=ctk.EW)

        # Row 1 is the progress card, only shown while the folder is transcribed
        self.card: ProgressCard | None = None
        self.frm_summary = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_summary.grid(row=2, column=0, padx=28, pady=(16, 0), sticky=ctk.EW)
        self.frm_summary.grid_columnconfigure(0, weight=1)
        self.lbl_summary = ctk.CTkLabel(
            self.frm_summary, text="", font=theme.font(13), anchor=ctk.W
        )
        self.lbl_summary.grid(row=0, column=0, sticky=ctk.W)
        self.frm_buttons = ctk.CTkFrame(self.frm_summary, fg_color="transparent")
        self.frm_buttons.grid(row=0, column=1, sticky=ctk.E)

        localize(
            ctk.CTkLabel(self, font=theme.font(15, "bold"), anchor=ctk.W),
            text=lambda: _("Files"),
        ).grid(row=3, column=0, padx=28, pady=(18, 6), sticky=ctk.W)
        self.frm_files = CTkScrollableFrame(
            self,
            fg_color=theme.CARD_BG,
            border_color=theme.CARD_BORDER,
            border_width=1,
            corner_radius=12,
        )
        self.frm_files.grid(row=4, column=0, padx=28, pady=(0, 20), sticky=ctk.NSEW)
        self.frm_files.grid_columnconfigure(1, weight=1)

        self._refresh(entry)
        # The summary and the list of the files are built again
        on_language_change(self, lambda: self._refresh(self._entry))

    def update_entry(self, entry: HistoryEntry) -> None:
        self.header.update_entry(entry)
        self._refresh(entry)

    def _refresh(self, entry: HistoryEntry) -> None:
        self._entry = entry
        children = self._store.children(entry.id)

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

        done = sum(child.status == EntryStatus.DONE for child in children)
        failed = sum(child.status == EntryStatus.FAILED for child in children)
        parts = [
            _("{count} files").format(count=len(children)),
            _("{count} done").format(count=done),
        ]
        if failed:
            parts.append(_("{count} failed").format(count=failed))
        self.lbl_summary.configure(text=" · ".join(parts))

        for widget in self.frm_buttons.winfo_children():
            widget.destroy()
        output_dir = Path(entry.output_dir) if entry.output_dir else entry.source_path
        if output_dir and output_dir.is_dir():
            ctk.CTkButton(
                self.frm_buttons,
                text=_("Open the folder of the saved files"),
                width=0,
                command=lambda: self._actions.files.open_folder(output_dir),
                **theme.SECONDARY_BUTTON,
            ).grid(row=0, column=0, padx=(8, 0))
        if not entry.status.is_active:
            ctk.CTkButton(
                self.frm_buttons,
                text=_("Transcribe again"),
                width=0,
                command=lambda: self._actions.jobs.retry_entry(entry.id),
                **theme.SECONDARY_BUTTON,
            ).grid(row=0, column=1, padx=(8, 0))

        self._render_files(entry, children)

    def update_progress(self) -> None:
        if self.card:
            self.card.update_progress()

    def _render_files(self, entry: HistoryEntry, children: list[HistoryEntry]) -> None:
        for widget in self.frm_files.winfo_children():
            widget.destroy()
        self._rows.clear()

        if not children:
            ctk.CTkLabel(
                self.frm_files,
                text=_("Waiting for new files…")
                if entry.status == EntryStatus.WATCHING
                else _("No files"),
                font=theme.font(13),
                text_color=theme.HINT_TEXT,
            ).grid(row=0, column=0, columnspan=3, padx=16, pady=24)
            return

        folder = entry.source_path
        for row, child in enumerate(children):
            path = Path(child.source)
            try:
                name = str(path.relative_to(folder)) if folder else path.name
            except ValueError:
                name = path.name

            icon_label = ctk.CTkLabel(
                self.frm_files, text="", width=18, image=status_icon(child.status, 15)
            )
            icon_label.grid(row=row, column=0, padx=(14, 8), pady=5)
            title = child.title if child.title != path.name else name
            name_label = ctk.CTkLabel(
                self.frm_files,
                text=title,
                font=theme.font(13),
                anchor=ctk.W,
                cursor="hand2",
            )
            name_label.grid(row=row, column=1, sticky=ctk.EW, pady=5)
            detail = (
                child.error
                if child.status == EntryStatus.FAILED
                else (
                    format_entry_date(child.created_datetime)
                    if child.status == EntryStatus.DONE
                    else status_label(child.status)
                )
            )
            detail_label = ctk.CTkLabel(
                self.frm_files,
                text=theme.fit_text(detail, theme.font(12), 320),
                font=theme.font(12),
                text_color=theme.ERROR_TEXT
                if child.status == EntryStatus.FAILED
                else theme.HINT_TEXT,
            )
            detail_label.grid(row=row, column=2, padx=14, sticky=ctk.E)
            for widget in (icon_label, name_label, detail_label):
                widget.bind(
                    "<Button-1>",
                    lambda _event, child_id=child.id: self._actions.window.select_entry(
                        child_id
                    ),
                )
            self._rows[child.id] = (icon_label, detail_label)
