import io
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

import handlers.url_handler as url_handler
from handlers.url_handler import UrlHandler, get_content_length, get_media_extension


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, headers: dict[str, str]) -> None:
        super().__init__(body)
        self.headers = Message()
        for name, value in headers.items():
            self.headers[name] = value

    def geturl(self) -> str:
        return "https://example.com/talk.mp3"


def fake_urlopen(
    monkeypatch: pytest.MonkeyPatch, body: bytes, headers: dict[str, str]
) -> None:
    def urlopen(*_args: Any, **_kwargs: Any) -> FakeResponse:
        return FakeResponse(body, headers)

    monkeypatch.setattr(url_handler.urllib.request, "urlopen", urlopen)


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


def headers(**values: str) -> Message:
    message = Message()
    for name, value in values.items():
        message[name.replace("_", "-")] = value
    return message


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"Content_Length": "1024"}, 1024),
        ({"Content_Length": "1024", "Content_Encoding": "identity"}, 1024),
        # The size is the one of the compressed body, not of the file
        ({"Content_Length": "1024", "Content_Encoding": "gzip"}, None),
        ({}, None),
        ({"Content_Length": "0"}, None),
        ({"Content_Length": "unknown"}, None),
    ],
)
def test_get_content_length(values: dict[str, str], expected: int | None) -> None:
    assert get_content_length(headers(**values)) == expected


def test_the_download_reports_the_bytes_downloaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(url_handler, "CHUNK_SIZE", 100)
    fake_urlopen(
        monkeypatch,
        b"x" * 400,
        {"Content-Type": "audio/mpeg", "Content-Length": "400"},
    )
    reports: list[tuple[float, float]] = []

    path = UrlHandler.download(
        "https://example.com/talk.mp3",
        tmp_path / "download",
        on_progress=lambda done, total: reports.append((done, total)),
    )

    assert path.read_bytes() == b"x" * 400
    assert reports == [(100, 400), (200, 400), (300, 400), (400, 400)]


def test_the_download_reports_nothing_if_the_size_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_urlopen(monkeypatch, b"x" * 400, {"Content-Type": "audio/mpeg"})
    reports: list[tuple[float, float]] = []

    UrlHandler.download(
        "https://example.com/talk.mp3",
        tmp_path / "download",
        on_progress=lambda done, total: reports.append((done, total)),
    )

    assert reports == []
