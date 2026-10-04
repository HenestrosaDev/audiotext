import pytest

from utils.i18n import get_docs_url

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
