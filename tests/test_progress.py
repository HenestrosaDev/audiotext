import pytest

import utils.progress as progress
from utils.progress import (
    DownloadProgress,
    by_percent,
    format_size,
    format_size_progress,
    format_time_progress,
    report_audio_time,
    report_download,
    with_detail,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def english(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(progress, "get_language", lambda: "en")


def test_the_time_processed_is_shown_with_the_duration() -> None:
    assert format_time_progress(200.9, 765) == "03:20 / 12:45"
    assert format_time_progress(65, 3725) == "01:05 / 01:02:05"


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (200, "200 byte"),
        (420_000, "420 kB"),
        (999_999, "1 MB"),
        (420_000_000, "420 MB"),
        (999_600_000, "1.0 GB"),
        (1_527_906_378, "1.5 GB"),
    ],
)
def test_sizes_are_shown_in_the_largest_unit(size: int, expected: str) -> None:
    assert format_size(size) == expected


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "420 MB / 1.5 GB"), ("fr", "420 Mo / 1,5 Go"), ("ru", "420 МБ / 1,5 ГБ")],
)
def test_sizes_are_in_the_units_of_the_language(
    language: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(progress, "get_language", lambda: language)

    detail = format_size_progress(420_000_000, 1_500_000_000)

    # Babel separates the number and the unit with a (narrow) no-break space
    assert detail.replace(" ", " ").replace(" ", " ") == expected


def test_the_time_left_is_estimated_once_the_rate_is_steady() -> None:
    clock = FakeClock()
    download = DownloadProgress(clock)

    assert download.describe(0, 1_000_000_000) == "0 byte / 1.0 GB"
    clock.now = 1
    # Too soon to know the rate
    assert download.describe(10_000_000, 1_000_000_000) == "10 MB / 1.0 GB"
    clock.now = 10
    # 100 MB in 10 seconds, so the other 900 MB take about 90 seconds
    assert download.describe(100_000_000, 1_000_000_000) == (
        "100 MB / 1.0 GB · About 2 min left"
    )
    clock.now = 100
    assert download.describe(1_000_000_000, 1_000_000_000) == "1.0 GB / 1.0 GB"


def test_a_resumed_download_counts_the_rate_from_where_it_resumed() -> None:
    clock = FakeClock()
    download = DownloadProgress(clock)

    download.describe(500_000_000, 1_000_000_000)
    clock.now = 10
    # 50 MB in 10 seconds, so the other 450 MB take 90 seconds, not 10
    assert download.describe(550_000_000, 1_000_000_000).endswith("About 2 min left")


def test_the_reports_have_the_detail_and_the_fraction() -> None:
    reports: list[tuple[str, float | None]] = []

    def on_progress(message: str, fraction: float | None) -> None:
        reports.append((message, fraction))

    report_audio_time("Isolating the speech…", on_progress)(200, 800)
    report_download("Downloading…", on_progress)(1_000_000, 4_000_000)

    assert reports == [
        ("Isolating the speech… 03:20 / 13:20", 0.25),
        ("Downloading… 1 MB / 4 MB", 0.25),
    ]


def test_a_step_without_detail_keeps_its_message() -> None:
    assert with_detail("Transcribing…", "") == "Transcribing…"


def test_only_the_changes_of_the_whole_percentage_are_reported() -> None:
    reports: list[tuple[float, float]] = []
    report = by_percent(lambda done, total: reports.append((done, total)))

    for done in (0, 1, 5, 10, 15, 999, 1000):
        report(done, 1000)

    assert reports == [(0, 1000), (10, 1000), (999, 1000), (1000, 1000)]
