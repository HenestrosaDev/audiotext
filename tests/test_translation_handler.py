import json
from typing import Any

import pytest

import handlers.translation_handler as translation_handler
from handlers.ai_providers import AiProvider
from handlers.translation_handler import (
    DEEPL,
    DEEPL_FREE_URL,
    DEEPL_PRO_URL,
    GOOGLE_TRANSLATE,
    TranslationHandler,
    chunk,
    get_env_key,
    has_api_key,
    translate_texts,
)
from models.transcript_segment import TranscriptSegment, TranscriptWord
from models.translation import TranscriptTranslation
from utils.env_keys import EnvKeys

SEGMENTS = [
    TranscriptSegment(
        0.0, 1.0, "Hello", "SPEAKER_00", (TranscriptWord(0.0, 1.0, "Hello"),)
    ),
    TranscriptSegment(1.5, 3.0, "Goodbye", "SPEAKER_01"),
]


def fake_llm(
    monkeypatch: pytest.MonkeyPatch, reply: Any = None
) -> list[dict[str, Any]]:
    """
    Replaces the language model by one that uppercases the texts (or returns the
    given reply), and records the requests.
    """
    calls: list[dict[str, Any]] = []

    def complete_json(
        provider: AiProvider,
        model: str,
        instructions: str,
        content: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        texts = json.loads(content)["texts"]
        calls.append(
            {
                "provider": provider,
                "model": model,
                "instructions": instructions,
                "texts": texts,
            }
        )
        if reply is not None:
            return reply(texts) if callable(reply) else reply
        return {"translations": [text.upper() for text in texts]}

    monkeypatch.setattr(translation_handler, "complete_json", complete_json)
    return calls


def test_the_segments_are_translated_keeping_their_timestamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_llm(monkeypatch)

    translation = TranslationHandler.translate(
        "[SPEAKER_00]: Hello\n\n[SPEAKER_01]: Goodbye",
        SEGMENTS,
        is_text_edited=False,
        language="es",
        provider="anthropic",
    )

    assert translation.segments == (
        TranscriptSegment(0.0, 1.0, "HELLO", "SPEAKER_00"),
        TranscriptSegment(1.5, 3.0, "GOODBYE", "SPEAKER_01"),
    )
    assert translation.text == "[SPEAKER_00]: HELLO\n\n[SPEAKER_01]: GOODBYE"
    assert translation.language == "es"
    assert translation.provider == "anthropic"
    assert translation.model == "claude-haiku-4-5"
    assert calls[0]["provider"] == AiProvider.ANTHROPIC
    assert "into Spanish" in calls[0]["instructions"]


def test_the_edited_text_is_translated_line_by_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_llm(monkeypatch)

    translation = TranslationHandler.translate(
        "First line.\n\nSecond line.",
        SEGMENTS,
        is_text_edited=True,
        language="fr",
        provider="openai",
    )

    assert translation.segments == ()
    assert translation.text == "FIRST LINE.\n\nSECOND LINE."
    # The empty lines aren't sent
    assert calls[0]["texts"] == ["First line.", "Second line."]


def test_the_configured_provider_and_model_are_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from models.config.config_ai import ConfigAi
    from utils.config_manager import ConfigManager

    calls = fake_llm(monkeypatch)
    for key, value in [
        (ConfigAi.Key.TRANSLATION_PROVIDER, "deepseek"),
        (ConfigAi.Key.TRANSLATION_MODEL, "deepseek-reasoner"),
    ]:
        ConfigManager.modify_value(ConfigAi.Key.SECTION, key, value)

    TranslationHandler.translate("Hi.", [], False, "de")

    assert calls[0]["provider"] == AiProvider.DEEPSEEK
    assert calls[0]["model"] == "deepseek-reasoner"


def test_a_reply_with_missing_translations_is_retried_in_halves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reply(texts: list[str]) -> dict[str, Any]:
        # The model merges the texts when it gets more than one
        if len(texts) > 1:
            return {"translations": [" ".join(texts)]}
        return {"translations": [f"<{texts[0]}>"]}

    calls = fake_llm(monkeypatch, reply)

    result = translate_texts(["a", "b", "c"], "es", "openai")

    assert result == ["<a>", "<b>", "<c>"]
    assert [call["texts"] for call in calls][0] == ["a", "b", "c"]


def test_a_reply_without_translations_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_llm(monkeypatch, {"other": []})

    with pytest.raises(ValueError, match="valid translation"):
        translate_texts(["a"], "es", "openai")


def test_nothing_to_translate_raises() -> None:
    with pytest.raises(ValueError, match="no text"):
        TranslationHandler.translate("  ", [], False, "es", "deepl")


def test_long_transcriptions_are_translated_in_chunks() -> None:
    assert list(chunk(["aa", "bb", "cc", "d"], max_chars=4, max_items=10)) == [
        ["aa", "bb"],
        ["cc", "d"],
    ]
    assert list(chunk(["a", "b", "c"], max_chars=100, max_items=2)) == [
        ["a", "b"],
        ["c"],
    ]
    # A text longer than the limit is sent on its own
    assert list(chunk(["a" * 10, "b"], max_chars=4, max_items=10)) == [
        ["a" * 10],
        ["b"],
    ]


@pytest.mark.parametrize(
    ("key", "url"), [("abc:fx", DEEPL_FREE_URL), ("abc", DEEPL_PRO_URL)]
)
def test_deepl_uses_the_server_of_the_plan_of_the_key(
    monkeypatch: pytest.MonkeyPatch, key: str, url: str
) -> None:
    requests: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    def post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> Any:
        requests.append((url, payload, headers))
        return {"translations": [{"text": f"[{text}]"} for text in payload["text"]]}

    monkeypatch.setattr(translation_handler, "_post_json", post_json)
    monkeypatch.setenv("DEEPL_API_KEY", key)

    assert translate_texts(["Hello", "", "Bye"], "en", DEEPL) == [
        "[Hello]",
        "",
        "[Bye]",
    ]
    assert requests == [
        (
            url,
            {"text": ["Hello", "Bye"], "target_lang": "EN-US"},
            {"Authorization": f"DeepL-Auth-Key {key}"},
        )
    ]


def test_deepl_rejects_the_languages_it_doesnt_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPL_API_KEY", "abc")

    with pytest.raises(ValueError, match="DeepL can't translate into Welsh"):
        translate_texts(["Hello"], "cy", DEEPL)


def test_google_translate_sends_the_key_and_the_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, dict[str, Any]]] = []

    def post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> Any:
        requests.append((url, payload))
        return {
            "data": {
                "translations": [
                    {"translatedText": text[::-1]} for text in payload["q"]
                ]
            }
        }

    monkeypatch.setattr(translation_handler, "_post_json", post_json)
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key")

    assert translate_texts(["abc"], "zh", GOOGLE_TRANSLATE) == ["cba"]
    url, payload = requests[0]
    assert url.endswith("?key=g-key")
    assert payload == {"q": ["abc"], "target": "zh-CN", "format": "text"}


def test_the_keys_needed_by_each_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    assert get_env_key(DEEPL) == EnvKeys.DEEPL_API_KEY
    assert get_env_key(GOOGLE_TRANSLATE) == EnvKeys.GOOGLE_API_KEY
    assert get_env_key("anthropic") == EnvKeys.ANTHROPIC_API_KEY
    assert get_env_key("ollama") is None
    assert has_api_key("ollama")
    assert not has_api_key(DEEPL)

    monkeypatch.setenv("DEEPL_API_KEY", "abc")
    assert has_api_key(DEEPL)


def test_translation_round_trip() -> None:
    translation = TranscriptTranslation(
        "es",
        "Hola",
        (TranscriptSegment(0.5, 2.0, "Hola", "SPEAKER_00"),),
        "deepl",
        "",
        "2026-10-03T10:00:00+02:00",
    )

    assert TranscriptTranslation.from_dict(translation.to_dict()) == translation
    assert TranscriptTranslation.from_dict({}) is None


def test_the_texts_of_the_segments_of_old_translations_are_dropped() -> None:
    translation = TranscriptTranslation.from_dict(
        {"language": "es", "text": "Hola", "segments": ["Hola"]}
    )

    assert translation is not None
    assert translation.segments == ()
    assert translation.text == "Hola"
