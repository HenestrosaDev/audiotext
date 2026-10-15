"""
Transcribes with MLX Whisper, which runs Whisper on the GPU of Apple Silicon, much
faster than on the CPU. It replaces the transcription step of WhisperX (see
`WhisperXHandler`), whose alignment and speaker identification still follow it.
"""

import contextlib
import importlib
import io
import logging
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from utils.cancellation import CancellationToken
from utils.progress import ProgressCallback

logger = logging.getLogger(__name__)

# The models converted to MLX, by the size of the model of WhisperX. The ones that
# aren't converted (some of the distilled ones) are transcribed on the CPU
MLX_MODELS = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "tiny.en": "mlx-community/whisper-tiny.en-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "base.en": "mlx-community/whisper-base.en-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "small.en": "mlx-community/whisper-small.en-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "medium.en": "mlx-community/whisper-medium.en-mlx",
    "large-v1": "mlx-community/whisper-large-v1-mlx",
    "large-v2": "mlx-community/whisper-large-v2-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "distil-medium.en": "mlx-community/distil-whisper-medium.en",
    "distil-large-v3": "mlx-community/distil-whisper-large-v3",
}
# The files of the weights of a model, in one of the formats that MLX loads
WEIGHTS_FILES = ("weights.safetensors", "weights.npz", "model.safetensors")

# A transcription at a time, since the progress of MLX Whisper is reported to a
# single callback
_lock = threading.Lock()


def has_mlx_model(model_size: str) -> bool:
    return model_size in MLX_MODELS


def is_model_downloaded(model_size: str) -> bool:
    """
    Whether the MLX model of the given size is downloaded, without downloading it.
    """
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    repo = MLX_MODELS.get(model_size)
    if repo is None:
        return False
    try:
        model_path = Path(snapshot_download(repo, local_files_only=True))
    except (LocalEntryNotFoundError, ValueError):
        return False

    # An interrupted download leaves the snapshot without the weights
    return any((model_path / name).is_file() for name in WEIGHTS_FILES)


def load_model(model_size: str) -> Any:
    """
    Loads the model of the given size (downloading it the first time), which MLX
    Whisper keeps loaded until another one is used.

    :raises ValueError: If the model has no MLX version.
    """
    repo = MLX_MODELS.get(model_size)
    if repo is None:
        raise ValueError(f"{model_size} has no MLX version")

    import mlx.core as mx
    from mlx_whisper.transcribe import ModelHolder

    logger.info("Loading MLX Whisper model %s", repo)
    # In half precision, like `mlx_whisper.transcribe` loads it
    return ModelHolder.get_model(repo, mx.float16)


def transcribe(
    audio: np.ndarray,
    model_size: str,
    language: str | None,
    task: str,
    prompt: str | None,
    on_progress: ProgressCallback,
    message: str,
    cancellation_token: CancellationToken,
) -> dict[str, Any]:
    """
    Transcribes the audio with the MLX model of the given size.

    :param audio: The samples, as WhisperX loads them (mono, at 16 kHz).
    :param task: "transcribe", or "translate" into English.
    :param message: The progress message of the transcription.
    :raises TranscriptionCancelledError: If the token is cancelled.
    :return: The result, like the one of WhisperX: its segments (with their start,
             end and text) and its language.
    """
    # By its name, since `mlx_whisper.transcribe` is also the function of the
    # package, which hides the module
    mlx_transcribe: Any = importlib.import_module("mlx_whisper.transcribe")

    def on_frames(done: int, total: int) -> None:
        # MLX Whisper can't be cancelled, so it's aborted from its progress
        cancellation_token.raise_if_cancelled()
        on_progress(message, done / total if total else None)

    with _lock:
        load_model(model_size)
        cancellation_token.raise_if_cancelled()

        # MLX Whisper reports its progress to a tqdm bar, which is replaced while
        # it transcribes. Only its module is patched, so other bars are kept
        original_tqdm = mlx_transcribe.tqdm
        mlx_transcribe.tqdm = SimpleNamespace(
            tqdm=lambda total, **_kwargs: _ProgressBar(total, on_frames)
        )
        # It prints the detected language, which would be mixed with the text
        # that the command line prints
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                result: dict[str, Any] = mlx_transcribe.transcribe(
                    audio,
                    path_or_hf_repo=MLX_MODELS[model_size],
                    # Shows the progress bar (None hides it, True prints the text)
                    verbose=False,
                    language=language,
                    task=task,
                    initial_prompt=prompt,
                    # Like WhisperX, which avoids repeating the text of a segment
                    # in the next ones when the model gets stuck
                    condition_on_previous_text=False,
                )
        finally:
            mlx_transcribe.tqdm = original_tqdm
            if printed := output.getvalue().strip():
                logger.info("MLX Whisper: %s", printed)

    return {
        "segments": [
            {
                "start": float(segment["start"]),
                "end": float(segment["end"]),
                "text": segment["text"],
            }
            for segment in result["segments"]
            if segment["text"].strip()
        ],
        "language": result["language"],
    }


class _ProgressBar:
    """Stands for the tqdm bar of MLX Whisper, reporting the frames transcribed."""

    def __init__(self, total: int, on_frames: Any) -> None:
        self._total = total
        self._done = 0
        self._on_frames = on_frames

    def __enter__(self) -> "_ProgressBar":
        self._on_frames(0, self._total)
        return self

    def __exit__(self, *_args: Any) -> None:
        pass

    def update(self, frames: int) -> None:
        self._done += frames
        self._on_frames(self._done, self._total)
