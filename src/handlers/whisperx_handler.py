import dataclasses
import gc
import logging
import os
import threading
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

import utils.config_manager as cm
from models.config.config_whisperx import ConfigWhisperX
from models.transcript_segment import (
    TranscriptSegment,
    TranscriptWord,
    join_segments,
)
from models.transcription import Transcription
from utils.cancellation import CancellationToken
from utils.env_keys import EnvKeys
from utils.i18n import _
from utils.progress import ProgressCallback, ignore_progress

if TYPE_CHECKING:
    from whisperx.schema import AlignedTranscriptionResult, TranscriptionResult

logger = logging.getLogger(__name__)


def is_model_downloaded(model_size: str) -> bool:
    """
    Checks whether the given WhisperX model is fully downloaded, without
    downloading anything.

    :param model_size: The size of the model, e.g. `large-v2`.
    :return: Whether the model can be loaded without an internet connection.
    """
    from faster_whisper.utils import download_model
    from huggingface_hub.errors import LocalEntryNotFoundError

    try:
        model_path = Path(download_model(model_size, local_files_only=True))
    except (LocalEntryNotFoundError, ValueError):
        return False

    # An interrupted download leaves the snapshot without the model weights
    return (model_path / "model.bin").is_file()


# pyannote warns about torchcodec on import, but WhisperX passes the audio already
# decoded (with FFmpeg), so torchcodec is never used
warnings.filterwarnings("ignore", message=r"\s*torchcodec is not installed correctly")

SUBTITLE_FILE_TYPES = {"srt", "vtt"}
# Translations made by Whisper are always into English
TRANSLATION_LANGUAGE = "en"
# Sample rate of the audio loaded by WhisperX
SAMPLE_RATE = 16000

DIARIZATION_MODEL = "pyannote/speaker-diarization-community-1"
DIARIZATION_MODEL_URL = f"https://huggingface.co/{DIARIZATION_MODEL}"
HF_TOKENS_URL = "https://huggingface.co/settings/tokens"


class WhisperXHandler:
    """
    Transcribes audio with WhisperX.

    Loading a model takes from seconds to minutes (it is downloaded the first time),
    so the last loaded transcription and alignment models are kept in memory and
    reused while the options that affect them don't change. The language and the
    task (transcribe or translate) are passed on each transcription, so changing
    them doesn't require reloading the model.
    """

    def __init__(
        self, config_provider: Callable[[], ConfigWhisperX] | None = None
    ) -> None:
        """
        :param config_provider: Returns the WhisperX configuration to use. By
                                default, the one stored in `config.ini`.
        """
        self._config_provider = config_provider or (
            lambda: cm.ConfigManager.get_config_whisperx()
        )

        self._whisperx_result: (
            TranscriptionResult | AlignedTranscriptionResult | None
        ) = None
        self._result_language: str | None = None
        # Audio of the last transcription (16-bit, mono, at `SAMPLE_RATE`), kept to
        # play it in the transcript viewer
        self._result_audio: np.ndarray | None = None

        # Guards the models, which can be loaded from a preload thread while a
        # transcription is requested
        self._models_lock = threading.Lock()
        self._model: Any = None
        self._model_key: tuple[str, str, str] | None = None
        self._align_model: Any = None
        self._align_metadata: Any = None
        self._align_model_key: tuple[str, str] | None = None
        self._diarize_model: Any = None
        self._diarize_model_key: tuple[str, str] | None = None

    @property
    def segments(self) -> list[TranscriptSegment]:
        """The segments of the last transcription, with their timestamps."""
        if self._whisperx_result is None:
            return []

        return [
            TranscriptSegment(
                start=float(segment["start"]),
                end=float(segment["end"]),
                text=segment["text"].strip(),
                speaker=segment.get("speaker"),
                words=self._get_words(segment),
            )
            for segment in self._whisperx_result["segments"]
        ]

    @staticmethod
    def _get_words(segment: Any) -> tuple[TranscriptWord, ...]:
        """
        Returns the words of an aligned segment. Some words (e.g. numbers) can't be
        aligned, so they take the timings of the previous word.
        """
        words = []
        previous_end = float(segment["start"])

        for word in segment.get("words", []):
            start = float(word.get("start", previous_end))
            end = float(word.get("end", start))
            words.append(TranscriptWord(start, end, str(word["word"]).strip()))
            previous_end = end

        return tuple(words)

    @property
    def result_language(self) -> str | None:
        """The language of the last transcription (e.g. "en")."""
        return self._result_language

    @property
    def audio(self) -> np.ndarray | None:
        """
        The audio of the last transcription as 16-bit samples, mono, at
        `SAMPLE_RATE`.
        """
        return self._result_audio

    def preload_model(self, on_progress: ProgressCallback = ignore_progress) -> bool:
        """
        Loads the transcription model of the current configuration, so the next
        transcription doesn't have to wait for it. Models that are not downloaded
        yet are skipped, as they're downloaded when a transcription needs them.

        :param on_progress: Called with the status of the loading process.
        :return: Whether the model was loaded.
        """
        config_whisperx = self._config_provider()

        if not is_model_downloaded(config_whisperx.model_size):
            logger.info(
                "Not preloading %s, it's not downloaded", config_whisperx.model_size
            )
            return False

        self._get_model(config_whisperx, on_progress)
        return True

    def transcribe_file(
        self,
        transcription: Transcription,
        on_progress: ProgressCallback = ignore_progress,
        cancellation_token: CancellationToken | None = None,
    ) -> str:
        """
        Transcribe audio from a file using the WhisperX library.

        :param transcription: An instance of Transcription containing information about
                              the audio file. Its model, if any, replaces the
                              configured one.
        :param on_progress: Called with the progress of each step of the process.
        :param cancellation_token: Checked between batches to abort the process.
        :raises ValueError: If no output file types are specified, or if the speakers
                            should be identified without a Hugging Face token.
        :raises TranscriptionCancelledError: If the token is cancelled.
        :return: The transcribed text. If the speakers are identified, each
                 paragraph is prefixed with the label of its speaker.
        """
        # Imported here because WhisperX takes several seconds to load
        import whisperx

        if not transcription.output_file_types:
            raise ValueError(
                _("No output file types selected. Please select at least one.")
            )

        if transcription.should_diarize:
            hf_token = self._get_hf_token()

        # The previous result is replaced, so its memory is released first
        self._whisperx_result = self._result_audio = None

        token = cancellation_token or CancellationToken()
        config_whisperx = self._config_provider()
        # The model chosen for the transcription, which may differ from the
        # configured one (e.g. an entry of the history transcribed again, or a
        # watched folder while another model is chosen)
        if transcription.model_size:
            config_whisperx = dataclasses.replace(
                config_whisperx, model_size=transcription.model_size
            )
        device = self._get_device(config_whisperx)
        task = "translate" if transcription.should_translate else "transcribe"

        model = self._get_model(config_whisperx, on_progress)
        token.raise_if_cancelled()

        on_progress(_("Loading audio…"), None)
        audio = whisperx.load_audio(str(transcription.audio_source_path))
        token.raise_if_cancelled()

        # The prompt is an option of the loaded model, so it's replaced on each
        # transcription instead of loading the model again
        model.options = dataclasses.replace(
            model.options, initial_prompt=transcription.whisper_prompt or None
        )

        on_progress(_("Transcribing…"), 0)
        result = model.transcribe(
            audio,
            batch_size=config_whisperx.batch_size,
            language=transcription.language_code,
            task=task,
            progress_callback=self._progress_callback(
                _("Transcribing…"), on_progress, token
            ),
        )

        if transcription.should_translate:
            result_language = TRANSLATION_LANGUAGE
        else:
            result_language = result["language"]

        # Subtitles need word-level timestamps, which also make the speaker
        # identification more precise
        needs_subtitles = bool(
            SUBTITLE_FILE_TYPES.intersection(transcription.output_file_types)
        )
        needs_words = needs_subtitles or transcription.should_align_words
        if needs_words or transcription.should_diarize:
            try:
                result = self._align(
                    result, audio, result_language, device, on_progress, token
                )
            except ValueError:
                # There are no alignment models for some languages. Without
                # subtitles, the transcription is kept without the word timings,
                # and the speakers are assigned to whole segments
                if needs_subtitles:
                    raise
                logger.warning("No alignment model for %s", result_language)

        if transcription.should_diarize:
            result = self._diarize(
                result,
                audio,
                transcription.num_speakers,
                hf_token,
                device,
                on_progress,
                token,
            )

        self._whisperx_result = result
        self._result_language = result_language
        self._result_audio = (np.clip(audio, -1, 1) * 32767).astype(np.int16)

        return join_segments(self.segments)

    def save_transcription(
        self,
        file_path: Path,
        output_file_types: list[str],
        should_overwrite: bool,
    ) -> None:
        """
        Save the last transcription as the specified file types.

        :param file_path: The path of the output files. Its extension is replaced by
                          each of the output file types.
        :param output_file_types: The file types to generate (e.g. "txt", "srt").
        :param should_overwrite: Indicates whether existing files should be
                                 overwritten. If False, a file is only generated if
                                 no file with the same name and type exists.
        :raises ValueError: If there is no transcription to save.
        """
        from whisperx.utils import get_writer

        if self._whisperx_result is None:
            raise ValueError(
                _("There is no transcription to save. Please generate it first.")
            )

        options = vars(cm.ConfigManager.get_config_subtitles())
        output_dir = file_path.parent

        # The writers expect the language of the result, which the aligned result
        # lacks: https://github.com/m-bain/whisperX/issues/455
        result = {**self._whisperx_result, "language": self._result_language}

        for output_type in output_file_types:
            output_file_path = file_path.with_suffix(f".{output_type}")

            if should_overwrite or not output_file_path.exists():
                writer = get_writer(output_type, str(output_dir))
                writer(result, str(file_path), options)

    def _align(
        self,
        result: "TranscriptionResult",
        audio: np.ndarray,
        language: str,
        device: str,
        on_progress: ProgressCallback,
        token: CancellationToken,
    ) -> "AlignedTranscriptionResult":
        """
        Aligns the transcription with the audio to get word-level timestamps.

        :raises ValueError: If there is no alignment model for the language.
        """
        import whisperx

        align_model, metadata = self._get_align_model(language, device, on_progress)
        token.raise_if_cancelled()

        on_progress(_("Aligning subtitles…"), 0)
        aligned_result: AlignedTranscriptionResult = whisperx.align(
            result["segments"],
            align_model,
            metadata,
            audio,
            device,
            return_char_alignments=False,
            progress_callback=self._progress_callback(
                _("Aligning subtitles…"), on_progress, token
            ),
        )
        return aligned_result

    def _diarize(
        self,
        result: "TranscriptionResult | AlignedTranscriptionResult",
        audio: np.ndarray,
        num_speakers: int | None,
        hf_token: str,
        device: str,
        on_progress: ProgressCallback,
        token: CancellationToken,
    ) -> "TranscriptionResult | AlignedTranscriptionResult":
        """
        Identifies the speakers of the audio and assigns them to the segments (and
        the words, if aligned) of the transcription.
        """
        import whisperx

        diarize_model = self._get_diarize_model(hf_token, device, on_progress)
        token.raise_if_cancelled()

        on_progress(_("Identifying speakers…"), 0)
        diarize_segments = diarize_model(
            audio,
            num_speakers=num_speakers or None,
            progress_callback=self._progress_callback(
                _("Identifying speakers…"), on_progress, token
            ),
        )
        token.raise_if_cancelled()

        diarized_result: TranscriptionResult | AlignedTranscriptionResult = (
            whisperx.assign_word_speakers(diarize_segments, result)
        )
        return diarized_result

    @staticmethod
    def _get_hf_token() -> str:
        """
        :raises ValueError: If the Hugging Face token is not set.
        :return: The Hugging Face token, needed to download the diarization model.
        """
        hf_token = EnvKeys.HF_TOKEN.get_value(default="").strip()

        if not hf_token:
            raise ValueError(
                _(
                    "Identifying speakers requires a Hugging Face token. Create one "
                    "at {tokens_url}, accept the conditions of {model_url} and set "
                    "the token in the WhisperX options."
                ).format(tokens_url=HF_TOKENS_URL, model_url=DIARIZATION_MODEL_URL)
            )

        return hf_token

    @staticmethod
    def _get_device(config_whisperx: ConfigWhisperX) -> str:
        return "cpu" if config_whisperx.use_cpu else "cuda"

    @staticmethod
    def _progress_callback(
        message: str, on_progress: ProgressCallback, token: CancellationToken
    ) -> Callable[[float], None]:
        """
        Adapts `on_progress` to the WhisperX progress callbacks, which receive the
        percentage completed after each batch. Since WhisperX doesn't support
        cancellation, the process is aborted by raising an exception from the
        callback.
        """

        def callback(percentage: float) -> None:
            token.raise_if_cancelled()
            on_progress(message, percentage / 100)

        return callback

    def _get_model(
        self, config_whisperx: ConfigWhisperX, on_progress: ProgressCallback
    ) -> Any:
        """
        Returns the transcription model for the given configuration, reusing the
        loaded one if the options that affect it have not changed.
        """
        import whisperx

        device = self._get_device(config_whisperx)
        model_key = (config_whisperx.model_size, device, config_whisperx.compute_type)

        with self._models_lock:
            if self._model is not None and self._model_key == model_key:
                return self._model

            if self._model is not None:
                # Free the memory of the previous model before loading the new one
                self._model = self._model_key = None
                self._release_memory()

            on_progress(
                _(
                    "Loading the {model} model (it's downloaded the first time it's "
                    "used)…"
                ).format(model=config_whisperx.model_size),
                None,
            )
            logger.info("Loading WhisperX model %s", model_key)
            self._model = whisperx.load_model(
                config_whisperx.model_size,
                device,
                compute_type=config_whisperx.compute_type,
                threads=os.cpu_count() or 4,
            )
            self._model_key = model_key

            return self._model

    def _get_align_model(
        self, language: str, device: str, on_progress: ProgressCallback
    ) -> tuple[Any, Any]:
        """
        Returns the alignment model for the given language, reusing the loaded one
        if the language and the device have not changed.
        """
        import whisperx

        align_model_key = (language, device)

        with self._models_lock:
            if self._align_model is None or self._align_model_key != align_model_key:
                if self._align_model is not None:
                    self._align_model = self._align_metadata = None
                    self._release_memory()

                on_progress(_("Loading the subtitle alignment model…"), None)
                logger.info("Loading WhisperX alignment model %s", align_model_key)
                self._align_model, self._align_metadata = whisperx.load_align_model(
                    language_code=language, device=device
                )
                self._align_model_key = align_model_key

            return self._align_model, self._align_metadata

    def _get_diarize_model(
        self, hf_token: str, device: str, on_progress: ProgressCallback
    ) -> Any:
        """
        Returns the speaker diarization model, reusing the loaded one if the token
        and the device have not changed.

        :raises ValueError: If the model can't be downloaded with the token.
        """
        from huggingface_hub.errors import GatedRepoError, HfHubHTTPError
        from whisperx.diarize import DiarizationPipeline

        diarize_model_key = (hf_token, device)

        with self._models_lock:
            if self._diarize_model is not None:
                if self._diarize_model_key == diarize_model_key:
                    return self._diarize_model

                self._diarize_model = self._diarize_model_key = None
                self._release_memory()

            on_progress(
                _(
                    "Loading the speaker identification model (it's downloaded the "
                    "first time it's used)…"
                ),
                None,
            )
            logger.info("Loading the diarization model on %s", device)

            try:
                self._diarize_model = DiarizationPipeline(
                    model_name=DIARIZATION_MODEL, token=hf_token, device=device
                )
            except (GatedRepoError, HfHubHTTPError) as e:
                raise ValueError(
                    _(
                        "Could not download the speaker identification model. Check "
                        "that the Hugging Face token is valid and that you've "
                        "accepted the conditions of {model_url}."
                    ).format(model_url=DIARIZATION_MODEL_URL)
                ) from e

            self._diarize_model_key = diarize_model_key
            return self._diarize_model

    @staticmethod
    def _release_memory() -> None:
        import torch

        gc.collect()

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
