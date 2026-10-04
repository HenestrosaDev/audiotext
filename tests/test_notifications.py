import subprocess
from typing import Any

import pytest

import utils.notifications as notifications
from utils.notifications import NotificationCommand, build_command, notify

# `notifications.notify` is replaced by a fixture of `conftest.py`, so the tests use
# the function imported above


class FakePopen:
    """Records the processes started instead of starting them."""

    calls: list[dict[str, Any]] = []

    def __init__(self, args: list[str], **kwargs: Any) -> None:
        FakePopen.calls.append({"args": args, **kwargs})


@pytest.fixture
def popen(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    FakePopen.calls = []
    monkeypatch.setattr(notifications.subprocess, "Popen", FakePopen)
    return FakePopen.calls


def test_macos_passes_the_text_as_arguments_of_the_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notifications.sys, "platform", "darwin")
    command = build_command('Say "hi"', "talk.mp3")

    assert command is not None
    assert command.args[0] == "osascript"
    assert command.args[-2:] == ['Say "hi"', "talk.mp3"]
    assert command.env == {}


def test_windows_passes_the_text_in_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notifications.sys, "platform", "win32")
    command = build_command("Ready", "it's done")

    assert command is not None
    assert command.args[0] == "powershell"
    assert "it's done" not in " ".join(command.args)
    assert command.env == {
        notifications.WINDOWS_TITLE_VARIABLE: "Ready",
        notifications.WINDOWS_MESSAGE_VARIABLE: "it's done",
    }


def test_linux_keeps_the_text_from_being_read_as_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notifications.sys, "platform", "linux")
    command = build_command("Ready", "--talk.mp3")

    assert command is not None
    assert command.args[0] == "notify-send"
    assert command.args[-3:] == ["--", "Ready", "--talk.mp3"]


def test_other_systems_are_not_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notifications.sys, "platform", "emscripten")

    assert build_command("Ready", "talk.mp3") is None


def test_notify_starts_the_command_without_waiting(
    monkeypatch: pytest.MonkeyPatch, popen: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(
        notifications,
        "build_command",
        lambda _title, _message: NotificationCommand(["notifier"], {"KEY": "value"}),
    )
    notify("Ready", "talk.mp3")

    [call] = popen
    assert call["args"] == ["notifier"]
    assert call["env"]["KEY"] == "value"
    assert call["stdout"] == subprocess.DEVNULL


def test_notify_does_nothing_on_unsupported_systems(
    monkeypatch: pytest.MonkeyPatch, popen: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(notifications, "build_command", lambda _title, _message: None)
    notify("Ready", "talk.mp3")

    assert popen == []


def test_notify_ignores_a_missing_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_tool(*_args: Any, **_kwargs: Any) -> None:
        raise FileNotFoundError("notify-send")

    monkeypatch.setattr(notifications.subprocess, "Popen", missing_tool)

    notify("Ready", "talk.mp3")
