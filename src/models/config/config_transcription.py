from dataclasses import dataclass
from enum import Enum


@dataclass
class ConfigTranscription:
    language: str
    audio_source: str
    method: str
    autosave: bool
    overwrite_files: bool
    # Added in a later version, so they have defaults for older `config.ini` files
    output_language: str = "same"
    translation_mode: str = "whisper"
    align_words: bool = False
    isolate_speech: bool = False
    # Folder of the files saved automatically for the URLs and the microphone
    output_dir: str = ""
    watch_folder: bool = False
    # What the audio is about (e.g. its topic or setting)
    prompt: str = ""
    # Names, terms or acronyms said in the audio, separated by commas
    keywords: str = ""

    class Key(Enum):
        """
        Enum class for keys associated with the transcription configuration.
        """

        SECTION = "transcription"
        LANGUAGE = "language"
        AUDIO_SOURCE = "audio_source"
        METHOD = "method"
        AUTOSAVE = "autosave"
        OVERWRITE_FILES = "overwrite_files"
        OUTPUT_LANGUAGE = "output_language"
        TRANSLATION_MODE = "translation_mode"
        ALIGN_WORDS = "align_words"
        ISOLATE_SPEECH = "isolate_speech"
        OUTPUT_DIR = "output_dir"
        WATCH_FOLDER = "watch_folder"
        PROMPT = "prompt"
        KEYWORDS = "keywords"
