from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from models.config.config_whisperx import ConfigWhisperX
from models.transcription_settings import TranscriptionSettings
from utils.enums import TranscriptionMethod
from utils.i18n import L_, _
from views.settings.cards.base import SettingsCard
from views.settings.option_labels import save_config
from views.widgets.option_menu import CTkOptionMenu

# Models fast enough to transcribe while recording, from the fastest
LIVE_MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3-turbo"]


class LiveCard(SettingsCard):
    """Whether to show the text while recording from the microphone."""

    def __init__(
        self,
        master: Any,
        on_change: Callable[[], None],
        config_whisperx: ConfigWhisperX,
    ) -> None:
        super().__init__(master, L_("Live text"), on_change)
        self.swi_live = self._switch(
            2,
            L_("Show the text while recording"),
            config_whisperx.live_transcription,
            ConfigWhisperX.Key.LIVE_TRANSCRIPTION,
        )

        self.lbl_live_model = self._field_label(3, L_("Live model"))
        self.omn_live_model = CTkOptionMenu(
            self,
            values=LIVE_MODEL_SIZES,
            command=lambda value: save_config(
                ConfigWhisperX.Key.LIVE_MODEL_SIZE, value
            ),
            dynamic_resizing=False,
        )
        self.omn_live_model.set(config_whisperx.live_model_size)
        self.omn_live_model.grid(row=4, column=0, columnspan=2, padx=18, sticky=ctk.EW)
        self.interactive_widgets.append(self.omn_live_model)
        self.lbl_live_hint = self._hint(5, pady=(4, 16))

    def update_settings(self, settings: TranscriptionSettings) -> None:
        settings.live_transcription = bool(self.swi_live.get())
        settings.live_model_size = self.omn_live_model.get()

    def refresh(self, settings: TranscriptionSettings) -> None:
        is_whisperx = settings.transcription_method == TranscriptionMethod.WHISPERX
        self.swi_live.configure(state=ctk.NORMAL if is_whisperx else ctk.DISABLED)

        is_live = is_whisperx and settings.live_transcription
        for widget in (self.lbl_live_model, self.omn_live_model):
            widget.grid() if is_live else widget.grid_remove()

        if not is_whisperx:
            hint = _("Only available with WhisperX.")
        elif is_live:
            hint = _(
                "A fast model writes a draft while you speak. When you stop, the "
                "whole recording is transcribed again with the model of the engine, "
                "which is more accurate."
            )
        else:
            hint = _("The text is shown when you stop recording.")
        self.lbl_live_hint.configure(text=hint)
