"""The actions on the entries and the groups of the history."""

import logging
import subprocess
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
from typing import TYPE_CHECKING, Any

from handlers.summary_handler import SummaryHandler
from handlers.translation_handler import MANUAL, TranslationHandler
from models.summary import TranscriptSummary
from models.transcript_segment import TranscriptSegment
from models.translation import TranscriptTranslation
from utils.errors import format_error
from utils.history_store import HistoryStore
from utils.i18n import _
from utils.system import open_in_file_manager, reveal_in_file_manager
from views.widgets.text_dialog import TextDialog

if TYPE_CHECKING:
    from views.history.history_sidebar import HistorySidebar

logger = logging.getLogger(__name__)


class EntryActionsMixin:
    """
    Renames, annotates, groups, corrects, summarizes, translates and deletes the
    entries of the history, on behalf of the sidebar and the views of the entries.
    """

    # Provided by the main window
    _store: HistoryStore
    sidebar: "HistorySidebar"
    _entry_view_id: str | None
    show_welcome: Callable[[], None]
    show_status: Callable[..., None]
    cancel_entry: Callable[[str], None]
    run_on_ui_thread: Callable[..., None]
    winfo_toplevel: Callable[[], Any]
    _on_entry_changed: Callable[..., None]
    _refresh_entry_view: Callable[[str], None]

    def _init_entry_actions(self) -> None:
        # The entries being summarized, and why the last summary of each failed
        self._summarizing: set[str] = set()
        self._summary_errors: dict[str, str] = {}
        # The same for the translations
        self._translating: set[str] = set()
        self._translation_errors: dict[str, str] = {}

    # ENTRIES

    def rename_entry(self, entry_id: str, title: str) -> None:
        if entry := self._store.get(entry_id):
            self._store.update(entry, title=title)
            self._on_entry_changed(entry_id)

    def rename_entry_dialog(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None:
            return
        title = TextDialog(
            self,
            _("Rename"),
            _("Name of the transcription:"),
            entry.title,
            allow_empty=False,
        ).get_input()
        if title:
            self.rename_entry(entry_id, title)

    def edit_note(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None:
            return
        note = TextDialog(
            self,
            _("Note"),
            _("A note about “{title}”:").format(title=entry.title),
            entry.note,
            is_multiline=True,
        ).get_input()
        if note is not None and note != entry.note:
            self._store.update(entry, note=note)
            self._on_entry_changed(entry_id)

    def delete_note(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None or not entry.note:
            return
        if messagebox.askyesno(
            _("Delete note"),
            _("Delete the note of “{title}”?").format(title=entry.title),
            icon=messagebox.WARNING,
            parent=self.winfo_toplevel(),
        ):
            self._store.update(entry, note="")
            self._on_entry_changed(entry_id)

    def edit_tag(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None:
            return
        tag = TextDialog(
            self,
            _("Tag"),
            _("Tag of “{title}”. Leave it empty to show the kind of source.").format(
                title=entry.title
            ),
            entry.tag,
            suggestions=self._store.tags(),
        ).get_input()
        if tag is not None and tag != entry.tag:
            self._store.update(entry, tag=tag)
            self._on_entry_changed(entry_id)

    def toggle_pin(self, entry_id: str) -> None:
        if entry := self._store.get(entry_id):
            self._store.update(entry, is_pinned=not entry.is_pinned)
            self.sidebar.refresh()

    def reveal_entry(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        path = entry.source_path if entry else None
        if path is None:
            return
        try:
            reveal_in_file_manager(path)
        except FileNotFoundError:
            self.show_status(
                _("The file was moved or deleted: {path}").format(path=path),
                is_error=True,
            )
        except (OSError, subprocess.SubprocessError) as e:
            logger.error("Could not show %s", path, exc_info=e)
            self.show_status(
                _("Could not open the file manager: {error}").format(error=e),
                is_error=True,
            )

    def open_folder(self, folder: Path) -> None:
        try:
            open_in_file_manager(folder)
        except (OSError, subprocess.SubprocessError) as e:
            logger.error("Could not open %s", folder, exc_info=e)
            self.show_status(
                _("Could not open the folder: {error}").format(error=e), is_error=True
            )

    def delete_entry(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None:
            return

        message = _("Delete “{title}” from the history?").format(title=entry.title)
        if entry.is_folder:
            message += "\n\n" + _("The transcriptions of its files are deleted too.")
        message += "\n\n" + _("Your audio, video and saved files are not deleted.")
        if not messagebox.askyesno(
            _("Delete transcription"), message, parent=self.winfo_toplevel()
        ):
            return

        if entry.status.is_active:
            self.cancel_entry(entry_id)

        shown_id = self._entry_view_id
        deleted = self._store.delete(entry_id)
        if shown_id in deleted:
            self.show_welcome()
        self.sidebar.refresh()
        if entry.parent_id:
            self._refresh_entry_view(entry.parent_id)

    # TRANSCRIPT

    def save_text(self, entry_id: str, text: str) -> None:
        if entry := self._store.get(entry_id):
            self._store.update(entry, text=text, is_text_edited=True)

    def update_transcript(
        self, entry_id: str, segments: list[TranscriptSegment], text: str
    ) -> None:
        """Saves the corrections of a transcription (e.g. a replaced word)."""
        if entry := self._store.get(entry_id):
            self._store.update(entry, segments=segments, text=text)
            self._on_entry_changed(entry_id)

    # SUMMARIES

    def summarize_entry(self, entry_id: str) -> None:
        """Summarizes a transcription in the background."""
        entry = self._store.get(entry_id)
        if entry is None or entry_id in self._summarizing:
            return

        self._summarizing.add(entry_id)
        self._summary_errors.pop(entry_id, None)
        text, segments = entry.text, entry.segments

        def summarize() -> None:
            summary: TranscriptSummary | None = None
            error = ""
            try:
                summary = SummaryHandler.summarize(text, segments)
            except Exception as e:
                logger.error("Could not summarize %s", entry_id, exc_info=e)
                error = format_error(e)
            self.run_on_ui_thread(self._on_summary_finished, entry_id, summary, error)

        threading.Thread(target=summarize, daemon=True).start()

    def is_summarizing(self, entry_id: str) -> bool:
        return entry_id in self._summarizing

    def get_summary_error(self, entry_id: str) -> str:
        return self._summary_errors.get(entry_id, "")

    def _on_summary_finished(
        self, entry_id: str, summary: TranscriptSummary | None, error: str
    ) -> None:
        self._summarizing.discard(entry_id)
        entry = self._store.get(entry_id)
        if entry is None:
            return

        if summary:
            self._store.update(entry, summary=summary.to_dict())
            self.show_status(
                _("The summary of “{title}” is ready.").format(title=entry.title)
            )
        else:
            self._summary_errors[entry_id] = error
            self.show_status(
                _("Could not summarize “{title}”: {error}").format(
                    title=entry.title, error=error
                ),
                is_error=True,
            )
        self._refresh_entry_view(entry_id)

    # TRANSLATIONS

    def translate_entry(
        self, entry_id: str, language: str, provider: str, model: str = ""
    ) -> None:
        """Translates a transcription in the background."""
        entry = self._store.get(entry_id)
        if entry is None or entry_id in self._translating:
            return

        self._translating.add(entry_id)
        self._translation_errors.pop(entry_id, None)
        text, segments, is_text_edited = (
            entry.text,
            entry.segments,
            entry.is_text_edited,
        )

        def translate() -> None:
            translation: TranscriptTranslation | None = None
            error = ""
            try:
                translation = TranslationHandler.translate(
                    text, segments, is_text_edited, language, provider, model
                )
            except Exception as e:
                logger.error("Could not translate %s", entry_id, exc_info=e)
                error = format_error(e)
            self.run_on_ui_thread(
                self._on_translation_finished, entry_id, translation, error
            )

        threading.Thread(target=translate, daemon=True).start()

    def start_manual_translation(self, entry_id: str, language: str) -> None:
        """
        Starts a translation for the user to write from scratch: each segment
        keeps its timestamps, with an empty text.
        """
        entry = self._store.get(entry_id)
        if entry is None or entry_id in self._translating:
            return

        self._translation_errors.pop(entry_id, None)
        translation = TranscriptTranslation(
            language=language,
            text="",
            segments=tuple(
                replace(segment, text="", words=()) for segment in entry.segments
            ),
            provider=MANUAL,
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        self._store.update(entry, translation=translation.to_dict())
        self._refresh_entry_view(entry_id)

    def is_translating(self, entry_id: str) -> bool:
        return entry_id in self._translating

    def get_translation_error(self, entry_id: str) -> str:
        return self._translation_errors.get(entry_id, "")

    def save_translation_text(self, entry_id: str, text: str) -> None:
        """Saves the text of the translation edited by the user."""
        entry = self._store.get(entry_id)
        translation = entry and TranscriptTranslation.from_dict(entry.translation)
        if entry and translation:
            self._store.update(
                entry,
                translation=replace(
                    translation, text=text, is_text_edited=True
                ).to_dict(),
            )

    def update_translation(
        self, entry_id: str, segments: list[TranscriptSegment], text: str
    ) -> None:
        """
        Saves the corrections of a translation, e.g. an edited, retimed, added or
        deleted segment.
        """
        entry = self._store.get(entry_id)
        translation = entry and TranscriptTranslation.from_dict(entry.translation)
        if entry and translation:
            self._store.update(
                entry,
                translation=replace(
                    translation, segments=tuple(segments), text=text
                ).to_dict(),
            )
            self._refresh_entry_view(entry_id)

    def remove_translation(self, entry_id: str) -> None:
        if entry := self._store.get(entry_id):
            self._translation_errors.pop(entry_id, None)
            self._store.update(entry, translation={})
            self._refresh_entry_view(entry_id)

    def _on_translation_finished(
        self, entry_id: str, translation: TranscriptTranslation | None, error: str
    ) -> None:
        self._translating.discard(entry_id)
        entry = self._store.get(entry_id)
        if entry is None:
            return

        if translation:
            self._store.update(entry, translation=translation.to_dict())
            self.show_status(
                _("The translation of “{title}” is ready.").format(title=entry.title)
            )
        else:
            self._translation_errors[entry_id] = error
            self.show_status(
                _("Could not translate “{title}”: {error}").format(
                    title=entry.title, error=error
                ),
                is_error=True,
            )
        self._refresh_entry_view(entry_id)

    # GROUPS

    def move_to_group(self, entry_id: str, group_id: str | None) -> None:
        if entry := self._store.get(entry_id):
            self._store.update(entry, group_id=group_id)
            self.sidebar.refresh()

    def move_to_new_group(self, entry_id: str) -> None:
        if group_id := self.create_group():
            self.move_to_group(entry_id, group_id)

    def create_group(self) -> str | None:
        name = TextDialog(
            self,
            _("New group"),
            _("Name of the group:"),
            ok_text=_("Create"),
            allow_empty=False,
        ).get_input()
        if not name:
            return None
        group = self._store.add_group(name)
        self.sidebar.refresh()
        return group.id

    def rename_group(self, group_id: str) -> None:
        group = self._store.get_group(group_id)
        if group is None:
            return
        name = TextDialog(
            self,
            _("Rename group"),
            _("Name of the group:"),
            group.name,
            allow_empty=False,
        ).get_input()
        if name:
            self._store.rename_group(group_id, name)
            self.sidebar.refresh()

    def delete_group(self, group_id: str) -> None:
        group = self._store.get_group(group_id)
        if group is None:
            return
        if messagebox.askyesno(
            _("Delete group"),
            _(
                "Delete the group “{name}”? Its transcriptions are kept, without a group."
            ).format(name=group.name),
            parent=self.winfo_toplevel(),
        ):
            self._store.delete_group(group_id)
            self.sidebar.refresh()
