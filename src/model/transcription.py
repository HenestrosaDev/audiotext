from dataclasses import dataclass
from pathlib import Path


@dataclass
class Transcription:
    text: str | None = None
    language_code: str | None = None
    source: str | None = None
    filepath_to_transcribe: Path = Path("/")
