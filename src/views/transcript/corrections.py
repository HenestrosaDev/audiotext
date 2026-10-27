from collections.abc import Callable
from dataclasses import dataclass, replace
from tkinter import messagebox
from typing import TYPE_CHECKING, Any

from models.transcript_segment import TranscriptSegment, join_segments
from utils.i18n import _
from utils.subtitle_cues import SegmentPart
from utils.transcript_editing import (
    delete_segment,
    edit_segment_part,
    insert_segment,
    rename_speakers,
    rename_speakers_in_text,
    replace_in_segments,
    replace_range,
    replace_text,
    set_segment_speaker,
    set_segment_timing,
    speakers,
    split_segment,
)
from views.transcript.edit_dialogs import (
    SpeakerDialog,
    SpeakersDialog,
    Timing,
    TimingDialog,
)
from views.transcript.transcript_text import PLAIN_TEXT_MODE
from views.widgets.text_dialog import TextDialog

if TYPE_CHECKING:
    from views.transcript.transcript_text import TranscriptText

# How long a subtitle added by default lasts, if there is no gap to fill until the
# next one
NEW_SEGMENT_SECONDS = 2.0


@dataclass(frozen=True)
class SegmentSource:
    """
    The segments that a `SegmentEditor` corrects (those of the transcription or of
    a translation), where they're shown and how they're saved.
    """

    text: "TranscriptText"
    # The segments, or None if there are none to correct (e.g. no translation)
    segments: Callable[[], list[TranscriptSegment] | None]
    # The parts of the segments shown in the text (see `transcript_parts`)
    parts: Callable[[], list[SegmentPart]]
    # Whether the user edited the text, which then doesn't follow the segments
    is_text_edited: Callable[[], bool]
    # Saves the corrected segments and the text
    save: Callable[[list[TranscriptSegment], str], None]
    # The title and the message of the dialog to edit the text of a segment
    edit_prompt: Callable[[TranscriptSegment], tuple[str, str]]
    # Whether a segment can be left without text, e.g. one of a translation, which
    # can be translated later
    allow_empty: bool = False
    # Whether who says each segment can be changed, e.g. in the transcription,
    # whose speakers are identified by the diarization
    edits_speakers: bool = False


class SegmentEditor:
    """
    Corrects the segments of a text: replaces a text, renames the speakers, edits
    the text or the timing of a segment, or adds and deletes segments.
    """

    def __init__(
        self,
        master: Any,
        source: SegmentSource,
        format_time: Callable[[float], str],
    ) -> None:
        """
        :param master: The widget the dialogs are shown over.
        :param format_time: Formats the time of a segment, as the user chose.
        """
        self._master = master
        self._source = source
        self._format_time = format_time

    def update(
        self, segments: list[TranscriptSegment], change_text: Callable[[str], str]
    ) -> None:
        """
        Saves the corrected segments. The text follows them, unless the user
        edited it, in which case the same correction is applied to it.
        """
        source = self._source
        source.text.save_pending_text()
        if source.is_text_edited() or not segments:
            text = change_text(source.text.get_text())
        else:
            text = join_segments(segments)
        source.save(segments, text)

    def replace_current(self, replacement: str) -> None:
        """Replaces the current match of the search."""
        text = self._source.text
        if text.mode == PLAIN_TEXT_MODE:
            text.replace_current_match(replacement)
            return
        segments = self._source.segments()
        if segments is None or (match := text.current_match()) is None:
            return

        idx, first, last = match
        part = self._source.parts()[idx]
        try:
            segments = replace_range(
                segments,
                part.segment_idx,
                part.first + first,
                part.first + last,
                replacement,
                allow_empty=self._source.allow_empty,
            )
        except ValueError:
            # A segment can't be left without text
            return
        # The edited text keeps the changes of the user, so only the segment changes
        self.update(segments, lambda edited_text: edited_text)

    def replace_all(self, find: str, replacement: str, match_case: bool) -> None:
        """Replaces a text everywhere."""
        self._source.text.save_pending_text()
        segments = self._source.segments()
        if segments is None:
            return

        self.update(
            replace_in_segments(segments, find, replacement, match_case),
            lambda text: replace_text(text, find, replacement, match_case),
        )

    def rename_speakers(self) -> None:
        segments = self._source.segments()
        if not segments:
            return
        names = SpeakersDialog(self._master, speakers(segments)).get_result()
        if not names:
            return

        self.update(
            rename_speakers(segments, names),
            lambda text: rename_speakers_in_text(text, names),
        )

    def edit_text(self, idx: int) -> None:
        """Edits the text of a part shown in the text, keeping the rest of it."""
        segments = self._source.segments()
        parts = self._source.parts()
        if segments is None or idx >= len(parts):
            return

        part = parts[idx]
        segment = part.segment
        title, message = self._source.edit_prompt(segment)
        text = TextDialog(
            self._master,
            title,
            message,
            segment.text,
            is_multiline=True,
            allow_empty=False,
        ).get_input()
        if not text or not text.strip() or text == segment.text:
            return

        # The edited text keeps the changes of the user, so only the segment changes
        self.update(
            edit_segment_part(segments, part.segment_idx, part.first, part.last, text),
            lambda edited_text: edited_text,
        )

    def edit_timing(self, idx: int) -> None:
        split = self._split_part(idx)
        if split is None:
            return

        segments, idx = split
        segment = segments[idx]
        timing = TimingDialog(
            self._master,
            _("Edit timing"),
            _("Save"),
            self._describe(segment),
            Timing(segment.start, segment.end),
            # The timings of its words no longer apply (see `set_segment_timing`)
            note=(
                _(
                    "Its words lose their timing and their confidence, so they "
                    "won't be highlighted anymore."
                )
                if segment.words
                else ""
            ),
        ).get_result()
        if timing is None or (timing.start, timing.end) == (segment.start, segment.end):
            return

        self.update(
            set_segment_timing(segments, idx, timing.start, timing.end),
            lambda text: text,
        )

    def add_after(self, idx: int) -> None:
        """
        Adds a segment after a part, and asks for its text right away. If it can't
        be left without text, it's only added once it has one.
        """
        split = self._split_part(idx)
        if split is None:
            return

        segments, idx = split

        # By default, it fills the gap until the next segment, said by the same
        # speaker
        previous = segments[idx]
        start = previous.end
        following = segments[idx + 1].start if idx + 1 < len(segments) else start
        end = following if following > start else start + NEW_SEGMENT_SECONDS
        names = speakers(segments) if self._source.edits_speakers else []
        timing = TimingDialog(
            self._master,
            _("Add subtitle"),
            _("Add"),
            _("The new subtitle goes after the one at {time}:").format(
                time=self._format_time(previous.start)
            ),
            Timing(start, end, previous.speaker),
            speakers=names or None,
        ).get_result()
        if timing is None:
            return

        speaker = timing.speaker if names else previous.speaker
        added = TranscriptSegment(timing.start, timing.end, "", speaker)
        if not self._source.allow_empty:
            title, message = self._source.edit_prompt(added)
            text = TextDialog(
                self._master, title, message, is_multiline=True, allow_empty=False
            ).get_input()
            if not text or not text.strip():
                return
            self.update(
                insert_segment(segments, replace(added, text=text)), lambda text: text
            )
            return

        segments = insert_segment(segments, added)
        self.update(segments, lambda text: text)
        # It's filled right away, or it's left to fill later
        added_idx = next(i for i, segment in enumerate(segments) if segment is added)
        self.edit_text(
            next(
                i
                for i, part in enumerate(self._source.parts())
                if part.segment_idx == added_idx
            )
        )

    def delete(self, idx: int) -> None:
        """Deletes a part, once confirmed if it has text."""
        split = self._split_part(idx)
        if split is None or len(split[0]) <= 1:
            return

        segments, idx = split
        segment = segments[idx]
        if segment.text and not messagebox.askyesno(
            _("Delete subtitle"),
            _("Delete the subtitle “{text}”?").format(text=segment.text),
            icon=messagebox.WARNING,
            parent=self._master.winfo_toplevel(),
        ):
            return
        self.update(delete_segment(segments, idx), lambda text: text)

    def change_speaker(self, idx: int) -> None:
        """Changes who says a part, choosing one of the speakers or a new one."""
        split = self._split_part(idx)
        if split is None:
            return

        segments, idx = split
        segment = segments[idx]
        speaker = SpeakerDialog(
            self._master, self._describe(segment), speakers(segments), segment.speaker
        ).get_result()
        if speaker is None or speaker == segment.speaker:
            return

        self.update(set_segment_speaker(segments, idx, speaker), lambda text: text)

    def _split_part(self, idx: int) -> tuple[list[TranscriptSegment], int] | None:
        """
        Makes a part shown in the text a segment of its own, to change its timing,
        add a segment after it or delete it, which are changes of what the user
        sees, not of the whole segment.

        :return: The segments, with the segment of the part split into its parts,
                 and the index of the part among them.
        """
        segments = self._source.segments()
        parts = self._source.parts()
        if segments is None or idx >= len(parts):
            return None

        part = parts[idx]
        pieces = [p for p in parts if p.segment_idx == part.segment_idx]
        if len(pieces) == 1:
            return segments, part.segment_idx
        segments = split_segment(
            segments, part.segment_idx, [piece.segment for piece in pieces]
        )
        return segments, part.segment_idx + pieces.index(part)

    def _describe(self, segment: TranscriptSegment) -> str:
        """Its text, or the time it starts if it has none yet."""
        if segment.text:
            return f"“{segment.text}”"
        return _("The subtitle at {time}, not translated yet.").format(
            time=self._format_time(segment.start)
        )
