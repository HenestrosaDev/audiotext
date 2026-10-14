from pathlib import Path
from typing import Any

from pytubefix import YouTube

from utils.i18n import _
from utils.progress import AmountCallback, ignore_amount


class YouTubeHandler:
    @staticmethod
    def download_audio_from_video(
        url: str,
        output_path: str = ".",
        output_filename: str = "yt-audio.mp3",
        on_progress: AmountCallback = ignore_amount,
    ) -> Path:
        """
        Downloads audio from a YouTube video.

        :param url: The URL of the YouTube video.
        :param output_path: The directory where the audio file will be saved.
        :param output_filename: The name of the audio file to be saved.
        :param on_progress: Called with the bytes downloaded and the size of the
                            audio.
        :raises ValueError: If the audio could not be downloaded.
        :return: The path to the downloaded audio file.
        """

        def on_chunk(stream: Any, _chunk: bytes, bytes_remaining: int) -> None:
            if stream.filesize:
                on_progress(stream.filesize - bytes_remaining, stream.filesize)

        try:
            stream = (
                YouTube(url, on_progress_callback=on_chunk)
                .streams.filter(only_audio=True)
                .first()
            )
            output_file = (
                stream.download(output_path=output_path, filename=output_filename)
                if stream
                else None
            )
        except Exception as e:
            raise ValueError(
                _(
                    "The audio of the YouTube video could not be downloaded. Please "
                    "make sure the URL is correct."
                )
            ) from e

        if not output_file:
            raise ValueError(_("The YouTube video doesn't have an audio track."))

        return Path(output_file)
