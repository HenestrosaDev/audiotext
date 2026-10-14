from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import customtkinter as ctk

from models.config.config_system import ConfigSystem
from models.history import HistoryEntry
from models.review import (
    FlaggedText,
    Review,
    ReviewState,
    build_review,
    edited_count,
    set_review,
    step_to,
)
from models.transcript_segment import ReviewMark, TranscriptSegment
from utils.transcript_editing import edit_segment, edit_word
from views.entries.delegates import TranscriptEditor
from views.style import theme
from views.transcript.player_bar import MarkKind, PlayerBar, TimelineMark
from views.transcript.review_bar import ReviewBar
from views.transcript.transcript_text import LOW_CONFIDENCE_COLOR, TranscriptText
from views.transcript.word_popover import WordPopover

# The (light, dark) colors of the marks of the low confidence words on the
# timeline, which also differ in height
REVIEW_MARK_COLORS = {
    MarkKind.PENDING: LOW_CONFIDENCE_COLOR,
    MarkKind.DONE: theme.ICON_MUTED,
    MarkKind.CURRENT: ("#9A3412", "#FFEDD5"),
}
# The corrections made in the window to find and replace
REPLACE_ONE = "one"
REPLACE_ALL = "all"
# The moment played before and after a low confidence word when it's gone to, so
# it's heard in its context
AUTO_PLAY_BEFORE_SECONDS = 1.5
AUTO_PLAY_AFTER_SECONDS = 1.5
# How long the reviews of the words wait to be written, so reviewing many in a
# row writes the history once, and a crash loses only the last ones
REVIEW_SAVE_DELAY_MS = 2000


@dataclass(frozen=True)
class UndoStep:
    """How to undo the last review: the transcription before and after it."""

    segments: list[TranscriptSegment]
    text: str
    # To check that nothing changed since, and the text reviewed (the first one,
    # if several were), to go back to it
    reviewed_segments: list[TranscriptSegment]
    flagged: FlaggedText
    # Whether the review only changed the marks (accepting the text), or the text
    is_accept: bool


@dataclass(frozen=True)
class ReviewWidgets:
    """The widgets of the transcript view that show the review."""

    text: TranscriptText
    popover: WordPopover
    bar: ReviewBar
    player: PlayerBar
    # Shown over the text when only the segments to review are, and there are none
    empty_notice: ctk.CTkFrame


class ReviewController:
    """
    The review of the low confidence words of a transcription: going to them,
    accepting or correcting them (and undoing it), showing only their segments,
    and marking them on the timeline of the audio.
    """

    def __init__(
        self,
        master: Any,
        entry: Callable[[], HistoryEntry],
        editor: TranscriptEditor,
        widgets: ReviewWidgets,
        config: ConfigSystem,
        is_transcript_shown: Callable[[], bool],
        show_transcript: Callable[[], None],
        correct: Callable[[list[TranscriptSegment]], None],
    ) -> None:
        """
        :param master: The view, to schedule the saving of the reviews.
        :param entry: The entry shown, which changes with each correction.
        :param editor: Saves the reviews and the corrections.
        :param is_transcript_shown: Whether the transcript is shown, the only mode
            that shows the low confidence words.
        :param show_transcript: Shows the transcript, to go to a word.
        :param correct: Saves the segments corrected in the popover.
        """
        self._master = master
        self._entry = entry
        self._editor = editor
        self._widgets = widgets
        self._config = config
        self._is_transcript_shown = is_transcript_shown
        self._show_transcript = show_transcript
        self._correct = correct

        self.review = Review(ReviewState.NO_DATA)
        # The text gone to, if any, and how to undo the last review
        self.current: FlaggedText | None = None
        self._undo: UndoStep | None = None
        self._save_after_id: str | None = None
        # The correction being made in the window to find and replace, if any
        self._find_edit: str | None = None
        # Whether only the segments with words to review are shown, and the ones
        # shown anyway until the user goes to another word: the one whose last
        # word was just reviewed, and the ones a search went to
        self._only_flagged = False
        self._kept_segment: int | None = None
        self._revealed_segments: set[int] = set()
        # The size of the window when the popover opened, to close it if the
        # window is resized
        self._window_size = (0, 0)

    def close(self) -> None:
        """Writes the reviews, which are written when the view is destroyed."""
        if self._save_after_id:
            self._master.after_cancel(self._save_after_id)
            self._save_after_id = None
        self._editor.save_reviews()

    # NAVIGATION

    def go_to(self, step: int) -> None:
        """
        Goes to the next (or the previous) low confidence text of the transcript,
        so the user can listen to it and correct it.

        :param step: 1 to go to the next text, -1 to go to the previous one.
        """
        if not self._entry().segments:
            return
        # Only the transcript shows them
        if not self._is_transcript_shown():
            self._show_transcript()
        self._widgets.popover.hide()
        self.move_on()

        text = step_to(
            self.review.unreviewed, self.current, self._widgets.player.position, step
        )
        if text is not None:
            self._go_to_flagged(text)

    def _go_to_flagged(
        self, text: FlaggedText, is_quiet: bool = False, focus: bool = True
    ) -> None:
        """
        Shows a low confidence text, which Return accepts, and plays it if the
        user chose to.

        :param is_quiet: Whether to only show it, e.g. after a correction made in
            the window to find and replace, which keeps the focus and the audio.
        :param focus: Whether to focus the transcript, so Return accepts it.
        """
        self.current = text
        self._widgets.text.show_flagged(text)
        self.refresh_marks()
        if is_quiet:
            return
        if focus:
            self._widgets.text.focus_text()
        if self._config.review_auto_play:
            self.replay_current()
        else:
            self._widgets.player.seek(text.start)

    def on_mark_click(self, idx: int) -> None:
        """Goes to the word of a mark, or plays it, if it was reviewed."""
        flagged = self.review.flagged
        if idx >= len(flagged):
            return
        text = flagged[idx]
        if text.review is not None:
            self._widgets.player.seek(text.start)
            return
        if not self._is_transcript_shown():
            self._show_transcript()
        self._widgets.popover.hide()
        self.move_on()
        self._go_to_flagged(text)

    def replay_current(self) -> None:
        if text := self.current:
            self._widgets.player.play_clip(
                text.start - AUTO_PLAY_BEFORE_SECONDS,
                text.end + AUTO_PLAY_AFTER_SECONDS,
            )

    # REVIEWS

    def accept_current(self) -> bool:
        """
        Accepts the low confidence text gone to as it is, and goes to the next one.
        Without one, it does nothing, and if it's not visible (e.g. the user
        scrolled away), it's only shown: it never accepts a text the user can't
        see.

        :return: Whether the key that accepts it was handled.
        """
        text = self.current
        if not self._is_transcript_shown() or text is None or text.review is not None:
            return False
        if not self._widgets.text.is_flagged_visible(text):
            self._widgets.text.show_flagged(text)
            return True

        entry = self._entry()
        segments = set_review(entry.segments, [text], ReviewMark.ACCEPTED)
        self._undo = UndoStep(entry.segments, entry.text, segments, text, True)
        # Going to the next text follows (see `refresh`)
        self._editor.review_transcript(entry.id, segments)
        self._schedule_save()
        return True

    def accept_remaining(self) -> None:
        """
        Accepts as they are all the low confidence texts left to review, which can
        be undone like accepting one.
        """
        review = self.review
        if review.state != ReviewState.ACTIVE:
            return

        entry = self._entry()
        segments = set_review(entry.segments, review.unreviewed, ReviewMark.ACCEPTED)
        first = self.current or review.unreviewed[0]
        self._undo = UndoStep(entry.segments, entry.text, segments, first, True)
        # None is left to go to
        self.current = None
        self._widgets.popover.hide()
        self._editor.review_transcript(entry.id, segments)
        self._schedule_save()
        self._widgets.text.focus_text()

    def undo(self) -> bool:
        """
        Undoes the last review (accepting or correcting a low confidence text),
        if nothing changed since, and goes back to the text.

        :return: Whether it was undone.
        """
        entry = self._entry()
        step, self._undo = self._undo, None
        if step is None or entry.segments is not step.reviewed_segments:
            self.refresh_bar()
            return False

        self.current = None
        if step.is_accept:
            self._editor.review_transcript(entry.id, step.segments)
            self._schedule_save()
        else:
            self._editor.update_transcript(entry.id, step.segments, step.text)
        # The text is back where it was, so it's found again by when it's said
        text = next(
            (
                text
                for text in self.review.unreviewed
                if text.segment_idx == step.flagged.segment_idx
                and text.word_idx == step.flagged.word_idx
            ),
            None,
        )
        if text is not None:
            self._go_to_flagged(text)
        return True

    def review_again(self) -> None:
        """
        Forgets which low confidence words at the threshold were accepted. The
        edited ones stay reviewed, as they were corrected.
        """
        self.current = None
        self._undo = None
        entry = self._entry()
        self._editor.review_transcript(
            entry.id, set_review(entry.segments, self.review.accepted, None)
        )
        self._schedule_save()

    def save_correction(self, segments: list[TranscriptSegment], text: str) -> None:
        """
        Saves a correction of the transcription. One that corrects the low
        confidence text gone to can be undone like accepting it.
        """
        entry = self._entry()
        before, before_text = entry.segments, entry.text
        current = self.current
        self._editor.update_transcript(entry.id, segments, text)
        # Only a correction of that text, and not of the whole transcription
        # (replacing a text everywhere), which isn't a review
        if (
            current is not None
            and self._find_edit != REPLACE_ALL
            and edited_count(segments) > edited_count(before)
            and current.key not in {other.key for other in self.review.unreviewed}
        ):
            self._undo = UndoStep(before, before_text, segments, current, False)
            self.refresh_bar()

    @contextmanager
    def correcting_from_find(self, kind: str) -> Iterator[None]:
        """
        Marks the corrections made meanwhile as made in the window to find and
        replace, which keeps the focus and the audio.

        :param kind: `REPLACE_ONE` or `REPLACE_ALL`, which isn't a review.
        """
        self._find_edit = kind
        try:
            yield
        finally:
            self._find_edit = None

    def _schedule_save(self) -> None:
        if self._save_after_id is None:
            self._save_after_id = self._master.after(
                REVIEW_SAVE_DELAY_MS, self.save_reviews
            )

    def save_reviews(self) -> None:
        self._save_after_id = None
        self._editor.save_reviews()

    # REFRESH

    def refresh(self, advance: bool = False) -> None:
        """
        Builds the review of the low confidence words again (e.g. after the
        threshold or the transcription changes), and shows it everywhere.

        :param advance: Whether to go to the next text if the one gone to was
            reviewed (accepted or corrected) since.
        """
        config = self._config
        previous = self.current
        self.review = build_review(
            self._entry().segments,
            config.highlight_low_confidence,
            config.low_confidence_threshold / 100,
        )
        # The text gone to, where it is now
        current = (
            next(
                (text for text in self.review.flagged if text.key == previous.key),
                None,
            )
            if previous
            else None
        )
        is_reviewed = previous is not None and (current is None or current.review)
        self.current = None if is_reviewed else current
        if self.current is None:
            self._widgets.popover.hide()
        if advance and is_reviewed and previous is not None:
            # Its segment stays while it's filtered, until the user moves on
            self._kept_segment = previous.segment_idx
        self._widgets.text.set_flagged(self.review.unreviewed)
        self._refresh_filter()
        self.refresh_bar()
        self.refresh_marks()

        # Once none are left, the review is done: there's nothing to go to
        if (
            advance
            and is_reviewed
            and previous is not None
            and (text := step_to(self.review.unreviewed, previous, 0, 1))
        ):
            self._go_to_flagged(text, is_quiet=self._find_edit is not None)

    def refresh_bar(self) -> None:
        undo = self._undo
        can_undo = undo is not None and self._entry().segments is undo.reviewed_segments
        self._widgets.bar.show(self.review, can_undo)

    def refresh_marks(self) -> None:
        """Marks the low confidence words on the timeline of the audio."""
        current = self.current
        marks = [
            TimelineMark(
                text.start,
                MarkKind.CURRENT
                if current is not None and text.key == current.key
                else MarkKind.DONE
                if text.review
                else MarkKind.PENDING,
            )
            for text in self.review.flagged
        ]
        self._widgets.player.set_marks(marks, REVIEW_MARK_COLORS, self.on_mark_click)

    # FILTER

    def set_only_flagged(self, is_on: bool) -> None:
        self._only_flagged = is_on
        self._kept_segment = None
        self._revealed_segments.clear()
        self._refresh_filter()
        if self.current:
            self._widgets.text.show_flagged(self.current)

    def move_on(self) -> None:
        """The user goes to another word, so the segments kept are no longer."""
        if self._kept_segment is not None or self._revealed_segments:
            self._kept_segment = None
            self._revealed_segments.clear()
            self._refresh_filter()

    def reveal_segment(self, segment_idx: int) -> None:
        """Shows a segment that the filter hides, e.g. one a search went to."""
        self._revealed_segments.add(segment_idx)
        self._refresh_filter()

    def _refresh_filter(self) -> None:
        """
        Shows only the segments with words to review, if the user chose to (and
        the one kept), or all of them.
        """
        review = self.review
        is_filtered = self._only_flagged and review.state in (
            ReviewState.ACTIVE,
            ReviewState.ALL_REVIEWED,
        )
        sources = {text.segment_idx for text in review.unreviewed}
        sources |= self._revealed_segments
        if self._kept_segment is not None:
            sources.add(self._kept_segment)
        shown = self._widgets.text.show_only(sources if is_filtered else None)

        notice = self._widgets.empty_notice
        if is_filtered and not shown:
            notice.place(relx=0.5, rely=0.45, anchor=ctk.CENTER)
            notice.lift()
        else:
            notice.place_forget()

    # WORD POPOVER

    def open_word_popover(self, text: FlaggedText) -> None:
        """Corrects (or accepts) a low confidence word where it is."""
        self.move_on()
        self._go_to_flagged(text, focus=False)
        widgets = self._widgets
        if box := widgets.text.flagged_box(text):
            window = self._master.winfo_toplevel()
            self._window_size = (window.winfo_width(), window.winfo_height())
            widgets.popover.open(
                text.text,
                widgets.text.text_widget,
                box,
                is_segment=text.word_idx is None,
            )

    def commit_word(self, value: str) -> None:
        """Saves the word corrected in the popover, or accepts it if unchanged."""
        text = self.current
        popover = self._widgets.popover
        if text is None:
            popover.close()
            return
        if value.strip() == text.text:
            self.accept_from_popover()
            return
        # Removing a word (or a segment) is done by editing its segment: a stray
        # Backspace here would remove it without being noticed
        if not value.strip():
            self._master.bell()
            return

        segments = self._entry().segments
        try:
            if text.word_idx is None:
                segments = edit_segment(segments, text.segment_idx, value)
            else:
                segments = edit_word(segments, text.segment_idx, text.word_idx, value)
        except ValueError:
            # E.g. a segment can't be left without text
            self._master.bell()
            return
        popover.hide()
        # Going to the next word follows, which focuses the transcript
        self._correct(segments)
        if self.current is None:
            self._widgets.text.focus_text()

    def accept_from_popover(self) -> None:
        self._widgets.popover.hide()
        self.accept_current()
        if self.current is None:
            self._widgets.text.focus_text()

    def follow_popover(self) -> None:
        """Moves the popover to its word, if it's open (e.g. after a scroll)."""
        widgets = self._widgets
        if widgets.popover.is_open and self.current:
            widgets.popover.place_at(
                widgets.text.text_widget, widgets.text.flagged_box(self.current)
            )

    def on_text_resize(self) -> None:
        """
        Closes the popover if the window is resized, which wraps the text again.
        Otherwise (e.g. the scrollbars of the text appear), it follows its word.
        """
        if not self._widgets.popover.is_open:
            return
        window = self._master.winfo_toplevel()
        if (window.winfo_width(), window.winfo_height()) != self._window_size:
            self._widgets.popover.close()
        else:
            self.follow_popover()
