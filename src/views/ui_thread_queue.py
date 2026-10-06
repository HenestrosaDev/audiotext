import logging
import queue
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# How often the callbacks sent from background threads are run
POLL_INTERVAL_MS = 50


class UiThreadQueue:
    """
    Runs on the Tkinter thread the callbacks sent from background threads, since
    Tkinter is not thread-safe. They stop being run when it's stopped.
    """

    def __init__(self, widget: Any) -> None:
        """:param widget: The widget whose event loop runs the callbacks."""
        self._widget = widget
        self._callbacks: queue.SimpleQueue[tuple[Callable[..., Any], tuple[Any, ...]]]
        self._callbacks = queue.SimpleQueue()
        self._after_id: str | None = None
        self._run_callbacks()

    def put(self, callback: Callable[..., Any], *args: Any) -> None:
        """Schedules a callback. It can be called from any thread."""
        self._callbacks.put((callback, args))

    def stop(self) -> None:
        if self._after_id:
            self._widget.after_cancel(self._after_id)
            self._after_id = None

    def _run_callbacks(self) -> None:
        while True:
            try:
                callback, args = self._callbacks.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args)
            except Exception:
                logger.exception("Error while updating the UI")

        self._after_id = self._widget.after(POLL_INTERVAL_MS, self._run_callbacks)
