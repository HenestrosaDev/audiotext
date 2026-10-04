import pytest

from app import is_on_screen, parse_geometry


@pytest.mark.parametrize(
    ("geometry", "expected"),
    [
        ("1280x820+100+50", (1280, 820, 100, 50)),
        ("1280x820+-1500+30", (1280, 820, -1500, 30)),
        (" 1000x700+0+0\n", (1000, 700, 0, 0)),
        ("", None),
        ("1280x820", None),
        ("garbage", None),
        # Smaller than the minimum size of the window
        ("200x100+10+10", None),
    ],
)
def test_parse_geometry(
    geometry: str, expected: tuple[int, int, int, int] | None
) -> None:
    assert parse_geometry(geometry) == expected


@pytest.mark.parametrize(
    ("window", "expected"),
    [
        ((1280, 820, 100, 50), True),
        # Screens to the right of and below the main screen
        ((1280, 820, 1920, 0), True),
        ((1280, 820, 0, 1080), True),
        # Screens to the left of and above the main screen
        ((1280, 820, -1920, 0), True),
        ((1280, 820, -3840, 0), True),
        ((1280, 820, 0, -1080), True),
        # Too far from the main screen
        ((1280, 820, -6000, 0), False),
        ((1280, 820, 6000, 0), False),
        ((1280, 820, 0, -3000), False),
        ((1280, 820, 0, 3000), False),
    ],
)
def test_is_on_screen(window: tuple[int, int, int, int], expected: bool) -> None:
    assert is_on_screen(window, (1920, 1080)) is expected
