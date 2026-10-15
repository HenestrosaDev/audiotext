import subprocess
from pathlib import Path

import av
import numpy as np
import pytest
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
    cjk_style,
    video_encoder_options,
    write_ass,
)
from utils.subtitle_cues import Cue

CUES = [Cue(0.0, 0.5, "Hello"), Cue(1.0, 1.5, "World")]


def ass_lines(path: Path, prefix: str) -> list[str]:
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(prefix)
    ]


def test_ass_is_in_the_resolution_of_the_video(tmp_path: Path) -> None:
    path = tmp_path / "subtitles.ass"
    cues = [Cue(0.5, 2.0, "Say {hi}\nC:\\Users"), Cue(3600, 3601.25, "你好")]

    write_ass(cues, path, SubtitleLook(), (1280, 720), LibassFonts("Arial", "Han"))

    content = path.read_text(encoding="utf-8")
    assert "PlayResX: 1280\nPlayResY: 720\n" in content
    # 6% of the shorter side, with a box behind the text (BorderStyle 3)
    styles = ass_lines(path, "Style:")
    assert styles[0].startswith("Style: Default,Arial,43,")
    assert styles[0].split(",")[15] == "3"
    assert styles[1].startswith("Style: Chinese,Han,43,")
    assert ass_lines(path, "Dialogue:") == [
        "Dialogue: 0,0:00:00.50,0:00:02.00,Default,,0,0,0,,Say (hi)\\NC:/Users",
        # The Chinese text has the font with its characters
        "Dialogue: 0,1:00:00.00,1:00:01.25,Chinese,,0,0,0,,你好",
    ]


def test_ass_follows_the_look(tmp_path: Path) -> None:
    path = tmp_path / "subtitles.ass"
    look = SubtitleLook(relative_size=0.08, is_top=True, is_outline=True)

    write_ass(CUES, path, look, (1080, 1920), LibassFonts())

    fields = ass_lines(path, "Style:")[0].split(",")
    assert fields[2] == "86"  # 8% of 1080
    assert fields[15] == "1"  # An outline
    assert fields[18] == "8"  # At the top


@pytest.mark.parametrize(
    ("text", "style"),
    [
        ("Hello", "Default"),
        ("مرحبا नमस्ते", "Default"),
        ("안녕하세요", "Default"),
        ("你好，说话", "Chinese"),
        ("臺灣 𠀀", "Chinese"),
        # Japanese has Han characters too, along with kana
        ("日本語です", "Japanese"),
        ("ｶﾀｶﾅ", "Japanese"),
    ],
)
def test_chinese_and_japanese_have_their_own_style(text: str, style: str) -> None:
    assert cjk_style(text) == style


def test_videotoolbox_is_given_a_bitrate_for_the_size_of_the_video() -> None:
    options = video_encoder_options("h264_videotoolbox", (1920, 1080))

    assert options[options.index("-b:v") + 1] == str(1920 * 1080 * 3)
    # Its constant quality isn't supported by its software encoder
    assert "-q:v" not in options
    assert video_encoder_options("libx264", (1920, 1080))[:2] == ["-c:v", "libx264"]
    assert video_encoder_options(None, (1920, 1080)) == []


def test_ffmpeg_without_libass_cant_burn_subtitles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    features = FFmpegFeatures(has_libass=False, video_encoder="libx264")
    monkeypatch.setattr(subtitle_burner, "ffmpeg_features", lambda _ffmpeg: features)
    video = make_video(tmp_path / "video.mp4", 64, 32)

    with pytest.raises(OSError, match="libass"):
        burn_subtitles(video, CUES, tmp_path / "output.mp4", SubtitleLook())


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


@pytest.fixture
def ffmpeg_with_libass() -> None:
    """
    Skips the test if the FFmpeg installed can't draw subtitles (e.g. the one of
    Homebrew, while the app bundles its own).
    """
    if not subtitle_burner.ffmpeg_features(AudioSegment.converter).has_libass:
        pytest.skip("FFmpeg is built without libass")


@pytest.mark.usefixtures("ffmpeg_with_libass")
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


@pytest.mark.usefixtures("ffmpeg_with_libass")
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
