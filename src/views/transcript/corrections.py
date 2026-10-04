from collections.abc import Callable
from typing import TYPE_CHECKING

import customtkinter as ctk

from models.history import HistoryEntry
from models.transcript_segment import TranscriptSegment, join_segments
from utils.i18n import _
from utils.time_format import format_timestamp
from utils.transcript_editing import (
    count_matches,
    edit_segment,
    rename_speakers,
    rename_speakers_in_text,
    replace_in_segments,
    replace_text,
    speakers,
)
from views.entries.delegates import TranscriptDelegate
from views.transcript.edit_dialogs import ReplaceDialog, SpeakersDialog
from views.widgets.text_dialog import TextDialog

if TYPE_CHECKING:
    from views.transcript.transcript_text import TranscriptText


class TranscriptCorrectionsMixin:
    """
    Corrects the transcription of the view: replaces a text, renames the speakers
    or edits the text of a segment.
    """

    # Provided by the view
    entry_id: str
    _entry: HistoryEntry
    _delegate: TranscriptDelegate
    _search_variable: ctk.StringVar
    text: "TranscriptText"

    def _update_transcript(
        self, segments: list[TranscriptSegment], change_text: Callable[[str], str]
    ) -> None:
        """
        Saves the corrected segments. The text follows them, unless the user
        edited it, in which case the same correction is applied to it.
        """
        self.text.save_pending_text()
        entry = self._entry
        if entry.is_text_edited or not segments:
            text = change_text(self.text.get_text())
        else:
            text = join_segments(segments)
        self._delegate.update_transcript(self.entry_id, segments, text)

    def _count_matches(self, find: str, match_case: bool) -> int:
        entry = self._entry
        if entry.segments and not entry.is_text_edited:
            # The labels of the speakers are not part of the segments
            return sum(count_matches(s.text, find, match_case) for s in entry.segments)
        return count_matches(self.text.get_text(), find, match_case)

    def _find_and_replace(self) -> None:
        result = ReplaceDialog(
            self, self._count_matches, initial_text=self._search_variable.get()
        ).get_result()
        if result is None:
            return

        segments = replace_in_segments(
            self._entry.segments, result.find, result.replacement, result.match_case
        )
        self._update_transcript(
            segments,
            lambda text: replace_text(
                text, result.find, result.replacement, result.match_case
            ),
        )
        self._delegate.show_status(_("Replaced."))

    def _rename_speakers(self) -> None:
        names = SpeakersDialog(self, speakers(self._entry.segments)).get_result()
        if not names:
            return

        self._update_transcript(
            rename_speakers(self._entry.segments, names),
            lambda text: rename_speakers_in_text(text, names),
        )

    def _edit_segment(self, idx: int) -> None:
        segment = self._entry.segments[idx]
        text = TextDialog(
            self,
            _("Edit the text"),
            _("Text said at {time}:").format(time=format_timestamp(segment.start)),
            segment.text,
            is_multiline=True,
            allow_empty=False,
        ).get_input()
        if not text or text == segment.text:
            return

        # The edited text keeps the changes of the user, so only the segment changes
        self._update_transcript(
            edit_segment(self._entry.segments, idx, text), lambda text: text
        )
