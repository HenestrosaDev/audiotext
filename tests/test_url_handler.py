import pytest

from handlers.url_handler import get_media_extension


@pytest.mark.parametrize(
    ("url", "content_type", "expected"),
    [
        ("https://example.com/talk.MP3", "text/html", ".mp3"),
        ("https://example.com/a%20b.mp4?x=1", "", ".mp4"),
        ("https://example.com/stream", "audio/mpeg", ".mp3"),
        ("https://example.com/stream", "video/x-unknown", ".media"),
        ("https://example.com/page", "text/html; charset=utf-8", None),
        ("https://example.com/file.bin", "application/octet-stream", ".bin"),
        ("https://example.com/", "application/octet-stream", None),
    ],
)
def test_get_media_extension(url: str, content_type: str, expected: str | None) -> None:
    assert get_media_extension(url, content_type) == expected
