from utils.i18n import _


def format_clock(total_seconds: int) -> str:
    """Formats whole seconds as `MM:SS`, or `HH:MM:SS` from one hour on."""
    hours, remainder = divmod(max(total_seconds, 0), 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    return f"{minutes:02}:{seconds:02}"


def format_timestamp(seconds: float) -> str:
    """Formats a position, rounded down so it doesn't go past the sentence."""
    return format_clock(int(max(seconds, 0)))


def format_duration(seconds: float) -> str:
    """Formats a duration, rounded to the nearest second."""
    return format_clock(round(max(seconds, 0)))


def format_elapsed_time(seconds: float) -> str:
    """Formats how long a process took, in words (e.g. "2 min 5 s")."""
    minutes, seconds = divmod(round(seconds), 60)

    if minutes:
        return _("{minutes} min {seconds} s").format(minutes=minutes, seconds=seconds)

    return _("{seconds} s").format(seconds=seconds)


def format_subtitle_time(seconds: float, decimal_marker: str) -> str:
    """Formats a position as `HH:MM:SS,mmm` (SRT) or `HH:MM:SS.mmm` (VTT)."""
    milliseconds = round(max(seconds, 0) * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds_part, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds_part:02}{decimal_marker}{milliseconds:03}"
