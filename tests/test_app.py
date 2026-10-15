import pytest

import utils.devices as devices
from app import is_on_screen, parse_geometry
from models.config.config_whisperx import ConfigWhisperX
from utils.config_manager import ConfigManager


@pytest.mark.parametrize(
    ("geometry", "expected"),
    [
        ("1280x820+100+50", (1280, 820, 100, 50)),
        ("1280x820+-1500+30", (1280, 820, -1500, 30)),
        (" 1000x700+0+0\n", (1000, 700, 0, 0)),
        ("", None),
        ("1280x820", None),
        ("garbage", None),
        # Smaller than the minimum size of the window
        ("200x100+10+10", None),
    ],
)
def test_parse_geometry(
    geometry: str, expected: tuple[int, int, int, int] | None
) -> None:
    assert parse_geometry(geometry) == expected


@pytest.mark.parametrize(
    ("window", "expected"),
    [
        ((1280, 820, 100, 50), True),
        # Screens to the right of and below the main screen
        ((1280, 820, 1920, 0), True),
        ((1280, 820, 0, 1080), True),
        # Screens to the left of and above the main screen
        ((1280, 820, -1920, 0), True),
        ((1280, 820, -3840, 0), True),
        ((1280, 820, 0, -1080), True),
        # Too far from the main screen
        ((1280, 820, -6000, 0), False),
        ((1280, 820, 6000, 0), False),
        ((1280, 820, 0, -3000), False),
        ((1280, 820, 0, 3000), False),
    ],
)
def test_is_on_screen(window: tuple[int, int, int, int], expected: bool) -> None:
    assert is_on_screen(window, (1920, 1080)) is expected


def set_whisperx(key: ConfigWhisperX.Key, value: str) -> None:
    ConfigManager.modify_value(ConfigWhisperX.Key.SECTION, key, value)


@pytest.mark.parametrize(
    ("has_cuda", "has_mlx", "can_use_gpu", "use_cpu", "compute_type"),
    [
        # Without a GPU, it runs on the CPU
        (False, False, False, True, "int8"),
        # A Mac uses its GPU (MLX) once it's found, and the CPU for the rest
        (False, True, True, False, "int8"),
        (True, False, True, False, "float16"),
    ],
)
def test_the_gpu_is_used_once_found(
    monkeypatch: pytest.MonkeyPatch,
    has_cuda: bool,
    has_mlx: bool,
    can_use_gpu: bool,
    use_cpu: bool,
    compute_type: str,
) -> None:
    monkeypatch.setattr(devices, "is_cuda_available", lambda: has_cuda)
    monkeypatch.setattr(devices, "is_mlx_available", lambda: has_mlx)
    # Like the previous versions on a Mac, which always ran on the CPU
    set_whisperx(ConfigWhisperX.Key.CAN_USE_GPU, "False")
    set_whisperx(ConfigWhisperX.Key.USE_CPU, "True")
    set_whisperx(ConfigWhisperX.Key.COMPUTE_TYPE, "float16")

    devices.configure_whisperx_device()

    config = ConfigManager.get_config_whisperx()
    assert (config.can_use_gpu, config.use_cpu, config.compute_type) == (
        can_use_gpu,
        use_cpu,
        compute_type,
    )


def test_the_cpu_chosen_with_a_gpu_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(devices, "is_mlx_available", lambda: True)
    monkeypatch.setattr(devices, "is_cuda_available", lambda: False)
    set_whisperx(ConfigWhisperX.Key.CAN_USE_GPU, "True")
    set_whisperx(ConfigWhisperX.Key.USE_CPU, "True")

    devices.configure_whisperx_device()

    assert ConfigManager.get_config_whisperx().use_cpu
