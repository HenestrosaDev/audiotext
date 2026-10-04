import threading
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from handlers.live_transcriber import (
    SAMPLE_RATE,
    LiveTranscriber,
    PhraseSplitter,
    get_dbfs,
    resample,
)

BLOCK = int(SAMPLE_RATE * 0.1)


def block(dbfs: float) -> tuple[np.ndarray, float]:
    return np.full(BLOCK, 10 ** (dbfs / 20), dtype=np.float32), dbfs


def feed(splitter: PhraseSplitter, dbfs: float, count: int) -> list[np.ndarray]:
    phrases = []
    for _ in range(count):
        if (phrase := splitter.feed(*block(dbfs))) is not None:
            phrases.append(phrase)
    return phrases


def test_get_dbfs() -> None:
    assert get_dbfs(np.ones(100, dtype=np.float32)) == pytest.approx(0)
    assert get_dbfs(np.full(100, 0.1, dtype=np.float32)) == pytest.approx(-20)
    assert get_dbfs(np.zeros(100, dtype=np.float32)) == -60


def test_resample_changes_the_number_of_samples() -> None:
    samples = np.zeros(48000, dtype=np.float32)

    assert len(resample(samples, 48000, SAMPLE_RATE)) == SAMPLE_RATE
    assert resample(samples, SAMPLE_RATE, SAMPLE_RATE) is samples


def test_phrases_end_at_the_pauses() -> None:
    splitter = PhraseSplitter()
    pause_blocks = round(PhraseSplitter.PAUSE_SECONDS / 0.1)

    assert feed(splitter, -55, 10) == []  # Background noise
    assert feed(splitter, -20, 15) == []  # Speech
    phrases = feed(splitter, -55, pause_blocks + 5)  # A pause

    assert len(phrases) == 1
    # The speech and the silence before and after it
    assert 1.5 < len(phrases[0]) / SAMPLE_RATE < 3.5


def test_long_phrases_are_cut() -> None:
    splitter = PhraseSplitter()
    feed(splitter, -55, 3)
    max_blocks = round(PhraseSplitter.MAX_PHRASE_SECONDS / 0.1)

    assert len(feed(splitter, -20, max_blocks + 1)) == 1


def test_flush_returns_the_phrase_being_said() -> None:
    splitter = PhraseSplitter()

    assert splitter.flush() is None
    feed(splitter, -55, 3)
    feed(splitter, -20, 5)
    assert splitter.flush() is not None


class FakeModel:
    def __init__(self) -> None:
        self.prompts: list[str | None] = []

    def transcribe(self, audio: np.ndarray, **kwargs: Any) -> tuple[Any, Any]:
        self.prompts.append(kwargs["initial_prompt"])
        segments = [
            SimpleNamespace(text=f" phrase {len(self.prompts)}", no_speech_prob=0.1),
            SimpleNamespace(text=" hallucination", no_speech_prob=0.9),
        ]
        return iter(segments), SimpleNamespace(language="es", language_probability=0.9)


def test_live_transcriber_shows_the_text_of_each_phrase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    texts: list[str] = []
    received = threading.Event()

    def on_text(text: str) -> None:
        texts.append(text)
        if len(texts) == 2:
            received.set()

    model = FakeModel()
    transcriber = LiveTranscriber(on_text=on_text, on_status=lambda _message: None)
    monkeypatch.setattr(transcriber, "_get_model", lambda _size: model)
    transcriber.start("tiny", sample_rate=48000, prompt=" Audiotext. ")

    def say(dbfs: float, seconds: float) -> None:
        samples = np.full(1024, 10 ** (dbfs / 20) * 32767, dtype=np.int16)
        for _ in range(round(seconds * 48000 / 1024)):
            transcriber.feed(samples.tobytes())

    for _ in range(2):
        say(-55, 2)
        say(-20, 1)
    say(-55, 2)

    assert received.wait(5)
    transcriber.stop()

    assert texts == ["phrase 1", "phrase 1 phrase 2"]
    # The keywords and the previous text are given as context, and the language
    # is kept
    assert model.prompts == ["Audiotext.", "Audiotext. phrase 1"]
    assert transcriber._language == "es"
