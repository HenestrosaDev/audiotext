from pathlib import Path

import pytest

from models.config.config_subtitles import ConfigSubtitles
from models.config.config_system import ConfigSystem
from models.config.config_transcription import ConfigTranscription
from models.config.config_whisper_api import ConfigWhisperApi
from models.config.config_whisperx import ConfigWhisperX
from utils.config_manager import ConfigManager


def test_values_are_parsed_with_the_type_of_the_dataclass_fields(
    config_file: Path,
) -> None:
    # Known values, since the app stores the user's choices in `config.ini`
    config_file.write_text(
        "[subtitles]\n"
        "highlight_words = False\n"
        "max_line_width = 42\n"
        "max_line_count = 2\n"
        "[whisper_api]\n"
        "response_format = text\n"
        "temperature = 0\n"
        "timestamp_granularities = word\n"
        "[whisperx]\n"
        "model_size = large-v2\n"
        "batch_size = 8\n"
        "compute_type = float16\n"
        "use_cpu = False\n"
        "can_use_gpu = False\n"
        "output_file_types = txt\n",
        encoding="utf-8",
    )

    config_subtitles = ConfigManager.get_config_subtitles()
    config_whisper_api = ConfigManager.get_config_whisper_api()
    config_whisperx = ConfigManager.get_config_whisperx()

    assert config_subtitles == ConfigSubtitles(
        highlight_words=False, max_line_count=2, max_line_width=42
    )
    assert config_whisper_api == ConfigWhisperApi(
        response_format="text", temperature=0.0, timestamp_granularities=["word"]
    )
    assert config_whisperx.batch_size == 8
    assert config_whisperx.use_cpu is False
    assert config_whisperx.output_file_types == ["txt"]


def test_all_sections_can_be_loaded() -> None:
    assert isinstance(ConfigManager.get_config_system(), ConfigSystem)
    assert isinstance(ConfigManager.get_config_transcription(), ConfigTranscription)
    assert isinstance(ConfigManager.get_config_whisperx(), ConfigWhisperX)


def test_modify_value_persists_the_new_value() -> None:
    ConfigManager.modify_value(
        ConfigWhisperX.Key.SECTION, ConfigWhisperX.Key.OUTPUT_FILE_TYPES, "srt, vtt"
    )
    ConfigManager.modify_value(
        ConfigWhisperX.Key.SECTION, ConfigWhisperX.Key.BATCH_SIZE, "16"
    )

    config_whisperx = ConfigManager.get_config_whisperx()
    assert config_whisperx.output_file_types == ["srt", "vtt"]
    assert config_whisperx.batch_size == 16


def test_values_can_contain_percent_signs() -> None:
    # A prompt or a path are typed by the user, so they can contain anything
    ConfigManager.modify_value(
        ConfigTranscription.Key.SECTION,
        ConfigTranscription.Key.PROMPT,
        "100% Audiotext, %(name)s",
    )

    assert ConfigManager.get_config_transcription().prompt == "100% Audiotext, %(name)s"


def test_empty_list_is_parsed_as_empty_list() -> None:
    ConfigManager.modify_value(
        ConfigWhisperX.Key.SECTION, ConfigWhisperX.Key.OUTPUT_FILE_TYPES, ""
    )

    assert ConfigManager.get_config_whisperx().output_file_types == []


def test_modify_value_creates_missing_keys_and_sections(
    user_config_file: Path,
) -> None:
    user_config_file.parent.mkdir()
    user_config_file.write_text("[transcription]\nlanguage = en\n")

    ConfigManager.modify_value(
        ConfigSystem.Key.SECTION, ConfigSystem.Key.UI_LANGUAGE, "es"
    )

    assert "[system]\nui_language = es" in user_config_file.read_text()


def test_modify_value_only_stores_the_changed_values_in_the_user_file(
    config_file: Path, user_config_file: Path
) -> None:
    defaults = config_file.read_text()

    ConfigManager.modify_value(
        ConfigSystem.Key.SECTION, ConfigSystem.Key.APPEARANCE_MODE, "Dark"
    )

    assert config_file.read_text() == defaults
    assert user_config_file.read_text() == "[system]\nappearance_mode = Dark\n\n"


def test_user_values_take_precedence_over_the_defaults(
    config_file: Path, user_config_file: Path
) -> None:
    config_file.write_text("[system]\nappearance_mode = System\nui_language = en\n")
    user_config_file.parent.mkdir()
    user_config_file.write_text("[system]\nui_language = es\n")

    assert ConfigManager.get_config_system() == ConfigSystem(
        appearance_mode="System", ui_language="es"
    )


def test_new_defaults_apply_to_the_values_not_changed_by_the_user(
    config_file: Path,
) -> None:
    ConfigManager.modify_value(
        ConfigWhisperX.Key.SECTION, ConfigWhisperX.Key.BATCH_SIZE, "16"
    )
    # An update of the app changes a default value
    config_file.write_text(
        config_file.read_text().replace("model_size = large-v2", "model_size = tiny")
    )

    config_whisperx = ConfigManager.get_config_whisperx()
    assert config_whisperx.model_size == "tiny"
    assert config_whisperx.batch_size == 16


def test_missing_keys_with_defaults_use_the_default(config_file: Path) -> None:
    # Configuration files from previous versions don't have the newest keys
    config_file.write_text("[system]\nappearance_mode = Dark\n")

    assert ConfigManager.get_config_system() == ConfigSystem(
        appearance_mode="Dark", ui_language="system"
    )


def test_missing_key_raises_value_error(config_file: Path) -> None:
    config_file.write_text("[system]\n")

    with pytest.raises(ValueError, match="appearance_mode"):
        ConfigManager.get_config_system()
