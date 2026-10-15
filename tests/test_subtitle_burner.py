import subprocess
from pathlib import Path

import av
import numpy as np
import pytest
from PIL import Image
from pydub import AudioSegment

from tests.test_media import make_video
from utils import subtitle_burner
from utils.cancellation import CancellationToken, TranscriptionCancelledError
from utils.media import decoded_video_size
from utils.subtitle_burner import (
    FFmpegFeatures,
    LibassFonts,
    SubtitleLook,
    burn_subtitles,
    render_subtitle,
    wrap_line,
    write_ass,
    write_overlays,
)
from utils.subtitle_cues import Cue

CUES = [Cue(0.0, 0.5, "Hello"), Cue(1.0, 1.5, "World")]


def ass_lines(path: Path, prefix: str) -> list[str]:
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(prefix)
    ]


def alpha_rows(image: Image.Image) -> tuple[int, int]:
    """The first and the last rows of the image that are not transparent."""
    rows = np.flatnonzero(np.asarray(image.getchannel("A")).any(axis=1))
    return int(rows[0]), int(rows[-1])


def test_ass_is_in_the_resolution_of_the_video(tmp_path: Path) -> None:
    path = tmp_path / "subtitles.ass"
    cues = [Cue(0.5, 2.0, "Say {hi}\nC:\\Users"), Cue(3600, 3601.25, "你好")]

    write_ass(cues, path, SubtitleLook(), (1280, 720), LibassFonts("Arial", "Wide"))

    content = path.read_text(encoding="utf-8")
    assert "PlayResX: 1280\nPlayResY: 720\n" in content
    # 6% of the shorter side, with a box behind the text (BorderStyle 3)
    styles = ass_lines(path, "Style:")
    assert styles[0].startswith("Style: Default,Arial,43,")
    assert styles[0].split(",")[15] == "3"
    assert styles[1].startswith("Style: Wide,Wide,43,")
    assert ass_lines(path, "Dialogue:") == [
        "Dialogue: 0,0:00:00.50,0:00:02.00,Default,,0,0,0,,Say (hi)\\NC:/Users",
        # The Chinese text has the font with its glyphs
        "Dialogue: 0,1:00:00.00,1:00:01.25,Wide,,0,0,0,,你好",
    ]


def test_ass_follows_the_look(tmp_path: Path) -> None:
    path = tmp_path / "subtitles.ass"
    look = SubtitleLook(relative_size=0.08, is_top=True, is_outline=True)

    write_ass(CUES, path, look, (1080, 1920), LibassFonts())

    fields = ass_lines(path, "Style:")[0].split(",")
    assert fields[2] == "86"  # 8% of 1080
    assert fields[15] == "1"  # An outline
    assert fields[18] == "8"  # At the top


def test_overlays_show_each_subtitle_from_its_start(tmp_path: Path) -> None:
    cues = [Cue(0.5, 2.0, "One"), Cue(1.5, 3.0, "Two"), Cue(2.5, 2.8, "Three")]

    write_overlays(cues, tmp_path, SubtitleLook(), (320, 180))

    lines = (tmp_path / "subtitles.ffconcat").read_text().splitlines()
    assert lines == [
        "ffconcat version 1.0",
        "file blank.png",
        "duration 0.500",
        "file subtitle00000.png",
        "duration 1.500",
        # The overlapping subtitle starts when the previous one ends
        "file subtitle00001.png",
        "duration 1.000",
        # The one hidden behind it is left out
        "file blank.png",
        "duration 1",
        "file blank.png",
    ]
    assert Image.open(tmp_path / "subtitle00000.png").size == (320, 180)
    assert not (tmp_path / "subtitle00002.png").exists()


@pytest.mark.parametrize("is_top", [False, True])
def test_subtitle_images_are_placed_as_configured(is_top: bool) -> None:
    image = render_subtitle("Hello", SubtitleLook(is_top=is_top), (640, 360))

    first, last = alpha_rows(image)
    if is_top:
        assert first < 40
    else:
        assert last > 320


def test_subtitle_images_have_a_box_or_an_outline() -> None:
    size = (640, 360)
    box = render_subtitle("Hello", SubtitleLook(), size)
    outline = render_subtitle("Hello", SubtitleLook(is_outline=True), size)

    def box_pixels(image: Image.Image) -> int:
        alpha = np.asarray(image.getchannel("A"))
        return int((alpha == round(subtitle_burner.BACKGROUND_OPACITY * 255)).sum())

    assert box_pixels(box) > 500
    assert box_pixels(outline) == 0


def test_long_lines_are_wrapped() -> None:
    font = subtitle_burner.load_font(20, False)

    assert len(wrap_line("word " * 40, font, 200)) > 1
    assert wrap_line("short", font, 200) == ["short"]
    # Without spaces, between the characters
    assert len(wrap_line("你" * 40, subtitle_burner.load_font(20, True), 200)) > 1


def test_progress_reports_are_read() -> None:
    lines = iter(["frame=10\n", "out_time_us=1500000\n", "out_time_ms=N/A\n"])

    assert list(subtitle_burner._progress_seconds(lines)) == [1.5]


def make_sound_video(path: Path) -> Path:
    """A video of two seconds with sound, made with FFmpeg."""
    subprocess.run(
        [
            AudioSegment.converter,
            *("-nostdin", "-loglevel", "error", "-y"),
            *("-f", "lavfi", "-i", "testsrc2=s=320x180:d=2:r=10"),
            *("-f", "lavfi", "-i", "sine=d=2"),
            *("-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(path)),
        ],
        check=True,
    )
    return path


@pytest.fixture(params=[False, True], ids=["overlays", "libass"])
def ffmpeg_features(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> FFmpegFeatures:
    """The FFmpeg used with and without libass, if it has it."""
    features = subtitle_burner.ffmpeg_features(AudioSegment.converter)
    if request.param and not features.has_libass:
        pytest.skip("FFmpeg is built without libass")
    features = FFmpegFeatures(has_libass=request.param, has_x264=features.has_x264)
    monkeypatch.setattr(subtitle_burner, "ffmpeg_features", lambda _ffmpeg: features)
    return features


@pytest.mark.usefixtures("ffmpeg_features")
def test_subtitles_are_burned_into_a_copy_of_the_video(tmp_path: Path) -> None:
    video = make_sound_video(tmp_path / "video.mp4")
    output = tmp_path / "video.subtitled.mp4"
    progress: list[float | None] = []

    burn_subtitles(
        video,
        [Cue(0.0, 2.0, "Hello")],
        output,
        SubtitleLook(),
        lambda _message, fraction: progress.append(fraction),
    )

    with av.open(str(output)) as container:
        assert container.streams.video[0].width == 320
        assert len(container.streams.audio) == 1
        frame = next(container.decode(video=0)).to_ndarray(format="rgb24")
    with av.open(str(video)) as container:
        original = next(container.decode(video=0)).to_ndarray(format="rgb24")
    changed = (np.abs(frame.astype(int) - original).max(axis=2) > 80).sum(axis=1)
    # The subtitle changed the bottom of the frame, and not the top
    assert changed[-40:].sum() > 200
    assert changed[:40].sum() < 20
    assert progress and progress[-1] == pytest.approx(1.0, abs=0.1)


def test_a_cancelled_burn_leaves_no_file(tmp_path: Path) -> None:
    video = make_video(tmp_path / "video.mp4", 64, 32, frames=10)
    output = tmp_path / "output.mp4"
    token = CancellationToken()
    token.cancel()

    with pytest.raises(TranscriptionCancelledError):
        burn_subtitles(video, CUES, output, SubtitleLook(), cancellation_token=token)

    assert not output.exists()


def test_the_video_is_not_replaced(tmp_path: Path) -> None:
    video = make_video(tmp_path / "video.mp4", 64, 32)

    with pytest.raises(ValueError):
        burn_subtitles(video, CUES, video, SubtitleLook())
    with pytest.raises(ValueError):
        burn_subtitles(video, [], tmp_path / "output.mp4", SubtitleLook())


def test_the_size_of_a_rotated_video_is_the_one_shown(tmp_path: Path) -> None:
    video = make_video(tmp_path / "video.mp4", 64, 32)
    rotated = tmp_path / "rotated.mp4"
    result = subprocess.run(
        [
            AudioSegment.converter,
            *("-nostdin", "-loglevel", "error", "-y", "-display_rotation", "90"),
            *("-i", str(video), "-c", "copy", str(rotated)),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        pytest.skip("This FFmpeg can't rotate videos (`-display_rotation`)")

    assert decoded_video_size(video) == (64, 32)
    assert decoded_video_size(rotated) == (32, 64)
