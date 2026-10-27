import json
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any

import customtkinter as ctk

from models.history import EntryStatus, HistoryEntry
from models.transcription_settings import SAME_LANGUAGE, TranscriptionSettings
from utils import constants as c
from utils.enums import AudioSource
from utils.i18n import _, get_language_name
from utils.time_format import format_duration
from views.entries.delegates import EntryFiles, EntryPrompts
from views.history.formatting import (
    format_full_date,
    format_method,
    reveal_label,
    source_icon,
    source_label,
)
from views.localization import on_language_change
from views.style import icons, theme
from views.widgets.bindings import bind_wraplength
from views.widgets.pill import Pill
from views.widgets.tooltip import Tooltip


def entry_meta_items(entry: HistoryEntry) -> list[tuple[str, str]]:
    """
    Icons and texts of the date, method and language of an entry, and the file
    types that a folder saves. The language is the detected one or, if it's not
    known yet (e.g. of a folder), the one of its settings.
    """
    items = [("calendar", format_full_date(entry.created_datetime))]
    if entry.method:
        items.append(("chip", format_method(entry)))
    if entry.language:
        language = get_language_name(entry.language, fallback=entry.language)
        items.append(("globe", language))
    elif entry.settings and (language := settings_language(entry.settings)):
        items.append(("globe", language))
    if entry.is_folder and entry.settings:
        file_types = TranscriptionSettings.from_dict(
            entry.settings
        ).effective_output_file_types
        if file_types:
            items.append(("file", " ".join(f".{t}" for t in file_types)))
    return items


def header_content(entry: HistoryEntry) -> tuple[Any, ...]:
    """What the header shows of an entry, to know whether it changed."""
    return (
        entry.title,
        entry.source,
        entry.kind,
        entry.status.is_active,
        entry.status == EntryStatus.WATCHING,
        entry.created_at,
        entry.method,
        entry.language,
        json.dumps(entry.settings, sort_keys=True, default=str),
        entry.tag,
        entry.note,
    )


def settings_language(settings: dict[str, Any]) -> str:
    """
    The language of the audio of the settings and, if it's translated, the one of
    the result (e.g. "Spanish → English").
    """
    try:
        options = TranscriptionSettings.from_dict(settings)
        is_translating = options.effective_translation_mode is not None
    except (TypeError, ValueError):
        return ""

    if options.input_language == c.AUTO_DETECT_LANGUAGE:
        language = _("Auto-detect")
    else:
        language = get_language_name(
            options.input_language, fallback=options.input_language
        )
    if is_translating and options.output_language != SAME_LANGUAGE:
        output = get_language_name(
            options.output_language, fallback=options.output_language
        )
        language = f"{language} → {output}"
    return language


class EntryHeader(ctk.CTkFrame):  # type: ignore[misc]
    """
    Title, source, date, tag and note of an entry. The source, and where a folder
    saves its files, open in the file manager when clicked.
    """

    def __init__(
        self,
        master: Any,
        entry: HistoryEntry,
        prompts: EntryPrompts,
        files: EntryFiles | None = None,
        on_edit_settings: Callable[[str], None] | None = None,
    ) -> None:
        """
        :param files: Opens the source in the file manager. If None, it isn't.
        :param on_edit_settings: Opens the settings of the entry, to change them.
                                 If None, there is no button to do it. While the
                                 entry is being transcribed, it's disabled.
        """
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self._prompts = prompts
        self._files = files
        self._on_edit_settings = on_edit_settings
        # Known once the media is loaded
        self._duration: float | None = None
        self._shown = header_content(entry)
        self._build(entry)
        # The dates and the names of the languages are in the interface language
        on_language_change(self, lambda: self.update_entry(self._entry, force=True))

    def update_entry(self, entry: HistoryEntry, force: bool = False) -> None:
        """
        Shows the changes of the entry, e.g. its new title or note. It's only
        built again if something it shows changed, since a folder is updated
        each time one of its files is.

        :param force: Whether to build it again anyway (e.g. in another language).
        """
        self._entry = entry
        content = header_content(entry)
        if content == self._shown and not force:
            return
        self._shown = content
        for widget in self.winfo_children():
            widget.destroy()
        self._build(entry)
        self.set_duration(self._duration)

    def _build(self, entry: HistoryEntry) -> None:
        prompts = self._prompts
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
            "<Double-Button-1>", lambda _event: prompts.ask_to_rename_entry(entry.id)
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
            if entry.kind == AudioSource.YOUTUBE.value:
                self._link_url(self.lbl_source, entry.source)
            else:
                self._link_path(self.lbl_source, entry.source_path, entry.id)

        # Where a folder saves the files, so it's clear which folder opens
        self._output_text = ""
        self.lbl_output = self._meta_label(meta, "export")
        if entry.is_folder and (output_dir := entry.transcripts_dir):
            is_same = entry.source_path is not None and (
                output_dir.resolve() == entry.source_path.resolve()
            )
            self._output_text = (
                _("Saved next to the source")
                if is_same
                else _("Saved in {folder}").format(folder=output_dir)
            )
            self.lbl_output.grid(row=1, column=0, pady=(2, 0), sticky=ctk.EW)
            self.lbl_output.bind("<Configure>", lambda _event: self._fit_output())
            self._link_path(self.lbl_output, output_dir)

        details = ctk.CTkFrame(meta, fg_color="transparent")
        details.grid(row=2, column=0, pady=(2, 0), sticky=ctk.W)
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
        self.pil_tag.bind("<Button-1>", lambda _event: prompts.ask_for_tag(entry.id))
        if not entry.note:
            # With a border, so it reads as a button and not as more metadata.
            # Rounded and as tall as the tag next to it
            ctk.CTkButton(
                actions,
                text=_("Add note"),
                image=icons.icon("note", 12, theme.ICON_MUTED),
                compound=ctk.LEFT,
                width=0,
                height=22,
                corner_radius=11,
                font=theme.font(12),
                command=lambda: prompts.ask_for_note(entry.id),
                **theme.SECONDARY_BUTTON,
            ).grid(row=0, column=1, padx=(8, 0))
        self.btn_settings: ctk.CTkButton | None = None
        if self._on_edit_settings:
            on_edit_settings = self._on_edit_settings
            self.btn_settings = ctk.CTkButton(
                actions,
                text=_("Edit settings"),
                image=icons.icon("gear", 12, theme.ICON_MUTED),
                compound=ctk.LEFT,
                width=0,
                height=22,
                corner_radius=11,
                font=theme.font(12),
                command=lambda: on_edit_settings(entry.id),
                **theme.SECONDARY_BUTTON,
            )
            self.btn_settings.grid(row=0, column=2, padx=(8, 0))
            # Shown while it's transcribed, so it's clear how to change them
            if entry.status.is_active:
                self.btn_settings.configure(state=ctk.DISABLED)
                is_watch = (
                    entry.status == EntryStatus.WATCHING
                    or entry.kind == AudioSource.WATCH.value
                )
                self.tip_settings = Tooltip(
                    self.btn_settings,
                    (lambda: _("Stop watching to edit settings"))
                    if is_watch
                    else (lambda: _("Wait until it finishes to edit settings")),
                )

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
            lbl_note.grid(row=0, column=1, padx=(0, 4), pady=10, sticky=ctk.EW)
            bind_wraplength(lbl_note, margin=10, minimum=200)
            for widget in (note, lbl_note):
                widget.bind("<Button-1>", lambda _event: prompts.ask_for_note(entry.id))

            note_actions = ctk.CTkFrame(note, fg_color="transparent")
            note_actions.grid(row=0, column=2, padx=(0, 8), pady=11, sticky=ctk.N)
            for column, (icon_name, command) in enumerate(
                (
                    ("pencil", lambda: prompts.ask_for_note(entry.id)),
                    ("trash", lambda: prompts.confirm_delete_note(entry.id)),
                )
            ):
                ctk.CTkButton(
                    note_actions,
                    text="",
                    image=icons.icon(icon_name, 14, theme.ICON_MUTED),
                    width=26,
                    height=26,
                    fg_color="transparent",
                    hover_color=theme.NOTE_BORDER,
                    command=command,
                ).grid(row=0, column=column)

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

    def _link_path(
        self, label: ctk.CTkLabel, path: Path | None, entry_id: str | None = None
    ) -> None:
        """
        Opens a path in the file manager when the label is clicked, if it exists.

        :param entry_id: The entry whose source is the path, to show a file in its
                         folder. Folders are opened.
        """
        files = self._files
        if files is None or path is None or not path.exists():
            return
        if path.is_dir():
            Tooltip(label, lambda: _("Open folder"))
            label.bind("<Button-1>", lambda _event: files.open_folder(path))
        elif entry_id:
            Tooltip(label, reveal_label)
            label.bind("<Button-1>", lambda _event: files.reveal_entry(entry_id))
        else:
            return
        self._show_as_link(label)

    def _link_url(self, label: ctk.CTkLabel, url: str) -> None:
        """Opens a URL in the browser when the label is clicked."""
        if self._files is None or not url.startswith(("http://", "https://")):
            return
        Tooltip(label, lambda: _("Open in browser"))
        label.bind("<Button-1>", lambda _event: webbrowser.open(url))
        self._show_as_link(label)

    @staticmethod
    def _show_as_link(label: ctk.CTkLabel) -> None:
        label.configure(cursor="hand2")
        label.bind(
            "<Enter>", lambda _event: label.configure(text_color=theme.ACCENT), add="+"
        )
        label.bind(
            "<Leave>",
            lambda _event: label.configure(text_color=theme.HINT_TEXT),
            add="+",
        )

    def _fit_source(self) -> None:
        self._fit(self.lbl_source, self._source_text)

    def _fit_output(self) -> None:
        self._fit(self.lbl_output, self._output_text)

    @staticmethod
    def _fit(label: ctk.CTkLabel, text: str) -> None:
        width = label.winfo_width()
        if width <= 1:
            return
        # Leave room for the icon
        available = max(width - 30, 80)
        label.configure(text=f" {theme.fit_text(text, theme.font(12), available)}")
