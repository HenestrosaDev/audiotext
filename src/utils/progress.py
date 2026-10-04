from collections.abc import Callable

# Receives a message describing the current step and the completed fraction of the
# step (between 0 and 1), or None if the progress cannot be measured.
ProgressCallback = Callable[[str, float | None], None]


def ignore_progress(_message: str, _fraction: float | None) -> None:
    """Default progress callback for callers that don't track progress."""
