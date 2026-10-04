"""Labels, icons and dates of the entries of the history."""

import sys
from datetime import datetime

import customtkinter as ctk
from babel.dates import format_date, format_time

from models.history import EntryStatus, HistoryEntry
from utils.enums import AudioSource
from utils.i18n import _, get_language
from views.style import icons, theme


def source_label(kind: str) -> str:
    """The name of a kind of source, shown as the default tag of an entry."""
    return {
        AudioSource.FILE.value: _("File"),
        AudioSource.YOUTUBE.value: _("URL"),
        AudioSource.MIC.value: _("Microphone"),
        AudioSource.DIRECTORY.value: _("Folder"),
        AudioSource.WATCH.value: _("Watched folder"),
    }.get(kind, kind)


def source_icon(kind: str) -> str:
    return {
        AudioSource.FILE.value: "file",
        AudioSource.YOUTUBE.value: "link",
        AudioSource.MIC.value: "mic",
        AudioSource.DIRECTORY.value: "folder",
        AudioSource.WATCH.value: "folder",
    }.get(kind, "file")


def status_label(status: EntryStatus) -> str:
    return {
        EntryStatus.QUEUED: _("Queued"),
        EntryStatus.PROCESSING: _("Transcribing…"),
        EntryStatus.WATCHING: _("Watching"),
        EntryStatus.DONE: _("Done"),
        EntryStatus.FAILED: _("Failed"),
        EntryStatus.CANCELLED: _("Cancelled"),
        EntryStatus.INTERRUPTED: _("Interrupted"),
    }[status]


def status_icon(
    status: EntryStatus, size: int = 13, spinner_frame: int = 0
) -> ctk.CTkImage:
    if status == EntryStatus.PROCESSING:
        return icons.spinner(spinner_frame, size)

    name, color = {
        EntryStatus.QUEUED: ("clock", theme.STATUS_QUEUED),
        EntryStatus.WATCHING: ("eye", theme.STATUS_WATCHING),
        EntryStatus.DONE: ("check_circle", theme.STATUS_DONE),
        EntryStatus.FAILED: ("x_circle", theme.STATUS_FAILED),
        EntryStatus.CANCELLED: ("alert_circle", theme.STATUS_CANCELLED),
        EntryStatus.INTERRUPTED: ("alert_circle", theme.STATUS_CANCELLED),
    }[status]
    return icons.icon(name, size, color)


def format_entry_date(value: datetime, now: datetime | None = None) -> str:
    """
    Formats the date of an entry like the Notes app: the time if it's from
    today, the day of the week if it's from the last seven days, and the date
    otherwise.
    """
    now = now or datetime.now().astimezone()
    locale = get_language()
    local_value = value.astimezone(now.tzinfo)
    days = (now.date() - local_value.date()).days

    try:
        if days <= 0:
            return format_time(local_value, "short", locale=locale)
        if days < 7:
            return format_date(local_value, "EEEE", locale=locale).capitalize()
        return format_date(local_value, "short", locale=locale)
    except (ValueError, LookupError):
        return local_value.strftime("%Y-%m-%d")


def format_method(entry: HistoryEntry) -> str:
    """The transcription method, with its model if it has one."""
    method = entry.method or ""
    if entry.model_name:
        method = f"{method} ({entry.model_name})"
    return method


def format_full_date(value: datetime) -> str:
    locale = get_language()
    try:
        return (
            format_date(value, "long", locale=locale)
            + ", "
            + format_time(value, "short", locale=locale)
        )
    except (ValueError, LookupError):
        return value.strftime("%Y-%m-%d %H:%M")


def reveal_label() -> str:
    if theme.IS_MACOS:
        return _("Show in Finder")
    if sys.platform == "win32":
        return _("Show in Explorer")
    return _("Show in file manager")
