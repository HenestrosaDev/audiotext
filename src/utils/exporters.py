"""
Exports the transcriptions of the history to files. Unlike the WhisperX writers,
they only need the stored segments (or text), so any entry of the history can be
exported at any time.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path

from models.summary import TranscriptSummary
from models.transcript_segment import TranscriptSegment
from utils.config_manager import ConfigManager
from utils.i18n import _
from utils.subtitle_cues import Cue, build_cues, line_limits
from utils.time_format import format_subtitle_time, format_timestamp

# A paragraph of a document is closed after a pause this long, or once it's this
# long, when the speakers are not identified
PARAGRAPH_PAUSE_SECONDS = 2.0
PARAGRAPH_MAX_CHARS = 600


@dataclass
class ExportDocument:
    """A transcription to export."""

    title: str
    text: str
    segments: list[TranscriptSegment]
    summary: TranscriptSummary | None = None
    # The text edited by the user is the one exported in the formats without
    # timestamps, since the segments keep the original transcription
    is_text_edited: bool = False
    # Whether the video is taller than it's wide, which narrows its subtitles
    is_vertical: bool = False


@dataclass(frozen=True)
class Paragraph:
    text: str
    # Only known if the transcription has timestamps
    start: float | None = None
    speaker: str | None = None


def _cue_text(segment: TranscriptSegment) -> str:
    return f"[{segment.speaker}]: {segment.text}" if segment.speaker else segment.text


def subtitle_cues(
    segments: list[TranscriptSegment], is_vertical: bool = False
) -> list[Cue]:
    """The segments split into subtitles, as the user configured them."""
    config = ConfigManager.get_config_subtitles()
    width, count = line_limits(config, segments, is_vertical)
    cues = []
    for segment in segments:
        segment_cues = build_cues([segment], width, count)
        # The speaker is added after splitting, so the subtitles are the ones
        # shown with the transcript and over the video, which show it apart
        if segment.speaker and segment_cues:
            first = segment_cues[0]
            segment_cues[0] = replace(first, text=f"[{segment.speaker}]: {first.text}")
        cues.extend(segment_cues)
    return cues


def segments_to_srt(
    segments: list[TranscriptSegment], is_vertical: bool = False
) -> str:
    cues = [
        f"{idx}\n{format_subtitle_time(cue.start, ',')} --> "
        f"{format_subtitle_time(cue.end, ',')}\n{cue.text}\n"
        for idx, cue in enumerate(subtitle_cues(segments, is_vertical), start=1)
    ]
    return "\n".join(cues)


def segments_to_vtt(
    segments: list[TranscriptSegment], is_vertical: bool = False
) -> str:
    cues = [
        f"{format_subtitle_time(cue.start, '.')} --> "
        f"{format_subtitle_time(cue.end, '.')}\n{cue.text}\n"
        for cue in subtitle_cues(segments, is_vertical)
    ]
    return "WEBVTT\n\n" + "\n".join(cues)


def paragraphs(document: ExportDocument) -> list[Paragraph]:
    """
    Splits the transcription into the paragraphs of a document: one per turn of
    each speaker, or after each pause if the speakers are not identified. The
    edited text is split by its blank lines.
    """
    if not document.segments or document.is_text_edited:
        return [
            Paragraph(block.strip())
            for block in document.text.split("\n\n")
            if block.strip()
        ]

    has_speakers = any(segment.speaker for segment in document.segments)
    result: list[Paragraph] = []
    texts: list[str] = []
    start: float | None = None
    speaker: str | None = None
    previous_end = 0.0

    def close() -> None:
        if texts:
            result.append(Paragraph(" ".join(texts), start, speaker))
            texts.clear()

    for segment in document.segments:
        if has_speakers:
            is_new = segment.speaker != speaker
        else:
            is_new = (
                segment.start - previous_end >= PARAGRAPH_PAUSE_SECONDS
                or sum(len(text) for text in texts) >= PARAGRAPH_MAX_CHARS
            )

        if is_new or not texts:
            close()
            start, speaker = segment.start, segment.speaker

        texts.append(segment.text)
        previous_end = segment.end

    close()
    return result


def to_srt(document: ExportDocument) -> str:
    return segments_to_srt(document.segments, document.is_vertical)


def to_vtt(document: ExportDocument) -> str:
    return segments_to_vtt(document.segments, document.is_vertical)


def to_tsv(document: ExportDocument) -> str:
    rows = ["start\tend\ttext"]
    rows.extend(
        f"{round(s.start * 1000)}\t{round(s.end * 1000)}\t"
        f"{_cue_text(s).replace(chr(9), ' ')}"
        for s in document.segments
    )
    return "\n".join(rows) + "\n"


def to_json(document: ExportDocument) -> str:
    data: dict[str, object] = {
        "text": document.text,
        "segments": [s.to_dict() for s in document.segments],
    }
    if document.summary:
        data["summary"] = document.summary.to_dict()
    return json.dumps(data, ensure_ascii=False, indent=2)


def to_txt(document: ExportDocument) -> str:
    text = document.text
    return text if text.endswith("\n") else f"{text}\n"


def to_markdown(document: ExportDocument) -> str:
    lines = [f"# {document.title}", ""]

    if summary := document.summary:
        lines += ["## " + _("Summary"), "", summary.summary, ""]
        if summary.key_points:
            lines += ["### " + _("Key points"), ""]
            lines += [f"- {point}" for point in summary.key_points]
            lines.append("")
        if summary.chapters:
            lines += ["### " + _("Chapters"), ""]
            lines += [
                f"- **{format_timestamp(chapter.start)}** {chapter.title}"
                for chapter in summary.chapters
            ]
            lines.append("")
        lines += ["## " + _("Transcription"), ""]

    for paragraph in paragraphs(document):
        prefix = ""
        if paragraph.start is not None:
            prefix = f"[{format_timestamp(paragraph.start)}] "
        if paragraph.speaker:
            prefix += f"{paragraph.speaker}: "
        lines += [
            f"**{prefix.strip()}** {paragraph.text}" if prefix else paragraph.text,
            "",
        ]

    return "\n".join(lines).rstrip() + "\n"


def to_docx(document: ExportDocument) -> bytes:
    # Imported here because it's only needed to export Word documents
    from docx import Document

    docx = Document()
    docx.core_properties.title = document.title
    docx.add_heading(document.title, level=0)

    if summary := document.summary:
        docx.add_heading(_("Summary"), level=1)
        docx.add_paragraph(summary.summary)
        if summary.key_points:
            docx.add_heading(_("Key points"), level=2)
            for point in summary.key_points:
                docx.add_paragraph(point, style="List Bullet")
        if summary.chapters:
            docx.add_heading(_("Chapters"), level=2)
            for chapter in summary.chapters:
                chapter_paragraph = docx.add_paragraph(style="List Bullet")
                chapter_paragraph.add_run(format_timestamp(chapter.start)).bold = True
                chapter_paragraph.add_run(f"  {chapter.title}")
        docx.add_heading(_("Transcription"), level=1)

    for paragraph in paragraphs(document):
        docx_paragraph = docx.add_paragraph()
        if paragraph.start is not None:
            docx_paragraph.add_run(
                f"[{format_timestamp(paragraph.start)}] "
            ).bold = True
        if paragraph.speaker:
            docx_paragraph.add_run(f"{paragraph.speaker}: ").bold = True
        docx_paragraph.add_run(paragraph.text)

    file = BytesIO()
    docx.save(file)
    return file.getvalue()


Exporter = Callable[[ExportDocument], str | bytes]

EXPORTERS: dict[str, Exporter] = {
    "txt": to_txt,
    "md": to_markdown,
    "docx": to_docx,
    "srt": to_srt,
    "vtt": to_vtt,
    "tsv": to_tsv,
    "json": to_json,
}
# Formats that need the timestamps of the segments
TIMED_FORMATS = {"srt", "vtt", "tsv"}


def available_formats(has_segments: bool) -> list[str]:
    """The formats a transcription can be exported to."""
    return [
        file_type
        for file_type in EXPORTERS
        if has_segments or file_type not in TIMED_FORMATS
    ]


def export(file_path: Path, file_type: str, document: ExportDocument) -> Path:
    """
    Writes the transcription to a file.

    :param file_path: The path of the file. Its extension is replaced by the one of
                      the file type.
    :param file_type: One of `EXPORTERS`.
    :raises ValueError: If the format needs segments and there are none.
    :return: The path of the written file.
    """
    if file_type not in EXPORTERS:
        raise ValueError(f"Unsupported file type: {file_type}")

    if file_type in TIMED_FORMATS and not document.segments:
        raise ValueError(f"The .{file_type} format needs the timestamps")

    output_path = file_path.with_suffix(f".{file_type}")
    content = EXPORTERS[file_type](document)

    if isinstance(content, bytes):
        output_path.write_bytes(content)
    else:
        output_path.write_text(content, encoding="utf-8")

    return output_path
