import bisect
import tkinter as tk
from collections.abc import Callable
from functools import partial
from typing import Any

import customtkinter as ctk

from models.review import FlaggedText, review_key
from models.transcript_segment import TranscriptSegment
from utils.i18n import L_, _, format_number
from utils.time_format import format_segment_range
from views.localization import Text, localize, on_language_change
from views.style import icons, theme
from views.widgets.bindings import bind_wraplength
from views.widgets.button import icon_button
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
        # Also in the text hidden (see `show_only`), which is shown when a search
        # goes to it
        start = textbox.search(
            query,
            start,
            stopindex=ctk.END,
            nocase=not match_case,
            count=count,
            elide=True,
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
        on_flagged_click: Callable[[FlaggedText], None] | None = None,
        on_reveal: Callable[[int], None] | None = None,
        show_usage_hints: bool = True,
        show_summary: bool = True,
        empty_segment_text: Text | None = None,
        empty_segment_action: tuple[Text, Callable[[int], None]] | None = None,
        on_hints_change: Callable[[], None] | None = None,
    ) -> None:
        """
        :param on_segment_click: Called with the index of a clicked segment.
        :param on_segment_menu: Called with the event and the index of a segment
                                that is right-clicked.
        :param on_text_edit: Called with the plain text after the user edits it.
        :param on_scroll: Called when the visible text scrolls.
        :param on_flagged_click: Called with a low confidence text that is
                                 clicked, instead of `on_segment_click`.
        :param on_reveal: Called with the index of a segment of the transcription
                          that is hidden (see `show_only`) and has to be shown,
                          e.g. because a search went to it.
        :param show_usage_hints: Whether to explain above the plain text how to
                                 use it (e.g. that it can be edited).
        :param show_summary: Whether to tell above the segments how many subtitles
                             are shown, and how many speakers.
        :param empty_segment_text: Shown, dimmed, in place of the text of a
                                   segment that has none (e.g. not translated yet).
        :param empty_segment_action: The text of a button shown on the right of a
                                     segment without a text while the pointer is
                                     over it, and what it does with its index
                                     (e.g. translate it).
        :param on_hints_change: Called when the note and the hints above the text
                                are shown or left out (see `has_hints`).
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
        self._on_flagged_click = on_flagged_click
        self._on_reveal = on_reveal
        self._show_usage_hints = show_usage_hints
        self._show_summary = show_summary
        self._empty_segment_text = empty_segment_text
        self._empty_segment_action = empty_segment_action
        # The segment without a text with the button of its action, and when the
        # button is hidden after the pointer leaves it
        self._hovered_empty: int | None = None
        self._hide_action_after_id: str | None = None

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
        # The segment of the transcription that each segment shown is part of
        self._source_indexes: list[int] = []
        # Where the text of each segment shown starts and ends
        self._text_ranges: list[tuple[str, str]] = []
        # Where each word is, by its segment of the transcription and its key
        self._word_positions: dict[tuple[int, str], list[tuple[str, str]]] = {}
        # The low confidence texts highlighted, and the one gone to, if any
        self._flagged: tuple[FlaggedText, ...] = ()
        self._current_flagged: FlaggedText | None = None
        # The segments of the transcription shown, or `None` to show them all
        self._shown_sources: set[int] | None = None
        self._query = ""
        self._match_case = False
        self._matches: list[tuple[str, str]] = []
        self._current_match: int | None = None
        self._save_text_after_id: str | None = None
        self._note = ""
        # Shown instead of the note with the plain text, which has no segments
        self._plain_text_note = ""
        self._is_note_error = False
        # Whether the note has buttons to go to the segments without a text
        self._can_go_to_empty = False
        self._has_hints = False
        self._is_hint_row_reserved = False
        self._on_hints_change = on_hints_change
        # The segment without a text gone to last (see `go_to_empty_segment`)
        self._current_empty: int | None = None
        # Where the text was scrolled to follow another one, to not follow it back
        self._synced_view: float | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # The note on its own line, then the hints of the text
        self.frm_hints = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_hints.grid(row=0, column=0, padx=16, pady=(2, 0), sticky=ctk.EW)
        self.frm_hints.grid_columnconfigure(0, weight=1)
        self.lbl_note = ctk.CTkLabel(
            self.frm_hints,
            text="",
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
            justify=ctk.LEFT,
        )
        self.lbl_note.grid(row=0, column=0, sticky=ctk.EW)
        # Which of the segments without a text is gone to, e.g. "1 of 3". As wide
        # as its longest text and aligned to the buttons, so they don't move and
        # only the current number changes (like the matches of `FindDialog`)
        position_font = theme.font(12)
        self.lbl_empty_position = ctk.CTkLabel(
            self.frm_hints,
            text="",
            width=position_font.measure(
                _("{current} of {total}").format(current=9999, total=9999)
            )
            + 8,
            font=position_font,
            text_color=theme.HINT_TEXT,
            anchor=ctk.E,
        )
        self.lbl_empty_position.grid(row=0, column=1, padx=(8, 0))
        self.btn_previous_empty = icon_button(
            self.frm_hints,
            "chevron_left",
            lambda: self.go_to_empty_segment(-1),
            L_("Previous untranslated subtitle"),
        )
        self.btn_previous_empty.grid(row=0, column=2)
        self.btn_next_empty = icon_button(
            self.frm_hints,
            "chevron_right",
            lambda: self.go_to_empty_segment(1),
            L_("Next untranslated subtitle"),
        )
        self.btn_next_empty.grid(row=0, column=3)
        self.lbl_hint = ctk.CTkLabel(
            self.frm_hints,
            text="",
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
            justify=ctk.LEFT,
        )
        self.lbl_hint.grid(row=1, column=0, columnspan=4, sticky=ctk.EW)
        # Takes the place of the hints when the text next to it has some
        self.lbl_spacer = ctk.CTkLabel(self, text="", height=28)
        self.lbl_spacer.grid(row=0, column=0, pady=(2, 0))
        self.lbl_spacer.grid_remove()
        self.frm_hints.grid_remove()
        for widget in (self.lbl_note, self.lbl_hint):
            bind_wraplength(widget, minimum=150)

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
        self.btn_empty_action: ctk.CTkButton | None = None
        if empty_segment_action:
            self._init_empty_action(empty_segment_action[0])
        self._configure_tags()
        on_language_change(self, self._on_language_change)

    def _init_empty_action(self, text: Text) -> None:
        """
        The button of the action of the segments without a text, shown on the
        right of the one under the pointer.
        """
        self.btn_empty_action = localize(
            ctk.CTkButton(
                self.tbx_transcript,
                image=icons.icon("pencil", 13),
                compound=ctk.LEFT,
                width=0,
                height=24,
                font=theme.font(12),
                command=self._run_empty_action,
                **theme.SECONDARY_BUTTON,
            ),
            text=text,
        )
        textbox = self.tbx_transcript._textbox
        textbox.bind("<Motion>", self._on_transcript_motion, add="+")
        textbox.bind("<Leave>", lambda _event: self._schedule_action_hide(), add="+")
        # Moving onto the button leaves the text, which mustn't hide it
        self.btn_empty_action.bind(
            "<Enter>", lambda _event: self._cancel_action_hide(), add="+"
        )
        self.btn_empty_action.bind(
            "<Leave>", lambda _event: self._schedule_action_hide(), add="+"
        )

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
        self,
        segments: list[TranscriptSegment],
        text: str,
        is_text_edited: bool,
        source_indexes: list[int] | None = None,
    ) -> None:
        """
        Shows the transcription, keeping the mode and the search.

        :param source_indexes: The segment of the transcription that each segment
            shown is part of, if they're split (e.g. into subtitles).
        """
        self._segments = segments
        self._source_indexes = (
            source_indexes if source_indexes is not None else list(range(len(segments)))
        )
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

    def set_note(
        self,
        note: str,
        is_error: bool = False,
        can_go_to_empty: bool = False,
        plain_text_note: str = "",
    ) -> None:
        """
        Shows a note on its own line, above the hints of the text. An error
        replaces the hints, and is shown with the plain text too.

        :param note: Shown with the segments, if it's not an error.
        :param can_go_to_empty: Whether the note has buttons to go to the segments
                                without a text (see `go_to_empty_segment`).
        :param plain_text_note: Shown instead with the plain text.
        """
        self._note = note
        self._is_note_error = is_error
        self._can_go_to_empty = can_go_to_empty
        self._plain_text_note = plain_text_note
        self._show_hint()

    def _shown_note(self) -> str:
        if self._is_note_error or self._mode == TRANSCRIPT_MODE:
            return self._note
        return self._plain_text_note

    def _show_hint(self) -> None:
        """
        Shows the note and the hints of the text above it. Their row is left out
        without them, unless the text next to it has some (see
        `reserve_hint_row`), so both texts start at the same height.
        """
        self._show_note()
        hints: list[str] = []
        # An error replaces the hints
        note = self._shown_note()
        is_error = bool(note and self._is_note_error)
        if self._mode == TRANSCRIPT_MODE and self._show_summary and not is_error:
            if summary := self._summary():
                hints.append(summary)
        elif self._mode == PLAIN_TEXT_MODE and not is_error:
            if self._show_usage_hints:
                hints.append(
                    _("You can edit the text. The changes are saved automatically.")
                )
            if self._is_text_edited:
                hints.append(_("Edits made here don't change the subtitles."))
            if self._show_usage_hints and not self._segments:
                hints.append(
                    _(
                        "Timestamps are only available with WhisperX and the "
                        "whisper-1 and gpt-4o-transcribe-diarize models of the "
                        "Whisper API."
                    )
                )
        self.lbl_hint.configure(text=" ".join(hints))
        if hints:
            self.lbl_hint.grid()
        else:
            self.lbl_hint.grid_remove()

        has_hints = bool(note or hints)
        self._place_hints(has_hints)
        if has_hints != self._has_hints:
            self._has_hints = has_hints
            if self._on_hints_change:
                self._on_hints_change()

    def _summary(self) -> str:
        """How many subtitles are shown, and how many speakers they have."""
        if not self._segments:
            return ""
        parts = [
            _("Subtitles: {count}").format(count=format_number(len(self._segments)))
        ]
        if speakers := {
            segment.speaker for segment in self._segments if segment.speaker
        }:
            parts.append(
                _("Speakers: {count}").format(count=format_number(len(speakers)))
            )
        return " · ".join(parts)

    @property
    def has_hints(self) -> bool:
        """Whether a note or a hint is shown above the text."""
        return self._has_hints

    def reserve_hint_row(self, is_reserved: bool) -> None:
        """
        Keeps the row of the hints even without them, so the text starts at the
        same height as the one next to it, which has some.
        """
        self._is_hint_row_reserved = is_reserved
        self._place_hints(self._has_hints)

    def _place_hints(self, has_hints: bool) -> None:
        if has_hints:
            self.frm_hints.grid()
            self.lbl_spacer.grid_remove()
        elif self._is_hint_row_reserved:
            # As tall as a line of hints with the buttons of the note
            self.frm_hints.grid_remove()
            self.lbl_spacer.grid()
        else:
            self.frm_hints.grid_remove()
            self.lbl_spacer.grid_remove()

    def _show_note(self) -> None:
        """Shows the note, with the buttons to go to the segments without a text."""
        note = self._shown_note()
        self.lbl_note.configure(
            text=note,
            text_color=theme.ERROR_TEXT if self._is_note_error else theme.HINT_TEXT,
        )
        empty = self._empty_segments()
        can_go = bool(
            note
            and self._can_go_to_empty
            and not self._is_note_error
            and self._mode == TRANSCRIPT_MODE
            and empty
        )
        position = ""
        if can_go and self._current_empty in empty:
            position = _("{current} of {total}").format(
                current=empty.index(self._current_empty) + 1, total=len(empty)
            )
        self.lbl_empty_position.configure(text=position)

        widgets = (
            self.lbl_empty_position,
            self.btn_previous_empty,
            self.btn_next_empty,
        )
        for widget in widgets:
            if can_go:
                widget.grid()
            else:
                widget.grid_remove()
        if note:
            self.lbl_note.grid()
        else:
            self.lbl_note.grid_remove()

    def _on_language_change(self) -> None:
        # The texts shown in place of the missing ones (e.g. a segment not
        # translated yet) are part of the transcript
        if not self._segments or any(
            not segment.text.strip() and not segment.words for segment in self._segments
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

    def bind_transcript_key(self, sequence: str, callback: Callable[[], bool]) -> None:
        """
        Handles a key while the transcript has the focus, and only then, so it
        doesn't change what's typed elsewhere (e.g. in the plain text).

        :param callback: Returns whether it handled the key.
        """
        self.tbx_transcript._textbox.bind(
            sequence, lambda _event: "break" if callback() else None, add="+"
        )

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
        # It would no longer be next to its segment
        if textbox is self.tbx_transcript:
            self._hide_empty_action()
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
        # A match in a hidden segment is shown, or going to it would do nothing
        if (
            textbox is self.tbx_transcript
            and self._on_reveal
            and "hidden" in textbox.tag_names(start)
        ):
            idx = (
                bisect.bisect_right(
                    self._segment_indexes, _index_key(start), key=_index_key
                )
                - 1
            )
            if 0 <= idx < len(self._source_indexes):
                self._on_reveal(self._source_indexes[idx])
        textbox.see(start)

    def go_to_empty_segment(self, step: int) -> None:
        """
        Highlights the next segment without a text (or the previous one), from the
        one gone to last, and shows it. Past the last one, it goes to the first.

        :param step: 1 to go forward, -1 to go back.
        """
        empty = self._empty_segments()
        if not empty or self._mode != TRANSCRIPT_MODE:
            return
        current = self._current_empty
        if step > 0:
            after = [idx for idx in empty if current is None or idx > current]
            self._current_empty = after[0] if after else empty[0]
        else:
            before = [idx for idx in empty if current is None or idx < current]
            self._current_empty = before[-1] if before else empty[-1]

        self._highlight_empty()
        self._center_segment(self._current_empty)
        self._show_note()

    def _empty_segments(self) -> list[int]:
        """The segments shown without a text (e.g. not translated yet)."""
        return [
            idx
            for idx, segment in enumerate(self._segments)
            if not segment.text.strip() and not segment.words
        ]

    def _highlight_empty(self) -> None:
        """Highlights the segment without a text gone to, while it has none."""
        textbox = self.tbx_transcript
        textbox.tag_remove("current_empty", "1.0", ctk.END)
        idx = self._current_empty
        if idx is not None and idx in self._empty_segments():
            start, end = self._segment_indexes[idx], self._next_segment_index(idx)
            textbox.tag_add("current_empty", start, end)

    def _next_segment_index(self, idx: int) -> str:
        """Where the segment after one starts, or the end of the transcript."""
        if idx + 1 < len(self._segment_indexes):
            return self._segment_indexes[idx + 1]
        return str(self.tbx_transcript.index("end-1c"))

    # ACTION OF THE SEGMENTS WITHOUT A TEXT

    def _on_transcript_motion(self, event: tk.Event) -> None:
        idx = self._segment_at(event.x, event.y)
        if idx is not None and idx in self._empty_segments():
            self._show_empty_action(idx)
        else:
            self._schedule_action_hide()

    def _segment_at(self, x: int, y: int) -> int | None:
        """The segment shown at a point of the transcript, with its spacing."""
        if self._mode != TRANSCRIPT_MODE or not self._segment_indexes:
            return None
        index = self.tbx_transcript._textbox.index(f"@{x},{y}")
        idx = (
            bisect.bisect_right(
                self._segment_indexes, _index_key(index), key=_index_key
            )
            - 1
        )
        return idx if idx >= 0 else None

    def _show_empty_action(self, idx: int) -> None:
        """Shows the button on the right of the line of the segment's placeholder."""
        self._cancel_action_hide()
        button = self.btn_empty_action
        line = self.tbx_transcript._textbox.dlineinfo(self._text_starts[idx])
        if button is None or line is None:
            return
        _x, y, _width, height, _baseline = line
        self._hovered_empty = idx
        button.place(
            in_=self.tbx_transcript._textbox,
            relx=1.0,
            x=-12,
            y=y + height / 2,
            anchor=ctk.E,
        )
        button.lift()

    def _schedule_action_hide(self) -> None:
        if self.btn_empty_action is None or self._hide_action_after_id:
            return
        # Delayed, so the pointer can move from the segment onto the button
        self._hide_action_after_id = self.after(150, self._hide_empty_action)

    def _cancel_action_hide(self) -> None:
        if self._hide_action_after_id:
            self.after_cancel(self._hide_action_after_id)
            self._hide_action_after_id = None

    def _hide_empty_action(self) -> None:
        self._cancel_action_hide()
        self._hovered_empty = None
        if self.btn_empty_action is not None:
            self.btn_empty_action.place_forget()

    def _run_empty_action(self) -> None:
        idx = self._hovered_empty
        self._hide_empty_action()
        if idx is not None and self._empty_segment_action:
            self._empty_segment_action[1](idx)

    def set_flagged(self, texts: tuple[FlaggedText, ...]) -> None:
        """
        Highlights the low confidence texts, moving the highlights without
        rendering the transcript again.
        """
        self._flagged = texts
        if self._current_flagged not in texts:
            self._current_flagged = None
        self._apply_flagged()

    def show_flagged(self, text: FlaggedText) -> None:
        """Highlights a low confidence text more than the others, and shows it."""
        self._current_flagged = text
        self._apply_flagged()
        if ranges := self._flagged_ranges(text):
            self.tbx_transcript.see(ranges[0][0])

    def show_only(self, sources: set[int] | None) -> int:
        """
        Shows only some segments of the transcription (e.g. the ones with low
        confidence words), hiding the others without rendering it again.

        :param sources: The indexes of the segments of the transcription, or
            `None` to show them all.
        :return: How many of the segments shown are left.
        """
        self._shown_sources = sources
        return self._apply_shown()

    def _apply_shown(self) -> int:
        textbox = self.tbx_transcript
        textbox.tag_remove("hidden", "1.0", ctk.END)
        sources = self._shown_sources
        if sources is None:
            return len(self._segments)

        starts = self._segment_indexes
        shown = 0
        for idx, source_idx in enumerate(self._source_indexes[: len(starts)]):
            if source_idx in sources:
                shown += 1
                continue
            # From its timestamps to the start of the next segment
            end = starts[idx + 1] if idx + 1 < len(starts) else ctk.END
            textbox.tag_add("hidden", starts[idx], end)
        return shown

    def is_flagged_visible(self, text: FlaggedText) -> bool:
        """Whether a low confidence text is shown, in the visible part of the text."""
        textbox = self.tbx_transcript
        if self._mode != TRANSCRIPT_MODE or not textbox.winfo_ismapped():
            return False
        return any(
            textbox._textbox.bbox(start) is not None
            for start, _end in self._flagged_ranges(text)
        )

    def flagged_box(self, text: FlaggedText) -> tuple[int, int, int] | None:
        """
        Where a low confidence text is in the transcript, if it's visible: the
        left of its start, its top, and its bottom (which is lower than its first
        line if it wraps), in the coordinates of `text_widget`.
        """
        if not self.is_flagged_visible(text):
            return None
        textbox = self.tbx_transcript._textbox
        boxes = [
            box
            for start, end in self._flagged_ranges(text)
            for box in (textbox.bbox(start), textbox.bbox(f"{end}-1c"))
            if box
        ]
        if not boxes:
            return None
        x, top = int(boxes[0][0]), int(min(box[1] for box in boxes))
        bottom = int(max(box[1] + box[3] for box in boxes))
        return x, top, bottom

    @property
    def text_widget(self) -> tk.Text:
        """The Tk widget of the transcript, to place widgets over it."""
        widget: tk.Text = self.tbx_transcript._textbox
        return widget

    def _apply_flagged(self) -> None:
        textbox = self.tbx_transcript
        for tag in ("low_confidence", "current_low_confidence"):
            textbox.tag_remove(tag, "1.0", ctk.END)
        for text in self._flagged:
            for start, end in self._flagged_ranges(text):
                textbox.tag_add("low_confidence", start, end)
        if self._current_flagged:
            for start, end in self._flagged_ranges(self._current_flagged):
                textbox.tag_add("current_low_confidence", start, end)

    def _flagged_ranges(self, text: FlaggedText) -> list[tuple[str, str]]:
        """Where a low confidence text is: a word, or all the parts of a segment."""
        if text.word_idx is not None:
            return self._word_positions.get((text.segment_idx, text.key), [])

        return [
            text_range
            for source_idx, text_range in zip(
                self._source_indexes, self._text_ranges, strict=True
            )
            if source_idx == text.segment_idx and text_range[0] != text_range[1]
        ]

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
        # The segment without a text gone to (see `go_to_empty_segment`)
        textbox.tag_config("current_empty", background=self._color(CURRENT_MATCH_COLOR))
        textbox.tag_config("current_word", background=self._color(CURRENT_WORD_COLOR))
        textbox.tag_config(
            "low_confidence",
            foreground=self._color(LOW_CONFIDENCE_COLOR),
            underline=True,
        )
        # The segments left out (e.g. without low confidence words)
        textbox._textbox.tag_config("hidden", elide=True)
        # Not only its color sets it apart: it's also bold and outlined
        textbox.tag_config(
            "current_low_confidence",
            background=self._color(CURRENT_MATCH_COLOR),
            relief="solid",
            borderwidth=1,
        )

        for textbox in (self.tbx_transcript, self.tbx_plain):
            textbox.tag_config("match", background=self._color(MATCH_COLOR))
            textbox.tag_config(
                "current_match", background=self._color(CURRENT_MATCH_COLOR)
            )

    def _tag_fonts(self) -> None:
        """Sets the fonts of the tags, with the scaled size of the interface."""
        self._tag_font("timestamp", theme.font(12, family=theme.MONOSPACE_FAMILY))
        self._tag_font("current_low_confidence", theme.font(15, "bold"))
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
        self._hide_empty_action()
        textbox.configure(state=ctk.NORMAL)
        textbox.delete("1.0", ctk.END)
        self._word_positions = {}
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
            self._text_ranges = []
            return

        word_entries: list[tuple[float, str, str]] = []
        self._segment_indexes, self._text_starts = [], []
        self._text_ranges = []
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
                word_entries.extend(
                    self._insert_words(segment, segment_tag, self._source_indexes[idx])
                )
            elif not segment.text.strip():
                empty_text = self._empty_segment_text
                textbox.insert(
                    ctk.END,
                    empty_text() if empty_text else "",
                    ("empty_segment", segment_tag),
                )
            else:
                textbox.insert(ctk.END, segment.text, (segment_tag, "text"))
            self._text_ranges.append(
                (text_start, textbox.index("end-1c") if segment.text else text_start)
            )
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
        self._apply_flagged()
        self._apply_shown()
        # The segment gone to stays highlighted until it has a text
        self._highlight_empty()
        textbox.configure(state=ctk.DISABLED)

    def _insert_words(
        self, segment: TranscriptSegment, segment_tag: str, source_idx: int
    ) -> list[tuple[float, str, str]]:
        """
        Inserts the text of a segment, recording the position of each word to
        highlight it while playing, or if it may be wrong. Words are looked up in
        the text, so its spacing and punctuation are kept.

        :param source_idx: The segment of the transcription it's part of.
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
            textbox.insert(ctk.END, word.text, tags)
            end_index = textbox.index("end-1c")
            entries.append((word.start, start_index, end_index))
            self._word_positions.setdefault(
                (source_idx, review_key(word.start, word.text)), []
            ).append((start_index, end_index))
            cursor = position + len(word.text)

        if cursor < len(text):
            textbox.insert(ctk.END, text[cursor:], tags)

        return entries

    # EVENT HANDLERS

    def _on_click(self, idx: int) -> None:
        # Selecting text doesn't play it
        if self.tbx_transcript.tag_ranges(ctk.SEL):
            return
        if self._on_flagged_click and (text := self._flagged_at(tk.CURRENT)):
            self._on_flagged_click(text)
        else:
            self._on_segment_click(idx)

    def _flagged_at(self, index: str) -> FlaggedText | None:
        """The low confidence text highlighted at an index, if any."""
        textbox = self.tbx_transcript._textbox
        for text in self._flagged:
            for start, end in self._flagged_ranges(text):
                if textbox.compare(start, "<=", index) and textbox.compare(
                    index, "<", end
                ):
                    return text
        return None

    def _schedule_text_save(self) -> None:
        if self._save_text_after_id:
            self.after_cancel(self._save_text_after_id)
        self._save_text_after_id = self.after(TEXT_SAVE_DELAY_MS, self._save_text_now)

    def _save_text_now(self) -> None:
        self._save_text_after_id = None
        if self._on_text_edit:
            self._on_text_edit(self.get_text())
