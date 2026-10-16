import pytest

import utils.i18n as i18n
from utils.i18n import format_number, format_percent, get_docs_url

DOCS_URL = "https://getaudiotext.com"


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", f"{DOCS_URL}/en/"),
        ("es", f"{DOCS_URL}/es/"),
        ("zh_CN", f"{DOCS_URL}/zh-cn/"),
        # Unknown languages fall back to English
        ("xx", f"{DOCS_URL}/en/"),
    ],
)
def test_get_docs_url(language: str, expected: str) -> None:
    assert get_docs_url(DOCS_URL, language) == expected


@pytest.mark.parametrize(
    ("language", "number", "percent"),
    [
        ("en", "1,234", "99%"),
        # A non-breaking space before the sign
        ("es", "1.234", "99\xa0%"),
        # The sign before the number
        ("tr", "1.234", "%99"),
    ],
)
def test_the_numbers_are_written_as_in_the_language(
    monkeypatch: pytest.MonkeyPatch, language: str, number: str, percent: str
) -> None:
    monkeypatch.setattr(i18n._interface_language, "code", language)

    assert format_number(1234) == number
    # Rounded down, so 100% means all of it
    assert format_percent(0.999) == percent
