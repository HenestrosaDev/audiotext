import subprocess
import sys
from typing import Any

import pytest

from utils.system import hide_console_windows

# Its value on Windows
CREATE_NO_WINDOW = 0x08000000


@pytest.fixture
def popen_flags(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Fakes Windows, recording the flags each process is started with."""
    flags: list[int] = []

    def init(self: subprocess.Popen[Any], *args: Any, **kwargs: Any) -> None:
        flags.append(kwargs.get("creationflags", 0))

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", CREATE_NO_WINDOW, raising=False)
    monkeypatch.setattr(subprocess.Popen, "__init__", init)
    hide_console_windows()
    return flags


def test_the_processes_dont_open_a_console_window_on_windows(
    popen_flags: list[int],
) -> None:
    subprocess.Popen(["ffmpeg"])
    # The flags given are kept
    subprocess.Popen(["ffmpeg"], creationflags=0x200)

    assert popen_flags == [CREATE_NO_WINDOW, CREATE_NO_WINDOW | 0x200]


def test_the_processes_are_started_as_usual_on_other_systems(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    init = subprocess.Popen.__init__
    hide_console_windows()

    assert subprocess.Popen.__init__ is init
