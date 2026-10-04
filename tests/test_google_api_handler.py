from unittest.mock import MagicMock

import pytest
import speech_recognition as sr

from handlers.google_api_handler import GoogleApiHandler
from models.transcription import Transcription


@pytest.fixture
def recognize_google(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(return_value="hello world")
    monkeypatch.setattr(sr.Recognizer, "recognize_google", mock)
    return mock


def test_transcription_is_punctuated(
    recognize_google: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    audio_data = sr.AudioData(b"\0\0", 16000, 2)

    text = GoogleApiHandler.transcribe(audio_data, Transcription(language_code="en"))

    assert text == "hello world. "
    recognize_google.assert_called_once_with(audio_data, language="en", key=None)


def test_api_key_is_used_if_set(
    recognize_google: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")

    GoogleApiHandler.transcribe(sr.AudioData(b"\0\0", 16000, 2), Transcription())

    assert recognize_google.call_args.kwargs["key"] == "google-key"


def test_free_tier_is_used_without_env_variable(
    recognize_google: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    GoogleApiHandler.transcribe(sr.AudioData(b"\0\0", 16000, 2), Transcription())

    assert recognize_google.call_args.kwargs["key"] is None
