import tkinter as tk
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from models.history import EntryStatus, HistoryEntry, HistoryGroup
from utils.i18n import _
from views.history.formatting import (
    format_entry_date,
    format_method,
    source_label,
    status_icon,
    status_label,
)
from views.style import icons, theme
from views.widgets.bindings import bind_context_menu, bind_recursive
from views.widgets.pill import Pill

if TYPE_CHECKING:
    from views.history.history_sidebar import HistorySidebar

ROW_PADDING_X = 10
# Between the date, model and status of a row
META_SEPARATOR = "  ·  "
# Width of the sidebar outside the rows: the left padding of the list, its
# scrollbar and the right padding of the rows
LIST_MARGIN = 6 + 17 + 6
# Width of the leading column of a row: the spacer of entries and files, or the
# chevron of folders
SPACER_WIDTH = 8
CHILD_SPACER_WIDTH = 26
CHEVRON_WIDTH = 6 + 16
STATUS_ICON_WIDTH = 14


class HistoryRow(ctk.CTkFrame):  # type: ignore[misc]
    """An entry of the history: title, status and date, and tag."""

    def __init__(
        self,
        master: Any,
        sidebar: "HistorySidebar",
        entry: HistoryEntry,
        is_child: bool = False,
        is_expanded: bool = False,
    ) -> None:
        super().__init__(
            master, fg_color="transparent", corner_radius=8, cursor="hand2"
        )
        self.entry_id = entry.id
        self._sidebar = sidebar
        self._is_child = is_child
        self._is_selected = False
        self._is_hovered = False
        self._title_font = theme.font(
            13 if not is_child else 12, "bold" if not is_child else "normal"
        )

        self.grid_columnconfigure(1, weight=1)

        # Folders have a chevron to show their files
        if entry.is_folder:
            self.btn_chevron = ctk.CTkLabel(
                self,
                text="",
                width=16,
                image=icons.icon(
                    "chevron_down" if is_expanded else "chevron_right",
                    12,
                    theme.ICON_MUTED,
                ),
            )
            self.btn_chevron.grid(
                row=0, column=0, padx=(6, 0), sticky=ctk.N, pady=(10, 0)
            )
            self.btn_chevron.bind(
                "<Button-1>", lambda _event: sidebar.toggle_folder(entry.id), add="+"
            )
        else:
            spacer_width = CHILD_SPACER_WIDTH if is_child else SPACER_WIDTH
            ctk.CTkFrame(
                self, width=spacer_width, height=1, fg_color="transparent"
            ).grid(row=0, column=0)

        self.frm_content = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_content.grid(
            row=0,
            column=1,
            padx=(4, ROW_PADDING_X),
            pady=6 if not is_child else 4,
            sticky=ctk.EW,
        )
        self.frm_content.grid_columnconfigure(0, weight=1)

        title_row = ctk.CTkFrame(self.frm_content, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky=ctk.EW)
        title_row.grid_columnconfigure(0, weight=1)
        self._title_row = title_row

        if is_child:
            # Files of a folder show their status before the name
            self.lbl_status_icon = ctk.CTkLabel(
                title_row, text="", width=STATUS_ICON_WIDTH
            )
            self.lbl_status_icon.grid(row=0, column=0, padx=(0, 6))
            title_row.grid_columnconfigure(0, weight=0)
            title_row.grid_columnconfigure(1, weight=1)
            title_column = 1
        else:
            title_column = 0

        self.lbl_title = ctk.CTkLabel(
            title_row, text="", font=self._title_font, anchor=ctk.W, height=20
        )
        self.lbl_title.grid(row=0, column=title_column, sticky=ctk.EW)
        self._title_column = title_column

        self.lbl_pin = ctk.CTkLabel(
            title_row,
            text="",
            width=14,
            image=icons.icon("pin", 12, theme.STATUS_CANCELLED),
        )
        self.lbl_note = ctk.CTkLabel(
            title_row, text="", width=14, image=icons.icon("note", 12, theme.ICON_MUTED)
        )

        if not is_child:
            meta_row = ctk.CTkFrame(self.frm_content, fg_color="transparent")
            meta_row.grid(row=1, column=0, sticky=ctk.W)
            self.lbl_status_icon = ctk.CTkLabel(
                meta_row, text="", width=STATUS_ICON_WIDTH, height=16
            )
            self.lbl_status_icon.grid(row=0, column=0, padx=(0, 5))
            self.lbl_meta = ctk.CTkLabel(
                meta_row,
                text="",
                font=theme.font(11),
                text_color=theme.HINT_TEXT,
                height=16,
            )
            self.lbl_meta.grid(row=0, column=1)

            self.pil_tag = Pill(self.frm_content)
            self.pil_tag.grid(row=2, column=0, pady=(4, 0), sticky=ctk.W)
        else:
            self.lbl_meta = ctk.CTkLabel(
                title_row,
                text="",
                font=theme.font(11),
                text_color=theme.HINT_TEXT,
                height=16,
            )

        self.update_entry(entry)

        bind_recursive(self, "<Enter>", lambda _event: self._set_hovered(True))
        bind_recursive(self, "<Leave>", self._on_leave)
        bind_recursive(self, "<Button-1>", self._on_click)
        bind_recursive(
            self, "<Double-Button-1>", lambda _event: sidebar.start_rename(entry.id)
        )
        for widget in self._all_widgets():
            bind_context_menu(
                widget, lambda event: sidebar.show_entry_menu(event, entry.id)
            )

    def _all_widgets(self) -> list[Any]:
        widgets: list[Any] = []
        stack: list[Any] = [self]
        while stack:
            widget = stack.pop()
            widgets.append(widget)
            stack.extend(widget.winfo_children())
        return widgets

    def update_entry(self, entry: HistoryEntry, spinner_frame: int = 0) -> None:
        self._entry = entry
        self.update_meta(entry)
        self.fit_title()

        column = self._title_column + 1
        for label, is_visible in (
            (self.lbl_note, bool(entry.note)),
            (self.lbl_pin, entry.is_pinned),
        ):
            if is_visible:
                label.grid(row=0, column=column, padx=(4, 0))
                column += 1
            else:
                label.grid_remove()

        self.lbl_status_icon.configure(
            image=status_icon(entry.status, 13, spinner_frame)
        )

        if not self._is_child:
            self.pil_tag.set_tag(entry.tag, source_label(entry.kind))

    def fit_title(self) -> None:
        """Shortens the title to the width of the sidebar."""
        entry = self._entry
        max_width = self._content_width()
        if self._is_child:
            # Files show their status before the title
            max_width -= STATUS_ICON_WIDTH + 6
        icon_count = int(entry.is_pinned) + int(bool(entry.note))
        max_width -= icon_count * 18
        if self._is_child:
            # Files show their date or status next to the title
            max_width -= theme.font(11).measure(self.lbl_meta.cget("text")) + 6

        self.lbl_title.configure(
            text=theme.fit_text(entry.title, self._title_font, max_width)
        )
        if not self._is_child:
            self._fit_meta()

    def update_meta(self, entry: HistoryEntry) -> None:
        if self._is_child:
            if entry.status == EntryStatus.DONE:
                text = format_entry_date(entry.created_datetime)
            else:
                text = status_label(entry.status)
            if entry.status == EntryStatus.PROCESSING:
                progress = self._sidebar.delegate.get_progress(entry.id)
                if progress is not None:
                    text = f"{progress:.0%}"
            self.lbl_meta.configure(text=text)
            self.lbl_meta.grid(row=0, column=self._title_column + 3, padx=(6, 0))
            return

        parts = [format_entry_date(entry.created_datetime)]
        if entry.method:
            parts.append(format_method(entry))
        if entry.status != EntryStatus.DONE:
            label = status_label(entry.status)
            if entry.status == EntryStatus.PROCESSING:
                progress = self._sidebar.delegate.get_progress(entry.id)
                if progress is not None:
                    label = f"{label} {progress:.0%}"
            parts.append(label)
        if entry.is_folder:
            children = self._sidebar.store.children(entry.id)
            if children:
                done = sum(child.status == EntryStatus.DONE for child in children)
                parts.append(
                    _("{done}/{total} files").format(done=done, total=len(children))
                )
        self._meta_text = META_SEPARATOR.join(parts)
        self._fit_meta()

    def _content_width(self) -> int:
        """Returns the width of the sidebar left for the content of the row."""
        if self._entry.is_folder:
            leading_width = CHEVRON_WIDTH
        elif self._is_child:
            leading_width = CHILD_SPACER_WIDTH
        else:
            leading_width = SPACER_WIDTH
        # The content has a padding of 4 on the left and ROW_PADDING_X on the right
        return self._sidebar.width - LIST_MARGIN - leading_width - 4 - ROW_PADDING_X

    def _fit_meta(self) -> None:
        # Width of the status icon before the text
        max_width = self._content_width() - STATUS_ICON_WIDTH - 5
        self.lbl_meta.configure(
            text=theme.fit_text(self._meta_text, theme.font(11), max_width)
        )

    def set_spinner_frame(self, frame: int) -> None:
        self.lbl_status_icon.configure(image=icons.spinner(frame, 13))

    def set_selected(self, is_selected: bool) -> None:
        self._is_selected = is_selected
        self._refresh_color()

    def _set_hovered(self, is_hovered: bool) -> None:
        self._is_hovered = is_hovered
        self._refresh_color()

    def _on_leave(self, event: Any) -> None:
        # Moving between the widgets of the row also triggers <Leave>
        x, y = self.winfo_pointerxy()
        widget = self.winfo_containing(x, y)
        while widget is not None:
            if widget is self:
                return
            widget = getattr(widget, "master", None)
        self._set_hovered(False)

    def _refresh_color(self) -> None:
        if self._is_selected:
            color: Any = theme.ROW_SELECTED
        elif self._is_hovered:
            color = theme.ROW_HOVER
        else:
            color = "transparent"
        self.configure(fg_color=color)

    def _on_click(self, event: Any) -> None:
        if getattr(event, "widget", None) is getattr(self, "btn_chevron", None):
            return
        self._sidebar.delegate.select_entry(self.entry_id)

    def start_rename(self, title: str) -> None:
        """Replaces the title with an entry to rename it in place."""
        variable = ctk.StringVar(self, title)
        entry = ctk.CTkEntry(
            self._title_row, textvariable=variable, height=24, font=self._title_font
        )
        entry.grid(row=0, column=self._title_column, columnspan=4, sticky=ctk.EW)
        self.lbl_title.grid_remove()
        entry.focus_set()
        entry.select_range(0, tk.END)
        is_finished = False

        def finish(should_save: bool) -> None:
            nonlocal is_finished
            if is_finished:
                return
            is_finished = True
            new_title = variable.get().strip()
            entry.destroy()
            self.lbl_title.grid()
            if should_save and new_title and new_title != title:
                self._sidebar.delegate.rename_entry(self.entry_id, new_title)

        entry.bind("<Return>", lambda _event: finish(True))

        def on_escape(_event: Any) -> str:
            finish(False)
            return "break"

        entry.bind("<Escape>", on_escape)
        entry.bind("<FocusOut>", lambda _event: finish(True))


class SectionHeader(ctk.CTkFrame):  # type: ignore[misc]
    def __init__(
        self,
        master: Any,
        sidebar: "HistorySidebar",
        key: str,
        title: str,
        count: int,
        is_collapsed: bool,
        group: HistoryGroup | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent", cursor="hand2")
        self.grid_columnconfigure(1, weight=1)

        chevron = ctk.CTkLabel(
            self,
            text="",
            width=14,
            image=icons.icon(
                "chevron_right" if is_collapsed else "chevron_down",
                10,
                theme.ICON_MUTED,
            ),
        )
        chevron.grid(row=0, column=0, padx=(8, 4))
        ctk.CTkLabel(
            self,
            text=theme.fit_text(title, theme.font(12, "bold"), sidebar.width - 90),
            font=theme.font(12, "bold"),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
            height=22,
        ).grid(row=0, column=1, sticky=ctk.W)
        ctk.CTkLabel(
            self,
            text=str(count),
            font=theme.font(11),
            text_color=theme.HINT_TEXT,
            height=22,
        ).grid(row=0, column=2, padx=(0, 12))

        bind_recursive(self, "<Button-1>", lambda _event: sidebar.toggle_section(key))
        if group is not None:
            stack: list[Any] = [self]
            while stack:
                widget = stack.pop()
                bind_context_menu(
                    widget, lambda event: sidebar.show_group_menu(event, group.id)
                )
                stack.extend(widget.winfo_children())
