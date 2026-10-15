"""
Burns subtitles into a copy of a video, so they're shown by any player, and in the
sites and apps that don't load subtitle files (e.g. social networks).

FFmpeg draws them with libass (the `subtitles` filter), which shapes the text of
any script and looks for the fonts that have its characters. The FFmpeg bundled on
each system is built with it (see `packaging/macos/build_ffmpeg.sh` for macOS).
"""

import functools
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
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


@dataclass(frozen=True)
class FontCandidate:
    """
    A font, by the name libass looks for, and its file, which tells whether it's
    installed. On Linux, fontconfig is asked for the name instead.
    """

    name: str
    file: str | None = None


# The fonts of the text in Chinese and in Japanese on each system, from the first one
# installed. The ones libass chooses for their characters may lack some of them
# (e.g. the simplified Chinese ones in the Japanese font of macOS, since its Chinese
# font can't be opened), and a font that isn't installed is even worse. The fonts
# in Chinese have the kana of Japanese too, so they're its last resort
CHINESE_FONTS = {
    "darwin": (
        FontCandidate("Hiragino Sans GB", "Hiragino Sans GB.ttc"),
        FontCandidate("Heiti SC", "STHeiti Medium.ttc"),
        FontCandidate("Songti SC", "Supplemental/Songti.ttc"),
        FontCandidate("Arial Unicode MS", "Supplemental/Arial Unicode.ttf"),
    ),
    "win32": (
        FontCandidate("Microsoft YaHei", "msyh.ttc"),
        FontCandidate("SimHei", "simhei.ttf"),
        FontCandidate("SimSun", "simsun.ttc"),
    ),
    "linux": (
        FontCandidate("Noto Sans CJK SC"),
        FontCandidate("Source Han Sans SC"),
        FontCandidate("WenQuanYi Zen Hei"),
        FontCandidate("Droid Sans Fallback"),
    ),
}
JAPANESE_FONTS = {
    "darwin": (
        FontCandidate("Hiragino Sans", "ヒラギノ角ゴシック W6.ttc"),
        FontCandidate("Hiragino Maru Gothic ProN", "ヒラギノ丸ゴ ProN W4.ttc"),
    ),
    "win32": (
        FontCandidate("Yu Gothic", "YuGothB.ttc"),
        FontCandidate("Meiryo", "meiryo.ttc"),
        FontCandidate("MS Gothic", "msgothic.ttc"),
    ),
    "linux": (
        FontCandidate("Noto Sans CJK JP"),
        FontCandidate("Source Han Sans JP"),
        FontCandidate("IPAGothic"),
        FontCandidate("TakaoGothic"),
    ),
}
# What libass logs for each character that no font has, which is drawn as a box
MISSING_GLYPH_PATTERN = re.compile(
    r"failed to find any fallback with glyph 0x([0-9A-Fa-f]+)"
)
# H.264, with the encoder of FFmpeg that's preferred, from the first one found: x264
# (in the GPL builds of Linux and Windows) or VideoToolbox (in the one of macOS)
VIDEO_ENCODERS = ("libx264", "h264_videotoolbox")
# The bitrate of VideoToolbox, per pixel of the video. About 6 Mbps in 1080p, like
# x264 with its CRF. Its constant quality (`-q:v`) is only supported by the hardware
# encoder of Apple Silicon, not by the software one it falls back to
VIDEOTOOLBOX_BITS_PER_PIXEL = 3
# Small videos would get too few bits to be watchable
MIN_VIDEOTOOLBOX_BITRATE = 1_000_000


@dataclass(frozen=True)
class SubtitleLook:
    """How the subtitles look, as the user configured them over the video."""

    # The height of the text, relative to the shorter side of the video
    relative_size: float = 0.06
    is_top: bool = False
    # An outline around the text, or a dark box behind it
    is_outline: bool = False


@dataclass(frozen=True)
class BurnedVideo:
    path: Path
    # The characters that no font has, so they're drawn as boxes, in their order
    missing_characters: str = ""


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
) -> BurnedVideo:
    """
    Writes a copy of a video with the subtitles drawn on it, as an MP4 file.

    :param on_progress: Called with the fraction of the video processed.
    :raises ValueError: If there are no subtitles.
    :raises OSError: If the video can't be read, FFmpeg can't draw subtitles (it's
                     built without libass) or it fails.
    :raises TranscriptionCancelledError: If the token is cancelled. The
                                         unfinished file is removed.
    :return: `output_path`, and the characters that couldn't be drawn.
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
            # The warnings tell the characters that no font has, and the level of
            # each message tells them from the errors
            *("-nostdin", "-hide_banner", "-loglevel", "level+warning", "-y"),
            *("-i", str(video_path.resolve())),
            *("-vf", "subtitles=filename=subtitles.ass,format=yuv420p"),
            *("-map", "0:v:0", "-map", "0:a?"),
            *video_encoder_options(features.video_encoder, size),
            *("-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"),
            *("-progress", "pipe:1", "-nostats"),
            str(output_path.resolve()),
        ]
        missing = _run(command, work_dir, duration, on_progress, token, output_path)

    if missing:
        logger.warning("No font has these characters: %s", missing)
    return BurnedVideo(output_path, missing)


def video_encoder_options(encoder: str | None, size: tuple[int, int]) -> list[str]:
    """The options of FFmpeg that encode the video, with one of `VIDEO_ENCODERS`."""
    if encoder == "libx264":
        return ["-c:v", "libx264", "-crf", "20", "-preset", "medium"]
    if encoder == "h264_videotoolbox":
        bitrate = max(
            size[0] * size[1] * VIDEOTOOLBOX_BITS_PER_PIXEL, MIN_VIDEOTOOLBOX_BITRATE
        )
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
) -> str:
    """
    Runs FFmpeg from the folder of the subtitles, so their paths don't have to be
    escaped in the filters.

    :return: The characters that no font has.
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
    # Read along, since FFmpeg would stop if the pipe filled up with warnings
    log = _FFmpegLog()
    log_reader = threading.Thread(target=log.read, args=(process.stderr,), daemon=True)
    log_reader.start()
    try:
        for seconds in _progress_seconds(process.stdout):
            if token.is_cancelled:
                process.kill()
                break
            if duration:
                on_progress("", min(seconds / duration, 1.0))
        process.wait()
        log_reader.join()
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
        raise OSError(
            "\n".join(log.errors) or f"FFmpeg exited with {process.returncode}"
        )
    return "".join(log.missing_characters)


class _FFmpegLog:
    """The errors and the characters without font in the messages of FFmpeg."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        # A dict, which keeps the order, to have each character once
        self.missing_characters: dict[str, None] = {}

    def read(self, lines: Iterator[str]) -> None:
        for line in lines:
            if match := MISSING_GLYPH_PATTERN.search(line):
                self.missing_characters[chr(int(match.group(1), 16))] = None
            elif "[error]" in line or "[fatal]" in line:
                # e.g. `[in#0 @ 0x...] [error] Error opening input: ...`
                self.errors.append(re.sub(r"^.*?\[(error|fatal)\] ", "", line.strip()))


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
        """
        The first fonts installed of `CHINESE_FONTS` and `JAPANESE_FONTS`. Without
        any, libass chooses the ones that have the characters.
        """
        platform = "linux" if sys.platform.startswith("linux") else sys.platform
        chinese = _first_installed(CHINESE_FONTS.get(platform, ()))
        japanese = _first_installed(JAPANESE_FONTS.get(platform, ())) or chinese
        return cls(chinese=chinese or cls.chinese, japanese=japanese or cls.japanese)


def _font_dirs() -> list[Path]:
    if sys.platform == "win32":
        dirs = [Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"]
        if local_app_data := os.environ.get("LOCALAPPDATA"):
            dirs.append(Path(local_app_data) / "Microsoft" / "Windows" / "Fonts")
        return dirs
    return [
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
        Path.home() / "Library" / "Fonts",
    ]


def _is_installed(font: FontCandidate) -> bool:
    if font.file is not None:
        return any((fonts_dir / font.file).is_file() for fonts_dir in _font_dirs())
    fc_list = shutil.which("fc-list")
    if fc_list is None:
        # It can't be known, so libass looks for it
        return True
    try:
        # It exits with 1 if no font matches
        return subprocess.run([fc_list, "-q", font.name], timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return True


@functools.cache
def _first_installed(fonts: tuple[FontCandidate, ...]) -> str | None:
    return next((font.name for font in fonts if _is_installed(font)), None)


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
    (see `LibassFonts.of_system`).
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
