from dataclasses import dataclass
from enum import Enum


@dataclass
class ConfigTranscription:
    language: str
    audio_source: str
    method: str
    autosave: bool
    # Added in a later version, so they have defaults for older `config.ini` files
    output_language: str = "same"
    translation_mode: str = "whisper"
    # On by default, as the transcript needs the timings and the scores of the
    # words to highlight them
    align_words: bool = True
    isolate_speech: bool = False
    # Folder of the files saved automatically for the URLs and the microphone
    output_dir: str = ""
    watch_folder: bool = False
    # Whether watching a folder transcribes the files it already contains first
    watch_transcribe_existing: bool = False
    folder_include_subfolders: bool = True
    # Patterns of the files of the folders to skip, separated by commas
    folder_exclude_patterns: str = ""
    # What the audio is about (e.g. its topic or setting)
    prompt: str = ""
    # Names, terms or acronyms said in the audio, separated by commas
    keywords: str = ""
    # Name of the last input device chosen for the microphone, or "" for the
    # default one of the system
    mic_device: str = ""

    class Key(Enum):
        """
        Enum class for keys associated with the transcription configuration.
        """

        SECTION = "transcription"
        LANGUAGE = "language"
        AUDIO_SOURCE = "audio_source"
        METHOD = "method"
        AUTOSAVE = "autosave"
        OUTPUT_LANGUAGE = "output_language"
        TRANSLATION_MODE = "translation_mode"
        ALIGN_WORDS = "align_words"
        ISOLATE_SPEECH = "isolate_speech"
        OUTPUT_DIR = "output_dir"
        WATCH_FOLDER = "watch_folder"
        WATCH_TRANSCRIBE_EXISTING = "watch_transcribe_existing"
        FOLDER_INCLUDE_SUBFOLDERS = "folder_include_subfolders"
        FOLDER_EXCLUDE_PATTERNS = "folder_exclude_patterns"
        PROMPT = "prompt"
        KEYWORDS = "keywords"
        MIC_DEVICE = "mic_device"
