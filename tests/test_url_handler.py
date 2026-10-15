import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

import handlers.url_handler as url_handler
from handlers.url_handler import CHUNK_SIZE, UrlHandler, get_media_extension
from utils.cancellation import CancellationToken, TranscriptionCancelledError


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


class MediaServer(BaseHTTPRequestHandler):
    """Serves the files of `ROUTES` by their path, with their content type."""

    ROUTES: dict[str, tuple[str, bytes]] = {
        "/talk.mp3": ("audio/mpeg", b"ID3" + b"\0" * 1000),
        "/stream": ("audio/mpeg", b"\0" * 1000),
        "/page": ("text/html; charset=utf-8", b"<html></html>"),
        "/big.mp3": ("audio/mpeg", b"\0" * (CHUNK_SIZE * 4)),
    }

    def do_GET(self) -> None:
        route = self.ROUTES.get(self.path)
        if route is None:
            self.send_error(404)
            return
        content_type, body = route
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: Any) -> None:
        pass


@pytest.fixture(scope="module")
def server_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), MediaServer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize(
    ("route", "extension"),
    # By the extension of its path, or by its content type
    [("/talk.mp3", ".mp3"), ("/stream", ".mp3")],
)
def test_media_files_are_downloaded(
    server_url: str, tmp_path: Path, route: str, extension: str
) -> None:
    output_path = tmp_path / "downloads" / "media"

    file_path = UrlHandler.download(server_url + route, output_path)

    assert file_path == output_path.with_suffix(extension)
    assert file_path.read_bytes() == MediaServer.ROUTES[route][1]


def test_a_page_is_not_downloaded(server_url: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="doesn't point to an audio or video"):
        UrlHandler.download(server_url + "/page", tmp_path / "downloads" / "media")

    assert list((tmp_path / "downloads").iterdir()) == []


def test_a_failed_download_explains_why(server_url: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="could not be downloaded.*404"):
        UrlHandler.download(server_url + "/missing.mp3", tmp_path / "media")


def test_a_cancelled_download_removes_the_partial_file(
    server_url: str, tmp_path: Path
) -> None:
    token = CancellationToken()
    token.cancel()

    with pytest.raises(TranscriptionCancelledError):
        UrlHandler.download(
            server_url + "/big.mp3", tmp_path / "downloads" / "media", token
        )

    assert list((tmp_path / "downloads").iterdir()) == []


def test_youtube_videos_are_downloaded_as_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str, str]] = []

    def download_audio(url: str, output_path: str, output_filename: str) -> Path:
        calls.append((url, output_path, output_filename))
        return Path(output_path) / output_filename

    monkeypatch.setattr(
        url_handler.YouTubeHandler, "download_audio_from_video", download_audio
    )
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    file_path = UrlHandler.download(url, tmp_path / "videos" / "entry")

    assert calls == [(url, str(tmp_path / "videos"), "entry.m4a")]
    assert file_path == tmp_path / "videos" / "entry.m4a"
