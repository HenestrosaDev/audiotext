import logging
import subprocess
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from handlers.summary_handler import SummaryHandler
from handlers.translation_handler import MANUAL, TranslationHandler
from interfaces.history_view import HistoryView
from interfaces.summarizer import Summarizer
from interfaces.translator import Translator
from models.summary import TranscriptSummary
from models.transcript_segment import TranscriptSegment
from models.translation import TranscriptTranslation
from utils.background import TaskStarter, start_in_background
from utils.errors import format_error
from utils.history_store import HistoryStore
from utils.system import open_in_file_manager, reveal_in_file_manager

logger = logging.getLogger(__name__)


class HistoryController:
    """
    Renames, annotates, groups, corrects, summarizes, translates and deletes the
    entries of the history. The view asks the user for the values (e.g. the new
    name) and to confirm the deletions before calling it.

    It's kept while the view is rebuilt (e.g. when the interface language
    changes), so the summaries and translations in progress aren't lost.
    """

    def __init__(
        self,
        store: HistoryStore,
        view: HistoryView,
        summarizer: Summarizer | None = None,
        translator: Translator | None = None,
        start_task: TaskStarter = start_in_background,
    ) -> None:
        """
        :param summarizer: Summarizes the transcriptions. By default, with the
                           configured language model.
        :param translator: Translates the transcriptions. By default, with the
                           provider chosen by the user.
        :param start_task: Starts the summaries and the translations, which take a
                           while, without waiting for them.
        """
        self._store = store
        self.view = view
        self._summarizer = summarizer or SummaryHandler()
        self._translator = translator or TranslationHandler()
        self._start_task = start_task
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
            self.view.on_entry_changed(entry_id)

    def set_note(self, entry_id: str, note: str) -> None:
        entry = self._store.get(entry_id)
        if entry is not None and note != entry.note:
            self._store.update(entry, note=note)
            self.view.on_entry_changed(entry_id)

    def set_tag(self, entry_id: str, tag: str) -> None:
        entry = self._store.get(entry_id)
        if entry is not None and tag != entry.tag:
            self._store.update(entry, tag=tag)
            self.view.on_entry_changed(entry_id)

    def toggle_pin(self, entry_id: str) -> None:
        if entry := self._store.get(entry_id):
            self._store.update(entry, is_pinned=not entry.is_pinned)
            self.view.refresh_sidebar()

    def reveal_entry(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        path = entry.source_path if entry else None
        if path is None:
            return
        try:
            reveal_in_file_manager(path)
        except FileNotFoundError as e:
            self.view.on_reveal_failed(path, e)
        except (OSError, subprocess.SubprocessError) as e:
            logger.error("Could not show %s", path, exc_info=e)
            self.view.on_reveal_failed(path, e)

    def open_folder(self, folder: Path) -> None:
        try:
            open_in_file_manager(folder)
        except (OSError, subprocess.SubprocessError) as e:
            logger.error("Could not open %s", folder, exc_info=e)
            self.view.on_open_folder_failed(folder, e)

    def delete_entry(self, entry_id: str) -> None:
        """
        Deletes an entry and, if it's a folder, the entries of its files. A
        transcription in progress must be cancelled first.
        """
        entry = self._store.get(entry_id)
        if entry is None:
            return
        self._store.delete(entry_id)
        # The view of the entry is closed if it was shown, or the one of its folder
        # is updated
        self.view.refresh_entry_view(entry.parent_id or entry_id)
        self.view.refresh_sidebar()

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
            self.view.on_entry_changed(entry_id)

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
                summary = self._summarizer.summarize(text, segments)
            except Exception as e:
                logger.error("Could not summarize %s", entry_id, exc_info=e)
                error = format_error(e)
            self.view.run_on_ui_thread(
                self._on_summary_finished, entry_id, summary, error
            )

        self._start_task(summarize)

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
            self.view.on_summary_finished(entry, None)
        else:
            self._summary_errors[entry_id] = error
            self.view.on_summary_finished(entry, error)

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
                translation = self._translator.translate(
                    text, segments, is_text_edited, language, provider, model
                )
            except Exception as e:
                logger.error("Could not translate %s", entry_id, exc_info=e)
                error = format_error(e)
            self.view.run_on_ui_thread(
                self._on_translation_finished, entry_id, translation, error
            )

        self._start_task(translate)

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
        self.view.refresh_entry_view(entry_id)

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
            self.view.refresh_entry_view(entry_id)

    def remove_translation(self, entry_id: str) -> None:
        if entry := self._store.get(entry_id):
            self._translation_errors.pop(entry_id, None)
            self._store.update(entry, translation={})
            self.view.refresh_entry_view(entry_id)

    def _on_translation_finished(
        self, entry_id: str, translation: TranscriptTranslation | None, error: str
    ) -> None:
        self._translating.discard(entry_id)
        entry = self._store.get(entry_id)
        if entry is None:
            return

        if translation:
            self._store.update(entry, translation=translation.to_dict())
            self.view.on_translation_finished(entry, None)
        else:
            self._translation_errors[entry_id] = error
            self.view.on_translation_finished(entry, error)

    # GROUPS

    def move_to_group(self, entry_id: str, group_id: str | None) -> None:
        if entry := self._store.get(entry_id):
            self._store.update(entry, group_id=group_id)
            self.view.refresh_sidebar()

    def create_group(self, name: str) -> str:
        group = self._store.add_group(name)
        self.view.refresh_sidebar()
        return group.id

    def rename_group(self, group_id: str, name: str) -> None:
        if self._store.get_group(group_id) is not None:
            self._store.rename_group(group_id, name)
            self.view.refresh_sidebar()

    def delete_group(self, group_id: str) -> None:
        if self._store.get_group(group_id) is not None:
            self._store.delete_group(group_id)
            self.view.refresh_sidebar()
