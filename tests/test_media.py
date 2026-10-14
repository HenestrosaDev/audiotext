from pathlib import Path

import av
import numpy as np
import pytest

from tests.conftest import make_tone
from utils.media import is_vertical_video


def make_video(path: Path, width: int, height: int) -> Path:
    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=10)
        stream.width, stream.height = width, height
        stream.pix_fmt = "yuv420p"
        for _idx in range(3):
            image = np.zeros((height, width, 3), np.uint8)
            frame = av.VideoFrame.from_ndarray(image, format="rgb24")
            container.mux(stream.encode(frame))
        container.mux(stream.encode())
    return path


@pytest.mark.parametrize(
    ("width", "height", "expected"), [(64, 32, False), (32, 64, True)]
)
def test_vertical_videos_are_detected(
    tmp_path: Path, width: int, height: int, expected: bool
) -> None:
    video = make_video(tmp_path / "video.mp4", width, height)

    assert is_vertical_video(video) is expected


def test_audios_and_missing_files_are_not_vertical_videos(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    make_tone().export(audio, format="wav")

    assert not is_vertical_video(audio)
    assert not is_vertical_video(tmp_path / "missing.mp4")
    assert not is_vertical_video(None)
