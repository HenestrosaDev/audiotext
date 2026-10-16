from typing import Any

import pytest

import handlers.question_handler as question_handler
from handlers.ai_providers import AiProvider
from handlers.question_handler import (
    MAX_SOURCES,
    QuestionHandler,
    answer_from_data,
    build_content,
)
from models.config.config_ai import ConfigAi
from models.question import AnswerSource, TranscriptAnswer
from models.transcript_segment import TranscriptSegment
from utils.config_manager import ConfigManager

SEGMENTS = [
    TranscriptSegment(0.0, 2.0, "We'll ship on Friday.", "SPEAKER_00"),
    TranscriptSegment(2.0, 4.0, "Agreed.", "SPEAKER_01"),
]


def test_the_content_has_the_previous_answers_and_the_question() -> None:
    previous = [TranscriptAnswer("When?", "On Friday.")]

    content = build_content("[0] Hi", "Who agreed?", previous)

    assert content == (
        "<transcription>\n[0] Hi\n</transcription>\n\n"
        "<previous_questions>\nQuestion: When?\nAnswer: On Friday.\n"
        "</previous_questions>\n\n<question>\nWho agreed?\n</question>"
    )
    assert "<previous_questions>" not in build_content("[0] Hi", "Who?", [])


def test_the_sources_are_checked_and_sorted() -> None:
    data = {
        "answer": " SPEAKER_01 agreed. ",
        "sources": [
            {"start": 2, "quote": " Agreed. "},
            {"start": 0, "quote": "We'll ship on Friday."},
            # After the end, without a quote, or not even an object
            {"start": 99, "quote": "Out"},
            {"start": 1},
            "2",
        ],
    }

    answer = answer_from_data(data, "Who?", "model", 4.0, is_partial=False)

    assert answer.answer == "SPEAKER_01 agreed."
    assert answer.sources == (
        AnswerSource(0.0, "We'll ship on Friday."),
        AnswerSource(2.0, "Agreed."),
    )
    # Without timestamps, there are no sources
    assert answer_from_data(data, "Who?", "model", None, False).sources == ()


def test_the_sources_are_limited() -> None:
    data = {
        "answer": "Yes.",
        "sources": [{"start": idx, "quote": "x"} for idx in range(10)],
    }

    assert len(answer_from_data(data, "?", "m", 10.0, False).sources) == MAX_SOURCES


@pytest.mark.parametrize("data", [{}, {"answer": "  "}, {"answer": 3}])
def test_a_reply_without_an_answer_is_an_error(data: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        answer_from_data(data, "?", "model", None, False)


@pytest.mark.parametrize(
    "settings",
    [
        {ConfigAi.Key.ASK_PROVIDER: "anthropic", ConfigAi.Key.ASK_MODEL: "claude-x"},
        # Without their own, the questions are answered like the summaries
        {
            ConfigAi.Key.SUMMARY_PROVIDER: "anthropic",
            ConfigAi.Key.SUMMARY_MODEL: "claude-x",
        },
    ],
)
def test_the_provider_of_the_questions_answers(
    monkeypatch: pytest.MonkeyPatch, settings: dict[ConfigAi.Key, str]
) -> None:
    for key, value in settings.items():
        ConfigManager.modify_value(ConfigAi.Key.SECTION, key, value)
    requests: list[tuple[Any, ...]] = []

    def complete_json(*args: Any) -> dict[str, Any]:
        requests.append(args)
        return {"answer": "On Friday.", "sources": [{"start": 0, "quote": "Friday"}]}

    monkeypatch.setattr(question_handler, "complete_json", complete_json)

    answer = QuestionHandler().answer(
        "", SEGMENTS, " When do we ship? ", [TranscriptAnswer("Who?", "Them.")]
    )

    provider, model, instructions, content, _schema = requests[0]
    assert (provider, model) == (AiProvider.ANTHROPIC, "claude-x")
    assert '"sources": a list of the lines' in instructions
    assert "[0] SPEAKER_00: We'll ship on Friday." in content
    assert "Question: Who?\nAnswer: Them." in content
    assert content.endswith("<question>\nWhen do we ship?\n</question>")
    assert answer == TranscriptAnswer(
        "When do we ship?",
        "On Friday.",
        (AnswerSource(0.0, "Friday"),),
        "claude-x",
        answer.created_at,
    )


def test_a_transcription_without_timestamps_has_no_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        question_handler,
        "complete_json",
        lambda *args: requests.append(args) or {"answer": "Yes.", "sources": []},
    )

    QuestionHandler().answer("Plain text.", [], "Is it?", [], AiProvider.OPENAI, "")

    instructions, content = requests[0][2], requests[0][3]
    assert "an empty list, since the transcription has no timestamps" in instructions
    assert "Plain text." in content


def test_the_answers_are_stored_and_read_back() -> None:
    answer = TranscriptAnswer(
        "When?", "Friday.", (AnswerSource(1.5, "Friday"),), "model", "2026-01-01"
    )

    assert TranscriptAnswer.from_dict(answer.to_dict()) == answer


def test_the_questions_have_their_own_provider_once_set() -> None:
    config = ConfigAi(summary_provider="anthropic", summary_model="claude-x")
    assert config.ask_provider_and_model() == ("anthropic", "claude-x")

    config.ask_provider = "openai"
    assert config.ask_provider_and_model() == ("openai", "")
