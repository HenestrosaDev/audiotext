from collections.abc import Callable
from typing import Any

import customtkinter as ctk
from customtkinter.windows.widgets import ctk_textbox

from views.widgets.option_menu import CTkScrollbar

# The textbox creates its scrollbars in its constructor, so they're replaced in
# its module. Otherwise, each textbox laid out the whole window when created,
# which froze it for half a second when opening the microphone view
ctk_textbox.CTkScrollbar = CTkScrollbar


class CTkTextbox(ctk.CTkTextbox):  # type: ignore[misc]
    """
    Textbox that stops checking its scrollbars when it's destroyed.

    CustomTkinter checks whether the scrollbars are needed every 100 ms with
    `after`, but doesn't cancel it when the textbox is destroyed. Tkinter deletes
    the callback, but the timer of Tcl still calls it by its name, which a new
    callback may have taken in the meantime (its name comes from its memory
    address): that callback would be called at the wrong time, without arguments.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._scrollbar_check_id: str | None = None
        super().__init__(*args, **kwargs)

    def _check_if_scrollbars_needed(
        self, event: Any = None, continue_loop: bool = False
    ) -> None:
        super()._check_if_scrollbars_needed(event, continue_loop=False)

        if continue_loop and self._textbox.winfo_exists():
            self._scrollbar_check_id = self.after(
                self._scrollbar_update_time,
                self._check_if_scrollbars_needed,
                None,
                True,
            )

    def destroy(self) -> None:
        if self._scrollbar_check_id:
            self.after_cancel(self._scrollbar_check_id)
            self._scrollbar_check_id = None
        super().destroy()


class CTkPlaceholderTextbox(CTkTextbox):
    """
    Textbox styled like `CTkEntry`, which shows a placeholder while it's empty and
    doesn't have the focus.
    """

    PLACEHOLDER_TAG = "placeholder"

    def __init__(
        self,
        *args: Any,
        placeholder_text: str = "",
        on_change: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        :param placeholder_text: The text shown while it's empty.
        :param on_change: Called when the user changes the text.
        """
        entry_theme = ctk.ThemeManager.theme["CTkEntry"]
        kwargs = {
            "fg_color": entry_theme["fg_color"],
            "border_color": entry_theme["border_color"],
            "border_width": entry_theme["border_width"],
            "text_color": entry_theme["text_color"],
            "wrap": ctk.WORD,
        } | kwargs
        super().__init__(*args, **kwargs)
        self._placeholder_text = placeholder_text
        self._placeholder_text_color = entry_theme["placeholder_text_color"]
        self._on_change = on_change
        self._is_placeholder_shown = False

        self._update_placeholder_color()
        self.bind("<FocusIn>", lambda _event: self._hide_placeholder())
        self.bind("<FocusOut>", lambda _event: self._show_placeholder())
        self.bind("<<Modified>>", lambda _event: self._on_modified())
        self._show_placeholder()

    def get_text(self) -> str:
        """:return: The text typed by the user, without the placeholder."""
        if self._is_placeholder_shown:
            return ""

        return str(self.get("1.0", "end-1c"))

    def _draw(self, no_color_updates: bool = False) -> None:
        super()._draw(no_color_updates)
        # Also called on appearance mode changes, before the attribute exists
        if hasattr(self, "_placeholder_text_color"):
            self._update_placeholder_color()

    def _update_placeholder_color(self) -> None:
        self.tag_config(
            self.PLACEHOLDER_TAG,
            foreground=self._apply_appearance_mode(self._placeholder_text_color),
        )

    def _show_placeholder(self) -> None:
        if (
            self._is_placeholder_shown
            or not self._placeholder_text
            or self.get("1.0", "end-1c")
            or self._textbox.cget("state") == ctk.DISABLED
        ):
            return

        self._is_placeholder_shown = True
        self.insert("1.0", self._placeholder_text, self.PLACEHOLDER_TAG)
        self.edit_modified(False)

    def _hide_placeholder(self) -> None:
        if (
            not self._is_placeholder_shown
            or self._textbox.cget("state") == ctk.DISABLED
        ):
            return

        self.delete("1.0", ctk.END)
        self._is_placeholder_shown = False
        self.edit_modified(False)

    def _on_modified(self) -> None:
        if not self.edit_modified():
            return

        self.edit_modified(False)
        if not self._is_placeholder_shown and self._on_change:
            self._on_change()
