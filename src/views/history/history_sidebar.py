import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any, Protocol

import customtkinter as ctk

from models.history import EntryStatus, HistoryEntry, HistoryGroup
from utils.history_store import HistoryStore
from utils.i18n import _
from views.entries.delegates import EntryFiles, EntryPrompts, JobControls
from views.history.formatting import reveal_label
from views.history.history_row import HistoryRow, SectionHeader
from views.localization import localize, on_language_change
from views.style import icons, theme
from views.widgets.bindings import bind_wraplength
from views.widgets.scrollable_frame import CTkScrollableFrame
from views.widgets.search_entry import SearchEntry

SPINNER_INTERVAL_MS = 90

# Key of the sections that are not groups
PINNED_SECTION = "__pinned__"
UNGROUPED_SECTION = "__ungrouped__"


class HistoryOrganizer(Protocol):
    """Renames, pins and groups the entries, without asking the user first."""

    def rename_entry(self, entry_id: str, title: str) -> None: ...
    def toggle_pin(self, entry_id: str) -> None: ...
    def move_to_group(self, entry_id: str, group_id: str | None) -> None: ...


class GroupPrompts(Protocol):
    """The actions on the groups that ask the user for a name or a confirmation."""

    def ask_to_create_group(self) -> str | None: ...
    def ask_to_move_to_new_group(self, entry_id: str) -> None: ...
    def ask_to_rename_group(self, group_id: str) -> None: ...
    def confirm_delete_group(self, group_id: str) -> None: ...


@dataclass(frozen=True)
class SidebarActions:
    """
    Everything the sidebar can do, grouped by who does it: the controllers change
    the data, while the window asks the user first or shows the selected entry.
    """

    history: HistoryOrganizer
    files: EntryFiles
    jobs: JobControls
    prompts: EntryPrompts
    groups: GroupPrompts
    select_entry: Callable[[str], None]


class HistorySidebar(ctk.CTkFrame):  # type: ignore[misc]
    """
    List of the transcriptions, like the list of notes of the Notes app: the
    pinned entries first, then the groups and the entries without a group, each
    sorted by date. Folder transcriptions can be expanded to show their files.
    """

    def __init__(
        self,
        master: Any,
        store: HistoryStore,
        actions: SidebarActions,
        width: int = theme.SIDEBAR_WIDTH,
    ) -> None:
        width = clamp_sidebar_width(width)
        super().__init__(
            master,
            width=width,
            corner_radius=0,
            fg_color=theme.SIDEBAR_BG,
        )
        self.width = width
        self.store = store
        self.actions = actions
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._rows: dict[str, HistoryRow] = {}
        self._visible_ids: list[str] = []
        self._selected_id: str | None = None
        self._expanded_folders: set[str] = set()
        self._collapsed_sections: set[str] = set()
        self._spinner_frame = 0
        self._spinner_after_id: str | None = None
        self._refresh_after_id: str | None = None
        # The variable of the groups of the open entry menu, which Tkinter needs to
        # be kept
        self._menu_group_variable: tk.StringVar | None = None

        self._init_search()
        self.frm_list = CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0
        )
        self.frm_list.grid(row=1, column=0, sticky=ctk.NSEW, padx=(6, 0))
        self.frm_list.grid_columnconfigure(0, weight=1)
        self._init_footer()

        self.refresh()
        # The list is built again, with its sections, dates and statuses
        on_language_change(self, self.refresh)

    def destroy(self) -> None:
        for after_id in (self._spinner_after_id, self._refresh_after_id):
            if after_id:
                self.after_cancel(after_id)
        super().destroy()

    # WIDGETS

    def _init_search(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=0, column=0, padx=12, pady=(12, 8), sticky=ctk.EW)
        frame.grid_columnconfigure(0, weight=1)

        self._search_variable = ctk.StringVar(self)
        self._search_variable.trace_add(
            "write", lambda *_args: self._schedule_refresh()
        )
        search = SearchEntry(
            frame,
            textvariable=self._search_variable,
            placeholder_text=lambda: _("Search"),
        )
        search.grid(row=0, column=0, sticky=ctk.EW)
        self.ent_search = search.entry
        self.ent_search.bind("<Escape>", lambda _event: self._search_variable.set(""))

    def _init_footer(self) -> None:
        ctk.CTkFrame(self, height=1, fg_color=theme.DIVIDER).grid(
            row=2, column=0, sticky=ctk.EW
        )
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, padx=8, pady=8, sticky=ctk.EW)
        footer.grid_columnconfigure(1, weight=1)

        localize(
            ctk.CTkButton(
                footer,
                image=icons.icon("plus", 14),
                compound=ctk.LEFT,
                anchor=ctk.W,
                height=28,
                width=0,
                command=self.actions.groups.ask_to_create_group,
                **theme.GHOST_BUTTON,
            ),
            text=lambda: _("New group"),
        ).grid(row=0, column=0, sticky=ctk.W)
        self.lbl_count = ctk.CTkLabel(
            footer, text="", font=theme.font(11), text_color=theme.HINT_TEXT
        )
        self.lbl_count.grid(row=0, column=2, padx=(0, 6))

    # PUBLIC METHODS

    @property
    def visible_entry_ids(self) -> list[str]:
        return list(self._visible_ids)

    def focus_search(self) -> None:
        self.ent_search.focus_set()
        self.ent_search.select_range(0, tk.END)

    def set_width(self, width: int, is_final: bool = True) -> int:
        """
        Resizes the sidebar.

        :param is_final: Whether the resizing has finished. While dragging, only
                         the titles are shortened again, since rebuilding the
                         whole list is slower.
        :return: The width set, within the limits.
        """
        width = clamp_sidebar_width(width)
        if width != self.width:
            self.width = width
            self.configure(width=width)
            for row in self._rows.values():
                row.fit_title()
        if is_final:
            self.refresh()
        return width

    def refresh(self) -> None:
        """Rebuilds the list."""
        self._refresh_after_id = None
        for widget in self.frm_list.winfo_children():
            widget.destroy()
        self._rows.clear()
        self._visible_ids.clear()

        query = self._search_variable.get().strip()
        top_level = self.store.top_level()
        count = len(top_level)
        self.lbl_count.configure(
            text=_("{count} transcriptions").format(count=count)
            if count != 1
            else _("1 transcription")
        )

        if query:
            self._build_search_results(query)
        elif not top_level:
            self._build_empty_state(
                _("No transcriptions yet"),
                _("Choose a source above to transcribe your first file."),
            )
        else:
            self._build_sections(top_level)

        self._refresh_selection()
        self._refresh_spinner()

    def update_entry(self, entry_id: str) -> None:
        """Updates the row of an entry, and its folder if it's a file of one."""
        entry = self.store.get(entry_id)
        if entry is None:
            return

        if row := self._rows.get(entry_id):
            row.update_entry(entry, self._spinner_frame)
        if entry.parent_id and (parent_row := self._rows.get(entry.parent_id)):
            parent = self.store.get(entry.parent_id)
            if parent:
                parent_row.update_meta(parent)
        self._refresh_spinner()

    def update_progress(self, entry_id: str) -> None:
        entry = self.store.get(entry_id)
        if entry and (row := self._rows.get(entry_id)):
            row.update_meta(entry)

    def set_selected(self, entry_id: str | None) -> None:
        self._selected_id = entry_id

        # The files of a folder are shown when one of them is selected
        entry = self.store.get(entry_id)
        if entry and entry.parent_id and entry.parent_id not in self._expanded_folders:
            self._expanded_folders.add(entry.parent_id)
            self.refresh()
            return

        self._refresh_selection()

    def expand_folder(self, entry_id: str) -> None:
        if entry_id not in self._expanded_folders:
            self._expanded_folders.add(entry_id)
            self.refresh()

    def toggle_folder(self, entry_id: str) -> None:
        if entry_id in self._expanded_folders:
            self._expanded_folders.discard(entry_id)
        else:
            self._expanded_folders.add(entry_id)
        self.refresh()

    def toggle_section(self, key: str) -> None:
        if key in self._collapsed_sections:
            self._collapsed_sections.discard(key)
        else:
            self._collapsed_sections.add(key)
        self.refresh()

    def start_rename(self, entry_id: str) -> None:
        entry = self.store.get(entry_id)
        row = self._rows.get(entry_id)
        if entry and row:
            self.actions.select_entry(entry_id)
            row.start_rename(entry.title)

    # MENUS

    def show_entry_menu(self, event: Any, entry_id: str) -> str:
        entry = self.store.get(entry_id)
        if entry is None:
            return "break"

        self.actions.select_entry(entry_id)
        menu = tk.Menu(self, tearoff=False)
        is_child = entry.parent_id is not None

        menu.add_command(label=_("Rename"), command=lambda: self.start_rename(entry_id))
        menu.add_command(
            label=_("Edit note…") if entry.note else _("Add note…"),
            command=lambda: self.actions.prompts.ask_for_note(entry_id),
        )
        if entry.note:
            menu.add_command(
                label=_("Delete note…"),
                command=lambda: self.actions.prompts.confirm_delete_note(entry_id),
            )
        menu.add_command(
            label=_("Edit tag…"),
            command=lambda: self.actions.prompts.ask_for_tag(entry_id),
        )

        if not is_child:
            menu.add_command(
                label=_("Unpin") if entry.is_pinned else _("Pin to the top"),
                command=lambda: self.actions.history.toggle_pin(entry_id),
            )
            groups_menu = tk.Menu(menu, tearoff=False)
            current_group = tk.StringVar(menu, entry.group_id or "")
            groups_menu.add_radiobutton(
                label=_("No group"),
                value="",
                variable=current_group,
                command=lambda: self.actions.history.move_to_group(entry_id, None),
            )
            for group in self.store.groups:
                groups_menu.add_radiobutton(
                    label=group.name,
                    value=group.id,
                    variable=current_group,
                    command=partial(
                        self.actions.history.move_to_group, entry_id, group.id
                    ),
                )
            groups_menu.add_separator()
            groups_menu.add_command(
                label=_("New group…"),
                command=lambda: self.actions.groups.ask_to_move_to_new_group(entry_id),
            )
            menu.add_cascade(label=_("Move to group"), menu=groups_menu)
            self._menu_group_variable = current_group

        menu.add_separator()
        source_path = entry.source_path
        menu.add_command(
            label=reveal_label(),
            command=lambda: self.actions.files.reveal_entry(entry_id),
            state=tk.NORMAL if source_path and source_path.exists() else tk.DISABLED,
        )

        if entry.status.is_active:
            menu.add_command(
                label=_("Stop watching")
                if entry.status == EntryStatus.WATCHING
                else _("Cancel"),
                command=lambda: self.actions.jobs.cancel_entry(entry_id),
            )
        elif not is_child:
            menu.add_command(
                label=_("Transcribe again"),
                command=lambda: self.actions.jobs.retry_entry(entry_id),
            )

        menu.add_separator()
        menu.add_command(
            label=_("Delete…"),
            command=lambda: self.actions.prompts.confirm_delete_entry(entry_id),
        )

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def show_group_menu(self, event: Any, group_id: str) -> str:
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(
            label=_("Rename group…"),
            command=lambda: self.actions.groups.ask_to_rename_group(group_id),
        )
        menu.add_command(
            label=_("Delete group…"),
            command=lambda: self.actions.groups.confirm_delete_group(group_id),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    # BUILDING THE LIST

    def _schedule_refresh(self) -> None:
        if self._refresh_after_id:
            self.after_cancel(self._refresh_after_id)
        self._refresh_after_id = self.after(150, self.refresh)

    def _build_sections(self, top_level: list[HistoryEntry]) -> None:
        pinned = [entry for entry in top_level if entry.is_pinned]
        unpinned = [entry for entry in top_level if not entry.is_pinned]
        groups = self.store.groups

        sections: list[tuple[str, str, list[HistoryEntry], HistoryGroup | None]] = []
        if pinned:
            sections.append((PINNED_SECTION, _("Pinned"), pinned, None))
        for group in groups:
            entries = [entry for entry in unpinned if entry.group_id == group.id]
            sections.append((group.id, group.name, entries, group))
        ungrouped = [entry for entry in unpinned if entry.group_id is None]
        # The section of the entries without a group only has a header when there
        # are other sections
        if ungrouped or not sections:
            sections.append((UNGROUPED_SECTION, _("Transcriptions"), ungrouped, None))

        has_headers = len(sections) > 1
        row = 0
        for key, title, entries, section_group in sections:
            is_collapsed = key in self._collapsed_sections
            if has_headers:
                SectionHeader(
                    self.frm_list,
                    self,
                    key,
                    title,
                    len(entries),
                    is_collapsed,
                    section_group,
                ).grid(row=row, column=0, sticky=ctk.EW, pady=(10 if row else 2, 2))
                row += 1
            if is_collapsed and has_headers:
                continue
            if not entries and section_group is not None:
                lbl_empty = ctk.CTkLabel(
                    self.frm_list,
                    text=_(
                        "Empty. To add a transcription, right-click it and choose "
                        "“Move to group”."
                    ),
                    font=theme.font(11),
                    text_color=theme.HINT_TEXT,
                    anchor=ctk.W,
                    justify=ctk.LEFT,
                )
                lbl_empty.grid(row=row, column=0, padx=26, pady=(0, 4), sticky=ctk.EW)
                bind_wraplength(lbl_empty)
                row += 1
            for entry in entries:
                row = self._add_entry_rows(entry, row)

    def _add_entry_rows(self, entry: HistoryEntry, row: int) -> int:
        is_expanded = entry.id in self._expanded_folders
        self._add_row(entry, row, is_expanded=is_expanded)
        row += 1

        if entry.is_folder and is_expanded:
            children = self.store.children(entry.id)
            if not children:
                ctk.CTkLabel(
                    self.frm_list,
                    text=_("No files yet"),
                    font=theme.font(11),
                    text_color=theme.HINT_TEXT,
                ).grid(row=row, column=0, padx=44, sticky=ctk.W)
                row += 1
            for child in children:
                self._add_row(child, row, is_child=True)
                row += 1

        return row

    def _add_row(
        self,
        entry: HistoryEntry,
        row: int,
        is_child: bool = False,
        is_expanded: bool = False,
    ) -> None:
        widget = HistoryRow(
            self.frm_list, self, entry, is_child=is_child, is_expanded=is_expanded
        )
        widget.grid(row=row, column=0, sticky=ctk.EW, padx=(0, 6), pady=1)
        self._rows[entry.id] = widget
        self._visible_ids.append(entry.id)

    def _build_search_results(self, query: str) -> None:
        results = []
        for entry in self.store.top_level():
            if entry.matches(query):
                results.append((entry, False))
            for child in self.store.children(entry.id) if entry.is_folder else []:
                if child.matches(query):
                    results.append((child, True))

        if not results:
            self._build_empty_state(
                _("No results"),
                _("No transcription contains “{query}”.").format(query=query),
            )
            return

        for row, (entry, is_child) in enumerate(results):
            self._add_row(entry, row, is_child=is_child)

    def _build_empty_state(self, title: str, message: str) -> None:
        frame = ctk.CTkFrame(self.frm_list, fg_color="transparent")
        frame.grid(row=0, column=0, pady=60, sticky=ctk.EW)
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text="", image=icons.app_logo(44, theme.ICON_MUTED)).grid(
            row=0, column=0
        )
        ctk.CTkLabel(frame, text=title, font=theme.font(14, "bold")).grid(
            row=1, column=0, pady=(8, 2)
        )
        lbl_message = ctk.CTkLabel(
            frame,
            text=message,
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
        )
        lbl_message.grid(row=2, column=0, padx=20, sticky=ctk.EW)
        bind_wraplength(lbl_message)

    def _refresh_selection(self) -> None:
        for entry_id, row in self._rows.items():
            row.set_selected(entry_id == self._selected_id)

    # SPINNER

    def _refresh_spinner(self) -> None:
        is_processing = any(
            (entry := self.store.get(entry_id)) is not None
            and entry.status == EntryStatus.PROCESSING
            for entry_id in self._rows
        )
        if is_processing and self._spinner_after_id is None:
            self._spinner_after_id = self.after(
                SPINNER_INTERVAL_MS, self._animate_spinner
            )

    def _animate_spinner(self) -> None:
        self._spinner_after_id = None
        self._spinner_frame = (self._spinner_frame + 1) % icons.SPINNER_FRAMES
        is_processing = False

        for entry_id, row in self._rows.items():
            entry = self.store.get(entry_id)
            if entry and entry.status == EntryStatus.PROCESSING:
                row.set_spinner_frame(self._spinner_frame)
                is_processing = True

        if is_processing:
            self._spinner_after_id = self.after(
                SPINNER_INTERVAL_MS, self._animate_spinner
            )


def clamp_sidebar_width(width: int) -> int:
    return max(theme.SIDEBAR_MIN_WIDTH, min(int(width), theme.SIDEBAR_MAX_WIDTH))
