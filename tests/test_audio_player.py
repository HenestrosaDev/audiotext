import numpy as np
import pytest

from utils.audio_player import AudioPlayer, change_speed

SAMPLE_RATE = 16000


def make_player(seconds: float = 4) -> AudioPlayer:
    samples = np.arange(int(seconds * SAMPLE_RATE), dtype=np.int64) % 1000
    player = AudioPlayer(samples.astype(np.int16), SAMPLE_RATE)
    # Tests don't open an audio output
    player._ensure_stream = lambda: None  # type: ignore[method-assign]
    return player


def fill(player: AudioPlayer, frames: int) -> np.ndarray:
    """Imitates the audio thread asking for the next samples."""
    outdata = np.full((frames, 1), -1, dtype=np.int16)
    player._fill_output(outdata, frames, None, None)
    return outdata[:, 0]


def test_outputs_silence_while_paused() -> None:
    player = make_player()

    assert not fill(player, 100).any()
    assert player.position == 0


def test_plays_from_the_position() -> None:
    player = make_player()
    player.seek(1)
    player.play()

    output = fill(player, 100)

    assert list(output[:3]) == list(player._samples[SAMPLE_RATE : SAMPLE_RATE + 3])
    assert player.position == pytest.approx(1 + 100 / SAMPLE_RATE)


def test_stops_at_the_end_and_restarts_from_the_beginning() -> None:
    player = make_player(seconds=1)
    player.seek(1 - 50 / SAMPLE_RATE)
    player.play()

    output = fill(player, 100)

    assert not output[50:].any()
    assert not player.is_playing
    player.play()
    assert player.position == 0


def test_seek_is_clamped_to_the_duration() -> None:
    player = make_player(seconds=2)

    player.seek(-3)
    assert player.position == 0
    player.seek(10)
    assert player.position == pytest.approx(2)


def test_changing_the_speed_keeps_the_position() -> None:
    player = make_player()
    player.seek(2)

    player.set_speed(2.0)

    assert player.speed == 2.0
    assert player.position == pytest.approx(2, abs=0.01)
    # At double speed, the same output time covers twice the audio
    player.play()
    fill(player, SAMPLE_RATE // 2)
    assert player.position == pytest.approx(3, abs=0.01)


def test_invalid_speeds_are_rejected() -> None:
    with pytest.raises(ValueError):
        make_player().set_speed(3)


def test_change_speed_keeps_the_sample_rate_and_shortens_the_audio() -> None:
    samples = (np.sin(np.arange(SAMPLE_RATE * 2) / 10) * 10000).astype(np.int16)

    faster = change_speed(samples, SAMPLE_RATE, 2.0, SAMPLE_RATE)
    resampled = change_speed(samples, SAMPLE_RATE, 1.0, SAMPLE_RATE * 2)

    assert len(faster) == pytest.approx(SAMPLE_RATE, rel=0.05)
    assert len(resampled) == pytest.approx(SAMPLE_RATE * 4, rel=0.05)


def test_change_speed_returns_the_same_audio_if_nothing_changes() -> None:
    samples = np.zeros(10, dtype=np.int16)

    assert change_speed(samples, SAMPLE_RATE, 1.0, SAMPLE_RATE) is samples
