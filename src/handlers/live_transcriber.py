"""
Transcribes the microphone while it's recording, phrase by phrase, to show a draft
of the text. When the recording stops, it's transcribed again as a whole with the
chosen model, which gives a better result.
"""

import logging
import math
import os
import queue
import threading
from collections import deque
from collections.abc import Callable
from typing import Any

import numpy as np

import utils.config_manager as cm
from utils.audio_utils import MIN_LEVEL_DBFS, SpeechDetector
from utils.i18n import _

logger = logging.getLogger(__name__)

# Sample rate of the audio that Whisper expects
SAMPLE_RATE = 16000
# Duration of the blocks the audio is analyzed in, as often as the level meter is
# updated, which `SpeechDetector` is tuned for
BLOCK_SECONDS = 0.1
# Characters of the previous text given to Whisper as context
PROMPT_CHARACTERS = 200
# Segments that are more likely silence than speech are discarded, since Whisper
# makes up text (e.g. "Thank you.") for them
MAX_NO_SPEECH_PROBABILITY = 0.6
# Probability above which the detected language is kept for the next phrases, so
# short phrases don't switch it
LANGUAGE_PROBABILITY = 0.6


def int16_to_float(frames: bytes) -> np.ndarray:
    """Converts 16-bit audio to float samples between -1 and 1."""
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768


def resample(samples: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    """Resamples audio by linear interpolation, which is enough for speech."""
    if from_rate == to_rate or not len(samples):
        return samples

    duration = len(samples) / from_rate
    target_length = max(round(duration * to_rate), 1)
    source_times = np.arange(len(samples)) / from_rate
    target_times = np.arange(target_length) / to_rate
    resampled: np.ndarray = np.interp(target_times, source_times, samples)
    return resampled.astype(np.float32)


def get_dbfs(samples: np.ndarray) -> float:
    """The loudness of float samples, from `MIN_LEVEL_DBFS` to 0."""
    if not len(samples):
        return float(MIN_LEVEL_DBFS)

    rms = float(np.sqrt(np.mean(np.square(samples))))
    if rms <= 0:
        return float(MIN_LEVEL_DBFS)

    return max(20 * math.log10(rms), float(MIN_LEVEL_DBFS))


class PhraseSplitter:
    """
    Splits the audio into phrases at the pauses of the speech, so each one can be
    transcribed while the next one is said. The audio without speech is skipped.
    """

    # Silence that ends a phrase, after the moment `SpeechDetector` keeps
    # detecting speech once it stops
    PAUSE_SECONDS = 0.5
    # Phrases are cut at this duration, so the text doesn't take long to appear
    # when there are no pauses
    MAX_PHRASE_SECONDS = 12.0
    # Audio kept before the speech, so the first syllable isn't cut
    PRE_ROLL_SECONDS = 0.3

    def __init__(self) -> None:
        self._detector = SpeechDetector()
        self._pre_roll: deque[np.ndarray] = deque()
        self._blocks: list[np.ndarray] = []
        self._seconds = 0.0
        self._silence_seconds = 0.0

    def feed(self, samples: np.ndarray, dbfs: float) -> np.ndarray | None:
        """
        :param samples: A block of audio at `SAMPLE_RATE`.
        :param dbfs: The loudness of the block.
        :return: The audio of a phrase, when it ends.
        """
        seconds = len(samples) / SAMPLE_RATE
        is_speech = self._detector.update(dbfs)

        if not self._blocks:
            if not is_speech:
                self._pre_roll.append(samples)
                while (
                    sum(len(block) for block in self._pre_roll) / SAMPLE_RATE
                    > self.PRE_ROLL_SECONDS
                ):
                    self._pre_roll.popleft()
                return None

            self._blocks = list(self._pre_roll)
            self._seconds = sum(len(block) for block in self._blocks) / SAMPLE_RATE
            self._pre_roll.clear()

        self._blocks.append(samples)
        self._seconds += seconds
        self._silence_seconds = 0.0 if is_speech else self._silence_seconds + seconds

        if (
            self._silence_seconds >= self.PAUSE_SECONDS
            or self._seconds >= self.MAX_PHRASE_SECONDS
        ):
            return self.flush()

        return None

    def flush(self) -> np.ndarray | None:
        """:return: The audio of the phrase being said, if any."""
        if not self._blocks:
            return None

        phrase = np.concatenate(self._blocks)
        self._blocks = []
        self._seconds = self._silence_seconds = 0.0
        return phrase


class LiveTranscriber:
    """
    Transcribes the phrases of a recording in a background thread with
    faster-whisper, which WhisperX is built on. A small model is used, so the text
    keeps up with the speech on a CPU. The model is kept in memory for the next
    recordings.
    """

    def __init__(
        self,
        on_text: Callable[[str], None],
        on_status: Callable[[str], None],
    ) -> None:
        """
        :param on_text: Called from the background thread with the whole text
                        transcribed so far.
        :param on_status: Called from the background thread with what's happening
                          (e.g. the model is loading), or "" when it's transcribing.
        """
        self._on_text = on_text
        self._on_status = on_status

        self._model: Any = None
        self._model_key: tuple[str, str, str] | None = None
        self._phrases: queue.Queue[np.ndarray | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._is_running = False

        self._sample_rate = SAMPLE_RATE
        self._pending: list[np.ndarray] = []
        self._splitter = PhraseSplitter()
        self._language: str | None = None
        self._task = "transcribe"
        self._prompt = ""
        self._texts: list[str] = []

    def start(
        self,
        model_size: str,
        sample_rate: int,
        language: str | None = None,
        should_translate: bool = False,
        prompt: str = "",
    ) -> None:
        """
        Starts transcribing the audio passed to `feed`.

        :param model_size: The Whisper model to use (e.g. "small").
        :param sample_rate: The sample rate of the audio passed to `feed`.
        :param language: The language of the audio. If None, it's detected.
        :param should_translate: Whether to translate the speech into English.
        :param prompt: The keywords and the context of the audio, given before the
                       previous text.
        """
        self.stop()

        self._sample_rate = sample_rate
        self._pending = []
        self._splitter = PhraseSplitter()
        self._language = language
        self._task = "translate" if should_translate else "transcribe"
        self._prompt = prompt.strip()
        self._texts = []
        self._phrases = queue.Queue()
        self._is_running = True

        self._thread = threading.Thread(
            target=self._run, args=(model_size, self._phrases), daemon=True
        )
        self._thread.start()

    def feed(self, frames: bytes) -> None:
        """Adds a chunk of 16-bit mono audio of the recording."""
        if not self._is_running:
            return

        self._pending.append(int16_to_float(frames))
        pending_samples = sum(len(samples) for samples in self._pending)
        if pending_samples / self._sample_rate < BLOCK_SECONDS:
            return

        block = np.concatenate(self._pending)
        self._pending = []
        dbfs = get_dbfs(block)
        block = resample(block, self._sample_rate, SAMPLE_RATE)

        if (phrase := self._splitter.feed(block, dbfs)) is not None:
            self._phrases.put(phrase)

    def stop(self) -> None:
        """
        Stops transcribing. The phrases not transcribed yet are discarded, since the
        whole recording is transcribed afterwards.
        """
        if not self._is_running:
            return

        self._is_running = False
        # Wakes up the thread so it ends
        self._phrases.put(None)
        self._thread = None

    # BACKGROUND THREAD

    def _run(self, model_size: str, phrases: "queue.Queue[np.ndarray | None]") -> None:
        try:
            model = self._get_model(model_size)
        except Exception:
            logger.exception("Could not load the live transcription model")
            self._on_status(_("The text can't be shown while recording."))
            return

        self._on_status("")

        while True:
            phrase = phrases.get()
            # A new recording replaces the queue, so this one has ended
            if phrase is None or phrases is not self._phrases:
                return

            try:
                text = self._transcribe(model, phrase)
            except Exception:
                logger.exception("Could not transcribe a phrase")
                continue

            # The phrases transcribed after stopping are discarded
            if text and self._is_running and phrases is self._phrases:
                self._texts.append(text)
                self._on_text(" ".join(self._texts))

    def _get_model(self, model_size: str) -> Any:
        # Imported here because it takes a moment to load
        from faster_whisper import WhisperModel

        config = cm.ConfigManager.get_config_whisperx()
        device = "cpu" if config.use_cpu else "cuda"
        model_key = (model_size, device, config.compute_type)

        if self._model is None or self._model_key != model_key:
            self._model = None
            self._on_status(
                _(
                    "Loading the {model} model (it's downloaded the first time it's "
                    "used)…"
                ).format(model=model_size)
            )
            logger.info("Loading live transcription model %s", model_key)
            self._model = WhisperModel(
                model_size,
                device=device,
                compute_type=config.compute_type,
                # Leaves cores for the recording and the interface
                cpu_threads=max((os.cpu_count() or 4) // 2, 1),
            )
            self._model_key = model_key

        return self._model

    def _transcribe(self, model: Any, phrase: np.ndarray) -> str:
        previous_text = " ".join(self._texts)[-PROMPT_CHARACTERS:]
        prompt = " ".join(part for part in (self._prompt, previous_text) if part)
        segments, info = model.transcribe(
            phrase,
            language=self._language,
            task=self._task,
            beam_size=1,
            condition_on_previous_text=False,
            initial_prompt=prompt or None,
            without_timestamps=True,
            vad_filter=False,
        )
        text = " ".join(
            segment.text.strip()
            for segment in segments
            if segment.no_speech_prob < MAX_NO_SPEECH_PROBABILITY
        ).strip()

        if self._language is None and info.language_probability >= LANGUAGE_PROBABILITY:
            self._language = info.language

        return text
