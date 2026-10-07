import tkinter as tk
import unicodedata
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from views.localization import Text
from views.style import theme
from views.widgets.option_menu import CTkOptionMenu
from views.widgets.placeholder import add_placeholder

DROPDOWN_WIDTH = 300
DROPDOWN_HEIGHT = 380
# Space between the option menu and the dropdown
DROPDOWN_OFFSET_Y = 4
# Space between the dropdown and the edges of the window
DROPDOWN_MARGIN = 8


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
    Option menu that opens a dropdown with a search entry instead of the native
    menu, which is cumbersome with many values.
    """

    def __init__(
        self,
        master: Any,
        values: list[str],
        search_placeholder: Text,
        no_results_text: Text,
        command: Callable[[str], None] | None = None,
        search_terms: dict[str, str] | None = None,
        **kwargs: Any,
    ):
        """
        :param values: The labels of the options.
        :param search_placeholder: The placeholder of the search entry.
        :param no_results_text: The text shown when no option matches the search.
        :param command: Called with the selected label.
        :param search_terms: Extra text matched by the search for each label (e.g.
                             the English name of a language).
        """
        # The native menu is never opened, so it doesn't need the values
        super().__init__(master, values=[], command=None, **kwargs)

        self._search_placeholder = search_placeholder
        self._no_results_text = no_results_text
        self._dropdown_command = command
        self._search_terms = search_terms or {}
        self._set_dropdown_values(values)
        self._dropdown: _SearchDropdown | None = None

    def configure(self, require_redraw: bool = False, **kwargs: Any) -> None:
        """Also takes the `search_terms` of the labels, like the constructor."""
        # The native menu is never opened, so the command is the dropdown's
        if "command" in kwargs:
            self._dropdown_command = kwargs.pop("command")
        if "search_terms" in kwargs:
            self._search_terms = kwargs.pop("search_terms") or {}
            self._set_dropdown_values(kwargs.pop("values", self._dropdown_values))
        elif "values" in kwargs:
            self._set_dropdown_values(kwargs.pop("values"))
        super().configure(require_redraw, **kwargs)

    def _set_dropdown_values(self, values: list[str]) -> None:
        # The dropdown keeps the values instead of the native menu
        self._dropdown_values = values
        self._search_index = {
            value: normalize_search_text(f"{value} {self._search_terms.get(value, '')}")
            for value in values
        }

    def _clicked(self, event: Any = None) -> None:
        # The parent only opens the dropdown when its own values aren't empty, but
        # they always are, since the dropdown keeps the values
        if self._state != tk.DISABLED and self._dropdown_values:
            self._open_dropdown_menu()

    def _open_dropdown_menu(self) -> None:
        # Clicking the option menu again closes the dropdown
        if self._dropdown is not None and self._dropdown.winfo_exists():
            self._dropdown.close()
            return

        self._dropdown = _SearchDropdown(
            option_menu=self,
            values=self._dropdown_values,
            search_index=self._search_index,
            current=self.get(),
            search_placeholder=self._search_placeholder,
            no_results_text=self._no_results_text(),
            on_select=self._on_dropdown_select,
        )

    def _on_dropdown_select(self, value: str) -> None:
        self.set(value)
        if self._dropdown_command:
            self._dropdown_command(value)

    def destroy(self) -> None:
        if self._dropdown is not None and self._dropdown.winfo_exists():
            self._dropdown.destroy()
        super().destroy()


class _SearchDropdown(ctk.CTkFrame):  # type: ignore[misc]
    """
    Dropdown with a search entry and the list of options, shown over the window of
    the option menu, below it or above it, wherever there is more space. The arrow
    keys move through the filtered options, Enter selects one, and Esc or a click
    outside closes it.
    """

    def __init__(
        self,
        option_menu: CTkSearchableOptionMenu,
        values: list[str],
        search_index: dict[str, str],
        current: str,
        search_placeholder: Text,
        no_results_text: str,
        on_select: Callable[[str], None],
    ):
        window = option_menu.winfo_toplevel()
        super().__init__(
            master=window,
            fg_color=theme.CARD_BG,
            border_color=theme.CARD_BORDER,
            border_width=1,
            corner_radius=8,
        )

        self._option_menu = option_menu
        self._window = window
        self._values = values
        self._search_index = search_index
        self._on_select = on_select
        self._filtered_values = values

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._search_variable = ctk.StringVar(self)
        self._search_variable.trace_add("write", lambda *_args: self._filter())

        self._ent_search = ctk.CTkEntry(
            master=self,
            textvariable=self._search_variable,
        )
        add_placeholder(self._ent_search, self._search_variable, search_placeholder)
        self._ent_search.grid(row=0, column=0, padx=8, pady=(8, 4), sticky=ctk.EW)

        self._init_listbox()

        self._lbl_no_results = ctk.CTkLabel(
            master=self,
            text=no_results_text,
            text_color=theme.HINT_TEXT,
        )

        for widget in (self._ent_search, self._listbox):
            widget.bind("<Escape>", lambda _event: self._close_and_refocus())
        self._ent_search.bind("<Down>", lambda _event: self._move_selection(1))
        self._ent_search.bind("<Up>", lambda _event: self._move_selection(-1))
        self._ent_search.bind("<Next>", lambda _event: self._move_selection(10))
        self._ent_search.bind("<Prior>", lambda _event: self._move_selection(-10))
        self._ent_search.bind("<Return>", lambda _event: self._select_highlighted())
        self._ent_search.bind("<KP_Enter>", lambda _event: self._select_highlighted())

        _watch_window(window, self)
        self._place()
        self._fill_listbox(current)
        self._ent_search.focus_set()

    def close(self) -> None:
        if self.winfo_exists():
            self.destroy()

    def on_window_event(self, event: tk.Event) -> None:
        """
        Closes the dropdown when the window is resized, or when the user clicks or
        scrolls outside of it, since it doesn't follow the option menu.
        """
        if event.type == tk.EventType.Configure:
            if event.widget is self._window:
                self.close()
        elif not self._contains(event.widget, self) and not (
            event.type == tk.EventType.ButtonPress
            and self._contains(event.widget, self._option_menu)
        ):
            # The clicks on the option menu close it on their own
            self.close()

    @staticmethod
    def _contains(widget: Any, container: tk.Misc) -> bool:
        path = str(widget)
        return path == str(container) or path.startswith(f"{container}.")

    def _place(self) -> None:
        """
        Places the dropdown below the option menu, or above it if there is more
        space, keeping it inside the window. The sizes are in pixels of the screen,
        so they're placed without the scaling of CustomTkinter.
        """
        scaling = self._get_widget_scaling()
        menu = self._option_menu
        margin = round(DROPDOWN_MARGIN * scaling)
        offset = round(DROPDOWN_OFFSET_Y * scaling)
        window_width, window_height = (
            self._window.winfo_width(),
            self._window.winfo_height(),
        )

        width = min(
            max(round(DROPDOWN_WIDTH * scaling), menu.winfo_width()),
            window_width - 2 * margin,
        )
        x = menu.winfo_rootx() - self._window.winfo_rootx()
        x = max(margin, min(x, window_width - width - margin))

        top = menu.winfo_rooty() - self._window.winfo_rooty()
        bottom = top + menu.winfo_height()
        space_below = window_height - bottom - offset - margin
        space_above = top - offset - margin
        max_height = round(DROPDOWN_HEIGHT * scaling)

        if space_below >= min(max_height, space_above):
            height = min(max_height, space_below)
            y = bottom + offset
        else:
            height = min(max_height, space_above)
            y = top - offset - height

        tk.Frame.place(self, x=x, y=y, width=width, height=height)
        self.lift()

    def _init_listbox(self) -> None:
        frame = ctk.CTkFrame(master=self, fg_color="transparent")
        frame.grid(row=1, column=0, padx=(8, 4), pady=(4, 8), sticky=ctk.NSEW)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        def color(value: theme.ColorPair) -> str:
            appearance_color: str = frame._apply_appearance_mode(value)
            return appearance_color

        self._listbox = tk.Listbox(
            master=frame,
            activestyle=tk.NONE,
            exportselection=False,
            borderwidth=0,
            highlightthickness=0,
            relief=tk.FLAT,
            font=ctk.CTkFont(size=13),
            background=color(theme.CARD_BG),
            foreground=color(theme.TEXT),
            selectbackground=color(theme.ACCENT),
            selectforeground=color(theme.ICON_ON_ACCENT),
        )
        self._listbox.grid(row=0, column=0, sticky=ctk.NSEW)

        scrollbar = ctk.CTkScrollbar(master=frame, command=self._listbox.yview)
        scrollbar.grid(row=0, column=1, padx=(2, 0), sticky=ctk.NS)
        self._listbox.configure(yscrollcommand=scrollbar.set)

        self._listbox.bind("<ButtonRelease-1>", self._on_listbox_click)
        self._listbox.bind("<Return>", lambda _event: self._select_highlighted())

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
        self._close_and_refocus()
        self._on_select(value)

    def _close_and_refocus(self) -> str:
        self.close()
        # The keyboard keeps working from the option menu
        self._option_menu.focus_set()
        return "break"


# The events of a window that close its open dropdown
_WINDOW_EVENTS = ("<Button>", "<MouseWheel>", "<Configure>")


def _watch_window(window: tk.Misc, dropdown: _SearchDropdown) -> None:
    """
    Sends the events of the window to its open dropdown. The window is only bound
    once, since unbinding one function of an event removes the other functions of
    the window bound to it too.
    """
    if getattr(window, "_search_dropdown", None) is None:
        for sequence in _WINDOW_EVENTS:
            window.bind(sequence, lambda event: _send_event(window, event), add="+")
    window._search_dropdown = dropdown  # type: ignore[attr-defined]


def _send_event(window: tk.Misc, event: tk.Event) -> None:
    dropdown = window._search_dropdown  # type: ignore[attr-defined]
    if dropdown.winfo_exists():
        dropdown.on_window_event(event)
