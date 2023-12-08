from dataclasses import dataclass
from pathlib import Path

from utils.constants import AudioSource


@dataclass
class Transcription:
    text: str | None = None
    language_code: str | None = None
    source: AudioSource | None = None
    file_path_to_transcribe: Path = Path("/")
    method: int = None
    should_translate: bool = False
    should_subtitle: bool = False
