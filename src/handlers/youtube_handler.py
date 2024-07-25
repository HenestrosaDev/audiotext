import traceback
from pathlib import Path
from typing import Optional

from pytubefix import YouTube


class YouTubeHandler:
    @staticmethod
    def download_audio_from_video(
        url: str,
        output_path: str = ".",
        output_filename: str = "yt-audio.mp3",
    ) -> Optional[Path]:
        """
        Downloads audio from a YouTube video.

        :param url: The URL of the YouTube video.
        :param output_path: (Optional) The directory where the audio file will be saved.
                            Default is the current directory.
        :param output_filename: (Optional) The name of the audio file to be saved.
                                 Default is "yt-audio.mp3".
        :return: The path to the downloaded audio file as a Path object,
                 or None if the download fails.
        """
        try:
            yt = YouTube(url)
            stream = yt.streams.filter(only_audio=True).first()
            output_file = stream.download(
                output_path=output_path, filename=output_filename
            )

            return Path(output_file) if output_file else None

        except Exception:
            print(traceback.format_exc())
