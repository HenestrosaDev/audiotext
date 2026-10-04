import bisect
import tkinter as tk
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from models.transcript_segment import TranscriptSegment
from utils.i18n import _
from utils.time_format import format_timestamp
from views.style import theme
from views.widgets.textbox import CTkTextbox

TEXT_SAVE_DELAY_MS = 800

# (light, dark) colors of the highlights of the transcript
CURRENT_SEGMENT_COLOR = ("#E3EEFC", "#1E3450")
CURRENT_WORD_COLOR = ("#B9D5FA", "#2F5C93")
MATCH_COLOR = ("#FFF3B0", "#5C4B00")
CURRENT_MATCH_COLOR = ("#FFC94D", "#A07800")
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


def find_index(starts: list[float], position: float) -> int | None:
    """:return: The index of the last item that starts before the position."""
    idx = bisect.bisect_right(starts, position) - 1
    return idx if idx >= 0 else None


class TranscriptText(ctk.CTkFrame):  # type: ignore[misc]
    """
    The text of a transcription, in two modes: the transcript, with the timestamp
    and the speaker of each segment, which highlights the segment (and the word)
    being played; and the plain text, which can be edited.
    """

    def __init__(
        self,
        master: Any,
        on_segment_click: Callable[[int], None],
        on_segment_menu: Callable[[Any, int], str | None] | None = None,
        on_text_edit: Callable[[str], None] | None = None,
    ) -> None:
        """
        :param on_segment_click: Called with the index of a clicked segment.
        :param on_segment_menu: Called with the event and the index of a segment
                                that is right-clicked.
        :param on_text_edit: Called with the plain text after the user edits it.
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

        self._segments: list[TranscriptSegment] = []
        self._segment_starts: list[float] = []
        self._word_starts: list[float] = []
        self._word_ranges: list[tuple[str, str]] = []
        self._current_segment: int | None = None
        self._current_word: int | None = None
        self._is_text_edited = False
        self._mode = PLAIN_TEXT_MODE
        self._query = ""
        self._matches: list[tuple[str, str]] = []
        self._current_match: int | None = None
        self._save_text_after_id: str | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.lbl_hint = ctk.CTkLabel(
            self,
            text="",
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
        )
        self.lbl_hint.grid(row=0, column=0, padx=16, pady=(8, 0), sticky=ctk.EW)

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
            textbox._textbox.configure(spacing1=2, spacing3=2, insertwidth=2)

        self.tbx_plain.bind(
            "<KeyRelease>", lambda _event: self._schedule_text_save(), add="+"
        )
        self.tbx_plain.bind(
            "<<Paste>>",
            lambda _event: self.after(10, self._schedule_text_save),
            add="+",
        )
        self._configure_tags()

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

    def set_mode(self, mode: str) -> None:
        self._mode = mode if self._segments else PLAIN_TEXT_MODE

        if self._mode == TRANSCRIPT_MODE:
            self.tbx_plain.grid_forget()
            self.tbx_transcript.grid(
                row=1, column=0, sticky=ctk.NSEW, padx=2, pady=(0, 2)
            )
            hint = _("Click a sentence to play it. Right-click it to edit it.")
            if self._is_text_edited:
                hint += " " + _(
                    "The plain text has been edited; the transcript keeps the original."
                )
        else:
            self.tbx_transcript.grid_forget()
            self.tbx_plain.grid(row=1, column=0, sticky=ctk.NSEW, padx=2, pady=(0, 2))
            hint = _("You can edit the text. The changes are saved automatically.")
            if not self._segments:
                hint += " " + _(
                    "Timestamps are only available with WhisperX and the whisper-1 "
                    "and gpt-4o-transcribe-diarize models of the Whisper API."
                )
        self.lbl_hint.configure(text=hint)
        self.search(self._query)

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
                textbox.see(ranges[0])

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

    # SEARCH

    @property
    def match_status(self) -> tuple[int | None, int]:
        """:return: The index of the current match, and the number of matches."""
        return self._current_match, len(self._matches)

    def search(self, query: str) -> None:
        """Highlights the matches of the query, and goes to the first one."""
        self._query = query
        for textbox in (self.tbx_transcript, self.tbx_plain):
            textbox.tag_remove("match", "1.0", ctk.END)
            textbox.tag_remove("current_match", "1.0", ctk.END)
        self._matches = []
        self._current_match = None

        textbox = self._visible_textbox
        if query.strip():
            count = tk.IntVar(self)
            start = "1.0"
            while True:
                start = textbox.search(
                    query, start, stopindex=ctk.END, nocase=True, count=count
                )
                if not start or not count.get():
                    break
                end = f"{start}+{count.get()}c"
                textbox.tag_add("match", start, end)
                self._matches.append((start, end))
                start = end

        if self._matches:
            self.go_to_match(1)

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
        self._tag_font("timestamp", theme.font(12, family=theme.MONOSPACE_FAMILY))
        textbox.tag_config("current", background=self._color(CURRENT_SEGMENT_COLOR))
        textbox.tag_config("current_word", background=self._color(CURRENT_WORD_COLOR))

        for textbox in (self.tbx_transcript, self.tbx_plain):
            textbox.tag_config("match", background=self._color(MATCH_COLOR))
            textbox.tag_config(
                "current_match", background=self._color(CURRENT_MATCH_COLOR)
            )

    def _tag_font(self, tag: str, font: ctk.CTkFont) -> None:
        # CTkTextbox forbids fonts in the tags, since they don't follow its
        # scaling, so they're set on the Tk widget with the scaled size
        textbox = self.tbx_transcript
        textbox._textbox.tag_config(tag, font=textbox._apply_font_scaling(font))

    def _render_transcript(self) -> None:
        textbox = self.tbx_transcript
        textbox.configure(state=ctk.NORMAL)
        textbox.delete("1.0", ctk.END)
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
            return

        word_entries: list[tuple[float, str, str]] = []
        for idx, segment in enumerate(self._segments):
            segment_tag = f"segment_{idx}"
            textbox.insert(
                ctk.END,
                format_timestamp(segment.start) + "   ",
                ("timestamp", segment_tag),
            )
            if segment.speaker:
                textbox.insert(
                    ctk.END,
                    f"{segment.speaker}  ",
                    (f"speaker_{segment.speaker}", segment_tag),
                )

            if segment.words:
                word_entries.extend(self._insert_words(segment, segment_tag))
            else:
                textbox.insert(ctk.END, segment.text, segment_tag)
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
        textbox.tag_raise("match")
        textbox.tag_raise("current_match")
        textbox.configure(state=ctk.DISABLED)

    def _insert_words(
        self, segment: TranscriptSegment, segment_tag: str
    ) -> list[tuple[float, str, str]]:
        """
        Inserts the text of a segment, recording the position of each word to
        highlight it while playing. Words are looked up in the text, so its
        spacing and punctuation are kept.
        """
        textbox = self.tbx_transcript
        text = segment.text
        cursor = 0
        entries = []

        for word in segment.words:
            position = text.find(word.text, cursor) if word.text else -1
            if position < 0:
                continue
            if position > cursor:
                textbox.insert(ctk.END, text[cursor:position], segment_tag)
            start_index = textbox.index("end-1c")
            textbox.insert(ctk.END, word.text, segment_tag)
            entries.append((word.start, start_index, textbox.index("end-1c")))
            cursor = position + len(word.text)

        if cursor < len(text):
            textbox.insert(ctk.END, text[cursor:], segment_tag)

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
