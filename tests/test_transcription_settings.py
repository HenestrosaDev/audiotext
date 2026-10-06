from pathlib import Path

import pytest

from models.transcription import Transcription
from models.transcription_settings import (
    SAME_LANGUAGE,
    TranscriptionSettings,
    TranslationMode,
)
from utils.enums import AudioSource, TranscriptionMethod


def test_same_language_is_not_a_translation() -> None:
    settings = TranscriptionSettings(input_language="es", output_language="es")
    transcription = settings.to_transcription(AudioSource.FILE, "/a.mp3")

    assert settings.effective_translation_mode is None
    assert transcription.language_code == "es"
    assert not transcription.should_translate


def test_auto_detect_language_is_none() -> None:
    transcription = TranscriptionSettings(
        input_language="auto", output_language=SAME_LANGUAGE
    ).to_transcription(AudioSource.FILE, "/a.mp3")

    assert transcription.language_code is None


def test_whisper_translates_into_english() -> None:
    settings = TranscriptionSettings(
        input_language="es",
        output_language="en",
        translation_mode=TranslationMode.WHISPER.value,
    )
    transcription = settings.to_transcription(AudioSource.FILE, "/a.mp3")

    assert settings.effective_translation_mode == TranslationMode.WHISPER
    assert transcription.should_translate
    assert transcription.language_code == "es"


@pytest.mark.parametrize(
    "mode", [TranslationMode.WHISPER, TranslationMode.FORCE_LANGUAGE]
)
def test_other_languages_force_the_output_language(mode: TranslationMode) -> None:
    settings = TranscriptionSettings(
        input_language="en", output_language="fr", translation_mode=mode.value
    )
    transcription = settings.to_transcription(AudioSource.FILE, "/a.mp3")

    assert settings.effective_translation_mode == TranslationMode.FORCE_LANGUAGE
    assert transcription.language_code == "fr"
    assert not transcription.should_translate


def test_google_api_does_not_translate() -> None:
    settings = TranscriptionSettings(
        method=TranscriptionMethod.GOOGLE_API.value,
        input_language="es",
        output_language="en",
        output_file_types=["srt"],
    )
    transcription = settings.to_transcription(AudioSource.FILE, "/a.mp3")

    assert settings.effective_translation_mode is None
    assert transcription.language_code == "es"
    assert transcription.output_file_types == ["txt"]


def test_whisperx_only_options_are_ignored_by_the_apis() -> None:
    settings = TranscriptionSettings(
        method=TranscriptionMethod.WHISPER_API.value,
        response_format="srt",
        align_words=True,
        diarize=True,
        num_speakers=2,
        isolate_speech=True,
    )
    transcription = settings.to_transcription(AudioSource.FILE, "/a.mp3")

    assert transcription.output_file_types == ["srt"]
    # Only the files of a folder are saved in the response format
    assert transcription.api_response_format == "text"
    folder = settings.to_transcription(AudioSource.DIRECTORY, "/music")
    assert folder.api_response_format == "srt"
    assert not transcription.should_align_words
    assert not transcription.should_diarize
    assert transcription.num_speakers is None
    assert transcription.should_isolate_speech


def test_sources() -> None:
    settings = TranscriptionSettings(output_dir="/out")

    url = settings.to_transcription(
        AudioSource.YOUTUBE, "https://youtu.be/x", media_path=Path("/m/x")
    )
    folder = settings.to_transcription(AudioSource.DIRECTORY, "/music")
    mic = settings.to_transcription(AudioSource.MIC, "", mic_device_index=2)

    assert url.url == "https://youtu.be/x"
    assert url.media_path == Path("/m/x")
    assert folder.audio_source_path == Path("/music")
    assert folder.should_autosave  # Folders are always saved
    assert not url.should_autosave and not mic.should_autosave
    assert folder.output_dir == Path("/out")
    assert mic.mic_device_index == 2


def test_round_trip_ignores_unknown_keys() -> None:
    settings = TranscriptionSettings(input_language="de", diarize=True)

    data = settings.to_dict() | {"removed_option": 1}

    assert TranscriptionSettings.from_dict(data) == settings


def test_live_transcription_is_only_for_the_microphone_with_whisperx() -> None:
    settings = TranscriptionSettings(live_transcription=True, live_model_size="base")

    assert settings.to_transcription(AudioSource.MIC, "").live_model_size == "base"
    assert settings.to_transcription(AudioSource.FILE, "/a.mp3").live_model_size is None

    api = TranscriptionSettings(
        method=TranscriptionMethod.WHISPER_API.value, live_transcription=True
    )
    assert api.to_transcription(AudioSource.MIC, "").live_model_size is None

    disabled = TranscriptionSettings(live_transcription=False)
    assert disabled.to_transcription(AudioSource.MIC, "").live_model_size is None


def test_the_model_of_whisperx_is_passed() -> None:
    settings = TranscriptionSettings(model_size="tiny")

    assert settings.to_transcription(AudioSource.FILE, "/a.mp3").model_size == "tiny"

    api = TranscriptionSettings(
        method=TranscriptionMethod.WHISPER_API.value, model_size="tiny"
    )
    assert api.to_transcription(AudioSource.FILE, "/a.mp3").model_size is None


def test_the_prompt_and_the_model_of_the_openai_api_are_passed() -> None:
    settings = TranscriptionSettings(
        method=TranscriptionMethod.WHISPER_API.value,
        openai_model="gpt-transcribe",
        prompt="  An interview ",
        keywords=" Audiotext, , WhisperX ",
    )

    transcription = settings.to_transcription(AudioSource.FILE, "/a.mp3")

    assert transcription.api_model == "gpt-transcribe"
    assert transcription.prompt == "An interview"
    assert transcription.keywords == ["Audiotext", "WhisperX"]


def test_the_openai_model_is_only_passed_to_the_whisper_api() -> None:
    transcription = TranscriptionSettings(
        method=TranscriptionMethod.WHISPERX.value,
        openai_model="gpt-transcribe",
        prompt="Names",
    ).to_transcription(AudioSource.FILE, "/a.mp3")

    assert transcription.api_model is None
    assert transcription.prompt == "Names"


def test_the_google_api_ignores_the_prompt_and_the_keywords() -> None:
    transcription = TranscriptionSettings(
        method=TranscriptionMethod.GOOGLE_API.value, prompt="A talk", keywords="Names"
    ).to_transcription(AudioSource.FILE, "/a.mp3")

    assert transcription.prompt == ""
    assert transcription.keywords == []


def test_whisper_gets_the_keywords_in_the_prompt() -> None:
    transcription = Transcription(prompt=" A talk ", keywords=["Audiotext", "WhisperX"])

    assert transcription.whisper_prompt == "Audiotext, WhisperX. A talk"
    assert Transcription(keywords=["Audiotext"]).whisper_prompt == "Audiotext."
    assert Transcription(prompt="A talk").whisper_prompt == "A talk"
    assert Transcription().whisper_prompt == ""
