"""
The providers of language models that summarize and translate the transcriptions.
Most of them have an API compatible with the one of OpenAI, while Claude has its
own. The replies are JSON objects, so they can be read reliably.
"""

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from anthropic import Anthropic
from openai import OpenAI

import utils.config_manager as cm
from utils.env_keys import EnvKeys
from utils.i18n import _

REQUEST_TIMEOUT_SECONDS = 300.0
# Enough for the longest replies (the translation of a chunk of the transcription)
# without needing to stream them
MAX_OUTPUT_TOKENS = 16_000


class AiProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"
    MISTRAL = "mistral"
    GROK = "grok"
    OLLAMA = "ollama"


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    default_model: str
    # The key of its API. None if it doesn't need one (it runs locally)
    env_key: EnvKeys | None
    # The URL of its API compatible with the one of OpenAI, if it differs
    base_url: str | None = None


PROVIDERS = {
    AiProvider.OPENAI: ProviderInfo("OpenAI", "gpt-5.4-mini", EnvKeys.OPENAI_API_KEY),
    AiProvider.ANTHROPIC: ProviderInfo(
        "Claude (Anthropic)", "claude-haiku-4-5", EnvKeys.ANTHROPIC_API_KEY
    ),
    AiProvider.DEEPSEEK: ProviderInfo(
        "DeepSeek",
        "deepseek-chat",
        EnvKeys.DEEPSEEK_API_KEY,
        "https://api.deepseek.com",
    ),
    AiProvider.GEMINI: ProviderInfo(
        "Gemini (Google)",
        "gemini-3.8-flash",
        EnvKeys.GEMINI_API_KEY,
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
    AiProvider.MISTRAL: ProviderInfo(
        "Mistral",
        "mistral-small-latest",
        EnvKeys.MISTRAL_API_KEY,
        "https://api.mistral.ai/v1",
    ),
    AiProvider.GROK: ProviderInfo(
        "Grok (xAI)", "grok-4.3", EnvKeys.XAI_API_KEY, "https://api.x.ai/v1"
    ),
    AiProvider.OLLAMA: ProviderInfo("Ollama (local)", "llama3.2", None),
}


def get_provider(value: str) -> AiProvider:
    """:return: The provider of the value, or OpenAI if it's not known."""
    try:
        return AiProvider(value)
    except ValueError:
        return AiProvider.OPENAI


def has_api_key(provider: AiProvider) -> bool:
    """Whether the provider can be used: its key is set, or it doesn't need one."""
    env_key = PROVIDERS[provider].env_key
    return env_key is None or bool(env_key.get_value(default=""))


def resolve_model(provider: AiProvider, model: str | None) -> str:
    """:return: The model, or the default one of the provider if it's empty."""
    return (model or "").strip() or PROVIDERS[provider].default_model


def load_json_object(content: str) -> dict[str, Any]:
    """
    Reads the JSON object of a reply. Some models wrap it in a Markdown code
    block, which is ignored.

    :raises ValueError: If the reply has no JSON object.
    """
    content = content.strip()
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < start:
        raise ValueError(_("The model didn't return a valid reply."))

    try:
        data = json.loads(content[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(_("The model didn't return a valid reply.")) from e

    if not isinstance(data, dict):
        raise ValueError(_("The model didn't return a valid reply."))
    return data


def complete_json(
    provider: AiProvider,
    model: str,
    instructions: str,
    content: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """
    Asks a language model for a JSON object.

    :param instructions: The system prompt, which describes the expected object.
    :param content: The message of the user (e.g. the transcription).
    :param schema: The JSON schema of the object, for the providers that enforce
                   it. Its objects must not allow additional properties.
    :raises OSError: If the API key of the provider is not set.
    :raises ValueError: If the reply is not a JSON object.
    :return: The object of the reply.
    """
    if provider == AiProvider.ANTHROPIC:
        reply = _complete_anthropic(model, instructions, content, schema)
    else:
        reply = _complete_openai_compatible(provider, model, instructions, content)

    return load_json_object(reply)


def _complete_anthropic(
    model: str, instructions: str, content: str, schema: dict[str, Any]
) -> str:
    client = Anthropic(
        api_key=EnvKeys.ANTHROPIC_API_KEY.get_value(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response: Any = client.messages.create(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=instructions,
        messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    if response.stop_reason == "max_tokens":
        raise ValueError(_("The reply of the model was too long."))

    return "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )


def _complete_openai_compatible(
    provider: AiProvider, model: str, instructions: str, content: str
) -> str:
    info = PROVIDERS[provider]
    if provider == AiProvider.OLLAMA:
        base_url: str | None = (
            cm.ConfigManager.get_config_ai().ollama_url.rstrip("/") + "/v1"
        )
        # Ollama ignores the key, but the client requires one
        api_key = "ollama"
    else:
        base_url = info.base_url
        api_key = info.env_key.get_value() if info.env_key else ""

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS)
    response: Any = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": content},
        ],
        # Unlike a schema, it's supported by all the providers
        response_format={"type": "json_object"},
    )
    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise ValueError(_("The reply of the model was too long."))

    return str(choice.message.content or "")
