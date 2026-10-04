import pytest

from utils.validators import (
    is_valid_non_negative_int,
    is_valid_positive_int,
    is_valid_temperature,
    is_valid_url,
    is_youtube_url,
)


@pytest.mark.parametrize("value", ["", "0", "0.5", "1", "1.0", ".5", "0."])
def test_valid_temperatures(value: str) -> None:
    assert is_valid_temperature(value)


@pytest.mark.parametrize("value", ["-0.1", "1.1", "abc", "2", "0.5.1"])
def test_invalid_temperatures(value: str) -> None:
    assert not is_valid_temperature(value)


@pytest.mark.parametrize("value", ["", "1", "8", "42"])
def test_valid_positive_ints(value: str) -> None:
    assert is_valid_positive_int(value)


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "a", " 1", "²"])
def test_invalid_positive_ints(value: str) -> None:
    assert not is_valid_positive_int(value)


@pytest.mark.parametrize("value", ["", "0", "2", "10"])
def test_valid_non_negative_ints(value: str) -> None:
    assert is_valid_non_negative_int(value)


@pytest.mark.parametrize("value", ["-1", "1.5", "a", " 1", "²"])
def test_invalid_non_negative_ints(value: str) -> None:
    assert not is_valid_non_negative_int(value)


@pytest.mark.parametrize(
    "value",
    [
        "https://www.youtube.com/watch?v=abc",
        "http://youtu.be/abc",
        "https://example.com/audio.mp3",
        ["https://example.com/a", "b"][0],
        "http://localhost:8000/file.wav",
    ],
)
def test_valid_urls(value: str) -> None:
    assert is_valid_url(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "youtube.com/watch?v=abc",
        "ftp://example.com/a.mp3",
        "https://",
        "https://example",
        "https://exa mple.com",
        "https://example.com:99999/",
        "javascript:alert(1)",
    ],
)
def test_invalid_urls(value: str) -> None:
    assert not is_valid_url(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://www.youtube.com/watch?v=abc", True),
        ("https://youtu.be/abc", True),
        ("https://m.youtube.com/shorts/abc", True),
        ("https://example.com/youtube.com.mp3", False),
        ("https://notyoutube.org/", False),
    ],
)
def test_is_youtube_url(value: str, expected: bool) -> None:
    assert is_youtube_url(value) is expected
