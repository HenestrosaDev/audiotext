from urllib.parse import urlsplit


def is_valid_temperature(value: str) -> bool:
    """
    Checks whether the value is a temperature between 0 and 1. An empty value is
    considered valid so the user can clear the field while typing.

    :param value: The text typed by the user.
    :return: True if the value is valid, False otherwise.
    """
    if value == "":
        return True

    try:
        return 0 <= float(value) <= 1
    except ValueError:
        return False


def is_valid_positive_int(value: str) -> bool:
    """
    Checks whether the value is a positive integer. An empty value is considered
    valid so the user can clear the field while typing.

    :param value: The text typed by the user.
    :return: True if the value is valid, False otherwise.
    """
    return value == "" or (value.isascii() and value.isdigit() and int(value) > 0)


def is_valid_non_negative_int(value: str) -> bool:
    """
    Checks whether the value is zero or a positive integer. An empty value is
    considered valid so the user can clear the field while typing.

    :param value: The text typed by the user.
    :return: True if the value is valid, False otherwise.
    """
    return value == "" or (value.isascii() and value.isdigit())


def is_valid_url(value: str) -> bool:
    """
    Checks whether the value is an HTTP or HTTPS URL with a host (e.g.
    `https://www.youtube.com/watch?v=…` or `https://example.com/audio.mp3`).

    :param value: The text typed by the user.
    :return: True if the value is a valid URL, False otherwise.
    """
    value = value.strip()

    if not value or any(char.isspace() for char in value):
        return False

    try:
        parts = urlsplit(value)
        port = parts.port  # Raises ValueError if the port is invalid
    except ValueError:
        return False

    host = parts.hostname or ""
    is_valid_host = host == "localhost" or (
        "." in host and not host.startswith(".") and not host.endswith(".")
    )

    return parts.scheme in ("http", "https") and is_valid_host and port != 0


def is_youtube_url(value: str) -> bool:
    """Whether the URL is the URL of a YouTube video."""
    host = (urlsplit(value.strip()).hostname or "").lower()
    return host == "youtu.be" or host.endswith(("youtube.com", "youtube-nocookie.com"))
