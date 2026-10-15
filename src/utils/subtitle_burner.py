"""
Burns subtitles into a copy of a video, so they're shown by any player, and in the
sites and apps that don't load subtitle files (e.g. social networks).

FFmpeg draws them with libass (the `subtitles` filter), which shapes the text of
any script and looks for the fonts that have its characters. The FFmpeg bundled on
each system is built with it (see `packaging/macos/build_ffmpeg.sh` for macOS).
"""

import functools
import logging
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from pydub import AudioSegment

from utils.cancellation import CancellationToken, TranscriptionCancelledError
from utils.media import decoded_video_size, probe_media
from utils.progress import ProgressCallback, ignore_progress
from utils.subtitle_cues import Cue

logger = logging.getLogger(__name__)

# Like the subtitles drawn over the video in the app (see `VideoPane`): their
# height relative to the shorter side of the video, and the margin relative to its
# height
MARGIN_RATIO = 0.05
MIN_FONT_SIZE = 11
# The width of the lines, relative to the one of the video
MAX_LINE_RATIO = 0.86
BACKGROUND_OPACITY = 0.6

# The fonts of the text in Chinese and in Japanese on each system. The ones libass
# chooses for their characters may lack some of them (e.g. the simplified Chinese
# ones in the Japanese font of macOS, since its Chinese font can't be opened)
CJK_FONTS = {
    "darwin": ("Hiragino Sans GB", "Hiragino Sans"),
    "win32": ("Microsoft YaHei", "Yu Gothic"),
    "linux": ("Noto Sans CJK SC", "Noto Sans CJK JP"),
}
# H.264, with the encoder of FFmpeg that's preferred, from the first one found: x264
# (in the GPL builds of Linux and Windows) or VideoToolbox (in the one of macOS)
VIDEO_ENCODERS = ("libx264", "h264_videotoolbox")
# The bitrate of VideoToolbox, per pixel of the video. About 6 Mbps in 1080p, like
# x264 with its CRF. Its constant quality (`-q:v`) is only supported by the hardware
# encoder of Apple Silicon, not by the software one it falls back to
VIDEOTOOLBOX_BITS_PER_PIXEL = 3


@dataclass(frozen=True)
class SubtitleLook:
    """How the subtitles look, as the user configured them over the video."""

    # The height of the text, relative to the shorter side of the video
    relative_size: float = 0.06
    is_top: bool = False
    # An outline around the text, or a dark box behind it
    is_outline: bool = False


@dataclass(frozen=True)
class FFmpegFeatures:
    has_libass: bool
    # One of `VIDEO_ENCODERS`, or None to use the default one of MP4
    video_encoder: str | None


@functools.cache
def ffmpeg_features(ffmpeg: str) -> FFmpegFeatures:
    """What the FFmpeg build supports. Checked once, since it takes a moment."""

    def run(*args: str) -> str:
        try:
            result = subprocess.run(
                [ffmpeg, "-hide_banner", *args], capture_output=True, check=True
            )
        except (OSError, subprocess.CalledProcessError):
            return ""
        return result.stdout.decode(errors="replace")

    encoders = run("-encoders").split()
    return FFmpegFeatures(
        has_libass="subtitles" in run("-filters").split(),
        video_encoder=next((name for name in VIDEO_ENCODERS if name in encoders), None),
    )


def burn_subtitles(
    video_path: Path,
    cues: list[Cue],
    output_path: Path,
    look: SubtitleLook,
    on_progress: ProgressCallback = ignore_progress,
    cancellation_token: CancellationToken | None = None,
) -> Path:
    """
    Writes a copy of a video with the subtitles drawn on it, as an MP4 file.

    :param on_progress: Called with the fraction of the video processed.
    :raises ValueError: If there are no subtitles.
    :raises OSError: If the video can't be read, FFmpeg can't draw subtitles (it's
                     built without libass) or it fails.
    :raises TranscriptionCancelledError: If the token is cancelled. The
                                         unfinished file is removed.
    :return: `output_path`.
    """
    if not cues:
        raise ValueError("There are no subtitles to burn")
    # FFmpeg would write over the video while reading it
    if output_path.resolve() == video_path.resolve():
        raise ValueError("The copy with subtitles can't replace the video")

    token = cancellation_token or CancellationToken()
    ffmpeg = AudioSegment.converter
    features = ffmpeg_features(ffmpeg)
    if not features.has_libass:
        raise OSError("FFmpeg is built without libass, which draws the subtitles")
    duration = probe_media(video_path).duration
    size = decoded_video_size(video_path)

    with tempfile.TemporaryDirectory(prefix="audiotext-burn-") as temp_dir:
        work_dir = Path(temp_dir)
        write_ass(cues, work_dir / "subtitles.ass", look, size, LibassFonts.of_system())
        command = [
            ffmpeg,
            *("-nostdin", "-hide_banner", "-loglevel", "error", "-y"),
            *("-i", str(video_path.resolve())),
            *("-vf", "subtitles=filename=subtitles.ass,format=yuv420p"),
            *("-map", "0:v:0", "-map", "0:a?"),
            *video_encoder_options(features.video_encoder, size),
            *("-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"),
            *("-progress", "pipe:1", "-nostats"),
            str(output_path.resolve()),
        ]
        _run(command, work_dir, duration, on_progress, token, output_path)

    return output_path


def video_encoder_options(encoder: str | None, size: tuple[int, int]) -> list[str]:
    """The options of FFmpeg that encode the video, with one of `VIDEO_ENCODERS`."""
    if encoder == "libx264":
        return ["-c:v", "libx264", "-crf", "20", "-preset", "medium"]
    if encoder == "h264_videotoolbox":
        bitrate = size[0] * size[1] * VIDEOTOOLBOX_BITS_PER_PIXEL
        # Without a hardware encoder (e.g. in virtual machines), the software one
        return ["-c:v", "h264_videotoolbox", "-b:v", str(bitrate), "-allow_sw", "1"]
    return []


def _run(
    command: list[str],
    work_dir: Path,
    duration: float | None,
    on_progress: ProgressCallback,
    token: CancellationToken,
    output_path: Path,
) -> None:
    """
    Runs FFmpeg from the folder of the subtitles, so their paths don't have to be
    escaped in the filters.
    """
    logger.info("Burning the subtitles into %s", output_path)
    process = subprocess.Popen(
        command,
        cwd=work_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None and process.stderr is not None
    try:
        for seconds in _progress_seconds(process.stdout):
            if token.is_cancelled:
                process.kill()
                break
            if duration:
                on_progress("", min(seconds / duration, 1.0))
        errors = process.stderr.read()
        process.wait()
    except BaseException:
        process.kill()
        process.wait()
        output_path.unlink(missing_ok=True)
        raise

    if token.is_cancelled:
        output_path.unlink(missing_ok=True)
        raise TranscriptionCancelledError()
    if process.returncode != 0:
        output_path.unlink(missing_ok=True)
        raise OSError(errors.strip() or f"FFmpeg exited with {process.returncode}")


def _progress_seconds(lines: Iterator[str]) -> Iterator[float]:
    """The position of each progress report of FFmpeg (`-progress`), in seconds."""
    for line in lines:
        key, _sep, value = line.strip().partition("=")
        # Both are in microseconds (the second one is misnamed)
        if key in ("out_time_us", "out_time_ms") and value.isdigit():
            yield int(value) / 1_000_000


# LIBASS


@dataclass(frozen=True)
class LibassFonts:
    """The fonts of the subtitles, by their names, which libass looks for."""

    latin: str = "Arial"
    chinese: str = "Arial"
    japanese: str = "Arial"

    @classmethod
    def of_system(cls) -> "LibassFonts":
        platform = "linux" if sys.platform.startswith("linux") else sys.platform
        if platform not in CJK_FONTS:
            return cls()
        chinese, japanese = CJK_FONTS[platform]
        return cls(chinese=chinese, japanese=japanese)


def _ass_time(seconds: float) -> str:
    centiseconds = round(max(seconds, 0) * 100)
    hours, centiseconds = divmod(centiseconds, 360_000)
    minutes, centiseconds = divmod(centiseconds, 6_000)
    seconds_part, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02}:{seconds_part:02}.{centiseconds:02}"


def font_size(look: SubtitleLook, size: tuple[int, int]) -> int:
    """The height of the text in the video, in pixels."""
    return max(round(min(size) * look.relative_size), MIN_FONT_SIZE)


def margin(size: tuple[int, int]) -> int:
    """The space between the subtitles and the edge of the video, in pixels."""
    return max(round(size[1] * MARGIN_RATIO), 6)


def write_ass(
    cues: list[Cue],
    path: Path,
    look: SubtitleLook,
    size: tuple[int, int],
    fonts: LibassFonts,
) -> None:
    """
    Writes the subtitles for libass, in the resolution of the video, so its sizes
    are in pixels. The ones in Chinese or Japanese have the style of their font
    (see `CJK_FONTS`).
    """
    width, height = size
    text_size = font_size(look, size)
    side_margin = round(width * (1 - MAX_LINE_RATIO) / 2)
    if look.is_outline:
        # The outline, of the color of `OutlineColour`
        border_style, border, border_color = 1, max(round(text_size / 16), 1), 0
    else:
        # A box behind the text, of the color of `OutlineColour`
        border_style, border = 3, round(text_size * 0.15)
        border_color = round((1 - BACKGROUND_OPACITY) * 255) << 24

    def style(name: str, font: str) -> str:
        # 8 is the top center, and 2 the bottom center
        alignment = 8 if look.is_top else 2
        return (
            f"Style: {name},{font},{text_size},&H00FFFFFF,&H00FFFFFF,"
            f"&H{border_color:08X},&H00000000,-1,0,0,0,100,100,0,0,{border_style},"
            f"{border},0,{alignment},{side_margin},{side_margin},{margin(size)},1"
        )

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        # Lines as even as possible
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        style("Default", fonts.latin),
        style("Chinese", fonts.chinese),
        style("Japanese", fonts.japanese),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text",
    ]
    for cue in cues:
        # The braces start the tags of ASS, and the backslash its line breaks.
        # Neither can be escaped
        text = cue.text.replace("{", "(").replace("}", ")").replace("\\", "/")
        style_name = cjk_style(text)
        text = text.replace("\n", "\\N")
        lines.append(
            f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},{style_name},,"
            f"0,0,0,,{text}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _is_kana(char: str) -> bool:
    # Hiragana, katakana and their half-width forms
    return "\u3040" <= char <= "\u30ff" or "\uff66" <= char <= "\uff9f"


def _is_han(char: str) -> bool:
    # The CJK unified ideographs, with their extensions and compatibility ones
    return (
        "\u3400" <= char <= "\u9fff"
        or "\uf900" <= char <= "\ufaff"
        or "\U00020000" <= char <= "\U0003ffff"
    )


def cjk_style(text: str) -> str:
    """
    The style of a subtitle: Japanese if it has kana, Chinese if it has other Han
    characters, or the default one. The text in Korean has the default one, whose
    font libass replaces with one that has its characters.
    """
    if any(_is_kana(char) for char in text):
        return "Japanese"
    if any(_is_han(char) for char in text):
        return "Chinese"
    return "Default"
