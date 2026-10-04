"""Labels, icons and dates of the entries of the history."""

import sys
from datetime import datetime
from enum import Enum
from typing import TypeVar

import customtkinter as ctk
from babel.dates import format_date, format_skeleton, format_time

from models.config.config_system import DateFormat, TimeFormat
from models.history import EntryStatus, HistoryEntry
from utils.config_manager import ConfigManager
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


# The formats chosen by the user, read once from the settings since dates are
# formatted for each row of the history
_formats: tuple[DateFormat, TimeFormat] | None = None


def get_date_formats() -> tuple[DateFormat, TimeFormat]:
    """The formats of the dates and the times chosen by the user."""
    global _formats
    if _formats is None:
        config = ConfigManager.get_config_system()
        _formats = (
            _parse(DateFormat, config.date_format, DateFormat.MEDIUM),
            _parse(TimeFormat, config.time_format, TimeFormat.AUTO),
        )
    return _formats


def set_date_formats(date_format: DateFormat, time_format: TimeFormat) -> None:
    global _formats
    _formats = (date_format, time_format)


_EnumT = TypeVar("_EnumT", bound=Enum)


def _parse(enum: type[_EnumT], value: str, default: _EnumT) -> _EnumT:
    try:
        return enum(value)
    except ValueError:
        return default


def format_clock_time(value: datetime, time_format: TimeFormat | None = None) -> str:
    """
    Formats a time of the day in the interface language, with the hours of its
    clock or of the 12- or 24-hour one chosen by the user.
    """
    time_format = time_format or get_date_formats()[1]
    locale = get_language()
    if time_format == TimeFormat.HOURS_12:
        return format_skeleton("hm", value, locale=locale)
    if time_format == TimeFormat.HOURS_24:
        return format_skeleton("Hm", value, locale=locale)
    return format_time(value, "short", locale=locale)


def format_day(value: datetime, date_format: DateFormat | None = None) -> str:
    """Formats a date in the interface language, as the user chose to."""
    date_format = date_format or get_date_formats()[0]
    if date_format == DateFormat.ISO:
        return value.strftime("%Y-%m-%d")
    return format_date(value, date_format.value, locale=get_language())


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
            return format_clock_time(local_value)
        if days < 7:
            return format_date(local_value, "EEEE", locale=locale).capitalize()
        # The sidebar is narrow, so the dates are short, unless they're ISO ones
        is_iso = get_date_formats()[0] == DateFormat.ISO
        return format_day(local_value, DateFormat.ISO if is_iso else DateFormat.SHORT)
    except (ValueError, LookupError):
        return local_value.strftime("%Y-%m-%d")


def format_method(entry: HistoryEntry) -> str:
    """The transcription method, with its model if it has one."""
    method = entry.method or ""
    if entry.model_name:
        method = f"{method} ({entry.model_name})"
    return method


def format_full_date(value: datetime) -> str:
    try:
        return format_day(value) + ", " + format_clock_time(value)
    except (ValueError, LookupError):
        return value.strftime("%Y-%m-%d %H:%M")


def reveal_label() -> str:
    if theme.IS_MACOS:
        return _("Show in Finder")
    if sys.platform == "win32":
        return _("Show in Explorer")
    return _("Show in file manager")
