import threading


class TranscriptionCancelledError(Exception):
    """Raised to abort a transcription that the user has cancelled."""


class CancellationToken:
    """
    Thread-safe flag used to cooperatively cancel a long-running task. The task
    checks the token at safe points (between files, chunks or batches) and stops
    by raising `TranscriptionCancelledError`.
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float) -> bool:
        """
        Waits until the token is cancelled or the timeout expires.

        :param timeout: The maximum time to wait, in seconds.
        :return: Whether the token has been cancelled.
        """
        return self._event.wait(timeout)

    def raise_if_cancelled(self) -> None:
        """
        :raises TranscriptionCancelledError: If the token has been cancelled.
        """
        if self.is_cancelled:
            raise TranscriptionCancelledError()
