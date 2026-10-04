"""
Translates transcriptions into another language with DeepL, Google Translate or a
language model of the providers of `AiProvider`.

The segments of the transcription are translated one by one, so the translation
starts with their timestamps and can be followed while playing the audio.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import datetime
from typing import Any

import utils.config_manager as cm
import utils.constants as c
from handlers.ai_providers import (
    PROVIDERS,
    REQUEST_TIMEOUT_SECONDS,
    AiProvider,
    complete_json,
    resolve_model,
)
from models.transcript_segment import TranscriptSegment, join_segments
from models.translation import TranscriptTranslation
from utils.env_keys import EnvKeys
from utils.i18n import _, sort_key

DEEPL = "deepl"
GOOGLE_TRANSLATE = "google"
# Not a provider: the user translates the transcription from scratch
MANUAL = "manual"

# The translations are requested in chunks, which keeps the replies of the models
# short and within the limits of the APIs
MAX_LLM_CHUNK_CHARS = 6_000
MAX_LLM_CHUNK_ITEMS = 80
MAX_DEEPL_CHUNK_CHARS = 30_000
MAX_DEEPL_CHUNK_ITEMS = 50
MAX_GOOGLE_CHUNK_CHARS = 5_000
MAX_GOOGLE_CHUNK_ITEMS = 100

DEEPL_FREE_URL = "https://api-free.deepl.com/v2/translate"
DEEPL_PRO_URL = "https://api.deepl.com/v2/translate"
GOOGLE_TRANSLATE_URL = "https://translation.googleapis.com/language/translate/v2"

# Target languages of DeepL, by the code of Whisper
DEEPL_LANGUAGES = {
    "ar": "AR",
    "bg": "BG",
    "cs": "CS",
    "da": "DA",
    "de": "DE",
    "el": "EL",
    "en": "EN-US",
    "es": "ES",
    "et": "ET",
    "fi": "FI",
    "fr": "FR",
    "he": "HE",
    "hu": "HU",
    "id": "ID",
    "it": "IT",
    "ja": "JA",
    "ko": "KO",
    "lt": "LT",
    "lv": "LV",
    "nl": "NL",
    "no": "NB",
    "pl": "PL",
    "pt": "PT-PT",
    "ro": "RO",
    "ru": "RU",
    "sk": "SK",
    "sl": "SL",
    "sv": "SV",
    "th": "TH",
    "tr": "TR",
    "uk": "UK",
    "vi": "VI",
    "zh": "ZH-HANS",
}
# Codes of Whisper that differ from the ones of Google Translate
GOOGLE_LANGUAGES = {"zh": "zh-CN", "jw": "jv", "yue": "yue", "haw": "haw"}

LLM_INSTRUCTIONS = """\
You translate fragments of a transcription of an audio or video recording into \
{language}.

You receive a JSON object with a list "texts". Reply with a JSON object with the \
key "translations": a list with the translation of each text, in the same order \
and with exactly the same number of items ({count}). Translate each text on its \
own, without merging, splitting or skipping any, but use the others as context. \
Keep the speaker labels (e.g. [SPEAKER_00]), the names and the tone. If a text is \
already in {language}, return it unchanged."""

LLM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"translations": {"type": "array", "items": {"type": "string"}}},
    "required": ["translations"],
    "additionalProperties": False,
}


def translation_providers() -> dict[str, str]:
    """The names of the providers of translations, by their value, sorted."""
    names = {
        DEEPL: "DeepL",
        GOOGLE_TRANSLATE: "Google Translate",
        **{provider.value: info.name for provider, info in PROVIDERS.items()},
    }
    return dict(sorted(names.items(), key=lambda item: sort_key(item[1])))


def get_ai_provider(provider: str) -> AiProvider | None:
    """:return: The provider of language models, or None if it's DeepL or Google."""
    try:
        return AiProvider(provider)
    except ValueError:
        return None


def get_env_key(provider: str) -> EnvKeys | None:
    """:return: The API key needed by the provider, or None if it needs none."""
    if provider == DEEPL:
        return EnvKeys.DEEPL_API_KEY
    if provider == GOOGLE_TRANSLATE:
        return EnvKeys.GOOGLE_API_KEY
    if ai_provider := get_ai_provider(provider):
        return PROVIDERS[ai_provider].env_key
    return None


def has_api_key(provider: str) -> bool:
    env_key = get_env_key(provider)
    return env_key is None or bool(env_key.get_value(default=""))


def chunk(texts: list[str], max_chars: int, max_items: int) -> Iterator[list[str]]:
    """Splits the texts in chunks of at most the given characters and items."""
    current: list[str] = []
    size = 0

    for text in texts:
        if current and (size + len(text) > max_chars or len(current) >= max_items):
            yield current
            current, size = [], 0
        current.append(text)
        size += len(text)

    if current:
        yield current


def translate_texts(
    texts: list[str], language: str, provider: str, model: str = ""
) -> list[str]:
    """
    Translates each text. The empty ones are kept as they are.

    :param language: The code of the target language (see `AUDIO_LANGUAGES`).
    :param provider: The value of the provider of the translation.
    :param model: The language model, for the providers of language models.
    :raises OSError: If the API key is not set or the API can't be reached.
    :raises ValueError: If the reply is not valid or the language isn't supported.
    """
    indexes = [idx for idx, text in enumerate(texts) if text.strip()]
    pending = [texts[idx] for idx in indexes]

    if provider == DEEPL:
        translated = _translate_chunks(
            pending,
            MAX_DEEPL_CHUNK_CHARS,
            MAX_DEEPL_CHUNK_ITEMS,
            lambda part: _translate_deepl(part, language),
        )
    elif provider == GOOGLE_TRANSLATE:
        translated = _translate_chunks(
            pending,
            MAX_GOOGLE_CHUNK_CHARS,
            MAX_GOOGLE_CHUNK_ITEMS,
            lambda part: _translate_google(part, language),
        )
    else:
        ai_provider = get_ai_provider(provider) or AiProvider.OPENAI
        model = resolve_model(ai_provider, model)
        translated = _translate_chunks(
            pending,
            MAX_LLM_CHUNK_CHARS,
            MAX_LLM_CHUNK_ITEMS,
            lambda part: _translate_llm(part, language, ai_provider, model),
        )

    result = list(texts)
    for idx, text in zip(indexes, translated, strict=True):
        result[idx] = text
    return result


def _translate_chunks(
    texts: list[str],
    max_chars: int,
    max_items: int,
    translate: Callable[[list[str]], list[str]],
) -> list[str]:
    result: list[str] = []
    for part in chunk(texts, max_chars, max_items):
        result.extend(translate(part))
    return result


# LANGUAGE MODELS


def _translate_llm(
    texts: list[str], language: str, provider: AiProvider, model: str
) -> list[str]:
    """
    Translates the texts with a language model. If the model doesn't return a
    translation for each text, each half is translated on its own.
    """
    instructions = LLM_INSTRUCTIONS.format(
        language=c.AUDIO_LANGUAGES.get(language, language), count=len(texts)
    )
    data = complete_json(
        provider,
        model,
        instructions,
        json.dumps({"texts": texts}, ensure_ascii=False),
        LLM_SCHEMA,
    )
    translations = data.get("translations")

    if (
        isinstance(translations, list)
        and len(translations) == len(texts)
        and all(isinstance(text, str) for text in translations)
    ):
        return [text.strip() for text in translations]

    if len(texts) == 1:
        raise ValueError(_("The model didn't return a valid translation."))

    middle = len(texts) // 2
    return _translate_llm(texts[:middle], language, provider, model) + _translate_llm(
        texts[middle:], language, provider, model
    )


# TRANSLATION APIS


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> Any:
    """
    :raises OSError: If the request fails, with the message of the API if any.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as reply:
            return json.loads(reply.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise OSError(_describe_http_error(e)) from e
    except urllib.error.URLError as e:
        raise OSError(str(e.reason)) from e


def _describe_http_error(error: urllib.error.HTTPError) -> str:
    try:
        data = json.loads(error.read().decode("utf-8"))
    except (OSError, ValueError):
        data = None

    message = ""
    if isinstance(data, dict):
        # DeepL: {"message": ...}. Google: {"error": {"message": ...}}
        inner = data.get("error")
        message = str(
            data.get("message")
            or (inner.get("message") if isinstance(inner, dict) else inner)
            or ""
        )
    return f"HTTP {error.code}: {message or error.reason}"


def _translate_deepl(texts: list[str], language: str) -> list[str]:
    target = DEEPL_LANGUAGES.get(language)
    if target is None:
        raise ValueError(
            _("DeepL can't translate into {language}.").format(
                language=c.AUDIO_LANGUAGES.get(language, language)
            )
        )

    key = EnvKeys.DEEPL_API_KEY.get_value()
    # The keys of the free plan end with ":fx" and have their own server
    url = DEEPL_FREE_URL if key.endswith(":fx") else DEEPL_PRO_URL
    data = _post_json(
        url,
        {"text": texts, "target_lang": target},
        {"Authorization": f"DeepL-Auth-Key {key}"},
    )
    translations = data.get("translations") if isinstance(data, dict) else None
    if not isinstance(translations, list) or len(translations) != len(texts):
        raise ValueError(_("DeepL didn't return a valid translation."))

    return [str(item.get("text", "")) for item in translations]


def _translate_google(texts: list[str], language: str) -> list[str]:
    key = EnvKeys.GOOGLE_API_KEY.get_value()
    url = f"{GOOGLE_TRANSLATE_URL}?{urllib.parse.urlencode({'key': key})}"
    data = _post_json(
        url,
        {
            "q": texts,
            "target": GOOGLE_LANGUAGES.get(language, language),
            "format": "text",
        },
        {},
    )
    translations = (
        data.get("data", {}).get("translations") if isinstance(data, dict) else None
    )
    if not isinstance(translations, list) or len(translations) != len(texts):
        raise ValueError(_("Google Translate didn't return a valid translation."))

    return [str(item.get("translatedText", "")) for item in translations]


class TranslationHandler:
    @staticmethod
    def translate(
        text: str,
        segments: list[TranscriptSegment],
        is_text_edited: bool,
        language: str,
        provider: str | None = None,
        model: str | None = None,
    ) -> TranscriptTranslation:
        """
        Translates a transcription: its segments, so the translation keeps their
        timestamps, or its text if it has no segments or the user edited it.

        :param language: The code of the target language (e.g. "es").
        :param provider: The value of the provider. Defaults to the configured one.
        :param model: The language model, for the providers of language models.
                      Defaults to the configured one.
        :raises ValueError: If there is nothing to translate or the reply is not
                            valid.
        :raises OSError: If the API key of the provider is not set or its API
                         can't be reached.
        """
        if not text.strip() and not segments:
            raise ValueError(_("There is no text to translate."))

        if provider is None:
            config = cm.ConfigManager.get_config_ai()
            provider = config.translation_provider
            model = model or config.translation_model
        ai_provider = get_ai_provider(provider)
        model = resolve_model(ai_provider, model) if ai_provider else ""

        if segments and not is_text_edited:
            translated = translate_texts(
                [segment.text for segment in segments], language, provider, model
            )
            translated_segments = tuple(
                replace(segment, text=segment_text, words=())
                for segment, segment_text in zip(segments, translated, strict=True)
            )
            translated_text = join_segments(list(translated_segments))
        else:
            # Line by line, which keeps the paragraphs
            translated_segments = ()
            translated_text = "\n".join(
                translate_texts(text.split("\n"), language, provider, model)
            )

        return TranscriptTranslation(
            language=language,
            text=translated_text,
            segments=translated_segments,
            provider=provider,
            model=model,
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
