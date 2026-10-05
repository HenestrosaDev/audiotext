import math

from utils.i18n import _


def format_clock(total_seconds: int) -> str:
    """Formats whole seconds as `MM:SS`, or `HH:MM:SS` from one hour on."""
    hours, remainder = divmod(max(total_seconds, 0), 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    return f"{minutes:02}:{seconds:02}"


def format_timestamp(seconds: float) -> str:
    """Formats a position, rounded down so it doesn't go past the segment."""
    return format_clock(int(max(seconds, 0)))


def format_segment_time(seconds: float, is_precise: bool) -> str:
    """
    Formats the start of a segment: simplified (`MM:SS`), or precise to the
    millisecond like the subtitles (`HH:MM:SS,mmm`), for professional
    transcribers and translators.
    """
    return (
        format_subtitle_time(seconds, ",") if is_precise else format_timestamp(seconds)
    )


def format_segment_range(start: float, end: float, is_precise: bool) -> str:
    """Formats when a segment starts and ends, e.g. `00:01 – 00:03`."""
    return (
        f"{format_segment_time(start, is_precise)} – "
        f"{format_segment_time(end, is_precise)}"
    )


def parse_segment_time(text: str) -> float:
    """
    Parses a position typed by the user: `SS`, `MM:SS` or `HH:MM:SS`, with
    optional fractions of a second (e.g. `01:05,900` or `01:05.9`).

    :raises ValueError: If it isn't a valid position.
    """
    *units_texts, seconds_text = text.strip().replace(",", ".").split(":")
    if len(units_texts) > 2:
        raise ValueError(f"Invalid time: {text!r}")

    units = [int(unit) for unit in units_texts]
    seconds = float(seconds_text)
    # Only the first part can exceed its range (e.g. 90 seconds or 75 minutes)
    if (
        not math.isfinite(seconds)
        or any(part < 0 for part in [*units, seconds])
        or ((units and seconds >= 60) or (len(units) == 2 and units[1] >= 60))
    ):
        raise ValueError(f"Invalid time: {text!r}")

    for multiplier, unit in zip((60, 3600), reversed(units), strict=False):
        seconds += unit * multiplier
    return seconds


def format_duration(seconds: float) -> str:
    """
    Formats a duration, rounded down like the positions, so it matches the one the
    player bar shows when the audio reaches the end.
    """
    return format_timestamp(seconds)


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
