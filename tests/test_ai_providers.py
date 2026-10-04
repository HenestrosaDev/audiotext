from unittest.mock import MagicMock

import pytest

import handlers.ai_providers as ai_providers
from handlers.ai_providers import (
    AiProvider,
    complete_json,
    get_provider,
    has_api_key,
    load_json_object,
    resolve_model,
)
from handlers.summary_handler import SummaryHandler

SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


@pytest.fixture
def openai_class(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content='{"ok": true}'), finish_reason="stop")
    ]
    openai_class = MagicMock(return_value=client)
    monkeypatch.setattr(ai_providers, "OpenAI", openai_class)
    return openai_class


@pytest.fixture
def anthropic_class(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = MagicMock(
        stop_reason="end_turn",
        content=[MagicMock(type="text", text='{"summary": "From Claude."}')],
    )
    anthropic_class = MagicMock(return_value=client)
    monkeypatch.setattr(ai_providers, "Anthropic", anthropic_class)
    return anthropic_class


def test_claude_gets_the_schema_and_the_instructions(
    anthropic_class: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")

    data = complete_json(
        AiProvider.ANTHROPIC, "claude-haiku-4-5", "Summarize.", "Text.", SCHEMA
    )

    assert data == {"summary": "From Claude."}
    assert anthropic_class.call_args.kwargs["api_key"] == "sk-ant"
    kwargs = anthropic_class.return_value.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5"
    assert kwargs["system"] == "Summarize."
    assert kwargs["messages"] == [{"role": "user", "content": "Text."}]
    assert kwargs["output_config"] == {
        "format": {"type": "json_schema", "schema": SCHEMA}
    }


def test_a_truncated_reply_of_claude_raises(
    anthropic_class: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    anthropic_class.return_value.messages.create.return_value.stop_reason = "max_tokens"

    with pytest.raises(ValueError, match="too long"):
        complete_json(AiProvider.ANTHROPIC, "model", "", "Text.", SCHEMA)


@pytest.mark.parametrize(
    ("provider", "env_name", "base_url"),
    [
        (AiProvider.OPENAI, "OPENAI_API_KEY", None),
        (AiProvider.DEEPSEEK, "DEEPSEEK_API_KEY", "https://api.deepseek.com"),
        (AiProvider.MISTRAL, "MISTRAL_API_KEY", "https://api.mistral.ai/v1"),
        (AiProvider.GROK, "XAI_API_KEY", "https://api.x.ai/v1"),
        (
            AiProvider.GEMINI,
            "GEMINI_API_KEY",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        ),
    ],
)
def test_the_compatible_providers_use_their_url_and_key(
    openai_class: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    provider: AiProvider,
    env_name: str,
    base_url: str | None,
) -> None:
    monkeypatch.setenv(env_name, "secret")

    assert complete_json(provider, "model", "Do it.", "Text.", SCHEMA) == {"ok": True}

    assert openai_class.call_args.kwargs["api_key"] == "secret"
    assert openai_class.call_args.kwargs["base_url"] == base_url
    kwargs = openai_class.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["messages"][0] == {"role": "system", "content": "Do it."}


def test_ollama_needs_no_key_and_uses_the_configured_server(
    openai_class: MagicMock,
) -> None:
    assert has_api_key(AiProvider.OLLAMA)

    complete_json(AiProvider.OLLAMA, "llama3.2", "", "Text.", SCHEMA)

    assert openai_class.call_args.kwargs["base_url"] == "http://localhost:11434/v1"


def test_a_missing_key_raises() -> None:
    assert not has_api_key(AiProvider.DEEPSEEK)
    with pytest.raises(OSError):
        complete_json(AiProvider.DEEPSEEK, "model", "", "Text.", SCHEMA)


def test_the_summary_uses_the_configured_provider(
    anthropic_class: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.config.config_ai import ConfigAi
    from utils.config_manager import ConfigManager

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    ConfigManager.modify_value(
        ConfigAi.Key.SECTION, ConfigAi.Key.SUMMARY_PROVIDER, "anthropic"
    )

    summary = SummaryHandler.summarize("Some text.", [])

    assert summary.summary == "From Claude."
    assert summary.model == "claude-haiku-4-5"


def test_models_default_to_the_ones_of_the_provider() -> None:
    assert resolve_model(AiProvider.DEEPSEEK, "") == "deepseek-chat"
    assert resolve_model(AiProvider.DEEPSEEK, " deepseek-reasoner ") == (
        "deepseek-reasoner"
    )
    assert get_provider("unknown") == AiProvider.OPENAI


@pytest.mark.parametrize(
    "content",
    ['{"a": 1}', '```json\n{"a": 1}\n```', 'Here it is: {"a": 1}'],
)
def test_json_objects_are_read_from_the_replies(content: str) -> None:
    assert load_json_object(content) == {"a": 1}


@pytest.mark.parametrize("content", ["", "not json", "[1, 2]", "{broken"])
def test_replies_without_an_object_raise(content: str) -> None:
    with pytest.raises(ValueError, match="valid reply"):
        load_json_object(content)
