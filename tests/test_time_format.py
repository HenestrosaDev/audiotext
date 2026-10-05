import pytest

from utils.enums import ModelSize
from utils.time_format import (
    format_duration,
    format_elapsed_time,
    format_segment_range,
    format_segment_time,
    format_timestamp,
    parse_segment_time,
)


def test_format_timestamp_without_hours() -> None:
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(65.9) == "01:05"
    assert format_timestamp(3599) == "59:59"


def test_format_timestamp_with_hours() -> None:
    assert format_timestamp(3600) == "01:00:00"
    assert format_timestamp(3661.5) == "01:01:01"


def test_format_duration_rounds_down_like_the_positions() -> None:
    assert format_duration(59.6) == "00:59"
    assert format_duration(3599.6) == "59:59"
    assert format_duration(209.6) == format_timestamp(209.6)


def test_english_only_models() -> None:
    assert ModelSize.is_english_only_model("small.en")
    assert ModelSize.is_english_only_model("distil-large-v3.5")
    assert not ModelSize.is_english_only_model("large-v3-turbo")
    assert not ModelSize.is_english_only_model("unknown")


def test_format_elapsed_time() -> None:
    assert format_elapsed_time(4.6) == "5 s"
    assert format_elapsed_time(125) == "2 min 5 s"


def test_format_segment_time() -> None:
    assert format_segment_time(65.9, is_precise=False) == "01:05"
    assert format_segment_time(65.9, is_precise=True) == "00:01:05,900"
    assert format_segment_time(3661.25, is_precise=True) == "01:01:01,250"


def test_format_segment_range() -> None:
    assert format_segment_range(1.5, 3, is_precise=False) == "00:01 – 00:03"
    assert (
        format_segment_range(1.5, 3, is_precise=True) == "00:00:01,500 – 00:00:03,000"
    )


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("5", 5),
        ("90", 90),
        ("01:05,9", 65.9),
        ("1:05.900", 65.9),
        ("75:00", 4500),
        (" 00:01:05,900 ", 3665.9 - 3600),
        ("1:00:00", 3600),
    ],
)
def test_parse_segment_time(text: str, seconds: float) -> None:
    assert parse_segment_time(text) == pytest.approx(seconds)


@pytest.mark.parametrize(
    "text", ["", "a", "-1", "1:75", "1:60:00", "1::2", "1:2:3:4", "nan", "inf"]
)
def test_parse_segment_time_rejects_invalid_times(text: str) -> None:
    with pytest.raises(ValueError):
        parse_segment_time(text)
