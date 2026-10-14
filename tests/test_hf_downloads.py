import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import huggingface_hub
import pytest
from huggingface_hub import constants
from huggingface_hub.errors import LocalEntryNotFoundError

import handlers.hf_downloads as hf_downloads
from handlers.hf_downloads import download_repo

REPO_ID = "org/model"
WEIGHTS_SHA = "a" * 64
CONFIG_BLOB = "b" * 40
FILES = [
    SimpleNamespace(
        rfilename="model.bin",
        size=1000,
        blob_id="c" * 40,
        lfs=SimpleNamespace(sha256=WEIGHTS_SHA),
    ),
    SimpleNamespace(rfilename="config.json", size=100, blob_id=CONFIG_BLOB, lfs=None),
    SimpleNamespace(rfilename="README.md", size=5000, blob_id="d" * 40, lfs=None),
]


@pytest.fixture
def blobs_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(constants, "HF_HUB_CACHE", str(tmp_path))
    monkeypatch.setattr(constants, "HF_HUB_DISABLE_XET", False)
    monkeypatch.delenv("HF_HUB_DISABLE_XET", raising=False)
    monkeypatch.setattr(hf_downloads, "POLL_INTERVAL_SECONDS", 0.01)
    path = tmp_path / "models--org--model" / "blobs"
    path.mkdir(parents=True)
    return path


def fake_hub(
    monkeypatch: pytest.MonkeyPatch, download: Any, info_error: Exception | None = None
) -> list[dict[str, Any]]:
    """Replaces the Hub, recording the arguments of each download."""
    downloads: list[dict[str, Any]] = []

    class FakeApi:
        def model_info(self, repo_id: str, **_kwargs: Any) -> SimpleNamespace:
            if info_error:
                raise info_error
            return SimpleNamespace(sha="rev1", siblings=FILES)

    def snapshot_download(repo_id: str, **kwargs: Any) -> str:
        if kwargs.get("local_files_only"):
            raise LocalEntryNotFoundError("Not cached")
        downloads.append(kwargs)
        download()
        return ""

    monkeypatch.setattr(huggingface_hub, "HfApi", FakeApi)
    monkeypatch.setattr(huggingface_hub, "snapshot_download", snapshot_download)
    return downloads


def test_the_progress_is_the_size_downloaded_of_the_files_wanted(
    blobs_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports: list[tuple[float, float]] = []
    seen_half = threading.Event()

    def on_progress(done: float, total: float) -> None:
        reports.append((done, total))
        if done == 550:
            seen_half.set()

    def download() -> None:
        # The config is complete and half of the weights are being written
        (blobs_path / CONFIG_BLOB).write_bytes(b"x" * 100)
        (blobs_path / f"{WEIGHTS_SHA}.incomplete").write_bytes(b"x" * 450)
        assert seen_half.wait(5)
        (blobs_path / f"{WEIGHTS_SHA}.incomplete").rename(blobs_path / WEIGHTS_SHA)

    downloads = fake_hub(monkeypatch, download)

    download_repo(REPO_ID, on_progress, ignore_patterns=["*.md"])

    # The README isn't downloaded, so it doesn't count
    assert (550, 1100) in reports
    assert reports == sorted(reports)
    assert downloads == [
        {
            "revision": "rev1",
            "token": None,
            "allow_patterns": None,
            "ignore_patterns": ["*.md"],
        }
    ]
    # Xet writes the files at once, so there would be nothing to measure
    assert constants.HF_HUB_DISABLE_XET is True


def test_nothing_is_downloaded_if_the_files_are_in_the_cache(
    blobs_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (blobs_path / CONFIG_BLOB).write_bytes(b"x" * 100)
    (blobs_path / WEIGHTS_SHA).write_bytes(b"x" * 1000)
    downloads = fake_hub(monkeypatch, lambda: None)
    reports: list[tuple[float, float]] = []

    download_repo(
        REPO_ID,
        lambda done, total: reports.append((done, total)),
        ignore_patterns=["*.md"],
    )

    assert downloads == []
    assert reports == []


def test_the_backend_chosen_by_the_user_is_kept(
    blobs_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HF_HUB_DISABLE_XET", "0")
    fake_hub(monkeypatch, lambda: None)

    download_repo(REPO_ID, lambda _done, _total: None)

    assert constants.HF_HUB_DISABLE_XET is False


def test_a_cached_model_is_left_to_load_offline(
    blobs_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloads = fake_hub(monkeypatch, lambda: None, info_error=OSError("Offline"))
    monkeypatch.setattr(hf_downloads, "_is_cached", lambda *_args: True)

    download_repo(REPO_ID, lambda _done, _total: None)

    assert downloads == []


def test_the_errors_of_the_hub_are_raised_if_the_model_isnt_cached(
    blobs_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_hub(monkeypatch, lambda: None, info_error=OSError("Offline"))

    with pytest.raises(OSError, match="Offline"):
        download_repo(REPO_ID, lambda _done, _total: None)
