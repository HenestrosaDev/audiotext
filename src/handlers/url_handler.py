import logging
import mimetypes
import urllib.request
from pathlib import Path, PurePosixPath
from urllib.error import URLError
from urllib.parse import unquote, urlsplit

from handlers.youtube_handler import YouTubeHandler
from utils import constants as c
from utils.cancellation import CancellationToken
from utils.i18n import _
from utils.validators import is_youtube_url

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30
CHUNK_SIZE = 1024 * 256
USER_AGENT = f"{c.APP_NAME}/{c.APP_VERSION}"
# Generic content types that servers send for any file
GENERIC_CONTENT_TYPES = {"application/octet-stream", "binary/octet-stream", ""}


def get_media_extension(url: str, content_type: str) -> str | None:
    """
    Determines the extension of the media that a URL points to, from its path or,
    if it has no supported extension, from the content type of the response.

    :return: The extension (e.g. ".mp3"), or None if it's not audio or video.
    """
    path_extension = PurePosixPath(unquote(urlsplit(url).path)).suffix.lower()
    if path_extension in c.SUPPORTED_FILE_EXTENSIONS:
        return path_extension

    content_type = content_type.split(";")[0].strip().lower()
    if content_type.startswith(("audio/", "video/")):
        guessed = mimetypes.guess_extension(content_type) or ""
        return guessed if guessed in c.SUPPORTED_FILE_EXTENSIONS else ".media"

    if content_type in GENERIC_CONTENT_TYPES and path_extension:
        return path_extension

    return None


class UrlHandler:
    @staticmethod
    def download(
        url: str,
        output_path: Path,
        cancellation_token: CancellationToken | None = None,
    ) -> Path:
        """
        Downloads the audio of a YouTube video, or the audio or video file that a
        URL points to.

        :param url: The URL.
        :param output_path: Where the file is saved. Its extension is replaced by
                            the one of the downloaded media.
        :raises ValueError: If the URL doesn't point to audio or video, or the
                            download fails.
        :raises TranscriptionCancelledError: If the token is cancelled.
        :return: The path of the downloaded file.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if is_youtube_url(url):
            return YouTubeHandler.download_audio_from_video(
                url,
                output_path=str(output_path.parent),
                output_filename=output_path.with_suffix(".m4a").name,
            )

        token = cancellation_token or CancellationToken()
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        file_path: Path | None = None

        try:
            with urllib.request.urlopen(
                request, timeout=REQUEST_TIMEOUT_SECONDS
            ) as response:
                extension = get_media_extension(
                    response.geturl(), response.headers.get("Content-Type", "")
                )
                if extension is None:
                    raise ValueError(
                        _(
                            "The URL doesn't point to an audio or video file. Use the "
                            "link of a YouTube video or of a media file."
                        )
                    )

                file_path = output_path.with_suffix(extension)
                with open(file_path, "wb") as output_file:
                    while chunk := response.read(CHUNK_SIZE):
                        token.raise_if_cancelled()
                        output_file.write(chunk)
        except BaseException as e:
            # Partial downloads are removed (e.g. if the user cancels)
            if file_path is not None:
                file_path.unlink(missing_ok=True)

            if isinstance(e, URLError | OSError):
                logger.error("Could not download %s", url, exc_info=e)
                raise ValueError(
                    _("The file could not be downloaded: {error}").format(error=e)
                ) from e
            raise

        return file_path
