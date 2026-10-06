from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from utils.enums import AudioSource
from utils.i18n import _
from views.localization import Text, localize
from views.style import icons, theme


class WelcomeView(ctk.CTkFrame):  # type: ignore[misc]
    """The first page: a card for each kind of source to transcribe."""

    def __init__(self, master: Any, on_source: Callable[[AudioSource], None]) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure((0, 4), weight=1)

        ctk.CTkLabel(self, text="", image=icons.app_logo(64, theme.ACCENT_TEXT)).grid(
            row=1, column=0
        )
        localize(
            ctk.CTkLabel(self, font=theme.font(24, "bold")),
            text=lambda: _("What do you want to transcribe?"),
        ).grid(row=2, column=0, pady=(12, 4))
        localize(
            ctk.CTkLabel(self, font=theme.font(14), text_color=theme.HINT_TEXT),
            text=lambda: _(
                "Choose a source, or select a transcription of your history to read and play it."
            ),
        ).grid(row=3, column=0)

        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.grid(row=4, column=0, pady=(30, 0), sticky=ctk.N)
        sources: list[tuple[AudioSource, str, Text, Text]] = [
            (
                AudioSource.FILE,
                "file",
                lambda: _("File"),
                lambda: _("An audio or video file"),
            ),
            (
                AudioSource.YOUTUBE,
                "link",
                lambda: _("URL"),
                lambda: _("YouTube or a link to a file"),
            ),
            (
                AudioSource.MIC,
                "mic",
                lambda: _("Microphone"),
                lambda: _("Record and transcribe"),
            ),
            (
                AudioSource.DIRECTORY,
                "folder",
                lambda: _("Folder"),
                lambda: _("Many files at once, or watch it"),
            ),
        ]
        for idx, (source, icon_name, title, description) in enumerate(sources):
            card = self._source_card(cards, icon_name, title, description)
            card.grid(row=0, column=idx, padx=8)

            def on_click(_event: Any, source: AudioSource = source) -> None:
                on_source(source)

            for widget in (card, *card.winfo_children()):
                widget.bind("<Button-1>", on_click)

        localize(
            ctk.CTkLabel(self, font=theme.font(12), text_color=theme.HINT_TEXT),
            text=lambda: _(
                "Tip: drop a file or a folder anywhere on the window to transcribe it."
            ),
        ).grid(row=5, column=0, pady=(24, 30))

    @staticmethod
    def _source_card(
        master: Any, icon_name: str, title: Text, description: Text
    ) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            master,
            width=170,
            height=150,
            fg_color=theme.CARD_BG,
            border_color=theme.CARD_BORDER,
            border_width=1,
            corner_radius=14,
            cursor="hand2",
        )
        card.grid_propagate(False)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card,
            text="",
            image=icons.icon(icon_name, 22, theme.ICON_ON_ACCENT),
            width=42,
            height=42,
            corner_radius=10,
            fg_color=theme.ACCENT,
        ).grid(row=0, column=0, pady=(22, 10))
        localize(ctk.CTkLabel(card, font=theme.font(15, "bold")), text=title).grid(
            row=1, column=0
        )
        localize(
            ctk.CTkLabel(
                card, font=theme.font(12), text_color=theme.HINT_TEXT, wraplength=150
            ),
            text=description,
        ).grid(row=2, column=0, padx=8)
        return card
