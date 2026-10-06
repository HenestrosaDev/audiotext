import threading
from collections.abc import Callable

# Starts a task that takes a while (e.g. a transcription or a summary) without
# waiting for it, so the UI stays responsive.
TaskStarter = Callable[[Callable[[], None]], None]


def start_in_background(task: Callable[[], None]) -> None:
    """
    Runs a task in a daemon thread, so it doesn't keep the app open when it's
    closed.
    """
    threading.Thread(target=task, daemon=True).start()
