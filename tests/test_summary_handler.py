import json
from typing import Any
from unittest.mock import MagicMock

import pytest

import handlers.ai_providers as ai_providers
from handlers.summary_handler import (
    MAX_INPUT_CHARS,
    SummaryHandler,
    format_summary,
    format_transcript,
    parse_summary,
)
from models.summary import Chapter, TranscriptSummary
from models.transcript_segment import TranscriptSegment

SEGMENTS = [
    TranscriptSegment(0.0, 5.0, "Welcome to the show.", speaker="SPEAKER_00"),
    TranscriptSegment(65.4, 70.0, "Let's talk about music."),
]


@pytest.fixture
def openai_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = MagicMock()
    monkeypatch.setattr(ai_providers, "OpenAI", MagicMock(return_value=client))
    return client


def reply(openai_client: MagicMock, data: Any) -> None:
    content = data if isinstance(data, str) else json.dumps(data)
    openai_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content=content))
    ]


def test_summarize_sends_the_transcript_with_its_timestamps(
    openai_client: MagicMock,
) -> None:
    reply(
        openai_client,
        {
            "summary": " A show. ",
            "key_points": ["Welcome", 3, ""],
            "chapters": [
                {"start": 65, "title": "Music"},
                {"start": 0, "title": "Intro"},
                {"start": 999, "title": "After the end"},
                {"start": "10", "title": "Not a number"},
            ],
        },
    )

    summary = SummaryHandler.summarize("Welcome. Music.", SEGMENTS)

    assert summary.summary == "A show."
    assert summary.key_points == ("Welcome",)
    assert summary.chapters == (Chapter(0.0, "Intro"), Chapter(65.0, "Music"))
    assert summary.model == "gpt-5.4-mini"
    assert not summary.is_partial
    kwargs = openai_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-5.4-mini"
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["messages"][1]["content"] == (
        "[0] SPEAKER_00: Welcome to the show.\n[65] Let's talk about music."
    )
    assert '"chapters": a list' in kwargs["messages"][0]["content"]


def test_summarize_without_timestamps_has_no_chapters(
    openai_client: MagicMock,
) -> None:
    reply(
        openai_client,
        {"summary": "Short.", "chapters": [{"start": 0, "title": "Ignored"}]},
    )

    summary = SummaryHandler.summarize("Some text.", [], model="other-model")

    assert summary.chapters == ()
    kwargs = openai_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "other-model"
    assert kwargs["messages"][1]["content"] == "Some text."
    assert "no timestamps" in kwargs["messages"][0]["content"]


def test_long_transcriptions_are_cut(openai_client: MagicMock) -> None:
    reply(openai_client, {"summary": "Long."})

    summary = SummaryHandler.summarize("a" * (MAX_INPUT_CHARS + 10), [])

    content = openai_client.chat.completions.create.call_args.kwargs["messages"][1][
        "content"
    ]
    assert len(content) == MAX_INPUT_CHARS
    assert summary.is_partial


def test_empty_text_raises(openai_client: MagicMock) -> None:
    with pytest.raises(ValueError, match="no text"):
        SummaryHandler.summarize("  ", [])

    openai_client.chat.completions.create.assert_not_called()


def test_summarize_without_api_key_raises() -> None:
    with pytest.raises(OSError):
        SummaryHandler.summarize("Text.", [])


@pytest.mark.parametrize("content", ["not json", "[]", '{"summary": ""}', "{}"])
def test_invalid_replies_raise(content: str) -> None:
    with pytest.raises(ValueError, match="valid summary"):
        parse_summary(content, "model", duration=None, is_partial=False)


def test_format_transcript_without_segments_is_the_text() -> None:
    assert format_transcript([], "Plain text.") == "Plain text."


def test_format_summary() -> None:
    summary = TranscriptSummary(
        "A show.", ("Welcome",), (Chapter(0, "Intro"), Chapter(3700, "End"))
    )

    assert (
        format_summary(summary) == "A show.\n\n• Welcome\n\n00:00  Intro\n01:01:40  End"
    )


def test_summary_round_trip() -> None:
    summary = TranscriptSummary(
        "A show.", ("Welcome",), (Chapter(1.5, "Intro"),), "model", "2026-10-03", True
    )

    assert TranscriptSummary.from_dict(summary.to_dict()) == summary
    assert TranscriptSummary.from_dict({}) is None
