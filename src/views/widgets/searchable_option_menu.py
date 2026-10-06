import tkinter as tk
import unicodedata
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from views.localization import Text
from views.widgets.option_menu import CTkOptionMenu
from views.widgets.placeholder import add_placeholder

PICKER_WIDTH = 300
PICKER_HEIGHT = 380
# Gap between the option menu and the picker window
PICKER_OFFSET_Y = 4


def normalize_search_text(text: str) -> str:
    """
    Normalizes a text to compare it with the search query, ignoring the case and
    the accents (e.g. "espanol" matches "Español").

    :param text: The text to normalize.
    :type text: str
    :return: The normalized text.
    :rtype: str
    """
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


class CTkSearchableOptionMenu(CTkOptionMenu):
    """
    Option menu that opens a window with a search entry instead of the native menu,
    which is cumbersome with many values.
    """

    def __init__(
        self,
        master: Any,
        values: list[str],
        title: Text,
        search_placeholder: Text,
        no_results_text: Text,
        command: Callable[[str], None] | None = None,
        search_terms: dict[str, str] | None = None,
        **kwargs: Any,
    ):
        """
        :param values: The labels of the options.
        :param title: The title of the picker window.
        :param search_placeholder: The placeholder of the search entry.
        :param no_results_text: The text shown when no option matches the search.
        :param command: Called with the selected label.
        :param search_terms: Extra text matched by the search for each label (e.g.
                             the English name of a language).
        """
        # The native menu is never opened, so it doesn't need the values
        super().__init__(master, values=[], command=None, **kwargs)

        self._picker_title = title
        self._search_placeholder = search_placeholder
        self._no_results_text = no_results_text
        self._picker_command = command
        self._search_terms = search_terms or {}
        self._set_picker_values(values)
        self._picker: _SearchPicker | None = None

    def configure(self, require_redraw: bool = False, **kwargs: Any) -> None:
        """Also takes the `search_terms` of the labels, like the constructor."""
        # The native menu is never opened, so the command is the picker's
        if "command" in kwargs:
            self._picker_command = kwargs.pop("command")
        if "search_terms" in kwargs:
            self._search_terms = kwargs.pop("search_terms") or {}
            self._set_picker_values(kwargs.pop("values", self._picker_values))
        elif "values" in kwargs:
            self._set_picker_values(kwargs.pop("values"))
        super().configure(require_redraw, **kwargs)

    def _set_picker_values(self, values: list[str]) -> None:
        # The picker keeps the values instead of the native menu
        self._picker_values = values
        self._search_index = {
            value: normalize_search_text(f"{value} {self._search_terms.get(value, '')}")
            for value in values
        }

    def _clicked(self, event: Any = None) -> None:
        # The parent only opens the dropdown when its own values aren't empty, but
        # they always are, since the picker keeps the values
        if self._state != tk.DISABLED and self._picker_values:
            self._open_dropdown_menu()

    def _open_dropdown_menu(self) -> None:
        if self._picker is not None and self._picker.winfo_exists():
            self._picker.focus_search()
            return

        self._picker = _SearchPicker(
            option_menu=self,
            values=self._picker_values,
            search_index=self._search_index,
            current=self.get(),
            title=self._picker_title(),
            search_placeholder=self._search_placeholder,
            no_results_text=self._no_results_text(),
            on_select=self._on_picker_select,
        )

    def _on_picker_select(self, value: str) -> None:
        self.set(value)
        if self._picker_command:
            self._picker_command(value)

    def destroy(self) -> None:
        if self._picker is not None and self._picker.winfo_exists():
            self._picker.destroy()
        super().destroy()


class _SearchPicker(ctk.CTkToplevel):  # type: ignore[misc]
    """
    Modal window with a search entry and the list of options. The arrow keys move
    through the filtered options, Enter selects one and Esc closes the window.

    It's a regular window instead of a borderless popup, since borderless windows
    don't receive the keyboard focus reliably on every platform.
    """

    def __init__(
        self,
        option_menu: ctk.CTkOptionMenu,
        values: list[str],
        search_index: dict[str, str],
        current: str,
        title: str,
        search_placeholder: Text,
        no_results_text: str,
        on_select: Callable[[str], None],
    ):
        super().__init__(master=option_menu.winfo_toplevel())

        self._option_menu = option_menu
        self._values = values
        self._search_index = search_index
        self._on_select = on_select
        self._filtered_values = values

        self.title(title)
        self.resizable(False, True)
        self.transient(option_menu.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._place_below(option_menu)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._search_variable = ctk.StringVar(self)
        self._search_variable.trace_add("write", lambda *_args: self._filter())

        self._ent_search = ctk.CTkEntry(
            master=self,
            textvariable=self._search_variable,
        )
        add_placeholder(self._ent_search, self._search_variable, search_placeholder)
        self._ent_search.grid(row=0, column=0, padx=10, pady=(10, 5), sticky=ctk.EW)

        self._init_listbox()

        self._lbl_no_results = ctk.CTkLabel(
            master=self,
            text=no_results_text,
            text_color=ctk.ThemeManager.theme["CTkEntry"]["placeholder_text_color"],
        )

        self._ent_search.bind("<Down>", lambda _event: self._move_selection(1))
        self._ent_search.bind("<Up>", lambda _event: self._move_selection(-1))
        self._ent_search.bind("<Next>", lambda _event: self._move_selection(10))
        self._ent_search.bind("<Prior>", lambda _event: self._move_selection(-10))
        self._ent_search.bind("<Return>", lambda _event: self._select_highlighted())
        self._ent_search.bind("<KP_Enter>", lambda _event: self._select_highlighted())
        self.bind("<Escape>", lambda _event: self._close())

        self._fill_listbox(current)

        # The window must be visible before grabbing the input
        self.after(50, self._grab)

    def focus_search(self) -> None:
        self.lift()
        self._ent_search.focus_set()

    def _init_listbox(self) -> None:
        frame = ctk.CTkFrame(master=self, border_width=2)
        frame.grid(row=1, column=0, padx=10, pady=(5, 10), sticky=ctk.NSEW)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        def color(widget: str, key: str) -> str:
            appearance_color: str = frame._apply_appearance_mode(
                ctk.ThemeManager.theme[widget][key]
            )
            return appearance_color

        self._listbox = tk.Listbox(
            master=frame,
            activestyle=tk.NONE,
            exportselection=False,
            borderwidth=0,
            highlightthickness=0,
            relief=tk.FLAT,
            font=ctk.CTkFont(size=13),
            background=color("CTkFrame", "top_fg_color"),
            foreground=color("CTkLabel", "text_color"),
            selectbackground=color("CTkOptionMenu", "fg_color"),
            selectforeground=color("CTkOptionMenu", "text_color"),
        )
        self._listbox.grid(row=0, column=0, padx=(6, 0), pady=6, sticky=ctk.NSEW)

        scrollbar = ctk.CTkScrollbar(master=frame, command=self._listbox.yview)
        scrollbar.grid(row=0, column=1, padx=(0, 3), pady=6, sticky=ctk.NS)
        self._listbox.configure(yscrollcommand=scrollbar.set)

        self._listbox.bind("<ButtonRelease-1>", self._on_listbox_click)
        self._listbox.bind("<Return>", lambda _event: self._select_highlighted())

    def _place_below(self, widget: tk.Misc) -> None:
        """
        Places the window below the widget, keeping it inside the screen.
        """
        width = max(PICKER_WIDTH, widget.winfo_width())
        x = min(widget.winfo_rootx(), self.winfo_screenwidth() - width)
        y = widget.winfo_rooty() + widget.winfo_height() + PICKER_OFFSET_Y
        y = max(0, min(y, self.winfo_screenheight() - PICKER_HEIGHT - 50))
        self.geometry(f"{width}x{PICKER_HEIGHT}+{max(0, x)}+{y}")

    def _grab(self) -> None:
        if not self.winfo_exists():
            return
        try:
            self.grab_set()
        except tk.TclError:
            # The window isn't viewable yet
            self.after(50, self._grab)
            return
        self.focus_force()
        self._ent_search.focus_set()

    def _fill_listbox(self, highlighted: str | None = None) -> None:
        self._listbox.delete(0, tk.END)
        self._listbox.insert(tk.END, *self._filtered_values)

        if self._filtered_values:
            self._lbl_no_results.place_forget()
            index = (
                self._filtered_values.index(highlighted)
                if highlighted in self._filtered_values
                else 0
            )
            self._highlight(index)
        else:
            self._lbl_no_results.place(relx=0.5, rely=0.5, anchor=ctk.CENTER)

    def _filter(self) -> None:
        query = normalize_search_text(self._search_variable.get().strip())
        self._filtered_values = [
            value for value in self._values if query in self._search_index[value]
        ]
        # The best matches are the ones that start with the query
        self._filtered_values.sort(
            key=lambda value: not normalize_search_text(value).startswith(query)
        )
        self._fill_listbox()

    def _highlight(self, index: int) -> None:
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(index)
        self._listbox.activate(index)
        self._listbox.see(index)

    def _move_selection(self, offset: int) -> str:
        if self._filtered_values:
            selection = self._listbox.curselection()  # type: ignore[no-untyped-call]
            current = selection[0] if selection else 0
            index = max(0, min(current + offset, len(self._filtered_values) - 1))
            self._highlight(index)
        # Prevents the entry from handling the key
        return "break"

    def _on_listbox_click(self, event: tk.Event) -> None:
        if not self._filtered_values:
            return
        index = self._listbox.nearest(event.y)  # type: ignore[no-untyped-call]
        bbox = self._listbox.bbox(index)
        # Clicks below the last option are ignored
        if bbox and event.y <= bbox[1] + bbox[3]:
            self._highlight(index)
            self._select_highlighted()

    def _select_highlighted(self) -> None:
        selection = self._listbox.curselection()  # type: ignore[no-untyped-call]
        if not selection:
            return
        value = self._filtered_values[selection[0]]
        self._close()
        self._on_select(value)

    def _close(self) -> None:
        self.grab_release()
        self.destroy()
        # Gives the focus back to the main window, so it responds to the next click
        # and keyboard shortcuts right away
        main_window = self._option_menu.winfo_toplevel()
        main_window.focus_force()
