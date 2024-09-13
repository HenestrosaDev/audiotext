from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from utils.enums import AudioSource, TranscriptionMethod


@dataclass
class Transcription:
    text: Optional[str] = None
    language_code: Optional[str] = None
    audio_source: Optional[AudioSource] = None
    audio_source_path: Optional[Path] = None
    method: Optional[TranscriptionMethod] = None
    output_file_types: Optional[list[str]] = None
    output_path: Optional[Path] = None
    should_translate: bool = False
    should_autosave: bool = False
    should_overwrite: bool = False
    youtube_url: Optional[str] = None
