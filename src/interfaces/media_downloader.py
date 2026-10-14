from pathlib import Path
from typing import Protocol

from utils.cancellation import CancellationToken
from utils.progress import AmountCallback


class MediaDownloader(Protocol):
    """Downloads the audio or video of a URL (see `UrlHandler`)."""

    def download(
        self,
        url: str,
        output_path: Path,
        cancellation_token: CancellationToken,
        on_progress: AmountCallback,
    ) -> Path:
        """
        :param output_path: Where the file is saved. Its extension is replaced by
                            the one of the downloaded media.
        :param on_progress: Called with the bytes downloaded and the size of the
                            media, when it's known.
        :raises ValueError: If the URL doesn't point to audio or video, or the
                            download fails.
        :raises TranscriptionCancelledError: If the token is cancelled.
        :return: The path of the downloaded file.
        """
        ...
