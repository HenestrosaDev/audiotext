from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from handlers.openai_api_handler import API_MODELS, get_api_model
from models.config.config_transcription import ConfigTranscription
from models.config.config_whisper_api import ConfigWhisperApi
from models.config.config_whisperx import ConfigWhisperX
from models.transcription_settings import TranscriptionSettings
from utils.enums import ModelSize, TranscriptionMethod
from utils.env_keys import EnvKeys
from utils.i18n import _
from views.settings.cards.base import SettingsCard
from views.settings.option_labels import save_config
from views.style import theme
from views.widgets.option_menu import CTkOptionMenu


def describe_api_model(name: str) -> str:
    """What a model of the OpenAI API offers, to choose one."""
    model = get_api_model(name)

    if model.has_speakers:
        return _("Identifies the speakers. With timestamps.")
    if model.has_timestamps:
        return _(
            "With timestamps, to play the transcription segment by segment and "
            "generate subtitles."
        )
    return _(
        "More accurate, but without timestamps: the transcription can't be played "
        "segment by segment nor subtitled."
    )


class EngineCard(SettingsCard):
    """The transcription method and its model."""

    def __init__(
        self,
        master: Any,
        on_change: Callable[[], None],
        on_set_api_key: Callable[[EnvKeys, str], None],
        on_model_change: Callable[[], None],
        config_transcription: ConfigTranscription,
        config_whisperx: ConfigWhisperX,
        config_whisper_api: ConfigWhisperApi,
    ) -> None:
        super().__init__(master, lambda: _("Engine"), on_change)
        self._on_set_api_key = on_set_api_key
        self._on_model_change = on_model_change

        self._field_label(2, lambda: _("Transcription method"))
        self.seg_method = ctk.CTkSegmentedButton(
            self,
            values=[method.value for method in TranscriptionMethod],
            command=self._on_method_change,
        )
        self.seg_method.grid(row=3, column=0, columnspan=2, padx=18, sticky=ctk.EW)
        self.seg_method.set(config_transcription.method)
        self.interactive_widgets.append(self.seg_method)
        self.lbl_method_hint = self._hint(4)

        # The model of WhisperX or of the OpenAI API, in the same place
        self.lbl_model = self._field_label(5, lambda: _("Model"))
        self.omn_model_size = CTkOptionMenu(
            self,
            values=[size.value for size in ModelSize],
            command=self._on_model_size_change,
            dynamic_resizing=False,
        )
        self.omn_model_size.set(config_whisperx.model_size)
        self.omn_model_size.grid(row=6, column=0, columnspan=2, padx=18, sticky=ctk.EW)

        self.omn_api_model = CTkOptionMenu(
            self,
            values=list(API_MODELS),
            command=self._on_api_model_change,
            dynamic_resizing=False,
        )
        self.omn_api_model.set(config_whisper_api.model)
        self.omn_api_model.grid(row=6, column=0, columnspan=2, padx=18, sticky=ctk.EW)
        self.interactive_widgets.extend([self.omn_model_size, self.omn_api_model])
        self.lbl_model_hint = self._hint(7)

        self.btn_api_key = ctk.CTkButton(
            self, command=self._on_api_key_click, **theme.SECONDARY_BUTTON
        )
        self.btn_api_key.grid(
            row=8, column=0, columnspan=2, padx=18, pady=(10, 0), sticky=ctk.W
        )
        self._spacer(9)

    def update_settings(self, settings: TranscriptionSettings) -> None:
        settings.method = self.seg_method.get()
        settings.model_size = self.omn_model_size.get()
        settings.openai_model = self.omn_api_model.get()

    def refresh(self, settings: TranscriptionSettings) -> None:
        method = settings.transcription_method
        is_whisperx = method == TranscriptionMethod.WHISPERX
        is_api = method == TranscriptionMethod.WHISPER_API

        has_model = is_whisperx or is_api
        for widget in (self.lbl_model, self.lbl_model_hint):
            widget.grid() if has_model else widget.grid_remove()
        self.omn_model_size.grid() if is_whisperx else self.omn_model_size.grid_remove()
        self.omn_api_model.grid() if is_api else self.omn_api_model.grid_remove()

        if is_whisperx:
            if ModelSize.is_english_only_model(settings.model_size):
                model_hint = _(
                    "Only transcribes English, faster than the multilingual model "
                    "of the same size."
                )
            else:
                model_hint = _("Larger models are more accurate, but slower.")
            self.lbl_model_hint.configure(text=model_hint)
            self.lbl_method_hint.configure(
                text=_("Runs on your computer. Free, private and unlimited.")
            )
            self.btn_api_key.grid_remove()
            return

        if is_api:
            env_key = EnvKeys.OPENAI_API_KEY
            self.lbl_model_hint.configure(
                text=describe_api_model(settings.openai_model)
            )
            method_hint = _("Runs on the servers of OpenAI. Requires an API key.")
        else:
            env_key = EnvKeys.GOOGLE_API_KEY
            method_hint = _(
                "Runs on the servers of Google. An API key is optional; without "
                "it, the free tier is used."
            )
        has_key = bool(env_key.get_value(default=""))
        self.btn_api_key.configure(
            text=("✓ " + _("API key set")) if has_key else _("Set API key…")
        )
        self.btn_api_key.grid()
        self.lbl_method_hint.configure(text=method_hint)

    # EVENT HANDLERS

    def _on_method_change(self, method: str) -> None:
        save_config(ConfigTranscription.Key.METHOD, method)
        self._on_change()
        self._on_model_change()

    def _on_model_size_change(self, model_size: str) -> None:
        save_config(ConfigWhisperX.Key.MODEL_SIZE, model_size)
        self._on_change()
        self._on_model_change()

    def _on_api_model_change(self, model: str) -> None:
        save_config(ConfigWhisperApi.Key.MODEL, model)
        self._on_change()

    def _on_api_key_click(self) -> None:
        if self.seg_method.get() == TranscriptionMethod.WHISPER_API.value:
            self._on_set_api_key(EnvKeys.OPENAI_API_KEY, _("OpenAI API key"))
        else:
            self._on_set_api_key(EnvKeys.GOOGLE_API_KEY, _("Google API key"))
