"""
Burns subtitles in several scripts into a video with the FFmpeg bundled in the app
built by PyInstaller, and checks that each one is drawn and that no character
lacks a font. The bundled FFmpeg loads its libraries (libass and the ones it uses)
from the app, which running it from the system doesn't check.

It saves a frame of each subtitle (`frames.png` in the output folder), to look at
how they're drawn.

Usage: python smoke_test_burn.py <folder of the built app> <output folder>
"""

import subprocess
import sys
from pathlib import Path

import av
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from pydub import AudioSegment  # noqa: E402

from utils import subtitle_burner  # noqa: E402
from utils.subtitle_burner import SubtitleLook, burn_subtitles  # noqa: E402
from utils.subtitle_cues import Cue  # noqa: E402

# One second each, with the scripts that need shaping, right to left or their own
# fonts
CUES = [
    Cue(0.0, 1.0, "Hello, مرحبا بالعالم"),
    Cue(1.0, 2.0, "नमस्ते दुनिया"),
    Cue(2.0, 3.0, "你好世界，说话"),
    Cue(3.0, 4.0, "こんにちは、世界\n안녕하세요"),
]
WIDTH, HEIGHT = 640, 360


def find_ffmpeg(app_dir: Path) -> Path:
    name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    paths = [path for path in app_dir.rglob(name) if path.is_file()]
    if not paths:
        raise SystemExit(f"There's no {name} in {app_dir}")
    # Absolute, since FFmpeg runs from the folder of the subtitles
    return paths[0].resolve()


def frames_at_cues(video: Path) -> list[np.ndarray]:
    """A frame from the middle of each subtitle."""
    frames: list[np.ndarray] = []
    with av.open(str(video)) as container:
        for frame in container.decode(video=0):
            is_next = len(frames) < len(CUES) and frame.time is not None
            if is_next and frame.time >= CUES[len(frames)].start + 0.5:
                frames.append(frame.to_ndarray(format="rgb24"))
    return frames


def main() -> int:
    # The console of Windows doesn't encode the texts of the subtitles otherwise
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    app_dir, output_dir = Path(sys.argv[1]), Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg(app_dir)
    AudioSegment.converter = str(ffmpeg)
    print(f"FFmpeg: {ffmpeg}")
    print(subtitle_burner.ffmpeg_features(str(ffmpeg)))
    print(subtitle_burner.LibassFonts.of_system())

    video = output_dir / "video.mp4"
    subprocess.run(
        [
            str(ffmpeg),
            *("-nostdin", "-loglevel", "error", "-y"),
            *("-f", "lavfi", "-i", f"color=gray:s={WIDTH}x{HEIGHT}:d=4:r=10"),
            *("-c:v", "mpeg4", str(video)),
        ],
        check=True,
    )
    burned = burn_subtitles(
        video, CUES, output_dir / "video.subtitled.mp4", SubtitleLook()
    )

    original = frames_at_cues(video)
    frames = frames_at_cues(burned.path)
    Image.fromarray(np.vstack(frames)).save(output_dir / "frames.png")

    failures = []
    for cue, before, after in zip(CUES, original, frames, strict=True):
        changed = (np.abs(after.astype(int) - before).max(axis=2) > 60).sum()
        print(f"{cue.text!r}: {changed} pixels changed")
        if changed < 500:
            failures.append(f"{cue.text!r} wasn't drawn")
    if burned.missing_characters:
        failures.append(f"No font has these characters: {burned.missing_characters}")

    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
