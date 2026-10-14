from pathlib import Path
from unittest.mock import MagicMock

import pytest

import handlers.youtube_handler as youtube_handler
from handlers.youtube_handler import YouTubeHandler


def mock_youtube(monkeypatch: pytest.MonkeyPatch, stream: MagicMock | None) -> None:
    youtube = MagicMock()
    youtube.streams.filter.return_value.first.return_value = stream
    monkeypatch.setattr(youtube_handler, "YouTube", MagicMock(return_value=youtube))


def test_returns_path_of_downloaded_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = MagicMock()
    stream.download.return_value = "/tmp/yt-audio.mp3"
    mock_youtube(monkeypatch, stream)

    path = YouTubeHandler.download_audio_from_video("https://youtu.be/id")

    assert path == Path("/tmp/yt-audio.mp3")
    stream.download.assert_called_once_with(output_path=".", filename="yt-audio.mp3")


def test_video_without_audio_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_youtube(monkeypatch, stream=None)

    with pytest.raises(ValueError, match="audio track"):
        YouTubeHandler.download_audio_from_video("https://youtu.be/id")


def test_download_errors_are_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        youtube_handler, "YouTube", MagicMock(side_effect=RuntimeError("bad url"))
    )

    with pytest.raises(ValueError, match="URL is correct") as exc_info:
        YouTubeHandler.download_audio_from_video("not a url")

    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_reports_the_bytes_downloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = MagicMock(filesize=400)
    youtube_class = MagicMock()
    youtube_class.return_value.streams.filter.return_value.first.return_value = stream
    monkeypatch.setattr(youtube_handler, "YouTube", youtube_class)

    def download(**_kwargs: str) -> str:
        on_chunk = youtube_class.call_args.kwargs["on_progress_callback"]
        for remaining in (300, 100, 0):
            on_chunk(stream, b"", remaining)
        return "/tmp/yt-audio.m4a"

    stream.download.side_effect = download
    reports: list[tuple[float, float]] = []

    YouTubeHandler.download_audio_from_video(
        "https://youtu.be/id",
        on_progress=lambda done, total: reports.append((done, total)),
    )

    assert reports == [(100, 400), (300, 400), (400, 400)]
