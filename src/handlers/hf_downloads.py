"""
Downloads models from the Hugging Face Hub reporting how much is downloaded,
which the libraries that load them (faster-whisper, pyannote) don't report.

The progress is the size of the files written to the cache of the Hub divided by
the size of the files of the model, as the Hub lists them. The Xet backend of the
Hub is disabled, since it writes each file at once when it's complete, so there
is nothing to measure until then; the downloads over HTTP are written as they
progress.
"""

import logging
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from utils.progress import AmountCallback, by_percent

logger = logging.getLogger(__name__)

# How often the size of the files being downloaded is checked
POLL_INTERVAL_SECONDS = 0.5

# The files that faster-whisper downloads (see `faster_whisper.utils.download_model`)
WHISPER_PATTERNS = [
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
]
# The pipelines of pyannote come with their docs and pictures, which aren't needed
PYANNOTE_IGNORE_PATTERNS = [".gitattributes", "*.md", "*.gif"]


def download_whisper_model(model_size: str, on_progress: AmountCallback) -> None:
    """
    Downloads a model of faster-whisper (which WhisperX uses) into the cache of
    the Hub, where it then loads it from.

    :param model_size: The size of the model (e.g. "medium") or its repository.
    """
    from faster_whisper import utils

    # The repositories of the sizes aren't public, but they're needed to know the
    # size of their files. Without them, the model is downloaded when it's loaded
    models: dict[str, str] = getattr(utils, "_MODELS", {})
    repo_id = model_size if "/" in model_size else models.get(model_size)
    if repo_id:
        download_repo(repo_id, on_progress, allow_patterns=WHISPER_PATTERNS)


def download_pyannote_pipeline(
    repo_id: str, token: str, on_progress: AmountCallback
) -> None:
    """Downloads a pipeline of pyannote with the models it's made of."""
    download_repo(
        repo_id, on_progress, ignore_patterns=PYANNOTE_IGNORE_PATTERNS, token=token
    )


def download_repo(
    repo_id: str,
    on_progress: AmountCallback,
    allow_patterns: list[str] | None = None,
    ignore_patterns: list[str] | None = None,
    token: str | None = None,
) -> None:
    """
    Downloads the files of a model repository that are not in the cache yet.

    :param on_progress: Called with the bytes downloaded and the size of the
                        files, while they're being downloaded. Not
                        called if the Hub doesn't list the hash of every file,
                        since their size in the cache can't be known.
    :raises Exception: The errors of the Hub (e.g. a gated repository without
                       access), unless the repository is in the cache, which is
                       then left for the library to load (e.g. offline).
    """
    from huggingface_hub import HfApi, constants, snapshot_download

    patterns: dict[str, Any] = {
        "allow_patterns": allow_patterns,
        "ignore_patterns": ignore_patterns,
    }
    try:
        info = HfApi().model_info(repo_id, files_metadata=True, token=token)
    except Exception:
        if _is_cached(repo_id, token, patterns):
            return
        raise

    files = [
        file
        for file in info.siblings or []
        if _is_wanted(file.rfilename, allow_patterns, ignore_patterns)
    ]
    # The files are saved by their hash: the SHA-256 of the large ones (LFS), and
    # the ID of the Git blob of the others
    blob_names = [file.lfs.sha256 if file.lfs else file.blob_id for file in files]
    blobs = {
        name: file.size or 0
        for name, file in zip(blob_names, files, strict=True)
        if name is not None
    }
    blobs_path = (
        Path(constants.HF_HUB_CACHE) / f"models--{repo_id.replace('/', '--')}" / "blobs"
    )
    is_measurable = len(blobs) == len(files)
    if is_measurable and _downloaded_size(blobs_path, blobs) >= sum(blobs.values()):
        return

    # The variable lets the user choose the backend, as with any other library
    if "HF_HUB_DISABLE_XET" not in os.environ:
        constants.HF_HUB_DISABLE_XET = True

    with _report_downloaded(
        blobs_path, blobs if is_measurable else {}, by_percent(on_progress)
    ):
        # The revision listed, so the files downloaded are the ones measured
        snapshot_download(repo_id, revision=info.sha, token=token, **patterns)


def _is_wanted(
    name: str, allow_patterns: list[str] | None, ignore_patterns: list[str] | None
) -> bool:
    """Whether a file is downloaded with the patterns, like `snapshot_download`."""
    return (
        allow_patterns is None or any(fnmatch(name, p) for p in allow_patterns)
    ) and not any(fnmatch(name, p) for p in ignore_patterns or [])


def _is_cached(repo_id: str, token: str | None, patterns: dict[str, Any]) -> bool:
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    try:
        snapshot_download(repo_id, token=token, local_files_only=True, **patterns)
    except LocalEntryNotFoundError:
        return False
    return True


@contextmanager
def _report_downloaded(
    blobs_path: Path, blobs: dict[str, int], on_progress: AmountCallback
) -> Iterator[None]:
    """
    Reports how much of the blobs is in the cache, from another thread, until
    the context is exited.

    :param blobs: The size of each blob, by its name.
    """
    total = sum(blobs.values())
    stopped = threading.Event()

    def report() -> None:
        while not stopped.is_set():
            on_progress(_downloaded_size(blobs_path, blobs), total)
            stopped.wait(POLL_INTERVAL_SECONDS)

    thread = threading.Thread(target=report, daemon=True)
    if total:
        thread.start()
    try:
        yield
    finally:
        stopped.set()
        # Nothing is reported once the context is exited
        if thread.is_alive():
            thread.join()


def _downloaded_size(blobs_path: Path, blobs: dict[str, int]) -> int:
    downloaded = 0
    for name, size in blobs.items():
        # A blob being downloaded has its own name until it's complete
        for path in (blobs_path / name, blobs_path / f"{name}.incomplete"):
            try:
                downloaded += min(path.stat().st_size, size)
                break
            except OSError:
                continue
    return downloaded
