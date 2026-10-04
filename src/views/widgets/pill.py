from typing import Any

import customtkinter as ctk

from views.style import theme


class Pill(ctk.CTkLabel):  # type: ignore[misc]
    """A small rounded label, used for the tags."""

    def __init__(self, master: Any, text: str = "", **kwargs: Any) -> None:
        super().__init__(
            master,
            text=text,
            height=18,
            corner_radius=9,
            font=theme.font(11),
            padx=7,
            **kwargs,
        )

    def set_tag(self, tag: str, placeholder: str = "") -> None:
        """Shows a tag with its colors, or the placeholder with neutral colors."""
        background, text_color = theme.tag_colors(tag)
        self.configure(
            text=tag or placeholder, fg_color=background, text_color=text_color
        )
