import pytest

from utils.cancellation import CancellationToken, TranscriptionCancelledError


def test_new_token_is_not_cancelled() -> None:
    token = CancellationToken()

    assert not token.is_cancelled
    token.raise_if_cancelled()


def test_cancelled_token_raises() -> None:
    token = CancellationToken()

    token.cancel()

    assert token.is_cancelled
    with pytest.raises(TranscriptionCancelledError):
        token.raise_if_cancelled()
