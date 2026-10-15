import time
from pathlib import Path

import av
import numpy as np
import pytest

from tests.conftest import make_tone
from utils.media import (
    MAX_FRAME_WIDTH,
    VideoFrameSource,
    is_vertical_video,
    load_audio_samples,
    probe_media,
)


def make_video(path: Path, width: int, height: int, frames: int = 3) -> Path:
    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=10)
        stream.width, stream.height = width, height
        stream.pix_fmt = "yuv420p"
        for _idx in range(frames):
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


def wait_for_frame(source: VideoFrameSource, after: int) -> int:
    """Waits until the decoding thread publishes a frame after the given one."""
    deadline = time.monotonic() + 5
    while source.frame_number <= after:
        assert time.monotonic() < deadline, "No frame was decoded"
        time.sleep(0.01)
    return source.frame_number


def test_probe_media_reads_the_duration_and_the_size(tmp_path: Path) -> None:
    info = probe_media(make_video(tmp_path / "video.mp4", 64, 32, frames=10))

    assert info.video_size == (64, 32)
    assert info.has_video and not info.is_portrait
    assert info.duration == pytest.approx(1.0, abs=0.15)


def test_probe_media_of_an_audio_has_no_video(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    make_tone(duration_ms=500).export(audio, format="wav")

    info = probe_media(audio)

    assert info.video_size is None and not info.has_video
    assert info.duration == pytest.approx(0.5, abs=0.05)


def test_probe_media_of_an_unreadable_file_raises(tmp_path: Path) -> None:
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video")

    with pytest.raises(OSError):
        probe_media(broken)


def test_load_audio_samples_decodes_the_audio(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    make_tone(duration_ms=500).export(audio, format="wav")

    samples = load_audio_samples(audio, sample_rate=8000)

    assert samples.dtype == np.int16
    assert len(samples) == pytest.approx(4000, abs=100)
    assert np.abs(samples).max() > 0


def test_load_audio_samples_of_an_unreadable_file_raises(tmp_path: Path) -> None:
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"not audio")

    with pytest.raises(OSError):
        load_audio_samples(broken)


def test_the_frames_are_decoded_at_the_position_requested(tmp_path: Path) -> None:
    video = make_video(tmp_path / "video.mp4", 64, 32, frames=30)
    source = VideoFrameSource(video)
    try:
        assert source.frame_size == (64, 32)
        # The first frame is decoded right away
        shown = wait_for_frame(source, 0)
        frame = source.latest_frame
        assert frame is not None and frame.size == (64, 32)

        # Forward, then backward, which seeks
        for seconds in (2.5, 0.5):
            source.request(seconds)
            shown = wait_for_frame(source, shown)
    finally:
        source.close()


def test_wide_videos_are_scaled_down_to_even_sizes(tmp_path: Path) -> None:
    video = make_video(tmp_path / "video.mp4", 1920, 1082, frames=1)
    source = VideoFrameSource(video)
    try:
        width, height = source.frame_size
        assert width == MAX_FRAME_WIDTH
        assert height % 2 == 0 and height == pytest.approx(1082 / 2, abs=2)
    finally:
        source.close()


def test_a_file_without_video_has_no_frames(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    make_tone().export(audio, format="wav")

    with pytest.raises(OSError, match="has no video"):
        VideoFrameSource(audio)
    with pytest.raises(OSError):
        VideoFrameSource(tmp_path / "missing.mp4")
