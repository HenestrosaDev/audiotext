import logging
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from pydub import AudioSegment

logger = logging.getLogger(__name__)

# Sample rate of the audio decoded to be played
PLAYBACK_SAMPLE_RATE = 16000
# Frames are scaled down to this width (at most) when decoded, so drawing them is
# fast. It's enough for the size of the video panel
MAX_FRAME_WIDTH = 960


@dataclass(frozen=True)
class MediaInfo:
    duration: float | None
    # Display size of the video, or None if the file has no video
    video_size: tuple[int, int] | None

    @property
    def has_video(self) -> bool:
        return self.video_size is not None

    @property
    def is_portrait(self) -> bool:
        return self.video_size is not None and self.video_size[1] > self.video_size[0]


def probe_media(path: Path) -> MediaInfo:
    """
    Reads the duration of an audio or video file and the size of its video. The
    cover art of audio files (e.g. MP3 or M4A) is not considered a video.

    :raises OSError: If the file can't be read.
    """
    import av

    try:
        with av.open(str(path)) as container:
            duration = (
                container.duration / av.time_base
                if container.duration is not None
                else None
            )
            stream = _find_video_stream(container)

            if stream is None:
                return MediaInfo(duration, None)

            width, height = stream.codec_context.width, stream.codec_context.height
            # Videos with non-square pixels (e.g. some DVDs) are stretched
            ratio = stream.sample_aspect_ratio
            if ratio and ratio.numerator and ratio.denominator:
                width = round(width * ratio.numerator / ratio.denominator)

            return MediaInfo(duration, (width, height) if width and height else None)
    except av.FFmpegError as e:
        raise OSError(str(e)) from e


def load_audio_samples(
    path: Path, sample_rate: int = PLAYBACK_SAMPLE_RATE
) -> np.ndarray:
    """
    Decodes the audio of a file with FFmpeg.

    :return: The 16-bit mono samples of the audio, at `sample_rate`.
    :raises OSError: If FFmpeg can't decode the file.
    """
    try:
        result = subprocess.run(
            [
                AudioSegment.converter,
                *("-nostdin", "-hide_banner", "-loglevel", "error"),
                *("-i", str(path)),
                *("-vn", "-f", "s16le", "-ac", "1", "-ar", str(sample_rate)),
                "pipe:1",
            ],
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        message = e.stderr.decode(errors="replace").strip() or str(e)
        raise OSError(message) from e

    return np.frombuffer(result.stdout, dtype=np.int16)


def _find_video_stream(container: Any) -> Any:
    import av

    for stream in container.streams.video:
        disposition = getattr(stream, "disposition", 0)
        if disposition & av.stream.Disposition.attached_pic:
            continue
        return stream

    return None


class VideoFrameSource:
    """
    Decodes the frames of a video in a background thread, following the position
    requested by the player. The UI asks for a position with `request` and draws
    `latest_frame` when its `frame_number` changes.

    Decoding goes forward from the last frame, so it's cheap while playing. When
    the requested position is behind the last frame or far ahead, it seeks to the
    nearest keyframe first.
    """

    # Seeking is faster than decoding when the target is this far (in seconds)
    SEEK_THRESHOLD_SECONDS = 2.0

    def __init__(self, path: Path) -> None:
        """
        :raises OSError: If the file can't be opened or has no video.
        """
        import av

        try:
            self._container = av.open(str(path))
        except av.FFmpegError as e:
            raise OSError(str(e)) from e

        self._stream = _find_video_stream(self._container)
        if self._stream is None:
            self._container.close()
            raise OSError(f"{path} has no video")

        self._stream.thread_type = "AUTO"
        info = probe_media(path)
        assert info.video_size
        width, height = info.video_size
        scale = min(1.0, MAX_FRAME_WIDTH / width)
        # Even sizes are required by some pixel formats
        self.frame_size = (
            max(2, round(width * scale) // 2 * 2),
            max(2, round(height * scale) // 2 * 2),
        )

        self._condition = threading.Condition()
        self._target: float | None = 0.0
        self._is_closed = False
        self._frame: Image.Image | None = None
        self._frame_number = 0

        # State of the decoder, only used from the decoding thread
        self._decoder: Any = None
        self._current: Any = None
        self._current_time: float | None = None
        self._pending: Any = None

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def frame_number(self) -> int:
        """Increases each time a new frame is decoded."""
        return self._frame_number

    @property
    def latest_frame(self) -> Image.Image | None:
        with self._condition:
            return self._frame

    def request(self, seconds: float) -> None:
        """Asks for the frame shown at the given position."""
        with self._condition:
            self._target = max(seconds, 0.0)
            self._condition.notify()

    def close(self) -> None:
        with self._condition:
            self._is_closed = True
            self._condition.notify()

        self._thread.join(timeout=1)

        try:
            self._container.close()
        except Exception:
            logger.exception("Could not close the video")

    def _run(self) -> None:
        while True:
            with self._condition:
                while self._target is None and not self._is_closed:
                    self._condition.wait()

                if self._is_closed:
                    return

                target = self._target
                self._target = None

            assert target is not None
            try:
                self._decode_until(target)
            except Exception:
                logger.exception("Could not decode the video")
                return

    def _decode_until(self, target: float) -> None:
        """
        Decodes the frames until the one shown at `target`, which is the last one
        that starts at or before it. The first frame that starts after it is kept
        as pending, since it's the next one to show while playing.
        """
        current_time = self._current_time
        must_seek = (
            self._decoder is None
            or current_time is None
            or target < current_time
            or target - current_time > self.SEEK_THRESHOLD_SECONDS
        )

        if must_seek:
            time_base = self._stream.time_base
            offset = int(target / time_base) if time_base else 0
            self._container.seek(offset, stream=self._stream, backward=True)
            self._decoder = self._container.decode(self._stream)
            self._current = self._pending = None
            self._current_time = None

        previous = self._current

        while True:
            frame = self._pending or next(self._decoder, None)
            self._pending = None

            if frame is None:  # End of the video
                break

            frame_time = frame.time if frame.time is not None else 0.0

            if frame_time > target and self._current is not None:
                self._pending = frame
                break

            self._current = frame
            self._current_time = frame_time

            with self._condition:
                # Stop decoding old frames if a newer position was requested
                if self._is_closed or (
                    self._target is not None and self._target < frame_time
                ):
                    break

        if self._current is not None and self._current is not previous:
            self._publish(self._current)

    def _publish(self, frame: Any) -> None:
        width, height = self.frame_size
        image = frame.to_image(width=width, height=height)

        with self._condition:
            self._frame = image
            self._frame_number += 1
