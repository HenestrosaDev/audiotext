"""
The devices that run the models: an NVIDIA GPU (CUDA) or the CPU for PyTorch and
faster-whisper, and the GPU of Apple Silicon (MLX) for the transcriptions of
WhisperX on Macs.
"""

import functools
import importlib.util
import platform
import sys

import utils.config_manager as cm
from models.config.config_whisperx import ConfigWhisperX
from utils.enums import ComputeType


@functools.cache
def is_mlx_available() -> bool:
    """Whether the GPU of Apple Silicon can transcribe, with MLX."""
    return (
        sys.platform == "darwin"
        and platform.machine() == "arm64"
        and importlib.util.find_spec("mlx_whisper") is not None
    )


@functools.cache
def is_cuda_available() -> bool:
    # Imported here because it takes several seconds
    import torch

    return bool(torch.cuda.is_available())


def can_use_gpu() -> bool:
    """Whether WhisperX can transcribe on a GPU: with CUDA, or with MLX."""
    return is_cuda_available() or is_mlx_available()


def torch_device(use_cpu: bool) -> str:
    """
    The device of the models of PyTorch and faster-whisper (e.g. the alignment and
    the speaker identification), which only use CUDA GPUs.

    :param use_cpu: Whether the user chose to use the CPU.
    """
    return "cpu" if use_cpu or not is_cuda_available() else "cuda"


def configure_whisperx_device() -> None:
    """
    Stores in the configuration whether a GPU is available: a CUDA one, or the one
    of Apple Silicon. Without CUDA, faster-whisper runs on the CPU (e.g. the live
    transcription), so the compute type is one the CPU supports. If a GPU is found
    for the first time, it's used.
    """
    config_whisperx = cm.ConfigManager.get_config_whisperx()
    has_gpu = can_use_gpu()

    cm.ConfigManager.modify_value(
        section=ConfigWhisperX.Key.SECTION,
        key=ConfigWhisperX.Key.CAN_USE_GPU,
        new_value=str(has_gpu),
    )

    if not is_cuda_available():
        cm.ConfigManager.modify_value(
            section=ConfigWhisperX.Key.SECTION,
            key=ConfigWhisperX.Key.COMPUTE_TYPE,
            new_value=ComputeType.INT8.value,
        )

    if not has_gpu or not config_whisperx.can_use_gpu:
        # Without a GPU, the CPU is used. A GPU found since the last time (e.g. on
        # a Mac, once it can use its GPU) is used
        cm.ConfigManager.modify_value(
            section=ConfigWhisperX.Key.SECTION,
            key=ConfigWhisperX.Key.USE_CPU,
            new_value=str(not has_gpu),
        )
