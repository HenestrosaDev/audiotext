import dataclasses
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

import utils.constants as c
from models.config.config_transcription import ConfigTranscription
from models.transcription_settings import (
    SAME_LANGUAGE,
    WHISPER_TRANSLATION_LANGUAGE,
    TranscriptionSettings,
    TranslationMode,
)
from utils.i18n import _
from views.localization import localize
from views.settings.cards.base import SettingsCard
from views.settings.option_labels import get_language_labels, save_config
from views.style import theme
from views.widgets.bindings import bind_wraplength
from views.widgets.localized_options import LocalizedOptions
from views.widgets.searchable_option_menu import CTkSearchableOptionMenu

# Old versions stored the name of the language instead of its code
_LEGACY_LANGUAGE_NAMES = {"Português": "pt"}


def get_configured_language(config_transcription: ConfigTranscription) -> str:
    """The code of the configured language of the audio."""
    language = config_transcription.language

    if language == c.AUTO_DETECT_LANGUAGE or language in c.AUDIO_LANGUAGES:
        return language

    for code, name in c.AUDIO_LANGUAGES.items():
        if name == language:
            return code

    return _LEGACY_LANGUAGE_NAMES.get(language, c.AUTO_DETECT_LANGUAGE)


class LanguageCard(SettingsCard):
    """
    The language of the audio and of the transcription, translating it if they
    differ.
    """

    def __init__(
        self,
        master: Any,
        on_change: Callable[[], None],
        config_transcription: ConfigTranscription,
    ) -> None:
        super().__init__(master, lambda: _("Language"), on_change)

        # The English names and the codes of the languages are also searched
        search_terms = {
            code: f"{name} {code}" for code, name in c.AUDIO_LANGUAGES.items()
        }

        self._field_label(2, lambda: _("Language of the audio"))
        self.omn_input_language = CTkSearchableOptionMenu(
            self,
            values=[],
            title=lambda: _("Language of the audio"),
            search_placeholder=lambda: _("Search language…"),
            no_results_text=lambda: _("No languages found."),
            dynamic_resizing=False,
        )
        self._input_languages = LocalizedOptions(
            self.omn_input_language,
            lambda: {c.AUTO_DETECT_LANGUAGE: _("Auto-detect")} | get_language_labels(),
            get_configured_language(config_transcription),
            search_terms=search_terms,
            command=self._on_input_language_change,
        )
        self.omn_input_language.grid(
            row=3, column=0, columnspan=2, padx=18, sticky=ctk.EW
        )

        self._field_label(4, lambda: _("Language of the transcription"))
        self.omn_output_language = CTkSearchableOptionMenu(
            self,
            values=[],
            title=lambda: _("Language of the transcription"),
            search_placeholder=lambda: _("Search language…"),
            no_results_text=lambda: _("No languages found."),
            dynamic_resizing=False,
        )
        self._output_languages = LocalizedOptions(
            self.omn_output_language,
            lambda: {SAME_LANGUAGE: _("Same as the audio")} | get_language_labels(),
            config_transcription.output_language,
            search_terms=search_terms,
            command=self._on_output_language_change,
        )
        self.omn_output_language.grid(
            row=5, column=0, columnspan=2, padx=18, sticky=ctk.EW
        )
        self.interactive_widgets.extend(
            [self.omn_input_language, self.omn_output_language]
        )

        self._init_translation(config_transcription.translation_mode)
        self._spacer(7)

    def _init_translation(self, translation_mode: str) -> None:
        """The translation options, only shown when the languages differ."""
        self.frm_translation = ctk.CTkFrame(
            self, fg_color=theme.SUBTLE_BG, corner_radius=10
        )
        self.frm_translation.grid(
            row=6, column=0, columnspan=2, padx=18, pady=(12, 0), sticky=ctk.EW
        )
        self.frm_translation.grid_columnconfigure(0, weight=1)

        localize(
            ctk.CTkLabel(self.frm_translation, font=theme.font(13, "bold")),
            text=lambda: _("Translation"),
        ).grid(row=0, column=0, padx=12, pady=(10, 0), sticky=ctk.W)

        # The mode chosen by the user, kept while another language forces a mode
        self._preferred_translation_mode = translation_mode
        self._translation_mode = ctk.StringVar(self, translation_mode)
        self.rad_whisper_translation = localize(
            ctk.CTkRadioButton(
                self.frm_translation,
                variable=self._translation_mode,
                value=TranslationMode.WHISPER.value,
                command=self._on_translation_mode_change,
                font=theme.font(13),
            ),
            text=lambda: _("Translate with Whisper (recommended)"),
        )
        self.rad_whisper_translation.grid(
            row=1, column=0, padx=12, pady=(8, 0), sticky=ctk.W
        )
        self.rad_force_language = ctk.CTkRadioButton(
            self.frm_translation,
            text="",
            variable=self._translation_mode,
            value=TranslationMode.FORCE_LANGUAGE.value,
            command=self._on_translation_mode_change,
            font=theme.font(13),
        )
        self.rad_force_language.grid(
            row=2, column=0, padx=12, pady=(8, 0), sticky=ctk.W
        )
        self.interactive_widgets.extend(
            [self.rad_whisper_translation, self.rad_force_language]
        )
        self.lbl_translation_hint = ctk.CTkLabel(
            self.frm_translation,
            text="",
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            justify=ctk.LEFT,
            anchor=ctk.W,
        )
        self.lbl_translation_hint.grid(
            row=3, column=0, padx=12, pady=(6, 10), sticky=ctk.EW
        )
        bind_wraplength(self.lbl_translation_hint, minimum=120)

    # SETTINGS

    def update_settings(self, settings: TranscriptionSettings) -> None:
        settings.input_language = self._input_languages.get()
        settings.output_language = self._output_languages.get()
        settings.translation_mode = self._translation_mode.get()

    def refresh(self, settings: TranscriptionSettings) -> None:
        if not settings.is_translating:
            self.frm_translation.grid_remove()
            return

        self.frm_translation.grid()
        output_name = self._output_languages.label(settings.output_language)

        if not settings.can_translate:
            self.rad_whisper_translation.grid_remove()
            self.rad_force_language.grid_remove()
            self.lbl_translation_hint.configure(
                text=_(
                    "The Google API can't translate. The transcription will be in the "
                    "language of the audio."
                ),
                text_color=theme.ERROR_TEXT,
            )
            return

        self.rad_whisper_translation.grid()
        self.rad_force_language.grid()
        self.rad_force_language.configure(
            text=_("Write it directly in {language} (experimental)").format(
                language=output_name
            )
        )
        self.rad_whisper_translation.configure(
            state=ctk.NORMAL if settings.can_use_whisper_translation else ctk.DISABLED
        )

        self._translation_mode.set(
            self._preferred_translation_mode
            if settings.can_use_whisper_translation
            else TranslationMode.FORCE_LANGUAGE.value
        )
        mode = dataclasses.replace(
            settings, translation_mode=self._translation_mode.get()
        ).effective_translation_mode

        if mode == TranslationMode.WHISPER:
            hint = _("Whisper transcribes and translates the audio in one step.")
        else:
            english = self._output_languages.label(WHISPER_TRANSLATION_LANGUAGE)
            hint = _(
                "Whisper can only translate into {english}. For other languages, it's "
                "asked to write the transcription in {language} directly. It works "
                "well for many languages, but check the result."
            ).format(english=english, language=output_name)
        self.lbl_translation_hint.configure(text=hint, text_color=theme.HINT_TEXT)

    # EVENT HANDLERS

    def _on_input_language_change(self, language: str) -> None:
        save_config(ConfigTranscription.Key.LANGUAGE, language)
        self._on_change()

    def _on_output_language_change(self, language: str) -> None:
        save_config(ConfigTranscription.Key.OUTPUT_LANGUAGE, language)
        self._on_change()

    def _on_translation_mode_change(self) -> None:
        self._preferred_translation_mode = self._translation_mode.get()
        save_config(
            ConfigTranscription.Key.TRANSLATION_MODE, self._translation_mode.get()
        )
        self._on_change()
