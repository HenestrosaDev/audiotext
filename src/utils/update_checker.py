"""
Checks whether a newer version of the app has been released on GitHub.

Only the published releases are considered: GitHub leaves the drafts and the
pre-releases (e.g. `v2.4.0-rc.1`) out of the latest release.
"""

import json
import logging
import re
import urllib.request
from dataclasses import dataclass
from urllib.error import URLError

import utils.constants as c

logger = logging.getLogger(__name__)

LATEST_RELEASE_API_URL = (
    "https://api.github.com/repos/HenestrosaDev/audiotext/releases/latest"
)
RELEASES_URL = f"{c.GITHUB_URL}/releases/latest"
REQUEST_TIMEOUT_SECONDS = 10
USER_AGENT = f"{c.APP_NAME}/{c.APP_VERSION}"

# E.g. "2.4.0", "v2.4.0" or "2.4.0-rc.1"
VERSION_PATTERN = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(-[0-9A-Za-z.-]+)?")


class UpdateCheckError(Exception):
    """The latest release could not be retrieved."""


@dataclass(frozen=True)
class Release:
    version: str
    url: str


def parse_version(version: str) -> tuple[int, int, int, bool] | None:
    """
    Parses a version like "2.4.0", "v2.4.0" or "2.4.0-rc.1".

    :return: The major, minor and patch numbers, and whether it's a final version
             (not a pre-release), so a pre-release is older than its final
             version. None if the version isn't valid.
    """
    match = VERSION_PATTERN.fullmatch(version.strip())
    if not match:
        return None
    return int(match[1]), int(match[2]), int(match[3]), match[4] is None


def is_newer(version: str, current_version: str) -> bool:
    """Whether a version is newer than the current one. False if any isn't valid."""
    parsed, parsed_current = parse_version(version), parse_version(current_version)
    return bool(parsed and parsed_current and parsed > parsed_current)


def fetch_latest_release() -> Release:
    """
    :raises UpdateCheckError: If the request fails or the response isn't valid.
    :return: The latest release published on GitHub.
    """
    request = urllib.request.Request(
        LATEST_RELEASE_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            data = json.load(response)
        tag = data["tag_name"]
        url = data.get("html_url") or RELEASES_URL
    except (URLError, OSError, ValueError, KeyError, TypeError) as e:
        raise UpdateCheckError(str(e)) from e

    if not isinstance(tag, str) or parse_version(tag) is None:
        raise UpdateCheckError(f"Invalid version of the latest release: {tag!r}")
    return Release(version=tag.strip().removeprefix("v"), url=url)


def get_available_update(current_version: str = c.APP_VERSION) -> Release | None:
    """
    :raises UpdateCheckError: If the latest release could not be retrieved.
    :return: The latest release if it's newer than the current version, or None.
    """
    release = fetch_latest_release()
    return release if is_newer(release.version, current_version) else None
