"""
Summarizes transcriptions with a language model of the configured provider (see
`AiProvider`): a summary, the key points and, if the transcription has
timestamps, its chapters.
"""

from datetime import datetime
from typing import Any

import utils.config_manager as cm
from handlers.ai_providers import (
    AiProvider,
    complete_json,
    get_provider,
    load_json_object,
    resolve_model,
)
from models.summary import Chapter, TranscriptSummary
from models.transcript_segment import TranscriptSegment
from utils.i18n import _
from utils.time_format import format_timestamp

# Longer transcriptions are cut, which keeps the request within the context of the
# model and its cost reasonable. It's about three hours of speech
MAX_INPUT_CHARS = 200_000
MAX_KEY_POINTS = 10
MAX_CHAPTERS = 20

INSTRUCTIONS = """\
You summarize transcriptions of audio and video recordings.

Reply with a JSON object with these keys:
- "summary": a summary of the transcription in one or two paragraphs.
- "key_points": a list of the most important points, ideas or decisions (at \
most {max_key_points}), each one a short sentence.
- "chapters": {chapters_instructions}

Write in the language of the transcription. Use only information from the \
transcription. If the speakers are labeled (e.g. SPEAKER_00), refer to them by \
their label unless the transcription reveals their names."""

CHAPTERS_INSTRUCTIONS = (
    "a list of the parts of the recording about a different topic (at most "
    "{max_chapters}), each one an object with the second where it starts "
    '("start", a number taken from the timestamps of the lines) and a short '
    '"title".'
)
NO_CHAPTERS_INSTRUCTIONS = "an empty list, since the transcription has no timestamps."

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "title": {"type": "string"},
                },
                "required": ["start", "title"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "key_points", "chapters"],
    "additionalProperties": False,
}


def format_transcript(segments: list[TranscriptSegment], text: str) -> str:
    """
    Writes the transcription for the model: one line per segment with its start (in
    seconds, so the model can give the start of each chapter) and its speaker.
    """
    if not segments:
        return text

    lines = []
    for segment in segments:
        speaker = f"{segment.speaker}: " if segment.speaker else ""
        lines.append(f"[{segment.start:.0f}] {speaker}{segment.text}")

    return "\n".join(lines)


def parse_summary(
    content: str, model: str, duration: float | None, is_partial: bool
) -> TranscriptSummary:
    """
    Reads the reply of the model, ignoring the values that don't have the expected
    type.

    :param duration: The duration of the transcription, to discard the chapters
                     that start after it. None if it has no timestamps.
    :raises ValueError: If the reply has no summary.
    """
    try:
        data = load_json_object(content)
    except ValueError as e:
        raise ValueError(_("The model didn't return a valid summary.")) from e

    return summary_from_data(data, model, duration, is_partial)


def summary_from_data(
    data: dict[str, Any], model: str, duration: float | None, is_partial: bool
) -> TranscriptSummary:
    """
    Reads the object replied by the model. See `parse_summary`.

    :raises ValueError: If it has no summary.
    """
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError(_("The model didn't return a valid summary."))

    key_points = [
        point.strip()
        for point in data.get("key_points") or []
        if isinstance(point, str) and point.strip()
    ]
    chapters = []
    if duration is not None:
        for chapter in data.get("chapters") or []:
            start = chapter.get("start") if isinstance(chapter, dict) else None
            title = chapter.get("title") if isinstance(chapter, dict) else None
            if (
                isinstance(start, int | float)
                and isinstance(title, str)
                and title.strip()
                and 0 <= start <= duration
            ):
                chapters.append(Chapter(float(start), title.strip()))

    return TranscriptSummary(
        summary=summary.strip(),
        key_points=tuple(key_points[:MAX_KEY_POINTS]),
        chapters=tuple(
            sorted(chapters, key=lambda chapter: chapter.start)[:MAX_CHAPTERS]
        ),
        model=model,
        created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        is_partial=is_partial,
    )


class SummaryHandler:
    @staticmethod
    def summarize(
        text: str,
        segments: list[TranscriptSegment],
        provider: AiProvider | None = None,
        model: str | None = None,
    ) -> TranscriptSummary:
        """
        Summarizes a transcription.

        :param text: The text of the transcription.
        :param segments: Its segments, if it has timestamps.
        :param provider: The provider of the language model. Defaults to the
                         configured one.
        :param model: The language model. Defaults to the configured one, or to
                      the default one of the provider.
        :raises ValueError: If there is nothing to summarize or the reply of the
                            model is not valid.
        :raises OSError: If the API key of the provider is not set.
        :return: The summary.
        """
        transcript = format_transcript(segments, text).strip()
        if not transcript:
            raise ValueError(_("There is no text to summarize."))

        if provider is None:
            config = cm.ConfigManager.get_config_ai()
            provider = get_provider(config.summary_provider)
            model = model or config.summary_model
        model = resolve_model(provider, model)
        is_partial = len(transcript) > MAX_INPUT_CHARS
        transcript = transcript[:MAX_INPUT_CHARS]
        has_timestamps = bool(segments)

        instructions = INSTRUCTIONS.format(
            max_key_points=MAX_KEY_POINTS,
            chapters_instructions=(
                CHAPTERS_INSTRUCTIONS.format(max_chapters=MAX_CHAPTERS)
                if has_timestamps
                else NO_CHAPTERS_INSTRUCTIONS
            ),
        )

        data = complete_json(provider, model, instructions, transcript, SUMMARY_SCHEMA)

        return summary_from_data(
            data,
            model,
            duration=segments[-1].end if has_timestamps else None,
            is_partial=is_partial,
        )


def format_summary(summary: TranscriptSummary) -> str:
    """The summary as plain text, e.g. to copy it."""
    parts = [summary.summary]

    if summary.key_points:
        parts.append("\n".join(f"• {point}" for point in summary.key_points))
    if summary.chapters:
        parts.append(
            "\n".join(
                f"{format_timestamp(chapter.start)}  {chapter.title}"
                for chapter in summary.chapters
            )
        )

    return "\n\n".join(parts)
