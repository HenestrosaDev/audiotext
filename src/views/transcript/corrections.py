from collections.abc import Callable
from typing import TYPE_CHECKING

from models.history import HistoryEntry
from models.transcript_segment import TranscriptSegment, join_segments
from utils.i18n import _
from utils.subtitle_cues import SegmentPart
from utils.transcript_editing import (
    edit_segment_part,
    rename_speakers,
    rename_speakers_in_text,
    replace_in_segments,
    replace_range,
    replace_text,
    speakers,
)
from views.entries.delegates import EntryActions
from views.transcript.edit_dialogs import SpeakersDialog
from views.transcript.transcript_text import PLAIN_TEXT_MODE
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
    # The parts of the segments shown in the transcript
    _parts: list[SegmentPart]
    _actions: EntryActions
    text: "TranscriptText"
    _format_time: Callable[[float], str]

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
        self._actions.transcript.update_transcript(self.entry_id, segments, text)

    def _replace_current(self, replacement: str) -> None:
        """Replaces the current match of the search in the transcription."""
        if self.text.mode == PLAIN_TEXT_MODE:
            self.text.replace_current_match(replacement)
            return
        if (match := self.text.current_match()) is None:
            return

        idx, first, last = match
        part = self._parts[idx]
        try:
            segments = replace_range(
                self._entry.segments,
                part.segment_idx,
                part.first + first,
                part.first + last,
                replacement,
            )
        except ValueError:
            # A segment can't be left without text
            return
        # The edited text keeps the changes of the user, so only the segment changes
        self._update_transcript(segments, lambda text: text)

    def _replace_all(self, find: str, replacement: str, match_case: bool) -> None:
        """Replaces a text in the whole transcription."""
        segments = replace_in_segments(
            self._entry.segments, find, replacement, match_case
        )
        self._update_transcript(
            segments, lambda text: replace_text(text, find, replacement, match_case)
        )

    def _rename_speakers(self) -> None:
        names = SpeakersDialog(self, speakers(self._entry.segments)).get_result()
        if not names:
            return

        self._update_transcript(
            rename_speakers(self._entry.segments, names),
            lambda text: rename_speakers_in_text(text, names),
        )

    def _edit_segment(self, idx: int) -> None:
        part = self._parts[idx]
        segment = part.segment
        text = TextDialog(
            self,
            _("Edit text"),
            _("Text said at {time}:").format(time=self._format_time(segment.start)),
            segment.text,
            is_multiline=True,
            allow_empty=False,
        ).get_input()
        if not text or text == segment.text:
            return

        # The edited text keeps the changes of the user, so only the segment changes
        self._update_transcript(
            edit_segment_part(
                self._entry.segments, part.segment_idx, part.first, part.last, text
            ),
            lambda text: text,
        )
