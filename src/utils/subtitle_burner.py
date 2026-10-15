"""
Burns subtitles into a copy of a video, so they're shown by any player, and in the
sites and apps that don't load subtitle files (e.g. social networks).

FFmpeg draws them with libass when it's built with it (the `subtitles` filter).
Otherwise (e.g. the FFmpeg of Homebrew, which macOS bundles), each subtitle is drawn
with Pillow into a transparent image, and the images are laid over the video.
"""

import functools
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
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

# The fonts used without libass, from the first one found. Their glyphs should
# cover the text, so the texts of Chinese, Japanese and Korean have their own
LATIN_FONTS = {
    "darwin": [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ],
    "win32": ["arialbd.ttf", "segoeuib.ttf", "arial.ttf"],
    "linux": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ],
}
WIDE_FONTS = {
    "darwin": [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ],
    "win32": ["msyhbd.ttc", "YuGothB.ttc", "malgunbd.ttf", "msyh.ttc"],
    "linux": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ],
}


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
    has_x264: bool


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

    filters = run("-filters").split()
    return FFmpegFeatures(
        has_libass="subtitles" in filters,
        has_x264="libx264" in run("-encoders").split(),
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
    :raises OSError: If the video can't be read or FFmpeg fails.
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
    duration = probe_media(video_path).duration
    size = decoded_video_size(video_path)

    with tempfile.TemporaryDirectory(prefix="audiotext-burn-") as temp_dir:
        work_dir = Path(temp_dir)
        if features.has_libass:
            fonts = copy_fonts(work_dir / "fonts")
            write_ass(cues, work_dir / "subtitles.ass", look, size, fonts)
            inputs: list[str] = []
            video_filter = "[0:v]subtitles=filename=subtitles.ass:fontsdir=fonts"
        else:
            write_overlays(cues, work_dir, look, size)
            inputs = ["-f", "concat", "-safe", "0", "-i", "subtitles.ffconcat"]
            video_filter = "[0:v][1:v]overlay=0:0:eof_action=pass:format=auto"

        command = [
            ffmpeg,
            *("-nostdin", "-hide_banner", "-loglevel", "error", "-y"),
            *("-i", str(video_path.resolve())),
            *inputs,
            *("-filter_complex", f"{video_filter},format=yuv420p[video]"),
            *("-map", "[video]", "-map", "0:a?"),
            *(("-c:v", "libx264", "-crf", "20", "-preset", "medium")),
            *("-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"),
            *("-progress", "pipe:1", "-nostats"),
            str(output_path.resolve()),
        ]
        if not features.has_x264:
            # FFmpeg chooses the default encoder of MP4
            command[command.index("-c:v") : command.index("-c:a")] = []

        _run(command, work_dir, duration, on_progress, token, output_path)

    return output_path


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
    """The fonts given to libass, by their names."""

    latin: str = "Arial"
    # For the text in Chinese, Japanese or Korean, if one was found
    wide: str | None = None


def copy_fonts(fonts_dir: Path) -> LibassFonts:
    """
    Copies the fonts of the system that are used without libass, so libass draws
    the same ones even if it can't find the fonts of the system on its own.
    """
    fonts_dir.mkdir()
    names: dict[bool, str] = {}
    for is_wide in (False, True):
        path = next((path for path in _font_paths(is_wide) if path.is_file()), None)
        if path is None:
            continue
        try:
            name = ImageFont.truetype(str(path)).getname()[0]
            shutil.copy(path, fonts_dir / f"{int(is_wide)}{path.suffix}")
        except OSError:
            logger.warning("Could not copy the font %s", path, exc_info=True)
            continue
        # The name is a field of the styles, which are separated by commas
        if name and "," not in name:
            names[is_wide] = name
    return LibassFonts(names.get(False, "Arial"), names.get(True))


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
    are in pixels. The ones with Chinese, Japanese or Korean characters have the
    style of the font that has them, since libass may not look for the missing
    glyphs in other fonts.
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
        style("Wide", fonts.wide or fonts.latin),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text",
    ]
    for cue in cues:
        # The braces start the tags of ASS, and the backslash its line breaks.
        # Neither can be escaped
        text = cue.text.replace("{", "(").replace("}", ")").replace("\\", "/")
        style_name = "Wide" if has_wide_characters(text) else "Default"
        text = text.replace("\n", "\\N")
        lines.append(
            f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},{style_name},,"
            f"0,0,0,,{text}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# PILLOW


def _font_paths(is_wide: bool) -> list[Path]:
    platform = "linux" if sys.platform.startswith("linux") else sys.platform
    names = (WIDE_FONTS if is_wide else LATIN_FONTS).get(platform, [])
    fonts_dir = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"
    return [
        Path(name) if Path(name).is_absolute() else fonts_dir / name for name in names
    ]


@functools.cache
def load_font(size: int, is_wide: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    The first font found for the text, or the one of Pillow, which only has the
    Latin characters.
    """
    for path in _font_paths(is_wide):
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                logger.warning("Could not load the font %s", path)
    return ImageFont.load_default(size)


def wrap_line(
    line: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: float,
) -> list[str]:
    """
    Splits a line that's wider than the video, at its spaces, or between any
    characters if it has none (e.g. Chinese).
    """
    draw = ImageDraw.Draw(Image.new("L", (1, 1)))
    words = line.split(" ") if " " in line.strip() else list(line)
    separator = " " if " " in line.strip() else ""
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current}{separator}{word}" if current else word
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def render_subtitle(
    text: str, look: SubtitleLook, size: tuple[int, int]
) -> Image.Image:
    """The subtitle drawn over a transparent image of the size of the video."""
    width, height = size
    text_size = font_size(look, size)
    font = load_font(text_size, has_wide_characters(text))
    lines = [
        wrapped
        for line in text.split("\n")
        for wrapped in wrap_line(line, font, width * MAX_LINE_RATIO)
    ]
    text = "\n".join(lines)

    stroke = max(round(text_size / 16), 1) if look.is_outline else 0
    spacing = round(text_size * 0.2)
    # Its top at the margin, or its bottom
    anchor = "ma" if look.is_top else "md"
    position = (width / 2, margin(size) if look.is_top else height - margin(size))

    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if not look.is_outline:
        left, top, right, bottom = draw.multiline_textbbox(
            position, text, font, anchor, spacing, "center"
        )
        padding_x, padding_y = round(text_size * 0.4), round(text_size * 0.15)
        draw.rectangle(
            (left - padding_x, top - padding_y, right + padding_x, bottom + padding_y),
            fill=(0, 0, 0, round(BACKGROUND_OPACITY * 255)),
        )

    # Drawn apart and laid over it, since drawing replaces the pixels of the box
    # instead of blending them
    text_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(text_layer).multiline_text(
        position,
        text,
        fill=(255, 255, 255, 255),
        font=font,
        anchor=anchor,
        spacing=spacing,
        align="center",
        stroke_width=stroke,
        stroke_fill=(0, 0, 0, 255),
    )
    return Image.alpha_composite(image, text_layer)


def has_wide_characters(text: str) -> bool:
    """
    Whether the text has characters of Chinese, Japanese or Korean, which the
    fonts of the Latin alphabet don't have.
    """
    return any(unicodedata.east_asian_width(char) in ("W", "F") for char in text)


def write_overlays(
    cues: list[Cue], work_dir: Path, look: SubtitleLook, size: tuple[int, int]
) -> None:
    """
    Draws each subtitle into an image, and writes the list of the images with the
    time each one is shown (`subtitles.ffconcat`), for the concat demuxer of
    FFmpeg. An empty image is shown between them.
    """
    Image.new("RGBA", size, (0, 0, 0, 0)).save(work_dir / "blank.png")
    lines = ["ffconcat version 1.0"]
    position = 0.0

    def show(file_name: str, until: float) -> None:
        nonlocal position
        lines.extend([f"file {file_name}", f"duration {until - position:.3f}"])
        position = until

    for idx, cue in enumerate(cues):
        # Overlapping subtitles are cut, since only one is shown at a time
        start, end = max(cue.start, position), cue.end
        if end <= start:
            continue
        if start > position:
            show("blank.png", start)
        file_name = f"subtitle{idx:05}.png"
        render_subtitle(cue.text, look, size).save(work_dir / file_name)
        show(file_name, end)

    # The last image is left on screen until the end of the video, and the concat
    # demuxer needs it repeated to apply its duration
    lines.extend(["file blank.png", "duration 1", "file blank.png"])
    (work_dir / "subtitles.ffconcat").write_text("\n".join(lines) + "\n")
