from pathlib import Path

from pytubefix import YouTube

from utils.i18n import _


class YouTubeHandler:
    @staticmethod
    def download_audio_from_video(
        url: str,
        output_path: str = ".",
        output_filename: str = "yt-audio.mp3",
    ) -> Path:
        """
        Downloads audio from a YouTube video.

        :param url: The URL of the YouTube video.
        :param output_path: The directory where the audio file will be saved.
        :param output_filename: The name of the audio file to be saved.
        :raises ValueError: If the audio could not be downloaded.
        :return: The path to the downloaded audio file.
        """
        try:
            stream = YouTube(url).streams.filter(only_audio=True).first()
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
