import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from models.transcript_segment import TranscriptSegment
from utils.enums import AudioSource, TranscriptionMethod


class EntryStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    WATCHING = "watching"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    # The app was closed while the entry was being processed
    INTERRUPTED = "interrupted"

    @property
    def is_active(self) -> bool:
        return self in ACTIVE_STATUSES

    @property
    def can_retry(self) -> bool:
        return self in (
            EntryStatus.FAILED,
            EntryStatus.CANCELLED,
            EntryStatus.INTERRUPTED,
        )


ACTIVE_STATUSES = {EntryStatus.QUEUED, EntryStatus.PROCESSING, EntryStatus.WATCHING}
FOLDER_SOURCES = {AudioSource.DIRECTORY.value, AudioSource.WATCH.value}


def new_id() -> str:
    return uuid.uuid4().hex


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class HistoryGroup:
    name: str
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now_iso)


@dataclass
class HistoryEntry:
    """A transcription of the history, with its result and its metadata."""

    # Value of `AudioSource` that was transcribed
    kind: str
    # The path of the file or folder, the URL, or "" for the microphone
    source: str
    title: str
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now_iso)
    status: EntryStatus = EntryStatus.QUEUED
    tag: str = ""
    note: str = ""
    is_pinned: bool = False
    group_id: str | None = None
    # The folder transcription that the entry belongs to, if any
    parent_id: str | None = None
    text: str = ""
    segments: list[TranscriptSegment] = field(default_factory=list)
    # Whether the user has edited the text, which then differs from the segments
    is_text_edited: bool = False
    # Language of the result (e.g. "en"), if known
    language: str | None = None
    method: str | None = None
    error: str = ""
    # The audio or video that can be played: the source file, the downloaded
    # audio of a URL or the recording of the microphone
    media_path: str | None = None
    # Folder where the output files were saved automatically
    output_dir: str | None = None
    # The settings used, to transcribe it again (see `TranscriptionSettings`)
    settings: dict[str, Any] = field(default_factory=dict)
    # Summary generated from the text (see `TranscriptSummary`), if any
    summary: dict[str, Any] = field(default_factory=dict)
    # Translation of the text (see `TranscriptTranslation`), if any
    translation: dict[str, Any] = field(default_factory=dict)

    @property
    def is_folder(self) -> bool:
        return self.kind in FOLDER_SOURCES

    @property
    def created_datetime(self) -> datetime:
        try:
            return datetime.fromisoformat(self.created_at)
        except ValueError:
            return datetime.fromtimestamp(0).astimezone()

    @property
    def model_name(self) -> str | None:
        """
        The model of the method (e.g. "large-v2" or "whisper-1"), if it has one.
        """
        if self.method == TranscriptionMethod.WHISPERX.value:
            return self.settings.get("model_size") or None
        if self.method == TranscriptionMethod.WHISPER_API.value:
            # Older entries didn't store it, and only used this model
            return self.settings.get("openai_model") or "whisper-1"

        return None

    @property
    def source_path(self) -> Path | None:
        """The path of the source on disk, if it's a file or a folder."""
        if self.kind in FOLDER_SOURCES or self.kind == AudioSource.FILE.value:
            return Path(self.source) if self.source else None

        return None

    def matches(self, query: str) -> bool:
        """Whether the entry contains the search query, ignoring the case."""
        query = query.casefold()

        return any(
            query in value.casefold()
            for value in (self.title, self.note, self.tag, self.source, self.text)
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}

        for entry_field in fields(self):
            value = getattr(self, entry_field.name)

            if entry_field.name == "status":
                value = value.value
            elif entry_field.name == "segments":
                value = [segment.to_dict() for segment in value]

            data[entry_field.name] = value

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HistoryEntry":
        known_fields = {entry_field.name for entry_field in fields(cls)}
        values = {key: value for key, value in data.items() if key in known_fields}

        try:
            values["status"] = EntryStatus(values.get("status", "done"))
        except ValueError:
            values["status"] = EntryStatus.DONE

        values["segments"] = [
            TranscriptSegment.from_dict(segment)
            for segment in values.get("segments", [])
        ]

        return cls(**values)
