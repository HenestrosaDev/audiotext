import time
from collections.abc import Callable
from datetime import timedelta

from babel.dates import format_timedelta
from babel.units import format_unit

from utils.i18n import _, get_language
from utils.time_format import format_clock

# Receives a message describing the current step and the completed fraction of the
# step (between 0 and 1), or None if the progress cannot be measured.
ProgressCallback = Callable[[str, float | None], None]

# Receives the completed fraction of a step (between 0 and 1)
FractionCallback = Callable[[float], None]

# Receives how much of a step is done and its total, in the same unit (e.g. bytes
# downloaded or seconds of audio processed)
AmountCallback = Callable[[float, float], None]

# A download needs this long before its rate is steady enough to estimate the time
# left
MIN_SECONDS_FOR_ESTIMATE = 3

BYTES_PER_KB = 1000
BYTES_PER_MB = 1000**2
BYTES_PER_GB = 1000**3


def ignore_progress(_message: str, _fraction: float | None) -> None:
    """Default progress callback for callers that don't track progress."""


def ignore_fraction(_fraction: float) -> None:
    """Default fraction callback for callers that don't track progress."""


def ignore_amount(_done: float, _total: float) -> None:
    """Default amount callback for callers that don't track progress."""


def by_percent(on_progress: AmountCallback) -> AmountCallback:
    """
    Forwards only the amounts that change the whole percentage, so the steps
    that report often (e.g. after each downloaded chunk) don't flood the UI.
    """
    last_percent: int | None = None

    def report(done: float, total: float) -> None:
        nonlocal last_percent
        percent = int(min(max(done / total, 0.0), 1.0) * 100) if total else 0
        if percent != last_percent:
            last_percent = percent
            on_progress(done, total)

    return report


def with_detail(message: str, detail: str) -> str:
    """Adds the measured detail of a step (e.g. `03:20 / 12:45`) to its message."""
    return f"{message} {detail}" if detail else message


def format_time_progress(done_seconds: float, total_seconds: float) -> str:
    """How much audio is processed, e.g. `03:20 / 12:45`."""
    return f"{format_clock(int(done_seconds))} / {format_clock(int(total_seconds))}"


def format_size(size: float) -> str:
    """A size in the units of the language of the interface, e.g. `1,5 Go`."""
    # A size that rounds to 1,000 of a unit is shown in the next one
    if round(size / BYTES_PER_MB) >= 1000:
        value, unit, pattern = size / BYTES_PER_GB, "digital-gigabyte", "#,##0.0"
    elif round(size / BYTES_PER_KB) >= 1000:
        value, unit, pattern = size / BYTES_PER_MB, "digital-megabyte", "#,##0"
    elif size >= BYTES_PER_KB:
        value, unit, pattern = size / BYTES_PER_KB, "digital-kilobyte", "#,##0"
    else:
        value, unit, pattern = size, "digital-byte", "#,##0"
    return str(
        format_unit(value, unit, length="short", format=pattern, locale=get_language())
    )


def format_size_progress(done_bytes: float, total_bytes: float) -> str:
    """How much is downloaded, e.g. `420 MB / 1.5 GB`."""
    return f"{format_size(done_bytes)} / {format_size(total_bytes)}"


class DownloadProgress:
    """
    Describes the progress of a download: its size and, once it has run long
    enough, the time left at its average rate so far.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._start: tuple[float, float] | None = None

    def describe(self, done_bytes: float, total_bytes: float) -> str:
        now = self._clock()
        if self._start is None:
            # A resumed download counts the rate from what was already there
            self._start = (now, done_bytes)
        start_time, start_bytes = self._start
        detail = format_size_progress(done_bytes, total_bytes)

        elapsed = now - start_time
        transferred = done_bytes - start_bytes
        if elapsed < MIN_SECONDS_FOR_ESTIMATE or transferred <= 0:
            return detail
        if done_bytes >= total_bytes:
            return detail

        seconds_left = (total_bytes - done_bytes) / (transferred / elapsed)
        time_left = format_timedelta(
            timedelta(seconds=seconds_left), format="short", locale=get_language()
        )
        return f"{detail} · " + _("About {time} left").format(time=time_left)


def report_download(message: str, on_progress: ProgressCallback) -> AmountCallback:
    """
    Reports a download (bytes downloaded and size) as the fraction of the step
    with its message, the sizes and the time left.
    """
    download = DownloadProgress()

    def report(done_bytes: float, total_bytes: float) -> None:
        on_progress(
            with_detail(message, download.describe(done_bytes, total_bytes)),
            done_bytes / total_bytes if total_bytes else None,
        )

    return report


def report_audio_time(message: str, on_progress: ProgressCallback) -> AmountCallback:
    """
    Reports the seconds of audio processed, out of its duration, as the fraction
    of the step with its message and both times.
    """

    def report(done_seconds: float, total_seconds: float) -> None:
        on_progress(
            with_detail(message, format_time_progress(done_seconds, total_seconds)),
            done_seconds / total_seconds if total_seconds else None,
        )

    return report
