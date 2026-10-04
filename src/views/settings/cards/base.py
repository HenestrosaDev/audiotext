from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from models.transcription_settings import TranscriptionSettings
from utils.config_manager import ConfigManager
from views.settings.option_labels import save_config
from views.style import theme
from views.widgets.bindings import bind_wraplength


class SettingsCard(ctk.CTkFrame):  # type: ignore[misc]
    """
    A group of options of the settings form. Each card sets its options in the
    settings of the transcription, and shows the ones that apply to the choices
    of the rest of the form when it's refreshed.
    """

    def __init__(
        self,
        master: Any,
        title: str,
        on_change: Callable[[], None],
        subtitle: str = "",
    ) -> None:
        """:param on_change: Called when an option changes, to refresh the form."""
        super().__init__(
            master,
            fg_color=theme.CARD_BG,
            border_color=theme.CARD_BORDER,
            border_width=1,
            corner_radius=12,
        )
        self._on_change = on_change
        # The widgets disabled while the form is disabled (e.g. while recording)
        self.interactive_widgets: list[Any] = []
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text=title, font=theme.font(15, "bold"), anchor=ctk.W).grid(
            row=0, column=0, columnspan=2, padx=18, pady=(16, 0), sticky=ctk.W
        )
        if subtitle:
            ctk.CTkLabel(
                self,
                text=subtitle,
                font=theme.font(12),
                text_color=theme.HINT_TEXT,
                anchor=ctk.W,
                justify=ctk.LEFT,
            ).grid(row=1, column=0, columnspan=2, padx=18, sticky=ctk.W)

    def update_settings(self, settings: TranscriptionSettings) -> None:
        """Sets the options of the card in the settings."""

    def refresh(self, settings: TranscriptionSettings) -> None:
        """Shows the options that apply to the settings."""

    # HELPERS

    def _field_label(self, row: int, text: str, master: Any = None) -> ctk.CTkLabel:
        label = ctk.CTkLabel(
            master or self, text=text, font=theme.font(13), anchor=ctk.W
        )
        label.grid(row=row, column=0, columnspan=2, padx=18, pady=(12, 2), sticky=ctk.W)
        return label

    def _hint(
        self, row: int, text: str = "", pady: Any = (2, 0), master: Any = None
    ) -> ctk.CTkLabel:
        label = ctk.CTkLabel(
            master or self,
            text=text,
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
            justify=ctk.LEFT,
        )
        label.grid(row=row, column=0, columnspan=2, padx=18, pady=pady, sticky=ctk.EW)
        bind_wraplength(label, minimum=120)
        return label

    def _switch(
        self, row: int, text: str, is_on: bool, key: ConfigManager.KeyType
    ) -> ctk.CTkSwitch:
        """A switch whose state is stored in the configuration."""
        switch = ctk.CTkSwitch(self, text=text, font=theme.font(13))

        def on_toggle() -> None:
            save_config(key, str(bool(switch.get())))
            self._on_change()

        switch.configure(command=on_toggle)
        switch.grid(
            row=row, column=0, columnspan=2, padx=18, pady=(14, 0), sticky=ctk.W
        )
        if is_on:
            switch.select()
        self.interactive_widgets.append(switch)
        return switch

    def _spacer(self, row: int) -> None:
        ctk.CTkFrame(self, fg_color="transparent", height=16).grid(row=row, column=0)
