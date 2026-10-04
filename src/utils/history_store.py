import contextlib
import json
import logging
import os
import re
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from models.history import EntryStatus, HistoryEntry, HistoryGroup

logger = logging.getLogger(__name__)

FILE_VERSION = 1


class HistoryStore:
    """
    Keeps the history of transcriptions and their groups in a JSON file.

    The entries of a folder transcription are children of the folder entry
    (`parent_id`). The audio downloaded from a URL or recorded from the microphone
    is kept in a folder of `media_dir` named after the entry, which is removed
    when the entry is deleted. The transcribed files of the user are never
    removed.

    The store is not thread-safe: it must only be used from the UI thread.
    """

    def __init__(self, file_path: Path, media_dir: Path) -> None:
        self.file_path = file_path
        self.media_dir = media_dir
        self._entries: dict[str, HistoryEntry] = {}
        self._groups: dict[str, HistoryGroup] = {}

        self._load()

    # ENTRIES

    def get(self, entry_id: str | None) -> HistoryEntry | None:
        return self._entries.get(entry_id) if entry_id else None

    @property
    def entries(self) -> list[HistoryEntry]:
        return list(self._entries.values())

    def top_level(self) -> list[HistoryEntry]:
        """The entries that don't belong to a folder, the newest first."""
        return sorted(
            (entry for entry in self._entries.values() if entry.parent_id is None),
            key=lambda entry: entry.created_datetime,
            reverse=True,
        )

    def children(self, parent_id: str) -> list[HistoryEntry]:
        """The entries of a folder transcription, sorted by their path."""
        return sorted(
            (e for e in self._entries.values() if e.parent_id == parent_id),
            key=lambda entry: entry.source.casefold(),
        )

    def find_child(self, parent_id: str, source: str) -> HistoryEntry | None:
        return next(
            (
                entry
                for entry in self._entries.values()
                if entry.parent_id == parent_id and entry.source == source
            ),
            None,
        )

    def add(self, entry: HistoryEntry) -> HistoryEntry:
        self._entries[entry.id] = entry
        self.save()
        return entry

    def add_many(self, entries: Iterable[HistoryEntry]) -> None:
        for entry in entries:
            self._entries[entry.id] = entry
        self.save()

    def update(self, entry: HistoryEntry, **changes: Any) -> HistoryEntry:
        """Changes the given attributes of an entry and saves the history."""
        for name, value in changes.items():
            if not hasattr(entry, name):
                raise AttributeError(f"HistoryEntry has no attribute {name!r}")
            setattr(entry, name, value)

        self._entries[entry.id] = entry
        self.save()
        return entry

    def delete(self, entry_id: str) -> list[str]:
        """
        Deletes an entry and its children, and the media kept for them.

        :return: The IDs of the deleted entries.
        """
        entry = self._entries.get(entry_id)
        if entry is None:
            return []

        deleted = [entry, *self.children(entry_id)]
        for deleted_entry in deleted:
            self._entries.pop(deleted_entry.id, None)
            self._remove_owned_media(deleted_entry)

        self.save()
        return [deleted_entry.id for deleted_entry in deleted]

    def tags(self) -> list[str]:
        """The tags used in the history, sorted alphabetically."""
        return sorted(
            {entry.tag for entry in self._entries.values() if entry.tag},
            key=str.casefold,
        )

    def new_media_path(self, entry_id: str, file_name: str) -> Path:
        """
        Returns the path where the media of an entry (e.g. a recording) is kept.
        Each entry has its own folder, so the file can have a readable name, which
        is also the name of the files saved automatically.
        """
        return self.media_dir / entry_id / sanitize_file_name(file_name)

    # GROUPS

    @property
    def groups(self) -> list[HistoryGroup]:
        return sorted(self._groups.values(), key=lambda group: group.name.casefold())

    def get_group(self, group_id: str | None) -> HistoryGroup | None:
        return self._groups.get(group_id) if group_id else None

    def add_group(self, name: str) -> HistoryGroup:
        group = HistoryGroup(name=name.strip())
        self._groups[group.id] = group
        self.save()
        return group

    def rename_group(self, group_id: str, name: str) -> None:
        if group := self._groups.get(group_id):
            group.name = name.strip()
            self.save()

    def delete_group(self, group_id: str) -> None:
        """Deletes a group. Its entries are kept, without a group."""
        self._groups.pop(group_id, None)

        for entry in self._entries.values():
            if entry.group_id == group_id:
                entry.group_id = None

        self.save()

    # PERSISTENCE

    def save(self) -> None:
        data = {
            "version": FILE_VERSION,
            "groups": [asdict(group) for group in self._groups.values()],
            "entries": [entry.to_dict() for entry in self._entries.values()],
        }

        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            # Written to a temporary file first, so a crash never corrupts it
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.file_path.parent,
                prefix=".history-",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                json.dump(data, temp_file, ensure_ascii=False)
            os.replace(temp_file.name, self.file_path)
        except OSError:
            logger.exception("Could not save the history to %s", self.file_path)

    def _load(self) -> None:
        if not self.file_path.exists():
            return

        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.exception("Could not read the history from %s", self.file_path)
            # Kept aside, so the next save doesn't lose the history
            backup_path = self.file_path.with_suffix(".corrupted.json")
            with contextlib.suppress(OSError):
                os.replace(self.file_path, backup_path)
            return

        for group_data in data.get("groups", []):
            try:
                group = HistoryGroup(**group_data)
                self._groups[group.id] = group
            except TypeError:
                logger.warning("Skipping invalid group: %s", group_data)

        for entry_data in data.get("entries", []):
            try:
                entry = HistoryEntry.from_dict(entry_data)
            except (KeyError, TypeError, ValueError):
                logger.warning("Skipping invalid history entry: %s", entry_data)
                continue

            # The processes don't survive the app being closed
            if entry.status.is_active:
                entry.status = EntryStatus.INTERRUPTED

            if entry.group_id not in self._groups:
                entry.group_id = None

            self._entries[entry.id] = entry

    def _remove_owned_media(self, entry: HistoryEntry) -> None:
        entry_media_dir = self.media_dir / entry.id

        try:
            if entry_media_dir.is_dir():
                shutil.rmtree(entry_media_dir)
        except OSError:
            logger.exception("Could not remove %s", entry_media_dir)


def sanitize_file_name(name: str, max_length: int = 120) -> str:
    """
    Replaces the characters that are not allowed in file names on any operating
    system, so a title or a URL can be used as a file name.
    """
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", name).strip(" .-")
    return name[:max_length].rstrip(" .-") or "media"
