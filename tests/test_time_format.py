from utils.enums import ModelSize
from utils.time_format import format_duration, format_elapsed_time, format_timestamp


def test_format_timestamp_without_hours() -> None:
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(65.9) == "01:05"
    assert format_timestamp(3599) == "59:59"


def test_format_timestamp_with_hours() -> None:
    assert format_timestamp(3600) == "01:00:00"
    assert format_timestamp(3661.5) == "01:01:01"


def test_format_duration_rounds() -> None:
    assert format_duration(59.6) == "01:00"
    assert format_duration(3599.6) == "01:00:00"


def test_english_only_models() -> None:
    assert ModelSize.is_english_only_model("small.en")
    assert ModelSize.is_english_only_model("distil-large-v3.5")
    assert not ModelSize.is_english_only_model("large-v3-turbo")
    assert not ModelSize.is_english_only_model("unknown")


def test_format_elapsed_time() -> None:
    assert format_elapsed_time(4.6) == "5 s"
    assert format_elapsed_time(125) == "2 min 5 s"
