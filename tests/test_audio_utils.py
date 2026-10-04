from array import array
from pathlib import Path

import pytest
import speech_recognition as sr
from pydub import AudioSegment
from pydub.generators import Sine

import utils.audio_utils as audio_utils
from tests.conftest import make_tone
from utils.audio_utils import (
    audio_segment_to_audio_data,
    get_audio_level,
    save_audio_data,
)


def test_save_audio_data_writes_a_wav_file(tmp_path: Path) -> None:
    audio_data = audio_segment_to_audio_data(make_tone(duration_ms=500))
    file_path = tmp_path / "recording.wav"

    save_audio_data(audio_data, file_path)

    saved_audio = AudioSegment.from_wav(file_path)
    assert len(saved_audio) == pytest.approx(500, abs=5)


def test_save_audio_data_without_audio_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No audio was recorded"):
        save_audio_data(sr.AudioData(b"", 16000, 2), tmp_path / "recording.wav")


def test_audio_segment_to_audio_data_converts_to_mono() -> None:
    stereo_audio = make_tone(duration_ms=200).set_channels(2)

    audio_data = audio_segment_to_audio_data(stereo_audio)

    assert audio_data.sample_rate == stereo_audio.frame_rate
    assert audio_data.sample_width == stereo_audio.sample_width
    assert len(audio_data.frame_data) == len(stereo_audio.raw_data) // 2


def samples_to_bytes(samples: list[int]) -> bytes:
    return array("h", samples).tobytes()


def test_silence_has_no_level() -> None:
    assert get_audio_level(samples_to_bytes([0] * 100), sample_width=2) == 0


def test_full_scale_audio_has_maximum_level() -> None:
    frames = samples_to_bytes([32767, -32767] * 50)

    assert get_audio_level(frames, sample_width=2) == pytest.approx(1, abs=0.01)


def test_level_grows_with_loudness() -> None:
    quiet = get_audio_level(samples_to_bytes([100, -100] * 50), sample_width=2)
    loud = get_audio_level(samples_to_bytes([10000, -10000] * 50), sample_width=2)

    assert 0 < quiet < loud < 1


def test_unsupported_sample_width_has_no_level() -> None:
    assert get_audio_level(b"\x7f" * 100, sample_width=1) == 0


def test_level_to_dbfs_is_the_inverse_of_the_level() -> None:
    assert audio_utils.level_to_dbfs(0) == audio_utils.MIN_LEVEL_DBFS
    assert audio_utils.level_to_dbfs(1) == 0
    assert audio_utils.level_to_dbfs(0.5) == audio_utils.MIN_LEVEL_DBFS / 2


def test_speech_detector_adapts_to_the_noise_floor() -> None:
    detector = audio_utils.SpeechDetector()
    hold = audio_utils.SpeechDetector.HOLD_UPDATES

    # Background noise is not speech, however loud it is
    assert not any(detector.update(-35) for _ in range(5))
    # Speech is louder than the noise
    assert detector.update(-15)
    # It's still detected for a moment after it stops, and then it's not
    assert all(detector.update(-35) for _ in range(hold))
    assert not detector.update(-35)


def test_speech_detector_ignores_very_quiet_sounds() -> None:
    detector = audio_utils.SpeechDetector()
    detector.update(-60)

    assert not detector.update(-52)


def test_level_monitor_reports_silence_and_good_speech() -> None:
    monitor = audio_utils.LevelMonitor()
    InputLevel = audio_utils.InputLevel

    assert monitor.update(-50) == InputLevel.SILENCE
    assert monitor.update(-20) == InputLevel.GOOD


def test_level_monitor_reports_quiet_speech() -> None:
    monitor = audio_utils.LevelMonitor()
    monitor.update(-58)

    assert monitor.update(-44) == audio_utils.InputLevel.TOO_QUIET


def test_level_monitor_keeps_reporting_distortion_for_a_moment() -> None:
    monitor = audio_utils.LevelMonitor()
    hold = audio_utils.LevelMonitor.LOUD_HOLD_UPDATES

    assert monitor.update(-1) == audio_utils.InputLevel.TOO_LOUD
    assert all(
        monitor.update(-20) == audio_utils.InputLevel.TOO_LOUD for _ in range(hold - 1)
    )
    assert monitor.update(-20) != audio_utils.InputLevel.TOO_LOUD


def test_level_monitor_reports_no_signal_after_a_while() -> None:
    monitor = audio_utils.LevelMonitor()
    updates = audio_utils.LevelMonitor.NO_SIGNAL_UPDATES
    minimum = audio_utils.MIN_LEVEL_DBFS

    assert all(
        monitor.update(minimum) == audio_utils.InputLevel.SILENCE
        for _ in range(updates - 1)
    )
    assert monitor.update(minimum) == audio_utils.InputLevel.NO_SIGNAL


def test_isolate_speech_writes_a_mono_wav(tmp_path: Path) -> None:
    source = tmp_path / "tone.wav"
    Sine(440).to_audio_segment(duration=500).set_channels(2).export(
        source, format="wav"
    )

    output = audio_utils.isolate_speech(source, tmp_path / "speech.wav")
    audio = AudioSegment.from_wav(output)

    assert audio.channels == 1
    assert audio.frame_rate == 16000
    assert len(audio) == pytest.approx(500, abs=20)


def test_isolate_speech_raises_os_error_on_invalid_files(tmp_path: Path) -> None:
    source = tmp_path / "invalid.mp3"
    source.write_text("not audio")

    with pytest.raises(OSError):
        audio_utils.isolate_speech(source, tmp_path / "speech.wav")
