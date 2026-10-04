from typing import Any

import customtkinter as ctk

from models.history import HistoryEntry
from utils.i18n import _, get_language_name
from utils.time_format import format_duration
from views.entries.delegates import TranscriptDelegate
from views.history.formatting import (
    format_full_date,
    format_method,
    source_icon,
    source_label,
)
from views.style import icons, theme
from views.widgets.bindings import bind_wraplength
from views.widgets.pill import Pill


def entry_meta_items(entry: HistoryEntry) -> list[tuple[str, str]]:
    """Icons and texts of the date, method and language of an entry."""
    items = [("calendar", format_full_date(entry.created_datetime))]
    if entry.method:
        items.append(("chip", format_method(entry)))
    if entry.language:
        language = get_language_name(entry.language, fallback=entry.language)
        items.append(("globe", language))
    return items


class EntryHeader(ctk.CTkFrame):  # type: ignore[misc]
    """Title, source, date, tag and note of an entry."""

    def __init__(
        self, master: Any, entry: HistoryEntry, delegate: TranscriptDelegate
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self._delegate = delegate
        # Known once the media is loaded
        self._duration: float | None = None
        self._build(entry)

    def update_entry(self, entry: HistoryEntry) -> None:
        """Shows the changes of the entry, e.g. its new title or note."""
        for widget in self.winfo_children():
            widget.destroy()
        self._build(entry)
        self.set_duration(self._duration)

    def _build(self, entry: HistoryEntry) -> None:
        delegate = self._delegate
        self._entry = entry

        self.lbl_title = ctk.CTkLabel(
            self,
            text=entry.title,
            font=theme.font(21, "bold"),
            anchor=ctk.W,
            justify=ctk.LEFT,
            cursor="hand2",
        )
        self.lbl_title.grid(row=0, column=0, sticky=ctk.EW)
        bind_wraplength(self.lbl_title, margin=10, minimum=200)
        self.lbl_title.bind(
            "<Double-Button-1>", lambda _event: delegate.rename_entry_dialog(entry.id)
        )

        meta = ctk.CTkFrame(self, fg_color="transparent")
        meta.grid(row=1, column=0, pady=(4, 0), sticky=ctk.EW)
        meta.grid_columnconfigure(0, weight=1)

        # The source (path or URL) on its own line, shortened to the width
        self._source_text = entry.source or ""
        self.lbl_source = self._meta_label(meta, source_icon(entry.kind))
        if self._source_text:
            self.lbl_source.grid(row=0, column=0, sticky=ctk.EW)
            self.lbl_source.bind("<Configure>", lambda _event: self._fit_source())

        details = ctk.CTkFrame(meta, fg_color="transparent")
        details.grid(row=1, column=0, pady=(2, 0), sticky=ctk.W)
        for column, (icon_name, text) in enumerate(entry_meta_items(entry)):
            label = self._meta_label(details, icon_name, text)
            label.grid(row=0, column=column, padx=(0, 16))
        self.lbl_duration = self._meta_label(details, "clock")
        self._duration_column = len(details.grid_slaves())

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=2, column=0, pady=(8, 0), sticky=ctk.W)
        self.pil_tag = Pill(actions, cursor="hand2")
        self.pil_tag.set_tag(entry.tag, source_label(entry.kind))
        self.pil_tag.grid(row=0, column=0)
        self.pil_tag.bind("<Button-1>", lambda _event: delegate.edit_tag(entry.id))
        if not entry.note:
            ctk.CTkButton(
                actions,
                text=_("Add note"),
                image=icons.icon("note", 13, theme.ICON_MUTED),
                compound=ctk.LEFT,
                width=0,
                height=22,
                font=theme.font(12),
                command=lambda: delegate.edit_note(entry.id),
                **theme.GHOST_BUTTON,
            ).grid(row=0, column=1, padx=(8, 0))

        if entry.note:
            note = ctk.CTkFrame(
                self,
                fg_color=theme.NOTE_BG,
                border_color=theme.NOTE_BORDER,
                border_width=1,
                corner_radius=10,
                cursor="hand2",
            )
            note.grid(row=3, column=0, pady=(10, 0), sticky=ctk.EW)
            note.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                note, text="", image=icons.icon("note", 15, theme.STATUS_CANCELLED)
            ).grid(row=0, column=0, padx=(12, 8), pady=10, sticky=ctk.N)
            lbl_note = ctk.CTkLabel(
                note,
                text=entry.note,
                font=theme.font(13),
                anchor=ctk.W,
                justify=ctk.LEFT,
            )
            lbl_note.grid(row=0, column=1, padx=(0, 12), pady=10, sticky=ctk.EW)
            bind_wraplength(lbl_note, margin=10, minimum=200)
            for widget in (note, lbl_note):
                widget.bind("<Button-1>", lambda _event: delegate.edit_note(entry.id))

    @staticmethod
    def _meta_label(master: Any, icon_name: str, text: str = "") -> ctk.CTkLabel:
        return ctk.CTkLabel(
            master,
            text=f" {text}",
            image=icons.icon(icon_name, 13, theme.ICON_MUTED),
            compound=ctk.LEFT,
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
            height=20,
        )

    def set_duration(self, seconds: float | None) -> None:
        self._duration = seconds
        if seconds:
            self.lbl_duration.configure(text=f" {format_duration(seconds)}")
            self.lbl_duration.grid(row=0, column=self._duration_column)
        else:
            self.lbl_duration.grid_remove()

    def _fit_source(self) -> None:
        width = self.lbl_source.winfo_width()
        if width <= 1:
            return
        # Leave room for the icon
        available = max(width - 30, 80)
        source = theme.fit_text(self._source_text, theme.font(12), available)
        self.lbl_source.configure(text=f" {source}")
