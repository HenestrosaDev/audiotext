import json
from pathlib import Path

import pytest
from docx import Document

from models.summary import Chapter, TranscriptSummary
from models.transcript_segment import TranscriptSegment
from utils.exporters import (
    ExportDocument,
    Paragraph,
    available_formats,
    export,
    paragraphs,
)

SEGMENTS = [
    TranscriptSegment(0.0, 1.5, "Hello."),
    TranscriptSegment(3661.25, 3662.0, "Bye.", speaker="SPEAKER_01"),
]
TEXT = "Hello. Bye."
SUMMARY = TranscriptSummary(
    summary="A greeting.",
    key_points=("They say hello",),
    chapters=(Chapter(0.0, "Greeting"), Chapter(3661.0, "Farewell")),
)


def document(**kwargs: object) -> ExportDocument:
    values: dict[str, object] = {"title": "Talk", "text": TEXT, "segments": SEGMENTS}
    return ExportDocument(**(values | kwargs))  # type: ignore[arg-type]


def test_srt(tmp_path: Path) -> None:
    path = export(tmp_path / "talk.mp4", "srt", document())

    assert path == tmp_path / "talk.srt"
    assert path.read_text(encoding="utf-8") == (
        "1\n00:00:00,000 --> 00:00:01,500\nHello.\n\n"
        "2\n01:01:01,250 --> 01:01:02,000\n[SPEAKER_01]: Bye.\n"
    )


def test_vtt(tmp_path: Path) -> None:
    content = export(tmp_path / "talk", "vtt", document()).read_text()

    assert content.startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nHello.\n")


def test_tsv(tmp_path: Path) -> None:
    content = export(tmp_path / "talk", "tsv", document()).read_text()

    assert content.splitlines() == [
        "start\tend\ttext",
        "0\t1500\tHello.",
        "3661250\t3662000\t[SPEAKER_01]: Bye.",
    ]


def test_json_and_txt_use_the_text(tmp_path: Path) -> None:
    data = json.loads(
        export(tmp_path / "talk", "json", document(text="Edited")).read_text()
    )
    txt = export(tmp_path / "talk", "txt", document(text="Edited", segments=[]))

    assert data["text"] == "Edited"
    assert data["segments"][1]["speaker"] == "SPEAKER_01"
    assert "summary" not in data
    assert txt.read_text() == "Edited\n"


def test_json_includes_the_summary(tmp_path: Path) -> None:
    path = export(tmp_path / "talk", "json", document(summary=SUMMARY))

    assert json.loads(path.read_text())["summary"]["summary"] == "A greeting."


def test_timed_formats_need_segments(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        export(tmp_path / "talk", "srt", document(segments=[]))

    assert available_formats(has_segments=False) == ["txt", "md", "docx", "json"]
    assert set(available_formats(has_segments=True)) == {
        "txt",
        "md",
        "docx",
        "srt",
        "vtt",
        "tsv",
        "json",
    }


def test_paragraphs_follow_the_turns_of_the_speakers() -> None:
    segments = [
        TranscriptSegment(0, 1, "Hi.", speaker="SPEAKER_00"),
        TranscriptSegment(1, 2, "How are you?", speaker="SPEAKER_00"),
        TranscriptSegment(2, 3, "Fine.", speaker="SPEAKER_01"),
    ]

    assert paragraphs(document(segments=segments)) == [
        Paragraph("Hi. How are you?", 0, "SPEAKER_00"),
        Paragraph("Fine.", 2, "SPEAKER_01"),
    ]


def test_paragraphs_without_speakers_are_split_at_the_pauses() -> None:
    segments = [
        TranscriptSegment(0, 1, "One."),
        TranscriptSegment(1.5, 2, "Two."),
        TranscriptSegment(10, 11, "Three."),
    ]

    assert paragraphs(document(segments=segments)) == [
        Paragraph("One. Two.", 0),
        Paragraph("Three.", 10),
    ]


def test_paragraphs_of_the_edited_text_are_its_blocks() -> None:
    edited = document(text="First.\n\nSecond.\n", is_text_edited=True)

    assert paragraphs(edited) == [Paragraph("First."), Paragraph("Second.")]


def test_markdown(tmp_path: Path) -> None:
    content = export(tmp_path / "talk", "md", document(summary=SUMMARY)).read_text()

    assert content.startswith("# Talk\n\n## Summary\n\nA greeting.\n")
    assert "- They say hello" in content
    assert "- **01:01:01** Farewell" in content
    assert "**[00:00]** Hello." in content
    assert "**[01:01:01] SPEAKER_01:** Bye." in content


def test_markdown_without_timestamps(tmp_path: Path) -> None:
    content = export(tmp_path / "talk", "md", document(segments=[])).read_text()

    assert content == "# Talk\n\nHello. Bye.\n"


def test_docx(tmp_path: Path) -> None:
    path = export(tmp_path / "talk", "docx", document(summary=SUMMARY))

    texts = [paragraph.text for paragraph in Document(str(path)).paragraphs]
    assert path.suffix == ".docx"
    assert texts[0] == "Talk"
    assert "A greeting." in texts
    assert "[01:01:01] SPEAKER_01: Bye." in texts
