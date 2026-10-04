from enum import Enum


class AudioSource(Enum):
    DIRECTORY = "Directory"
    FILE = "File"
    MIC = "Microphone"
    WATCH = "Watch folder"
    YOUTUBE = "YouTube"

    @property
    def has_several_files(self) -> bool:
        """Whether it transcribes several files, which are always autosaved."""
        return self in (AudioSource.DIRECTORY, AudioSource.WATCH)

    @property
    def is_temporary(self) -> bool:
        """
        Whether the audio is downloaded or recorded, so it's removed after being
        transcribed unless the history keeps it.
        """
        return self in (AudioSource.MIC, AudioSource.YOUTUBE)


class Color(Enum):
    LIGHT_RED = "#D30000"
    DARK_RED = "#8b0000"
    HOVER_LIGHT_RED = "#BF0000"
    HOVER_DARK_RED = "#610000"

    LIGHT_BLUE = "#3B8ED0"
    DARK_BLUE = "#1F6AA5"
    HOVER_LIGHT_BLUE = "#36719F"
    HOVER_DARK_BLUE = "#144870"

    LIGHT_GREEN = "#2E7D32"
    DARK_GREEN = "#2E7D32"
    HOVER_LIGHT_GREEN = "#1B5E20"
    HOVER_DARK_GREEN = "#1B5E20"

    # Text colors with enough contrast in the light and dark themes
    LIGHT_ERROR_TEXT = "#C62828"
    DARK_ERROR_TEXT = "#FF8A80"
    LIGHT_HINT_TEXT = "#5F6368"
    DARK_HINT_TEXT = "#A0A4A8"


class ComputeType(Enum):
    INT8 = "int8"
    FLOAT16 = "float16"
    FLOAT32 = "float32"


class ModelSize(Enum):
    TINY = "tiny"
    TINY_EN = "tiny.en"
    BASE = "base"
    BASE_EN = "base.en"
    SMALL = "small"
    SMALL_EN = "small.en"
    DISTIL_SMALL_EN = "distil-small.en"
    MEDIUM = "medium"
    MEDIUM_EN = "medium.en"
    DISTIL_MEDIUM_EN = "distil-medium.en"
    LARGE_V1 = "large-v1"
    LARGE_V2 = "large-v2"
    LARGE_V3 = "large-v3"
    LARGE_V3_TURBO = "large-v3-turbo"
    DISTIL_LARGE_V2 = "distil-large-v2"
    DISTIL_LARGE_V3 = "distil-large-v3"
    DISTIL_LARGE_V3_5 = "distil-large-v3.5"

    @property
    def is_english_only(self) -> bool:
        """Whether it only transcribes English, like the distilled models."""
        return self.value.endswith(".en") or self.value.startswith("distil-")

    @staticmethod
    def is_english_only_model(model_size: str) -> bool:
        try:
            return ModelSize(model_size).is_english_only
        except ValueError:
            return False


class TimestampGranularities(Enum):
    SEGMENT = "segment"
    WORD = "word"


class TranscriptionMethod(Enum):
    GOOGLE_API = "Google API"
    WHISPER_API = "Whisper API"
    WHISPERX = "WhisperX"


class WhisperApiResponseFormats(Enum):
    JSON = "json"
    SRT = "srt"
    TEXT = "text"
    VERBOSE_JSON = "verbose_json"
    VTT = "vtt"


class WhisperXFileTypes(Enum):
    AUD = "aud"
    JSON = "json"
    SRT = "srt"
    TXT = "txt"
    TSV = "tsv"
    VTT = "vtt"
