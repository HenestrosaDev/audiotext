from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from utils.enums import AudioSource


@dataclass
class Transcription:
    text: Optional[str] = None
    language_code: Optional[str] = None
    source_type: Optional[AudioSource] = None
    source_path: Path = Path("/")
    method: Optional[int] = None
    output_file_types: list[str] = field(default_factory=lambda: ["txt"])
    should_translate: bool = False
    should_autosave: bool = False
    should_overwrite: bool = False
    youtube_url: str = None
