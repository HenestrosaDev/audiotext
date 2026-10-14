import bisect
import tkinter as tk
from collections.abc import Callable
from functools import partial
from typing import Any

import customtkinter as ctk

from models.transcript_segment import TranscriptSegment, TranscriptWord
from utils.i18n import _
from utils.time_format import format_segment_range
from views.localization import Text, on_language_change
from views.style import theme
from views.widgets.textbox import CTkTextbox

TEXT_SAVE_DELAY_MS = 800

# (light, dark) colors of the highlights of the transcript
CURRENT_SEGMENT_COLOR = ("#E3EEFC", "#1E3450")
CURRENT_WORD_COLOR = ("#B9D5FA", "#2F5C93")
MATCH_COLOR = ("#FFF3B0", "#5C4B00")
CURRENT_MATCH_COLOR = ("#FFC94D", "#A07800")
# (light, dark) color of the words that may be wrong, to proofread them first
LOW_CONFIDENCE_COLOR = ("#C2410C", "#FDBA74")
SPEAKER_COLORS = [
    ("#1565C0", "#64B5F6"),
    ("#2E7D32", "#81C784"),
    ("#AD1457", "#F48FB1"),
    ("#E65100", "#FFB74D"),
    ("#6A1B9A", "#CE93D8"),
    ("#00838F", "#4DD0E1"),
]

TRANSCRIPT_MODE = "transcript"
PLAIN_TEXT_MODE = "plain"


def _count_chars(textbox: tk.Text, start: str, end: str) -> int:
    """The number of characters between two indexes of a text."""
    # A tuple of the counts, or None if there are none (it depends on the version)
    count: Any = textbox.count(start, end, "chars")
    if isinstance(count, tuple):
        return int(count[0])
    return int(count or 0)


def _index_key(index: str) -> tuple[int, int]:
    """Sorts the indexes of a text (`line.char`) by their position."""
    line, char = index.split(".")
    return int(line), int(char)


def _count_pixels(textbox: tk.Text, start: str, end: str) -> int:
    """The height between two indexes of a text, in pixels."""
    count: Any = textbox.count(start, end, "ypixels")
    if isinstance(count, tuple):
        return int(count[0])
    return int(count or 0)


def find_matches(
    textbox: tk.Text | ctk.CTkTextbox,
    query: str,
    match_case: bool,
    is_match: Callable[[str, str], bool] = lambda _start, _end: True,
) -> list[tuple[str, str]]:
    """
    Highlights the matches of a query in a text with the "match" tag.

    :param is_match: Whether a range found can be a match (e.g. it's not in a
                     timestamp).
    :return: Where each match starts and ends.
    """
    matches: list[tuple[str, str]] = []
    if not query.strip():
        return matches
    count = tk.IntVar(textbox)
    start = "1.0"
    while True:
        start = textbox.search(
            query, start, stopindex=ctk.END, nocase=not match_case, count=count
        )
        if not start or not count.get():
            break
        end = textbox.index(f"{start}+{count.get()}c")
        if is_match(start, end):
            textbox.tag_add("match", start, end)
            matches.append((start, end))
        start = end
    return matches


def find_index(starts: list[float], position: float) -> int | None:
    """:return: The index of the last item that starts before the position."""
    idx = bisect.bisect_right(starts, position) - 1
    return idx if idx >= 0 else None


def is_low_confidence(
    item: TranscriptWord | TranscriptSegment, min_score: float | None
) -> bool:
    """
    :param item: A word, or a segment for the engines that only score segments.
    :param min_score: The score below which a text may be wrong, or `None` if the
        low confidence texts are not highlighted.
    :return: Whether the text may be wrong. Texts without a score are not.
    """
    return min_score is not None and item.score is not None and item.score < min_score


class TranscriptText(ctk.CTkFrame):  # type: ignore[misc]
    """
    The text of a transcription, in two modes: the transcript, with the timestamps
    (start and end) and the speaker of each segment above its text, which
    highlights the segment (and the word) being played; and the plain text, which
    can be edited.
    """

    def __init__(
        self,
        master: Any,
        on_segment_click: Callable[[int], None],
        on_segment_menu: Callable[[Any, int], str | None] | None = None,
        on_text_edit: Callable[[str], None] | None = None,
        on_scroll: Callable[[], None] | None = None,
        show_usage_hints: bool = True,
        empty_segment_text: Text | None = None,
    ) -> None:
        """
        :param on_segment_click: Called with the index of a clicked segment.
        :param on_segment_menu: Called with the event and the index of a segment
                                that is right-clicked.
        :param on_text_edit: Called with the plain text after the user edits it.
        :param on_scroll: Called when the visible text scrolls.
        :param show_usage_hints: Whether to explain above the text how to use it
                                 (e.g. that its segments can be clicked).
        :param empty_segment_text: Shown, dimmed, in place of the text of a
                                   segment that has none (e.g. not translated yet).
        """
        super().__init__(
            master,
            fg_color=theme.CARD_BG,
            border_color=theme.CARD_BORDER,
            border_width=1,
            corner_radius=12,
        )
        self._on_segment_click = on_segment_click
        self._on_segment_menu = on_segment_menu
        self._on_text_edit = on_text_edit
        self._on_scroll = on_scroll
        self._show_usage_hints = show_usage_hints
        self._empty_segment_text = empty_segment_text

        self._segments: list[TranscriptSegment] = []
        self._segment_starts: list[float] = []
        self._word_starts: list[float] = []
        self._word_ranges: list[tuple[str, str]] = []
        # Where each segment starts in the transcript (the line of its
        # timestamps), and where its text starts, after that line
        self._segment_indexes: list[str] = []
        self._text_starts: list[str] = []
        self._current_segment: int | None = None
        self._current_word: int | None = None
        self._is_text_edited = False
        self._mode = PLAIN_TEXT_MODE
        self._is_precise = False
        self._low_confidence_score: float | None = None
        # The start of the low confidence text that was gone to, if any
        self._current_low_confidence: str | None = None
        self._query = ""
        self._match_case = False
        self._matches: list[tuple[str, str]] = []
        self._current_match: int | None = None
        self._save_text_after_id: str | None = None
        self._note = ""
        self._is_note_error = False
        # Where the text was scrolled to follow another one, to not follow it back
        self._synced_view: float | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.lbl_hint = ctk.CTkLabel(
            self,
            text="",
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
        )
        self.lbl_hint.grid(row=0, column=0, padx=16, pady=(2, 0), sticky=ctk.EW)

        text_options = {
            "wrap": ctk.WORD,
            "font": theme.font(15),
            "fg_color": "transparent",
            "border_spacing": 10,
            "activate_scrollbars": True,
        }
        self.tbx_transcript = CTkTextbox(self, cursor="hand2", **text_options)
        self.tbx_plain = CTkTextbox(self, undo=True, **text_options)
        for textbox in (self.tbx_transcript, self.tbx_plain):
            textbox._textbox.configure(
                spacing1=2,
                spacing3=2,
                insertwidth=2,
                yscrollcommand=partial(self._on_yscroll, textbox),
            )

        self.tbx_plain.bind(
            "<KeyRelease>", lambda _event: self._schedule_text_save(), add="+"
        )
        self.tbx_plain.bind(
            "<<Paste>>",
            lambda _event: self.after(10, self._schedule_text_save),
            add="+",
        )
        self._configure_tags()
        on_language_change(self, self._on_language_change)

    def _set_scaling(
        self, new_widget_scaling: float, new_window_scaling: float
    ) -> None:
        super()._set_scaling(new_widget_scaling, new_window_scaling)
        # The size of the interface changed (see `PreferencesDialog`)
        self._tag_fonts()

    def destroy(self) -> None:
        if self._save_text_after_id:
            self.after_cancel(self._save_text_after_id)
            self._save_text_now()
        super().destroy()

    # PUBLIC METHODS

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def has_segments(self) -> bool:
        return bool(self._segments)

    def set_content(
        self, segments: list[TranscriptSegment], text: str, is_text_edited: bool
    ) -> None:
        """Shows the transcription, keeping the mode and the search."""
        self._segments = segments
        self._segment_starts = [segment.start for segment in segments]
        self._is_text_edited = is_text_edited
        self._current_segment = self._current_word = None

        self._render_transcript()
        # The text being edited is not replaced, so its cursor is kept
        if self.get_text() != text:
            self.tbx_plain.delete("1.0", ctk.END)
            self.tbx_plain.insert("1.0", text)
            self.tbx_plain.edit_reset()

        if not segments:
            self._mode = PLAIN_TEXT_MODE
        self.set_mode(self._mode)

    def set_precise_timestamps(self, is_precise: bool) -> None:
        """Shows the timestamps as `HH:MM:SS,mmm` instead of `MM:SS`."""
        if is_precise == self._is_precise:
            return
        self._is_precise = is_precise
        self._current_segment = self._current_word = None
        self._render_transcript()
        self.search(self._query, self._match_case, self._current_match)

    def set_low_confidence_score(self, min_score: float | None) -> None:
        """
        Highlights the words whose score is below `min_score`, or none if it's
        `None`.
        """
        if min_score == self._low_confidence_score:
            return
        self._low_confidence_score = min_score
        self._current_segment = self._current_word = None
        self._render_transcript()
        self.search(self._query, self._match_case, self._current_match)

    def set_mode(self, mode: str) -> None:
        self._mode = mode if self._segments else PLAIN_TEXT_MODE

        if self._mode == TRANSCRIPT_MODE:
            self.tbx_plain.grid_forget()
            self.tbx_transcript.grid(
                row=1, column=0, sticky=ctk.NSEW, padx=2, pady=(0, 2)
            )
        else:
            self.tbx_transcript.grid_forget()
            self.tbx_plain.grid(row=1, column=0, sticky=ctk.NSEW, padx=2, pady=(0, 2))
        self._show_hint()
        self.search(self._query, self._match_case, self._current_match)

    def bind_interaction(self, callback: Callable[[], None]) -> None:
        """Calls the callback when the user clicks, scrolls or focuses the text."""
        for textbox in (self.tbx_transcript, self.tbx_plain):
            for sequence in ("<FocusIn>", "<ButtonPress>", "<MouseWheel>"):
                textbox._textbox.bind(sequence, lambda _event: callback(), add="+")

    def set_note(self, note: str, is_error: bool = False) -> None:
        """Shows a note in place of the hint, before the hints of the text."""
        self._note = note
        self._is_note_error = is_error
        self._show_hint()

    def _show_hint(self) -> None:
        """
        Shows the hints of the text above it. Its row is kept even without them,
        so the text starts at the same height as the one next to it.
        """
        if self._note and self._is_note_error:
            self.lbl_hint.configure(text=self._note, text_color=theme.ERROR_TEXT)
            return

        hints = [self._note] if self._note else []
        if self._mode == TRANSCRIPT_MODE:
            if self._show_usage_hints:
                hints.append(
                    _("Click a segment to play it. Right-click it to edit it.")
                )
            if self._is_text_edited:
                hints.append(
                    _(
                        "The plain text has been edited; the transcript keeps the "
                        "original."
                    )
                )
        elif self._show_usage_hints:
            hints.append(
                _("You can edit the text. The changes are saved automatically.")
            )
            if not self._segments:
                hints.append(
                    _(
                        "Timestamps are only available with WhisperX and the "
                        "whisper-1 and gpt-4o-transcribe-diarize models of the "
                        "Whisper API."
                    )
                )
        self.lbl_hint.configure(text=" ".join(hints), text_color=theme.HINT_TEXT)

    def _on_language_change(self) -> None:
        # The texts shown in place of the missing ones (e.g. a segment not
        # translated yet) are part of the transcript
        if not self._segments or any(
            not segment.text and not segment.words for segment in self._segments
        ):
            self._current_segment = self._current_word = None
            self._render_transcript()
        # Shows the hint again, and the search in the new transcript
        self.set_mode(self._mode)

    def get_text(self) -> str:
        return str(self.tbx_plain.get("1.0", ctk.END)).rstrip("\n")

    def save_pending_text(self) -> None:
        """Saves the edited text right away, if its saving is pending."""
        if self._save_text_after_id:
            self.after_cancel(self._save_text_after_id)
            self._save_text_now()

    def contains_widget(self, widget: Any) -> bool:
        """Whether the widget is the text of the transcript (not the plain one)."""
        return widget is self.tbx_transcript._textbox

    def focus_text(self) -> None:
        self._visible_textbox.focus_set()

    # PLAYBACK

    def highlight(self, position: float, is_playing: bool) -> None:
        """Highlights the segment and the word at the position of the playback."""
        self._highlight_segment(find_index(self._segment_starts, position), is_playing)
        self._highlight_word(find_index(self._word_starts, position), position)

    def _highlight_segment(self, idx: int | None, is_playing: bool) -> None:
        if idx == self._current_segment:
            return
        self._current_segment = idx
        textbox = self.tbx_transcript
        textbox.tag_remove("current", "1.0", ctk.END)
        if idx is None:
            return
        ranges = textbox.tag_ranges(f"segment_{idx}")
        if ranges:
            textbox.tag_add("current", ranges[0], ranges[-1])
            # Follow the playback, unless the user is reading a search result
            if is_playing and self._current_match is None:
                self._center_segment(idx)

    def _center_segment(self, idx: int) -> None:
        """Scrolls the transcript to show a segment in the middle of it."""
        textbox = self.tbx_transcript._textbox
        view_height = textbox.winfo_height()
        total = _count_pixels(textbox, "1.0", ctk.END)
        # Not laid out yet (e.g. the plain text is shown)
        if view_height <= 1 or not total:
            textbox.see(self._segment_indexes[idx])
            return
        top = _count_pixels(textbox, "1.0", self._segment_indexes[idx])
        # A segment taller than the text is shown from its start
        middle = top + min(self._segment_height(idx), view_height) / 2
        fraction = (middle - view_height / 2) / total
        textbox.yview_moveto(min(max(fraction, 0), 1))
        # The other text follows the playback by itself, not this scroll
        self._synced_view = float(textbox.yview()[0])

    def _highlight_word(self, idx: int | None, position: float) -> None:
        if idx == self._current_word:
            return
        self._current_word = idx
        self.tbx_transcript.tag_remove("current_word", "1.0", ctk.END)
        if idx is not None and position <= self._word_end(idx):
            self.tbx_transcript.tag_add("current_word", *self._word_ranges[idx])

    def _word_end(self, idx: int) -> float:
        # A word stays highlighted until the next one starts
        if idx + 1 < len(self._word_starts):
            return self._word_starts[idx + 1]
        return float("inf")

    # SCROLL

    def scroll_anchor(self) -> tuple[str, float]:
        """
        :return: Where the text is scrolled to, to scroll another one there: the
                 time at the top of the transcript, or the fraction of the
                 plain text above it.
        """
        if self._mode != TRANSCRIPT_MODE or not self._segment_indexes:
            return "fraction", float(self._visible_textbox.yview()[0])

        textbox = self.tbx_transcript._textbox
        top = textbox.index("@0,0")
        idx = max(
            bisect.bisect_right(self._segment_indexes, _index_key(top), key=_index_key)
            - 1,
            0,
        )
        start, end = self._segment_span(idx)
        offset = _count_pixels(textbox, self._segment_indexes[idx], top)
        height = self._segment_height(idx)
        progress = min(max(offset / height, 0), 1) if height else 0
        return "time", start + progress * (end - start)

    def scroll_to_anchor(self, anchor: tuple[str, float]) -> None:
        """Scrolls to where another text is scrolled (see `scroll_anchor`)."""
        kind, value = anchor
        textbox = self._visible_textbox
        if kind == "fraction":
            fraction = value
        elif self._mode == TRANSCRIPT_MODE and self._segment_indexes:
            idx = find_index(self._segment_starts, value) or 0
            start, end = self._segment_span(idx)
            progress = (
                min(max((value - start) / (end - start), 0), 1) if end > start else 0
            )
            tk_textbox = textbox._textbox
            total = _count_pixels(tk_textbox, "1.0", ctk.END)
            if not total:
                return
            top = _count_pixels(tk_textbox, "1.0", self._segment_indexes[idx])
            fraction = (top + progress * self._segment_height(idx)) / total
        else:
            return
        textbox.yview_moveto(fraction)
        self._synced_view = float(textbox.yview()[0])

    def _segment_span(self, idx: int) -> tuple[float, float]:
        """When a segment starts, and when the next one does (or it ends)."""
        start = self._segments[idx].start
        if idx + 1 < len(self._segments):
            return start, self._segments[idx + 1].start
        return start, max(self._segments[idx].end, start)

    def _segment_height(self, idx: int) -> int:
        """The height of a segment, up to the next one, in pixels."""
        end = (
            self._segment_indexes[idx + 1]
            if idx + 1 < len(self._segment_indexes)
            else ctk.END
        )
        return _count_pixels(
            self.tbx_transcript._textbox, self._segment_indexes[idx], end
        )

    def _on_yscroll(self, textbox: ctk.CTkTextbox, first: str, last: str) -> None:
        textbox._y_scrollbar.set(first, last)
        if textbox is not self._visible_textbox or not self._on_scroll:
            return
        # It scrolled to follow the other text, which doesn't have to follow it
        if self._synced_view is not None:
            is_synced = abs(float(first) - self._synced_view) < 1e-6
            self._synced_view = None
            if is_synced:
                return
        self._on_scroll()

    # SEARCH

    @property
    def match_status(self) -> tuple[int | None, int]:
        """:return: The index of the current match, and the number of matches."""
        return self._current_match, len(self._matches)

    def search(
        self, query: str, match_case: bool = False, current: int | None = None
    ) -> None:
        """
        Highlights the matches of the query in the text (not in the timestamps or
        the speakers), and goes to the first one.

        :param current: The index of the match to go to instead, e.g. the one
                        that was current before the text changed.
        """
        self._query = query
        self._match_case = match_case
        for textbox in (self.tbx_transcript, self.tbx_plain):
            textbox.tag_remove("match", "1.0", ctk.END)
            textbox.tag_remove("current_match", "1.0", ctk.END)
        self._matches = []
        self._current_match = None

        textbox = self._visible_textbox
        self._matches = find_matches(
            textbox,
            query,
            match_case,
            lambda start, end: self._is_text(textbox, start, end),
        )

        if self._matches:
            if current is None:
                self.go_to_match(1)
            else:
                self._current_match = min(current, len(self._matches) - 1)
                self.go_to_match(0)

    def _is_text(self, textbox: ctk.CTkTextbox, start: str, end: str) -> bool:
        """Whether a range is in the text of a segment, not in its timestamps."""
        if textbox is not self.tbx_transcript:
            return True
        return "text" in textbox.tag_names(start) and "text" in textbox.tag_names(
            f"{end}-1c"
        )

    def current_match(self) -> tuple[int, int, int] | None:
        """
        :return: The index of the segment shown with the current match of the
                 transcript, and where the match starts and ends in its text.
                 None if there is no match, or if the plain text is shown.
        """
        if self._mode != TRANSCRIPT_MODE or self._current_match is None:
            return None
        start, end = self._matches[self._current_match]
        textbox = self.tbx_transcript._textbox
        idx = next(
            (
                int(tag.removeprefix("segment_"))
                for tag in textbox.tag_names(start)
                if tag.startswith("segment_")
            ),
            None,
        )
        if idx is None:
            return None
        text_start = self._text_starts[idx]
        first = _count_chars(textbox, text_start, start)
        return idx, first, first + _count_chars(textbox, start, end)

    def replace_current_match(self, replacement: str) -> None:
        """Replaces the current match of the plain text, which is then saved."""
        if self._mode != PLAIN_TEXT_MODE or self._current_match is None:
            return
        start, end = self._matches[self._current_match]
        self.tbx_plain.delete(start, end)
        self.tbx_plain.insert(start, replacement)
        if self._save_text_after_id:
            self.after_cancel(self._save_text_after_id)
        self._save_text_now()
        self.search(self._query, self._match_case, self._current_match)

    def selected_text(self) -> str:
        """The text selected by the user, if any (e.g. to search it)."""
        try:
            return str(self._visible_textbox.get(ctk.SEL_FIRST, ctk.SEL_LAST))
        except tk.TclError:
            return ""

    def go_to_match(self, step: int) -> None:
        if not self._matches:
            return
        if self._current_match is None:
            self._current_match = 0 if step > 0 else len(self._matches) - 1
        else:
            self._current_match = (self._current_match + step) % len(self._matches)
        start, end = self._matches[self._current_match]
        textbox = self._visible_textbox
        textbox.tag_remove("current_match", "1.0", ctk.END)
        textbox.tag_add("current_match", start, end)
        textbox.see(start)

    def go_to_low_confidence(self, step: int) -> float | None:
        """
        Shows the next (or the previous) low confidence text of the transcript,
        after the one that was gone to, or the segment being played. It goes
        around when it reaches the end (or the start).

        :param step: 1 to go to the next text, -1 to go to the previous one.
        :return: When the text is said, in seconds, or `None` if there is none.
        """
        textbox = self.tbx_transcript
        if self._mode != TRANSCRIPT_MODE or not textbox.tag_ranges("low_confidence"):
            return None

        position = self._current_low_confidence
        if position is None and self._current_segment is not None:
            position = self._text_starts[self._current_segment]

        if step > 0:
            after = f"{position}+1c" if position else "1.0"
            found = textbox.tag_nextrange("low_confidence", after) or (
                textbox.tag_nextrange("low_confidence", "1.0")
            )
        else:
            before = position or ctk.END
            found = textbox.tag_prevrange("low_confidence", before) or (
                textbox.tag_prevrange("low_confidence", ctk.END)
            )
        start, end = (str(index) for index in found)

        self._current_low_confidence = start
        textbox.tag_remove("current_low_confidence", "1.0", ctk.END)
        textbox.tag_add("current_low_confidence", start, end)
        textbox.see(start)
        return self._time_at(start)

    def _time_at(self, index: str) -> float:
        """When the text at an index of the transcript is said, in seconds."""
        for (word_start, _word_end), seconds in zip(
            self._word_ranges, self._word_starts, strict=True
        ):
            if word_start == index:
                return seconds

        # The text of a whole segment (or a word that wasn't found)
        key = _index_key(index)
        idx = max(
            (
                i
                for i, start in enumerate(self._text_starts)
                if _index_key(start) <= key
            ),
            default=0,
        )
        return self._segments[idx].start

    # RENDERING

    @property
    def _visible_textbox(self) -> ctk.CTkTextbox:
        return self.tbx_transcript if self._mode == TRANSCRIPT_MODE else self.tbx_plain

    def _color(self, pair: tuple[str, str]) -> str:
        value: str = self._apply_appearance_mode(pair)
        return value

    def _configure_tags(self) -> None:
        textbox = self.tbx_transcript
        textbox.tag_config("timestamp", foreground=self._color(theme.HINT_TEXT))
        self._tag_fonts()
        textbox.tag_config("empty_segment", foreground=self._color(theme.HINT_TEXT))
        textbox.tag_config("current", background=self._color(CURRENT_SEGMENT_COLOR))
        textbox.tag_config("current_word", background=self._color(CURRENT_WORD_COLOR))
        textbox.tag_config(
            "low_confidence",
            foreground=self._color(LOW_CONFIDENCE_COLOR),
            underline=True,
        )
        textbox.tag_config(
            "current_low_confidence", background=self._color(CURRENT_MATCH_COLOR)
        )

        for textbox in (self.tbx_transcript, self.tbx_plain):
            textbox.tag_config("match", background=self._color(MATCH_COLOR))
            textbox.tag_config(
                "current_match", background=self._color(CURRENT_MATCH_COLOR)
            )

    def _tag_fonts(self) -> None:
        """Sets the fonts of the tags, with the scaled size of the interface."""
        self._tag_font("timestamp", theme.font(12, family=theme.MONOSPACE_FAMILY))
        for tag in self.tbx_transcript.tag_names():
            if tag.startswith("speaker_"):
                self._tag_font(tag, theme.font(13, "bold"))

    def _tag_font(self, tag: str, font: ctk.CTkFont) -> None:
        # CTkTextbox forbids fonts in the tags, since they don't follow its
        # scaling, so they're set on the Tk widget with the scaled size
        self.tbx_transcript._textbox.tag_config(
            tag, font=self._apply_font_scaling(font)
        )

    def _render_transcript(self) -> None:
        textbox = self.tbx_transcript
        textbox.configure(state=ctk.NORMAL)
        textbox.delete("1.0", ctk.END)
        self._current_low_confidence = None
        for tag in textbox.tag_names():
            if tag.startswith("segment_"):
                textbox.tag_delete(tag)

        for idx, speaker in enumerate(
            sorted({s.speaker for s in self._segments if s.speaker})
        ):
            textbox.tag_config(
                f"speaker_{speaker}",
                foreground=self._color(SPEAKER_COLORS[idx % len(SPEAKER_COLORS)]),
            )
            self._tag_font(f"speaker_{speaker}", theme.font(13, "bold"))

        if not self._segments:
            textbox.insert(ctk.END, _("This transcription has no timestamps."))
            textbox.configure(state=ctk.DISABLED)
            self._word_starts, self._word_ranges = [], []
            self._segment_indexes, self._text_starts = [], []
            return

        word_entries: list[tuple[float, str, str]] = []
        self._segment_indexes, self._text_starts = [], []
        for idx, segment in enumerate(self._segments):
            segment_tag = f"segment_{idx}"
            self._segment_indexes.append(textbox.index("end-1c"))
            # The timestamps and the speaker on their own line, above the text
            textbox.insert(
                ctk.END,
                format_segment_range(segment.start, segment.end, self._is_precise),
                ("timestamp", segment_tag),
            )
            if segment.speaker:
                textbox.insert(
                    ctk.END,
                    f"   {segment.speaker}",
                    (f"speaker_{segment.speaker}", segment_tag),
                )
            textbox.insert(ctk.END, "\n", segment_tag)

            text_start = textbox.index("end-1c")
            self._text_starts.append(text_start)
            if segment.words:
                word_entries.extend(self._insert_words(segment, segment_tag))
            elif not segment.text:
                empty_text = self._empty_segment_text
                textbox.insert(
                    ctk.END,
                    empty_text() if empty_text else "",
                    ("empty_segment", segment_tag),
                )
            else:
                textbox.insert(ctk.END, segment.text, (segment_tag, "text"))
            # The engines that only score segments highlight their whole text
            if segment.text and is_low_confidence(segment, self._low_confidence_score):
                textbox.tag_add("low_confidence", text_start, "end-1c")
            textbox.insert(ctk.END, "\n\n")

            textbox.tag_bind(
                segment_tag,
                "<ButtonRelease-1>",
                lambda _event, idx=idx: self._on_click(idx),
            )
            if on_segment_menu := self._on_segment_menu:
                for sequence in theme.CONTEXT_MENU_EVENTS:
                    textbox.tag_bind(
                        segment_tag,
                        sequence,
                        lambda event, idx=idx, menu=on_segment_menu: menu(event, idx),
                    )

        word_entries.sort(key=lambda item: item[0])
        self._word_starts = [start for start, _start_index, _end_index in word_entries]
        self._word_ranges = [
            (start_index, end_index) for _start, start_index, end_index in word_entries
        ]

        # The search highlights are shown above the playback ones
        textbox.tag_raise("current_word")
        textbox.tag_raise("current_low_confidence")
        textbox.tag_raise("match")
        textbox.tag_raise("current_match")
        textbox.configure(state=ctk.DISABLED)

    def _insert_words(
        self, segment: TranscriptSegment, segment_tag: str
    ) -> list[tuple[float, str, str]]:
        """
        Inserts the text of a segment, recording the position of each word to
        highlight it while playing, and highlighting the low confidence words.
        Words are looked up in the text, so its spacing and punctuation are kept.
        """
        textbox = self.tbx_transcript
        text = segment.text
        tags = (segment_tag, "text")
        cursor = 0
        entries = []

        for word in segment.words:
            position = text.find(word.text, cursor) if word.text else -1
            if position < 0:
                continue
            if position > cursor:
                textbox.insert(ctk.END, text[cursor:position], tags)
            start_index = textbox.index("end-1c")
            textbox.insert(
                ctk.END,
                word.text,
                (*tags, "low_confidence")
                if is_low_confidence(word, self._low_confidence_score)
                else tags,
            )
            entries.append((word.start, start_index, textbox.index("end-1c")))
            cursor = position + len(word.text)

        if cursor < len(text):
            textbox.insert(ctk.END, text[cursor:], tags)

        return entries

    # EVENT HANDLERS

    def _on_click(self, idx: int) -> None:
        # Selecting text doesn't play it
        if not self.tbx_transcript.tag_ranges(ctk.SEL):
            self._on_segment_click(idx)

    def _schedule_text_save(self) -> None:
        if self._save_text_after_id:
            self.after_cancel(self._save_text_after_id)
        self._save_text_after_id = self.after(TEXT_SAVE_DELAY_MS, self._save_text_now)

    def _save_text_now(self) -> None:
        self._save_text_after_id = None
        if self._on_text_edit:
            self._on_text_edit(self.get_text())
