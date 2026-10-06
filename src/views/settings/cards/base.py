from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from models.transcription_settings import TranscriptionSettings
from utils.config_manager import ConfigManager
from views.localization import Text, localize
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
        title: Text,
        on_change: Callable[[], None],
        subtitle: Text | None = None,
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

        localize(
            ctk.CTkLabel(self, font=theme.font(15, "bold"), anchor=ctk.W), text=title
        ).grid(row=0, column=0, columnspan=2, padx=18, pady=(16, 0), sticky=ctk.W)
        if subtitle:
            localize(
                ctk.CTkLabel(
                    self,
                    font=theme.font(12),
                    text_color=theme.HINT_TEXT,
                    anchor=ctk.W,
                    justify=ctk.LEFT,
                ),
                text=subtitle,
            ).grid(row=1, column=0, columnspan=2, padx=18, sticky=ctk.W)

    def update_settings(self, settings: TranscriptionSettings) -> None:
        """Sets the options of the card in the settings."""

    def refresh(self, settings: TranscriptionSettings) -> None:
        """
        Shows the options that apply to the settings. It's also called when the
        interface language changes, to show the texts that depend on them.
        """

    # HELPERS

    def _field_label(self, row: int, text: Text, master: Any = None) -> ctk.CTkLabel:
        label = localize(
            ctk.CTkLabel(master or self, font=theme.font(13), anchor=ctk.W), text=text
        )
        label.grid(row=row, column=0, columnspan=2, padx=18, pady=(12, 2), sticky=ctk.W)
        return label

    def _hint(
        self, row: int, text: Text | None = None, pady: Any = (2, 0), master: Any = None
    ) -> ctk.CTkLabel:
        """:param text: The hint, or None if it's set when the card is refreshed."""
        label = ctk.CTkLabel(
            master or self,
            text="",
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
            justify=ctk.LEFT,
        )
        if text:
            localize(label, text=text)
        label.grid(row=row, column=0, columnspan=2, padx=18, pady=pady, sticky=ctk.EW)
        bind_wraplength(label, minimum=120)
        return label

    def _switch(
        self, row: int, text: Text, is_on: bool, key: ConfigManager.KeyType
    ) -> ctk.CTkSwitch:
        """A switch whose state is stored in the configuration."""
        switch = localize(ctk.CTkSwitch(self, font=theme.font(13)), text=text)

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
