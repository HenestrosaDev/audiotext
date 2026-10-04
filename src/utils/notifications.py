"""
Notifications of the desktop, shown with the tools that come with each operating
system, so they don't require any dependency:

- macOS: AppleScript (`osascript`).
- Windows: a toast of the Windows Runtime, shown from PowerShell.
- Linux: `notify-send` (libnotify), available in most desktops.

They're shown in the background and never raise an error, since the app works
the same without them (e.g. on a Linux desktop without `notify-send`).
"""

import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field

import utils.constants as c

logger = logging.getLogger(__name__)

# The text is passed as arguments of the run handler, so it doesn't need escaping
MACOS_SCRIPT = [
    "on run argv",
    "display notification (item 2 of argv) with title (item 1 of argv)",
    "end run",
]

# The text is read from environment variables, so it doesn't need escaping
WINDOWS_TITLE_VARIABLE = "AUDIOTEXT_NOTIFICATION_TITLE"
WINDOWS_MESSAGE_VARIABLE = "AUDIOTEXT_NOTIFICATION_MESSAGE"
# A toast needs the ID of an installed app to be shown, so PowerShell's is used
WINDOWS_APP_ID = (
    "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"
)
WINDOWS_SCRIPT = "\n".join(
    [
        "$ErrorActionPreference = 'Stop'",
        "$Manager = [Windows.UI.Notifications.ToastNotificationManager,"
        " Windows.UI.Notifications, ContentType = WindowsRuntime]",
        "$Type = [Windows.UI.Notifications.ToastTemplateType]::ToastText02",
        "$Template = $Manager::GetTemplateContent($Type)",
        "$Texts = $Template.GetElementsByTagName('text')",
        f"$Title = $Template.CreateTextNode($env:{WINDOWS_TITLE_VARIABLE})",
        f"$Message = $Template.CreateTextNode($env:{WINDOWS_MESSAGE_VARIABLE})",
        "$Texts.Item(0).AppendChild($Title) | Out-Null",
        "$Texts.Item(1).AppendChild($Message) | Out-Null",
        "$Toast = [Windows.UI.Notifications.ToastNotification]::new($Template)",
        f"$Manager::CreateToastNotifier('{WINDOWS_APP_ID}').Show($Toast)",
    ]
)


@dataclass(frozen=True)
class NotificationCommand:
    """The process that shows a notification."""

    args: list[str]
    # Variables added to the environment of the process
    env: dict[str, str] = field(default_factory=dict)


def notify(title: str, message: str) -> None:
    """
    Shows a notification of the system, without waiting for it.

    :param title: The title of the notification.
    :param message: The text below the title.
    """
    command = build_command(title, message)
    if command is None:
        logger.info("Notifications are not supported on %s", sys.platform)
        return

    try:
        subprocess.Popen(
            command.args,
            env=os.environ | command.env if command.env else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # Without it, a console would flash when the app is packaged on Windows
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        logger.warning("The notification could not be shown", exc_info=True)


def build_command(title: str, message: str) -> NotificationCommand | None:
    """
    :return: The command that shows the notification on the current system, or
             `None` if the system is not supported.
    """
    if sys.platform == "darwin":
        return _macos_command(title, message)
    if sys.platform == "win32":
        return _windows_command(title, message)
    if sys.platform.startswith("linux") or "bsd" in sys.platform:
        return _linux_command(title, message)
    return None


def _macos_command(title: str, message: str) -> NotificationCommand:
    script_args = [arg for line in MACOS_SCRIPT for arg in ("-e", line)]
    return NotificationCommand(["osascript", *script_args, title, message])


def _windows_command(title: str, message: str) -> NotificationCommand:
    return NotificationCommand(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            WINDOWS_SCRIPT,
        ],
        env={WINDOWS_TITLE_VARIABLE: title, WINDOWS_MESSAGE_VARIABLE: message},
    )


def _linux_command(title: str, message: str) -> NotificationCommand:
    # `--` keeps a text starting with "-" from being read as an option
    return NotificationCommand(
        ["notify-send", f"--app-name={c.APP_NAME}", "--", title, message]
    )
