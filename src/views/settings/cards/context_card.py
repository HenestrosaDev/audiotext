from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from handlers.openai_api_handler import get_api_model
from models.config.config_transcription import ConfigTranscription
from models.transcription_settings import TranscriptionSettings, TranslationMode
from utils.enums import TranscriptionMethod
from utils.i18n import _
from views.settings.cards.base import SettingsCard
from views.settings.option_labels import save_config
from views.style import theme
from views.widgets.textbox import CTkPlaceholderTextbox

DEBOUNCE_DELAY_MS = 600


class ContextCard(SettingsCard):
    """The keywords and the description that help to transcribe the audio."""

    def __init__(
        self,
        master: Any,
        on_change: Callable[[], None],
        config_transcription: ConfigTranscription,
    ) -> None:
        super().__init__(master, _("Context"), on_change)
        self._debounce_after_id: str | None = None

        # Why the fields are disabled, if they are
        self.lbl_unavailable = self._hint(2, pady=(2, 0))

        self._field_label(3, _("Keywords"))
        self._keywords = ctk.StringVar(self, config_transcription.keywords)
        self.ent_keywords = ctk.CTkEntry(
            self,
            textvariable=self._keywords,
            placeholder_text=_("e.g. Audiotext, WhisperX, Henestrosa"),
        )
        self.ent_keywords.grid(row=4, column=0, columnspan=2, padx=18, sticky=ctk.EW)
        self._keywords.trace_add("write", lambda *_args: self._debounce_save())
        self._hint(
            5,
            _(
                "Names, terms or acronyms said in the audio, separated by commas, "
                "so they're spelled right."
            ),
        )

        self._field_label(6, _("Description"))
        self.tbx_prompt = CTkPlaceholderTextbox(
            self,
            height=84,
            font=theme.font(13),
            placeholder_text=_("e.g. An interview about speech recognition"),
            on_change=self._debounce_save,
        )
        if config_transcription.prompt:
            self.tbx_prompt.insert("1.0", config_transcription.prompt)
        self.tbx_prompt.grid(row=7, column=0, columnspan=2, padx=18, sticky=ctk.EW)
        self._hint(
            8, _("What the audio is about, such as its topic or setting."), (2, 16)
        )
        self.interactive_widgets.extend([self.ent_keywords, self.tbx_prompt])

    def destroy(self) -> None:
        if self._debounce_after_id:
            self.after_cancel(self._debounce_after_id)
            self._save_text_fields()
        super().destroy()

    # SETTINGS

    def update_settings(self, settings: TranscriptionSettings) -> None:
        settings.prompt = self.tbx_prompt.get_text().strip()
        settings.keywords = self._keywords.get().strip()

    def refresh(self, settings: TranscriptionSettings) -> None:
        unavailable_reason = self._get_unavailable_reason(settings)
        state = ctk.DISABLED if unavailable_reason else ctk.NORMAL
        for widget in (self.ent_keywords, self.tbx_prompt):
            if widget.cget("state") != state:
                widget.configure(state=state)

        if unavailable_reason:
            self.lbl_unavailable.configure(text=unavailable_reason)
            self.lbl_unavailable.grid()
        else:
            self.lbl_unavailable.grid_remove()

    @staticmethod
    def _get_unavailable_reason(settings: TranscriptionSettings) -> str | None:
        """
        The Google API and the diarization model of the OpenAI API don't accept a
        prompt. Without one, the keywords would be ignored too.
        """
        method = settings.transcription_method
        if method == TranscriptionMethod.GOOGLE_API:
            return _("Not used by the Google API.")
        if method == TranscriptionMethod.WHISPERX:
            return None

        # Whisper translates, whichever model is chosen
        is_whisper_translation = (
            settings.effective_translation_mode == TranslationMode.WHISPER
        )
        if get_api_model(
            None if is_whisper_translation else settings.openai_model
        ).supports_prompt:
            return None
        return _("Not used by the {model} model.").format(model=settings.openai_model)

    # EVENT HANDLERS

    def _debounce_save(self) -> None:
        if self._debounce_after_id:
            self.after_cancel(self._debounce_after_id)
        self._debounce_after_id = self.after(DEBOUNCE_DELAY_MS, self._save_text_fields)

    def _save_text_fields(self) -> None:
        self._debounce_after_id = None
        # The configuration file keeps the line breaks, but not the indentation
        lines = self.tbx_prompt.get_text().strip().splitlines()
        save_config(
            ConfigTranscription.Key.PROMPT, "\n".join(line.strip() for line in lines)
        )
        # Line breaks would only separate the keywords, like the commas
        save_config(
            ConfigTranscription.Key.KEYWORDS, " ".join(self._keywords.get().split())
        )
