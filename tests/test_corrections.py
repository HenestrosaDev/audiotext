"""
The corrections of the segments of a text, without the widgets that show them:
the text is a fake that only keeps what the editor reads and writes.
"""

from typing import Any

import pytest

import views.transcript.corrections as corrections
from models.transcript_segment import TranscriptSegment
from utils.subtitle_cues import SegmentPart
from views.transcript.corrections import SegmentEditor, SegmentSource
from views.transcript.edit_dialogs import Timing
from views.transcript.transcript_text import PLAIN_TEXT_MODE, TRANSCRIPT_MODE

SEGMENTS = [
    TranscriptSegment(0.0, 1.0, "Hello wisper"),
    TranscriptSegment(1.5, 3.0, "Bye wisper."),
]


class FakeText:
    def __init__(self, text: str, mode: str = TRANSCRIPT_MODE) -> None:
        self.text = text
        self.mode = mode
        self.match: tuple[int, int, int] | None = None
        self.pending_saves = 0

    def save_pending_text(self) -> None:
        self.pending_saves += 1

    def get_text(self) -> str:
        return self.text

    def current_match(self) -> tuple[int, int, int] | None:
        return self.match

    def replace_current_match(self, replacement: str) -> None:
        self.text = replacement


class Store:
    """Keeps what the editor saves, and shows each segment as a whole part."""

    def __init__(
        self, segments: list[TranscriptSegment], text: str, is_edited: bool = False
    ) -> None:
        self.segments = segments
        self.is_edited = is_edited
        self.text = FakeText(text)
        self.saved: list[tuple[list[TranscriptSegment], str]] = []

    def parts(self) -> list[SegmentPart]:
        return [
            SegmentPart(idx, 0, len(segment.text), segment)
            for idx, segment in enumerate(self.segments)
        ]

    def save(self, segments: list[TranscriptSegment], text: str) -> None:
        self.saved.append((segments, text))
        self.segments, self.text.text = segments, text

    def editor(self, allow_empty: bool = False) -> SegmentEditor:
        source = SegmentSource(
            text=self.text,  # type: ignore[arg-type]
            segments=lambda: self.segments,
            parts=self.parts,
            is_text_edited=lambda: self.is_edited,
            save=self.save,
            edit_prompt=lambda _segment: ("Edit text", "Text:"),
            allow_empty=allow_empty,
        )
        return SegmentEditor(FakeMaster(), source, lambda seconds: f"{seconds:.1f}")


class FakeMaster:
    def winfo_toplevel(self) -> Any:
        return None


def test_replace_all_updates_the_segments_and_the_text_follows() -> None:
    store = Store(SEGMENTS, "Hello wisper Bye wisper.")
    store.editor().replace_all("wisper", "Whisper", match_case=False)

    assert [s.text for s in store.segments] == ["Hello Whisper", "Bye Whisper."]
    assert store.text.text == "Hello Whisper Bye Whisper."
    assert store.text.pending_saves >= 1


def test_replace_all_keeps_the_edits_of_the_text() -> None:
    store = Store(SEGMENTS, "My own wisper notes", is_edited=True)
    store.editor().replace_all("wisper", "Whisper", match_case=False)

    assert store.text.text == "My own Whisper notes"


def test_replace_all_without_segments_replaces_in_the_text() -> None:
    # E.g. a translation of a transcription without timestamps
    store = Store([], "Hola wisper")
    store.editor().replace_all("wisper", "Whisper", match_case=False)

    assert store.saved == [([], "Hola Whisper")]


def test_replace_current_replaces_the_match_in_its_segment() -> None:
    store = Store(SEGMENTS, "")
    store.text.match = (1, 4, 10)
    store.editor().replace_current("Whisper")

    assert [s.text for s in store.segments] == ["Hello wisper", "Bye Whisper."]


def test_replace_current_in_the_plain_text_replaces_it_there() -> None:
    store = Store(SEGMENTS, "wisper")
    store.text.mode = PLAIN_TEXT_MODE
    store.editor().replace_current("Whisper")

    assert store.text.text == "Whisper"
    assert store.saved == []


def test_replace_current_only_empties_a_segment_if_allowed() -> None:
    store = Store(SEGMENTS, "")
    store.text.match = (0, 0, 12)

    store.editor().replace_current("")
    assert store.saved == []

    store.editor(allow_empty=True).replace_current("")
    assert store.segments[0].text == ""


def test_edit_text_ignores_an_unchanged_text(monkeypatch: pytest.MonkeyPatch) -> None:
    store = Store(SEGMENTS, "")
    monkeypatch.setattr(
        corrections.TextDialog, "__init__", lambda self, *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        corrections.TextDialog, "get_input", lambda _self: "Bye wisper."
    )
    store.editor().edit_text(1)
    assert store.saved == []

    monkeypatch.setattr(corrections.TextDialog, "get_input", lambda _self: "Bye now.")
    store.editor().edit_text(1)
    assert store.segments[1].text == "Bye now."


def test_add_after_fills_the_gap_and_asks_for_its_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = Store(SEGMENTS, "")
    defaults: list[Timing] = []

    def timing_init(self: Any, *args: Any, **_kwargs: Any) -> None:
        defaults.append(args[-1])

    monkeypatch.setattr(corrections.TimingDialog, "__init__", timing_init)
    monkeypatch.setattr(
        corrections.TimingDialog, "get_result", lambda _self: Timing(1.0, 1.5)
    )
    monkeypatch.setattr(
        corrections.TextDialog, "__init__", lambda self, *_args, **_kwargs: None
    )
    monkeypatch.setattr(corrections.TextDialog, "get_input", lambda _self: "Well")
    store.editor(allow_empty=True).add_after(0)

    assert defaults == [Timing(1.0, 1.5)]
    assert [s.text for s in store.segments] == ["Hello wisper", "Well", "Bye wisper."]


def test_delete_keeps_the_last_segment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(corrections.messagebox, "askyesno", lambda *_a, **_k: True)
    store = Store(SEGMENTS, "")
    store.editor().delete(0)
    assert [s.text for s in store.segments] == ["Bye wisper."]

    store.editor().delete(0)
    assert len(store.segments) == 1
