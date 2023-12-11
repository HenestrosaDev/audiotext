from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from utils.enums import AudioSource


@dataclass
class Transcription:
    text: Optional[str] = None
    language_code: Optional[str] = None
    source: Optional[AudioSource] = None
    file_path_to_transcribe: Path = Path("/")
    method: Optional[int] = None
    should_translate: bool = False
    should_subtitle: bool = False
