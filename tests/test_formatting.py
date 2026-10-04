from datetime import datetime

from models.config.config_system import ConfigSystem, DateFormat, TimeFormat
from utils.config_manager import ConfigManager
from views.history.formatting import (
    format_clock_time,
    format_day,
    format_entry_date,
    format_full_date,
    get_date_formats,
    set_date_formats,
)

AFTERNOON = datetime(2026, 10, 4, 13, 30)


def test_the_dates_have_a_short_month_by_default() -> None:
    assert get_date_formats() == (DateFormat.MEDIUM, TimeFormat.AUTO)
    assert format_full_date(AFTERNOON) == "Oct 4, 2026, 1:30 PM"


def test_the_dates_can_be_formatted() -> None:
    assert format_day(AFTERNOON, DateFormat.SHORT) == "10/4/26"
    assert format_day(AFTERNOON, DateFormat.LONG) == "October 4, 2026"
    assert format_day(AFTERNOON, DateFormat.ISO) == "2026-10-04"


def test_the_clock_can_have_12_or_24_hours() -> None:
    assert format_clock_time(AFTERNOON, TimeFormat.HOURS_24) == "13:30"
    assert format_clock_time(AFTERNOON, TimeFormat.HOURS_12).startswith("1:30")


def test_the_formats_are_read_from_the_settings() -> None:
    section = ConfigSystem.Key.SECTION
    ConfigManager.modify_value(section, ConfigSystem.Key.DATE_FORMAT, "iso")
    ConfigManager.modify_value(section, ConfigSystem.Key.TIME_FORMAT, "24")
    assert format_full_date(AFTERNOON) == "2026-10-04, 13:30"


def test_unknown_formats_are_ignored() -> None:
    section = ConfigSystem.Key.SECTION
    ConfigManager.modify_value(section, ConfigSystem.Key.DATE_FORMAT, "weird")
    assert get_date_formats() == (DateFormat.MEDIUM, TimeFormat.AUTO)


def test_old_entries_are_short_or_iso() -> None:
    old = AFTERNOON.astimezone()
    now = old.replace(month=11)
    assert format_entry_date(old, now) == "10/4/26"
    set_date_formats(DateFormat.ISO, TimeFormat.AUTO)
    assert format_entry_date(old, now) == "2026-10-04"
