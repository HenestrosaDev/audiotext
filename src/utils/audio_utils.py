import logging
import math
import subprocess
from array import array
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import speech_recognition as sr
from pydub import AudioSegment

from utils.i18n import _

logger = logging.getLogger(__name__)

# Level (dBFS) shown as silence in the recording level meter
MIN_LEVEL_DBFS = -60
_MAX_16_BIT_AMPLITUDE = 32768


def save_audio_data(audio_data: sr.AudioData, file_path: Path) -> None:
    """
    Save recorded audio data to a WAV file.

    :param audio_data: The recorded audio.
    :param file_path: The path of the file to save the audio data to.
    :raises ValueError: If there is no audio data to save.
    """
    if not audio_data.frame_data:
        raise ValueError(_("No audio was recorded."))

    audio = AudioSegment(
        audio_data.frame_data,
        sample_width=audio_data.sample_width,
        frame_rate=audio_data.sample_rate,
        channels=1,
    )
    audio.export(file_path, format="wav")


def audio_segment_to_audio_data(audio_segment: AudioSegment) -> sr.AudioData:
    """
    Converts a pydub `AudioSegment` into a SpeechRecognition `AudioData` object.

    :param audio_segment: The audio segment to convert.
    :return: The same audio, as mono `AudioData`.
    """
    mono_audio = audio_segment.set_channels(1)
    return sr.AudioData(
        mono_audio.raw_data, mono_audio.frame_rate, mono_audio.sample_width
    )


def get_audio_level(frames: bytes, sample_width: int) -> float:
    """
    Calculates the loudness of 16-bit audio, scaled to show it in a level meter.

    :param frames: Raw audio in the native byte order.
    :param sample_width: The size of each sample in bytes. Only 16-bit audio (2
                         bytes) is supported; other widths return 0.
    :return: The level, from 0 (silence or below `MIN_LEVEL_DBFS`) to 1 (maximum).
    """
    if sample_width != 2 or len(frames) < 2:
        return 0.0

    samples = array("h", frames[: len(frames) // 2 * 2])

    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    if rms == 0:
        return 0.0

    dbfs = 20 * math.log10(rms / _MAX_16_BIT_AMPLITUDE)
    return min(max(1 - dbfs / MIN_LEVEL_DBFS, 0.0), 1.0)


def level_to_dbfs(level: float) -> float:
    """
    Converts a level returned by `get_audio_level` back to dBFS.

    :param level: The level, from 0 to 1.
    :return: The loudness in dBFS, from `MIN_LEVEL_DBFS` to 0.
    """
    return float(MIN_LEVEL_DBFS * (1 - min(max(level, 0.0), 1.0)))


class SpeechDetector:
    """
    Detects whether there is speech in the recording, comparing the loudness with
    the background noise. The noise floor follows the quietest moments: it drops
    at once to quieter levels and rises slowly, so speech doesn't raise it.
    """

    # Speech is this many decibels above the noise floor
    SPEECH_MARGIN_DB = 12.0
    # Nothing quieter than this is speech, whatever the noise floor
    MIN_SPEECH_DBFS = -50.0
    # How fast the noise floor rises per update, in decibels
    NOISE_FLOOR_RISE_DB = 0.05
    # Updates that speech is still considered detected after it stops, so the
    # indicator doesn't flicker between words
    HOLD_UPDATES = 5

    def __init__(self) -> None:
        self.noise_floor_dbfs = float(MIN_LEVEL_DBFS)
        self._is_initialized = False
        self._hold = 0

    def update(self, dbfs: float) -> bool:
        """
        :param dbfs: The loudness of the last chunk of audio.
        :return: Whether there is speech.
        """
        if not self._is_initialized or dbfs < self.noise_floor_dbfs:
            self.noise_floor_dbfs = dbfs
            self._is_initialized = True
        else:
            self.noise_floor_dbfs += self.NOISE_FLOOR_RISE_DB

        is_loud = dbfs >= max(
            self.noise_floor_dbfs + self.SPEECH_MARGIN_DB, self.MIN_SPEECH_DBFS
        )

        if is_loud:
            self._hold = self.HOLD_UPDATES
            return True

        if self._hold > 0:
            self._hold -= 1
            return True

        return False


class InputLevel(Enum):
    """How the level of the microphone is for transcribing speech."""

    # Nothing is being received, e.g. the microphone is muted or not allowed
    NO_SIGNAL = "no_signal"
    # Only background noise, nobody is speaking
    SILENCE = "silence"
    TOO_QUIET = "too_quiet"
    GOOD = "good"
    # Close to the maximum, so the audio is distorted
    TOO_LOUD = "too_loud"


class LevelMonitor:
    """
    Tells whether the level of the microphone is right for transcribing, from the
    loudness of the speech and of its peaks.
    """

    # Peaks this loud are distorted
    CLIPPING_DBFS = -3.0
    # Speech quieter than this, on average, is harder to transcribe
    QUIET_SPEECH_DBFS = -40.0
    # Updates without any sound before telling that nothing is received
    NO_SIGNAL_UPDATES = 20
    # Updates that a distorted peak keeps being reported, so it can be read
    LOUD_HOLD_UPDATES = 15
    # Weight of the last update in the average loudness of the speech
    SMOOTHING = 0.2

    def __init__(self) -> None:
        self._speech_detector = SpeechDetector()
        self._speech_dbfs: float | None = None
        self._silent_updates = 0
        self._loud_hold = 0

    def update(self, dbfs: float) -> InputLevel:
        """
        :param dbfs: The loudness of the last chunk of audio.
        :return: How the level of the microphone is.
        """
        is_speech = self._speech_detector.update(dbfs)

        self._silent_updates = self._silent_updates + 1 if dbfs <= MIN_LEVEL_DBFS else 0
        if dbfs >= self.CLIPPING_DBFS:
            self._loud_hold = self.LOUD_HOLD_UPDATES
        elif self._loud_hold > 0:
            self._loud_hold -= 1

        if self._loud_hold > 0:
            return InputLevel.TOO_LOUD
        if self._silent_updates >= self.NO_SIGNAL_UPDATES:
            return InputLevel.NO_SIGNAL
        if not is_speech:
            return InputLevel.SILENCE

        # Only the chunks with speech count, not the pauses between words
        noise_floor = self._speech_detector.noise_floor_dbfs
        if dbfs >= noise_floor + SpeechDetector.SPEECH_MARGIN_DB:
            if self._speech_dbfs is None:
                self._speech_dbfs = dbfs
            else:
                self._speech_dbfs += self.SMOOTHING * (dbfs - self._speech_dbfs)

        if self._speech_dbfs is not None and self._speech_dbfs < self.QUIET_SPEECH_DBFS:
            return InputLevel.TOO_QUIET
        return InputLevel.GOOD


# Keeps the frequencies of the voice, reduces the stationary noise and evens out
# the volume, which helps with music, hum and quiet speakers
SPEECH_FILTER = (
    "highpass=f=80,lowpass=f=8000,afftdn=nr=12:nf=-30:tn=1,dynaudnorm=f=150:g=15:p=0.9"
)


def isolate_speech(source_path: Path, output_path: Path) -> Path:
    """
    Writes a copy of the audio of a file with the speech enhanced and the music
    and background noise reduced, as a 16 kHz mono WAV file.

    :raises OSError: If FFmpeg can't process the file.
    :return: `output_path`.
    """
    try:
        subprocess.run(
            [
                AudioSegment.converter,
                *("-nostdin", "-hide_banner", "-loglevel", "error", "-y"),
                *("-i", str(source_path)),
                *("-vn", "-af", SPEECH_FILTER, "-ac", "1", "-ar", "16000"),
                str(output_path),
            ],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        message = e.stderr.decode(errors="replace").strip() or str(e)
        raise OSError(message) from e

    return output_path


@dataclass(frozen=True)
class InputDevice:
    index: int
    name: str
    is_default: bool


def list_input_devices() -> list[InputDevice]:
    """
    Lists the devices that can record audio. Their indexes are the PortAudio ones,
    which `Microphone` also uses.

    :return: The devices, or an empty list if they can't be listed.
    """
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        default_index = sd.default.device[0]
    except Exception:
        logger.exception("Could not list the input devices")
        return []

    return [
        InputDevice(
            index=idx, name=str(device["name"]), is_default=idx == default_index
        )
        for idx, device in enumerate(devices)
        if device["max_input_channels"] > 0
    ]


class Microphone:
    """
    Records 16-bit mono audio from an input device, in chunks. It uses sounddevice,
    whose wheels include PortAudio, so nothing has to be compiled to install it
    (unlike PyAudio, which `speech_recognition.Microphone` needs).
    """

    SAMPLE_WIDTH = 2
    # Frames read at a time
    CHUNK = 1024

    def __init__(self, device_index: int | None = None) -> None:
        """
        :param device_index: The PortAudio index of the device. By default, the
                             default input device of the system.
        :raises sounddevice.PortAudioError: If the device can't be opened.
        """
        import sounddevice as sd

        device = sd.query_devices(device_index, "input")
        # The native sample rate of the device, which every device supports
        self.sample_rate = int(device["default_samplerate"])
        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self.CHUNK,
            device=device_index,
            channels=1,
            dtype="int16",
        )

    def __enter__(self) -> "Microphone":
        self._stream.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stream.stop()
        self._stream.close()

    def read(self) -> bytes:
        """
        Waits for the next chunk of audio.

        :return: `CHUNK` frames of 16-bit audio, in the native byte order.
        """
        data, _overflowed = self._stream.read(self.CHUNK)
        return bytes(data)
