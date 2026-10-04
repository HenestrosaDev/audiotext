from dataclasses import dataclass
from enum import Enum


@dataclass
class ConfigAi:
    """The providers of language models that summarize and translate."""

    # Values of `AiProvider`. The models are the defaults of the providers if empty
    summary_provider: str = "openai"
    summary_model: str = ""
    # Values of `TranslationProvider`
    translation_provider: str = "openai"
    translation_model: str = ""
    # Language of the last translation (e.g. "es"), offered for the next one
    translation_language: str = ""
    # Server of Ollama, which runs the models locally
    ollama_url: str = "http://localhost:11434"

    class Key(Enum):
        """
        Enum class for keys associated with the AI configuration.
        """

        SECTION = "ai"
        SUMMARY_PROVIDER = "summary_provider"
        SUMMARY_MODEL = "summary_model"
        TRANSLATION_PROVIDER = "translation_provider"
        TRANSLATION_MODEL = "translation_model"
        TRANSLATION_LANGUAGE = "translation_language"
        OLLAMA_URL = "ollama_url"
