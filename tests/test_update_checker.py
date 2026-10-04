import io
import json
from typing import Any
from urllib.error import URLError

import pytest

import utils.update_checker as update_checker
from utils.update_checker import (
    Release,
    UpdateCheckError,
    fetch_latest_release,
    get_available_update,
    is_newer,
    parse_version,
)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("2.4.0", (2, 4, 0, True)),
        ("v2.4.0", (2, 4, 0, True)),
        (" v10.0.12\n", (10, 0, 12, True)),
        ("2.4.0-rc.1", (2, 4, 0, False)),
        ("2.4", None),
        ("latest", None),
        ("", None),
    ],
)
def test_parse_version(version: str, expected: Any) -> None:
    assert parse_version(version) == expected


@pytest.mark.parametrize(
    ("version", "current_version", "expected"),
    [
        ("2.4.0", "2.3.0", True),
        ("2.10.0", "2.9.0", True),
        ("3.0.0", "2.99.99", True),
        ("v2.3.1", "2.3.0", True),
        ("2.3.0", "2.3.0", False),
        ("2.2.9", "2.3.0", False),
        ("2.4.0", "2.4.0-rc.1", True),
        ("2.4.0-rc.1", "2.3.0", True),
        ("2.4.0-rc.1", "2.4.0", False),
        ("invalid", "2.3.0", False),
        ("2.4.0", "invalid", False),
    ],
)
def test_is_newer(version: str, current_version: str, expected: bool) -> None:
    assert is_newer(version, current_version) == expected


def mock_response(monkeypatch: pytest.MonkeyPatch, body: Any) -> list[Any]:
    """Makes the requests return a JSON body. Returns the requests made."""
    requests: list[Any] = []

    def urlopen(request: Any, timeout: float) -> io.BytesIO:
        requests.append(request)
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(update_checker.urllib.request, "urlopen", urlopen)
    return requests


def test_fetch_latest_release(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://github.com/HenestrosaDev/audiotext/releases/tag/v2.4.0"
    requests = mock_response(monkeypatch, {"tag_name": "v2.4.0", "html_url": url})

    assert fetch_latest_release() == Release("2.4.0", url)
    assert requests[0].full_url == update_checker.LATEST_RELEASE_API_URL
    assert requests[0].get_header("User-agent") == update_checker.USER_AGENT


def test_fetch_latest_release_without_url(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response(monkeypatch, {"tag_name": "2.4.0"})

    assert fetch_latest_release().url == update_checker.RELEASES_URL


@pytest.mark.parametrize(
    "body", [{}, {"tag_name": None}, {"tag_name": "nightly"}, ["v2.4.0"]]
)
def test_fetch_latest_release_with_invalid_response(
    monkeypatch: pytest.MonkeyPatch, body: Any
) -> None:
    mock_response(monkeypatch, body)

    with pytest.raises(UpdateCheckError):
        fetch_latest_release()


def test_fetch_latest_release_without_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def urlopen(request: Any, timeout: float) -> Any:
        raise URLError("No connection")

    monkeypatch.setattr(update_checker.urllib.request, "urlopen", urlopen)

    with pytest.raises(UpdateCheckError):
        fetch_latest_release()


@pytest.mark.parametrize(
    ("tag", "expected"), [("v2.4.0", "2.4.0"), ("v2.3.0", None), ("v2.2.0", None)]
)
def test_get_available_update(
    monkeypatch: pytest.MonkeyPatch, tag: str, expected: str | None
) -> None:
    mock_response(monkeypatch, {"tag_name": tag})

    release = get_available_update("2.3.0")

    assert (release.version if release else None) == expected
