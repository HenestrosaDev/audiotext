from typing import Protocol

from models.transcript_segment import TranscriptSegment
from models.translation import TranscriptTranslation


class Translator(Protocol):
    """Translates the transcriptions of the history (see `TranslationHandler`)."""

    def translate(
        self,
        text: str,
        segments: list[TranscriptSegment],
        is_text_edited: bool,
        language: str,
        provider: str,
        model: str,
    ) -> TranscriptTranslation:
        """
        Translates a transcription. It takes a while, so it's called from a
        background thread.

        :param is_text_edited: Whether the user edited the text, which is then
                               translated instead of the segments.
        :param language: The code of the target language (e.g. "es").
        :param provider: The value of the provider of the translation.
        :param model: The language model, for the providers of language models.
                      If empty, the default one of the provider.
        """
        ...
