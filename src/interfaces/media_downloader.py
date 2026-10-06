from pathlib import Path
from typing import Protocol

from utils.cancellation import CancellationToken


class MediaDownloader(Protocol):
    """Downloads the audio or video of a URL (see `UrlHandler`)."""

    def download(
        self, url: str, output_path: Path, cancellation_token: CancellationToken
    ) -> Path:
        """
        :param output_path: Where the file is saved. Its extension is replaced by
                            the one of the downloaded media.
        :raises ValueError: If the URL doesn't point to audio or video, or the
                            download fails.
        :raises TranscriptionCancelledError: If the token is cancelled.
        :return: The path of the downloaded file.
        """
        ...
