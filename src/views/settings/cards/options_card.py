from collections.abc import Callable
from typing import Any

import customtkinter as ctk

import utils.validators as validators
from handlers.openai_api_handler import get_api_model
from models.config.config_transcription import ConfigTranscription
from models.config.config_whisperx import ConfigWhisperX
from models.transcription_settings import TranscriptionSettings
from utils.enums import TranscriptionMethod
from utils.env_keys import EnvKeys
from utils.i18n import _
from views.settings.cards.base import SettingsCard
from views.settings.option_labels import save_config
from views.style import theme

DEBOUNCE_DELAY_MS = 600


class OptionsCard(SettingsCard):
    """The timings of the words, the speech isolation and the speakers."""

    def __init__(
        self,
        master: Any,
        on_change: Callable[[], None],
        on_set_api_key: Callable[[EnvKeys, str], None],
        has_subtitles: Callable[[TranscriptionSettings], bool],
        config_transcription: ConfigTranscription,
        config_whisperx: ConfigWhisperX,
    ) -> None:
        """
        :param has_subtitles: Whether subtitles are saved with the settings, which
                              already need the timings of the words.
        """
        super().__init__(master, _("Options"), on_change)
        self._has_subtitles = has_subtitles
        self._debounce_after_id: str | None = None

        self.swi_align_words = self._switch(
            2,
            _("Word-level timings"),
            config_transcription.align_words,
            ConfigTranscription.Key.ALIGN_WORDS,
        )
        self.lbl_align_hint = self._hint(3)

        self.swi_isolate_speech = self._switch(
            4,
            _("Extract speech"),
            config_transcription.isolate_speech,
            ConfigTranscription.Key.ISOLATE_SPEECH,
        )
        self._hint(5, _("Reduces music and background noise before transcribing."))

        self.swi_diarize = self._switch(
            6,
            _("Identify speakers"),
            config_whisperx.diarize,
            ConfigWhisperX.Key.DIARIZE,
        )
        self.frm_speakers = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_speakers.grid(
            row=7, column=0, columnspan=2, padx=18, pady=(8, 0), sticky=ctk.EW
        )
        ctk.CTkLabel(
            self.frm_speakers,
            text=_("Number of speakers (0 = auto)"),
            font=theme.font(12),
        ).grid(row=0, column=0, sticky=ctk.W)
        self._num_speakers = ctk.StringVar(self, str(config_whisperx.num_speakers))
        self.ent_num_speakers = ctk.CTkEntry(
            self.frm_speakers, width=48, textvariable=self._num_speakers
        )
        self.ent_num_speakers.configure(
            validate="key",
            validatecommand=(
                self.ent_num_speakers.register(validators.is_valid_non_negative_int),
                "%P",
            ),
        )
        self.ent_num_speakers.grid(row=0, column=1, padx=(10, 0))
        self._num_speakers.trace_add("write", lambda *_args: self._debounce_save())
        self.btn_hf_token = ctk.CTkButton(
            self.frm_speakers,
            text=_("Set Hugging Face token…"),
            height=26,
            command=lambda: on_set_api_key(EnvKeys.HF_TOKEN, _("Hugging Face token")),
            **theme.SECONDARY_BUTTON,
        )
        self.btn_hf_token.grid(row=1, column=0, columnspan=2, pady=(8, 0), sticky=ctk.W)
        self.interactive_widgets.extend([self.ent_num_speakers, self.btn_hf_token])
        self.lbl_diarize_hint = self._hint(8, pady=(2, 16))

    def destroy(self) -> None:
        if self._debounce_after_id:
            self.after_cancel(self._debounce_after_id)
        super().destroy()

    def update_settings(self, settings: TranscriptionSettings) -> None:
        num_speakers = self._num_speakers.get().strip()
        settings.align_words = bool(self.swi_align_words.get())
        settings.isolate_speech = bool(self.swi_isolate_speech.get())
        settings.diarize = bool(self.swi_diarize.get())
        settings.num_speakers = int(num_speakers) if num_speakers.isdigit() else 0

    def refresh(self, settings: TranscriptionSettings) -> None:
        method = settings.transcription_method
        is_whisperx = method == TranscriptionMethod.WHISPERX
        state = ctk.NORMAL if is_whisperx else ctk.DISABLED
        self.swi_align_words.configure(state=state)
        self.swi_diarize.configure(state=state)

        if not is_whisperx:
            align_hint = _("Only available with WhisperX.")
        elif self._has_subtitles(settings) and not settings.align_words:
            align_hint = _(
                "Highlights each word while playing. The subtitles already use them."
            )
        else:
            align_hint = _("Highlights each word while playing. Takes a bit longer.")
        self.lbl_align_hint.configure(text=align_hint)

        if is_whisperx and settings.diarize:
            self.frm_speakers.grid()
        else:
            self.frm_speakers.grid_remove()

        if is_whisperx:
            diarize_hint = _(
                "Labels who speaks in each part. Requires a Hugging Face token."
            )
        elif (
            method == TranscriptionMethod.WHISPER_API
            and get_api_model(settings.openai_model).has_speakers
        ):
            diarize_hint = _("The model of the Whisper API identifies the speakers.")
        elif method == TranscriptionMethod.WHISPER_API:
            diarize_hint = _(
                "Only available with WhisperX, or with the gpt-4o-transcribe-diarize "
                "model of the Whisper API."
            )
        else:
            diarize_hint = _("Only available with WhisperX.")
        self.lbl_diarize_hint.configure(text=diarize_hint)

    def _debounce_save(self) -> None:
        if self._debounce_after_id:
            self.after_cancel(self._debounce_after_id)
        value = self._num_speakers.get()
        if value:
            self._debounce_after_id = self.after(
                DEBOUNCE_DELAY_MS,
                lambda: save_config(ConfigWhisperX.Key.NUM_SPEAKERS, value),
            )
