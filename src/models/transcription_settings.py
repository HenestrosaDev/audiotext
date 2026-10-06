from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import Any

from models.transcription import Transcription, split_keywords
from utils import constants as c
from utils.enums import AudioSource, TranscriptionMethod, WhisperApiResponseFormats

# Value of the output language to keep the language of the audio
SAME_LANGUAGE = "same"
# Whisper only translates into this language
WHISPER_TRANSLATION_LANGUAGE = "en"


class TranslationMode(Enum):
    # The translation task of Whisper, which only translates into English
    WHISPER = "whisper"
    # Transcribes telling Whisper that the audio is in the output language, which
    # makes it write the transcription in that language. Unofficial, but it works
    # for many languages
    FORCE_LANGUAGE = "force"


@dataclass
class TranscriptionSettings:
    """
    The options chosen to transcribe an audio source. They're stored with each
    entry of the history, so it can be transcribed again with the same options.
    """

    method: str = TranscriptionMethod.WHISPERX.value
    model_size: str = "large-v2"
    # A code of `AUDIO_LANGUAGES`, or `AUTO_DETECT_LANGUAGE`
    input_language: str = c.AUTO_DETECT_LANGUAGE
    # A code of `AUDIO_LANGUAGES`, or `SAME_LANGUAGE`
    output_language: str = SAME_LANGUAGE
    translation_mode: str = TranslationMode.WHISPER.value
    align_words: bool = False
    isolate_speech: bool = False
    diarize: bool = False
    num_speakers: int = 0
    output_file_types: list[str] = field(default_factory=lambda: ["txt"])
    # Response format of the Whisper API
    response_format: str = "text"
    # Model of the OpenAI API
    openai_model: str = "whisper-1"
    # What the audio is about (e.g. its topic or setting)
    prompt: str = ""
    # Names, terms or acronyms said in the audio, separated by commas
    keywords: str = ""
    # Unused: only the files of a folder are saved, always. Kept so the settings
    # of older entries can be read
    autosave: bool = False
    overwrite: bool = False
    # Folder of the files saved automatically. If empty, they're saved next to
    # the transcribed file
    output_dir: str = ""
    # Whether to watch the folder for new files instead of transcribing its files
    watch: bool = False
    # Whether to show the text while recording from the microphone (WhisperX)
    live_transcription: bool = False
    live_model_size: str = "small"

    @property
    def transcription_method(self) -> TranscriptionMethod:
        return TranscriptionMethod(self.method)

    @property
    def is_translating(self) -> bool:
        """Whether the output language differs from the language of the audio."""
        return self.output_language not in (SAME_LANGUAGE, self.input_language)

    @property
    def can_translate(self) -> bool:
        """The Google API can't translate."""
        return self.transcription_method != TranscriptionMethod.GOOGLE_API

    @property
    def can_use_whisper_translation(self) -> bool:
        return self.can_translate and (
            self.output_language == WHISPER_TRANSLATION_LANGUAGE
        )

    @property
    def effective_translation_mode(self) -> TranslationMode | None:
        """
        :return: How the transcription is translated, or None if it's not.
        """
        if not self.is_translating or not self.can_translate:
            return None

        if (
            self.translation_mode == TranslationMode.WHISPER.value
            and self.can_use_whisper_translation
        ):
            return TranslationMode.WHISPER

        return TranslationMode.FORCE_LANGUAGE

    @property
    def effective_output_file_types(self) -> list[str]:
        method = self.transcription_method

        if method == TranscriptionMethod.GOOGLE_API:
            return ["txt"]
        if method == TranscriptionMethod.WHISPER_API:
            return [self.response_format]

        return list(self.output_file_types)

    def to_transcription(
        self,
        audio_source: AudioSource,
        source: str,
        media_path: Path | None = None,
        mic_device_index: int | None = None,
    ) -> Transcription:
        """
        Creates the transcription of an audio source with these settings.

        :param audio_source: The kind of source.
        :param source: The path of the file or the folder, or the URL. Ignored for
                       the microphone.
        :param media_path: Where the downloaded or recorded audio is kept.
        :param mic_device_index: The input device to record from.
        """
        method = self.transcription_method
        input_language = (
            None
            if self.input_language == c.AUTO_DETECT_LANGUAGE
            else self.input_language
        )
        translation_mode = self.effective_translation_mode

        if translation_mode == TranslationMode.FORCE_LANGUAGE:
            language_code: str | None = self.output_language
        else:
            language_code = input_language

        is_folder = audio_source in (AudioSource.DIRECTORY, AudioSource.WATCH)
        is_whisperx = method == TranscriptionMethod.WHISPERX
        # The Google API doesn't accept a prompt nor keywords
        is_google = method == TranscriptionMethod.GOOGLE_API

        transcription = Transcription(
            audio_source=audio_source,
            method=method,
            model_size=self.model_size if is_whisperx else None,
            language_code=language_code,
            should_translate=translation_mode == TranslationMode.WHISPER,
            output_file_types=self.effective_output_file_types,
            should_diarize=is_whisperx and self.diarize,
            num_speakers=(self.num_speakers or None) if is_whisperx else None,
            should_align_words=is_whisperx and self.align_words,
            should_isolate_speech=self.isolate_speech,
            # Only the files of a folder are saved, since there is no other way to
            # get all of them at once. The rest are exported from the history
            should_autosave=is_folder,
            should_overwrite=self.overwrite,
            output_dir=Path(self.output_dir) if self.output_dir else None,
            media_path=media_path,
            mic_device_index=mic_device_index,
            live_model_size=(
                self.live_model_size
                if audio_source == AudioSource.MIC
                and is_whisperx
                and self.live_transcription
                else None
            ),
            # Only the files of a folder are saved in the format of the response.
            # The rest are kept as text in the history and exported from there
            api_response_format=(
                self.response_format
                if is_folder
                else WhisperApiResponseFormats.TEXT.value
            ),
            api_model=(
                self.openai_model if method == TranscriptionMethod.WHISPER_API else None
            ),
            prompt="" if is_google else self.prompt.strip(),
            keywords=[] if is_google else split_keywords(self.keywords),
        )

        if audio_source == AudioSource.YOUTUBE:
            transcription.url = source
        elif audio_source != AudioSource.MIC:
            transcription.audio_source_path = Path(source)

        return transcription

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptionSettings":
        known_fields = {settings_field.name for settings_field in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in known_fields})
