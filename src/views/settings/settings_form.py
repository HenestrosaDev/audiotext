from collections.abc import Callable
from enum import Enum
from typing import Any

import customtkinter as ctk

import utils.constants as c
from models.config.config_transcription import ConfigTranscription
from models.config.config_whisper_api import ConfigWhisperApi
from models.config.config_whisperx import ConfigWhisperX
from models.transcription_settings import TranscriptionSettings
from utils.config_manager import ConfigManager
from utils.enums import ModelSize, TranscriptionMethod
from utils.env_keys import EnvKeys
from utils.i18n import _
from views.settings.cards.base import SettingsCard
from views.settings.cards.context_card import ContextCard
from views.settings.cards.engine_card import EngineCard
from views.settings.cards.folder_card import FolderCard
from views.settings.cards.language_card import LanguageCard
from views.settings.cards.live_card import LiveCard
from views.settings.cards.options_card import OptionsCard
from views.settings.cards.output_card import OutputCard
from views.settings.option_labels import save_config
from views.widgets.option_menu import skip_scrollbar_forced_layout

SUBTITLE_FILE_TYPES = {"srt", "vtt"}


class FormMode(Enum):
    FILE = "file"
    URL = "url"
    FOLDER = "folder"
    MIC = "mic"


class SettingsForm(ctk.CTkScrollableFrame):  # type: ignore[misc]
    """
    The options to transcribe an audio source, grouped in cards. The choices are
    stored in the configuration, so they're the defaults of the next
    transcription.
    """

    def __init__(
        self,
        master: Any,
        mode: FormMode,
        on_set_api_key: Callable[[EnvKeys, str], None],
        on_model_change: Callable[[], None],
        columns: int = 2,
        on_change: Callable[[], None] | None = None,
        initial: TranscriptionSettings | None = None,
        **kwargs: Any,
    ) -> None:
        """
        :param on_change: Called when the options shown change, e.g. the method.
        :param initial: The settings to start from (e.g. those of a transcription
                        that failed), instead of the configured ones.
        """
        super().__init__(master, fg_color="transparent", **kwargs)
        skip_scrollbar_forced_layout(self)

        self._mode = mode
        self._on_set_api_key = on_set_api_key
        self._on_model_change = on_model_change
        self._on_change = on_change
        # Only the files of a folder are saved. The rest are kept in the history,
        # from where they can be exported in any format
        self._has_output = mode == FormMode.FOLDER
        self._initial_output_dir = initial.output_dir if initial else ""
        if initial:
            self._store_settings(initial)

        self._config_transcription = ConfigManager.get_config_transcription()
        self._config_whisperx = ConfigManager.get_config_whisperx()
        self._config_whisper_api = ConfigManager.get_config_whisper_api()

        for column in range(columns):
            self.grid_columnconfigure(column, weight=1, uniform="settings")

        self._cards = self._create_cards()

        # Cards are placed in columns, filling each row
        for idx, card in enumerate(self._cards):
            card.grid(
                row=idx // columns,
                column=idx % columns,
                padx=(
                    0 if idx % columns == 0 else 8,
                    0 if idx % columns == columns - 1 else 8,
                ),
                pady=(0, 16),
                sticky=ctk.NSEW,
            )

        self._refresh()

    def _create_cards(self) -> list[SettingsCard]:
        refresh = self._refresh
        config_transcription = self._config_transcription
        config_whisperx = self._config_whisperx

        cards: list[SettingsCard] = [
            EngineCard(
                self,
                refresh,
                on_set_api_key=self._on_set_api_key,
                on_model_change=self._on_model_change,
                config_transcription=config_transcription,
                config_whisperx=config_whisperx,
                config_whisper_api=self._config_whisper_api,
            ),
            LanguageCard(self, refresh, config_transcription),
            ContextCard(self, refresh, config_transcription),
            OptionsCard(
                self,
                refresh,
                on_set_api_key=self._on_set_api_key,
                has_subtitles=self._has_subtitles,
                config_transcription=config_transcription,
                config_whisperx=config_whisperx,
            ),
        ]
        if self._has_output:
            cards.append(
                OutputCard(
                    self,
                    refresh,
                    config_transcription,
                    config_whisperx,
                    self._config_whisper_api,
                    output_dir=self._initial_output_dir,
                )
            )
            # Last, so the other cards keep the same order as in other modes
            cards.append(FolderCard(self, refresh, config_transcription))
        if self._mode == FormMode.MIC:
            cards.insert(1, LiveCard(self, refresh, config_whisperx))

        return cards

    # PUBLIC METHODS

    def get_settings(self) -> TranscriptionSettings:
        # The options without a card take the configured values
        settings = TranscriptionSettings(
            output_file_types=list(self._config_whisperx.output_file_types),
            response_format=self._config_whisper_api.response_format,
            live_model_size=self._config_whisperx.live_model_size,
            autosave=self._has_output,
        )
        for card in self._cards:
            card.update_settings(settings)

        return settings

    def validate(self) -> str | None:
        """:return: The error that prevents transcribing, if any."""
        settings = self.get_settings()

        if self._has_output and not settings.effective_output_file_types:
            return _("Select at least one output file type.")

        if (
            settings.transcription_method == TranscriptionMethod.GOOGLE_API
            and settings.input_language == c.AUTO_DETECT_LANGUAGE
        ):
            return _(
                "The Google API can't detect the language. Please select the "
                "language of the audio."
            )

        if (
            settings.transcription_method == TranscriptionMethod.WHISPERX
            and ModelSize.is_english_only_model(settings.model_size)
            and settings.input_language not in (c.AUTO_DETECT_LANGUAGE, "en")
        ):
            return _(
                "The {model} model only transcribes English. Choose a multilingual "
                "model or set the language of the audio to English."
            ).format(model=settings.model_size)

        if (
            settings.transcription_method == TranscriptionMethod.WHISPER_API
            and not EnvKeys.OPENAI_API_KEY.get_value(default="")
        ):
            return _("The Whisper API requires an OpenAI API key.")

        return None

    def set_enabled(self, is_enabled: bool) -> None:
        state = ctk.NORMAL if is_enabled else ctk.DISABLED
        for card in self._cards:
            for widget in card.interactive_widgets:
                widget.configure(state=state)
        if is_enabled:
            self._refresh()

    def refresh_api_keys(self) -> None:
        self._refresh()

    # HELPERS

    def _store_settings(self, settings: TranscriptionSettings) -> None:
        """
        Stores the settings in the configuration, from where the cards take their
        initial values. Like any other choice, they're the defaults of the next
        transcription.
        """
        values: dict[ConfigManager.KeyType, str] = {
            ConfigTranscription.Key.METHOD: settings.method,
            ConfigWhisperX.Key.MODEL_SIZE: settings.model_size,
            ConfigWhisperApi.Key.MODEL: settings.openai_model,
            ConfigTranscription.Key.LANGUAGE: settings.input_language,
            ConfigTranscription.Key.OUTPUT_LANGUAGE: settings.output_language,
            ConfigTranscription.Key.TRANSLATION_MODE: settings.translation_mode,
            ConfigTranscription.Key.KEYWORDS: settings.keywords,
            ConfigTranscription.Key.PROMPT: settings.prompt,
            ConfigTranscription.Key.ALIGN_WORDS: str(settings.align_words),
            ConfigTranscription.Key.ISOLATE_SPEECH: str(settings.isolate_speech),
            ConfigWhisperX.Key.DIARIZE: str(settings.diarize),
            ConfigWhisperX.Key.NUM_SPEAKERS: str(settings.num_speakers),
        }
        if self._has_output:
            values |= {
                ConfigTranscription.Key.WATCH_FOLDER: str(settings.watch),
                ConfigTranscription.Key.OVERWRITE_FILES: str(settings.overwrite),
                ConfigWhisperX.Key.OUTPUT_FILE_TYPES: ",".join(
                    settings.output_file_types
                ),
                ConfigWhisperApi.Key.RESPONSE_FORMAT: settings.response_format,
            }
        for key, value in values.items():
            save_config(key, value)

    def _refresh(self) -> None:
        """Shows the options that apply to the current choices."""
        settings = self.get_settings()
        for card in self._cards:
            card.refresh(settings)

        if self._on_change:
            self._on_change()

    def _has_subtitles(self, settings: TranscriptionSettings) -> bool:
        return self._has_output and bool(
            SUBTITLE_FILE_TYPES.intersection(settings.output_file_types)
        )
