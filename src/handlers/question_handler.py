"""
Answers questions about transcriptions with a language model of the provider set
for them, or of the one of the summaries if none is (see `AiProvider`).
If the transcription has timestamps, each answer links to the parts of the
transcription that support it.
"""

from datetime import datetime
from typing import Any

import utils.config_manager as cm
from handlers.ai_providers import AiProvider, complete_json, get_provider, resolve_model
from handlers.summary_handler import MAX_INPUT_CHARS, format_transcript
from models.question import AnswerSource, TranscriptAnswer
from models.transcript_segment import TranscriptSegment
from utils.i18n import _

MAX_SOURCES = 5
# The previous questions sent with each one, so it can refer to them
MAX_PREVIOUS_ANSWERS = 6

INSTRUCTIONS = """\
You answer questions about a transcription of an audio or video recording.

You receive the transcription, the questions asked before with their answers, if \
any, and the question to answer. Reply with a JSON object with these keys:
- "answer": the answer, in a few sentences or a short list. Use only information \
from the transcription, and say so if it doesn't have the answer. Write in the \
language of the question.
- "sources": {sources_instructions}

If the speakers are labeled (e.g. SPEAKER_00), refer to them by their label \
unless the transcription reveals their names."""

SOURCES_INSTRUCTIONS = (
    "a list of the lines of the transcription that support the answer (at most "
    "{max_sources}), each one an object with the second where it starts "
    '("start", a number taken from the timestamps of the lines) and a short '
    '"quote" of what is said there.'
)
NO_SOURCES_INSTRUCTIONS = "an empty list, since the transcription has no timestamps."

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "quote": {"type": "string"},
                },
                "required": ["start", "quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answer", "sources"],
    "additionalProperties": False,
}


def build_content(
    transcript: str, question: str, previous: list[TranscriptAnswer]
) -> str:
    """The message with the transcription, the previous answers and the question."""
    parts = [f"<transcription>\n{transcript}\n</transcription>"]
    if previous:
        turns = "\n\n".join(
            f"Question: {answer.question}\nAnswer: {answer.answer}"
            for answer in previous[-MAX_PREVIOUS_ANSWERS:]
        )
        parts.append(f"<previous_questions>\n{turns}\n</previous_questions>")
    parts.append(f"<question>\n{question}\n</question>")
    return "\n\n".join(parts)


def answer_from_data(
    data: dict[str, Any],
    question: str,
    model: str,
    duration: float | None,
    is_partial: bool,
) -> TranscriptAnswer:
    """
    Reads the object replied by the model, ignoring the values that don't have the
    expected type.

    :param duration: The duration of the transcription, to discard the sources
                     after it. None if it has no timestamps.
    :raises ValueError: If it has no answer.
    """
    answer = data.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError(_("The model didn't return a valid reply."))

    sources = []
    if duration is not None:
        for source in data.get("sources") or []:
            start = source.get("start") if isinstance(source, dict) else None
            quote = source.get("quote") if isinstance(source, dict) else None
            if (
                isinstance(start, int | float)
                and isinstance(quote, str)
                and 0 <= start <= duration
            ):
                sources.append(AnswerSource(float(start), quote.strip()))

    return TranscriptAnswer(
        question=question,
        answer=answer.strip(),
        sources=tuple(sorted(sources, key=lambda source: source.start)[:MAX_SOURCES]),
        model=model,
        created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        is_partial=is_partial,
    )


class QuestionHandler:
    def answer(
        self,
        text: str,
        segments: list[TranscriptSegment],
        question: str,
        previous: list[TranscriptAnswer],
        provider: AiProvider | None = None,
        model: str | None = None,
    ) -> TranscriptAnswer:
        """
        Answers a question about a transcription.

        :param provider: The provider of the language model. Defaults to the one
                         of the questions (see `ConfigAi.ask_provider_and_model`).
        :param model: The language model. Defaults to the one of the questions, or
                      to the default one of the provider.
        :raises ValueError: If there is no question or nothing to ask about, or the
                            reply of the model is not valid.
        :raises OSError: If the API key of the provider is not set.
        """
        question = question.strip()
        transcript = format_transcript(segments, text).strip()
        # The view doesn't ask empty questions, nor about empty transcriptions
        if not question or not transcript:
            raise ValueError("There is no question or no transcription")

        if provider is None:
            provider_name, config_model = (
                cm.ConfigManager.get_config_ai().ask_provider_and_model()
            )
            provider = get_provider(provider_name)
            model = model or config_model
        model = resolve_model(provider, model)
        is_partial = len(transcript) > MAX_INPUT_CHARS
        has_timestamps = bool(segments)

        instructions = INSTRUCTIONS.format(
            sources_instructions=(
                SOURCES_INSTRUCTIONS.format(max_sources=MAX_SOURCES)
                if has_timestamps
                else NO_SOURCES_INSTRUCTIONS
            )
        )
        content = build_content(transcript[:MAX_INPUT_CHARS], question, previous)

        data = complete_json(provider, model, instructions, content, ANSWER_SCHEMA)

        return answer_from_data(
            data,
            question,
            model,
            duration=segments[-1].end if has_timestamps else None,
            is_partial=is_partial,
        )
