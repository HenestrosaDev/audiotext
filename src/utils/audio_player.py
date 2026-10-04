import logging
import subprocess
import threading
from typing import Any

import numpy as np
from pydub import AudioSegment

logger = logging.getLogger(__name__)

# Speeds supported by the FFmpeg `atempo` filter without chaining it
MIN_SPEED = 0.5
MAX_SPEED = 2.0


class PlaybackUnavailableError(Exception):
    """Raised when the audio can't be played on this system."""


def is_playback_available() -> bool:
    """
    :return: Whether the audio output library (sounddevice) can be loaded.
    """
    try:
        import sounddevice  # noqa: F401
    except (ImportError, OSError):
        return False

    return True


def change_speed(
    samples: np.ndarray, sample_rate: int, speed: float, output_rate: int
) -> np.ndarray:
    """
    Changes the speed of the audio keeping its pitch, and resamples it.

    :param samples: The 16-bit mono samples of the audio.
    :param sample_rate: The sample rate of `samples`.
    :param speed: The speed factor, between `MIN_SPEED` and `MAX_SPEED`.
    :param output_rate: The sample rate of the result.
    :return: The 16-bit mono samples of the processed audio.
    """
    if speed == 1 and sample_rate == output_rate:
        return samples

    pcm_format = ["-f", "s16le", "-ac", "1"]
    result = subprocess.run(
        [
            AudioSegment.converter,
            *("-hide_banner", "-loglevel", "error"),
            *pcm_format,
            *("-ar", str(sample_rate)),
            *("-i", "pipe:0"),
            *("-filter:a", f"atempo={speed}"),
            *pcm_format,
            *("-ar", str(output_rate)),
            "pipe:1",
        ],
        input=samples.astype(np.int16).tobytes(),
        capture_output=True,
        check=True,
    )

    return np.frombuffer(result.stdout, dtype=np.int16)


class AudioPlayer:
    """
    Plays mono 16-bit audio, allowing to pause it, seek and change its speed.

    The output stream is opened on the first call to `play` and runs until
    `close` is called, outputting silence while paused, so pausing and resuming
    is immediate.
    """

    def __init__(self, samples: np.ndarray, sample_rate: int) -> None:
        """
        :param samples: The 16-bit mono samples of the audio.
        :param sample_rate: The sample rate of the samples.
        """
        self._samples = samples
        self._sample_rate = sample_rate
        self._output_rate = sample_rate

        # Guards the playback state, shared with the audio thread
        self._lock = threading.Lock()
        self._buffers: dict[float, np.ndarray] = {}
        self._speed = 1.0
        self._buffer = samples
        self._position = 0  # Index of the next sample of `_buffer` to play
        self._is_playing = False
        self._stream: Any = None

    @property
    def duration(self) -> float:
        """The duration of the audio at normal speed, in seconds."""
        return len(self._samples) / self._sample_rate

    @property
    def position(self) -> float:
        """The current position, in seconds of the audio at normal speed."""
        with self._lock:
            return self._buffer_index_to_seconds(self._position)

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def speed(self) -> float:
        return self._speed

    def play(self) -> None:
        """
        Plays the audio from the current position, or from the beginning if it has
        reached the end.

        :raises PlaybackUnavailableError: If there is no audio output available.
        """
        self._ensure_stream()

        with self._lock:
            if self._position >= len(self._buffer):
                self._position = 0
            self._is_playing = True

    def pause(self) -> None:
        self._is_playing = False

    def toggle(self) -> None:
        """
        Pauses the audio if it's playing, and plays it otherwise.

        :raises PlaybackUnavailableError: If there is no audio output available.
        """
        if self._is_playing:
            self.pause()
        else:
            self.play()

    def seek(self, seconds: float) -> None:
        """
        Moves to the given position, keeping the audio playing or paused.

        :param seconds: The position, in seconds of the audio at normal speed. It's
                        clamped to the duration of the audio.
        """
        seconds = min(max(seconds, 0), self.duration)

        with self._lock:
            self._position = self._seconds_to_buffer_index(seconds)

    def set_speed(self, speed: float) -> None:
        """
        Changes the playback speed, keeping the position. The audio is processed
        the first time each speed is used, which can take a few seconds for long
        files, so it should be called from a background thread.

        :param speed: The speed factor, between `MIN_SPEED` and `MAX_SPEED`.
        :raises ValueError: If the speed is out of range.
        :raises PlaybackUnavailableError: If there is no audio output available.
        """
        if not MIN_SPEED <= speed <= MAX_SPEED:
            raise ValueError(f"The speed must be between {MIN_SPEED} and {MAX_SPEED}")

        self._ensure_stream()

        if speed not in self._buffers:
            self._buffers[speed] = change_speed(
                self._samples, self._sample_rate, speed, self._output_rate
            )

        with self._lock:
            seconds = self._buffer_index_to_seconds(self._position)
            self._speed = speed
            self._buffer = self._buffers[speed]
            self._position = self._seconds_to_buffer_index(seconds)

    def close(self) -> None:
        """Stops the playback and releases the audio output."""
        self._is_playing = False

        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                logger.exception("Could not close the audio stream")
            self._stream = None

    def _ensure_stream(self) -> None:
        """
        Opens the output stream, at the sample rate of the audio if the device
        supports it, or at the default rate of the device otherwise.

        :raises PlaybackUnavailableError: If there is no audio output available.
        """
        if self._stream is not None:
            return

        try:
            import sounddevice as sd

            try:
                sd.check_output_settings(
                    samplerate=self._sample_rate, channels=1, dtype="int16"
                )
                output_rate = self._sample_rate
            except sd.PortAudioError:
                device = sd.query_devices(kind="output")
                output_rate = int(device["default_samplerate"])

            if output_rate != self._output_rate:
                self._output_rate = output_rate
                self._buffers.clear()
                with self._lock:
                    self._buffer = change_speed(
                        self._samples, self._sample_rate, self._speed, output_rate
                    )
                    self._position = 0

            self._buffers[self._speed] = self._buffer

            self._stream = sd.OutputStream(
                samplerate=output_rate,
                channels=1,
                dtype="int16",
                callback=self._fill_output,
            )
            self._stream.start()
        except Exception as e:
            # sounddevice can't be loaded, there is no output device (PortAudioError)
            # or FFmpeg failed
            self._stream = None
            raise PlaybackUnavailableError(str(e)) from e

    def _fill_output(
        self, outdata: np.ndarray, frames: int, _time: Any, _status: Any
    ) -> None:
        """Fills the buffer of the output stream. Called from the audio thread."""
        with self._lock:
            if not self._is_playing:
                outdata.fill(0)
                return

            chunk = self._buffer[self._position : self._position + frames]
            outdata[: len(chunk), 0] = chunk
            outdata[len(chunk) :] = 0
            self._position += len(chunk)

            if self._position >= len(self._buffer):
                self._is_playing = False

    def _buffer_index_to_seconds(self, index: int) -> float:
        return index * self._speed / self._output_rate

    def _seconds_to_buffer_index(self, seconds: float) -> int:
        return min(round(seconds * self._output_rate / self._speed), len(self._buffer))
