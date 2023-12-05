from enum import Enum

APP_NAME = "Audiotext"
APP_LANGUAGES = {"en": "English", "es": "Español"}

# Code languages convention: ISO 639-1
AUDIO_LANGUAGES = {
    "af": "Afrikaans",
    "am": "Amharic",
    "ar": "Arabic",
    "hy": "Armenian",
    "az": "Azerbaijan",
    "eu": "Basque",
    "be": "Belarusian",
    "bn": "Bengali",
    "bg": "Bulgarian",
    "ca": "Catalan",
    "zh": "Chinese (China)",
    "zh_HK": "Chinese (Hong Kong)",
    "zh_TW": "Chinese (Taiwan)",
    "hr": "Croatian",
    "cs": "Czech",
    "da": "Danish",
    "nl": "Dutch",
    "en": "English",
    "et": "Estonian",
    "fa": "Farsi",
    "fil": "Filipino",
    "fi": "Finnish",
    "fr": "French",
    "gl": "Galician",
    "ka": "Georgian",
    "de": "German",
    "de_CH": "German (Swiss Standard)",
    "el": "Greek",
    "gu": "Gujarati",
    "iw": "Hebrew",
    "hi": "Hindi",
    "hu": "Hungarian",
    "is": "Icelandic",
    "id": "Indonesian",
    "it": "Italian",
    "it_CH": "Swiss Italian",
    "ja": "Japanese",
    "jv": "Javanese",
    "kn": "Kannada",
    "kk": "Kazakh",
    "km": "Khmer",
    "ko": "Korean",
    "lo": "Lao",
    "lv": "Latvian",
    "lt": "Lithuanian",
    "ms": "Malay",
    "ml": "Malayalam",
    "mt": "Maltese",
    "mr": "Marathi",
    "mn": "Mongolian",
    "ne": "Nepali",
    "no": "Norwegian",
    "nn": "Norwegian Nynorsk",
    "pl": "Polish",
    "pt": "Português",
    "pa": "Punjabi",
    "ro": "Romanian",
    "ru": "Russian",
    "sr": "Serbian",
    "si": "Sinhala",
    "sk": "Slovak",
    "sl": "Slovenian",
    "es": "Spanish",
    "su": "Sundanese",
    "sw": "Swahili",
    "sv": "Swedish",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "vi": "Vietnamese",
    "zu": "Zulu",
}


class Color(Enum):
    LIGHT_RED = "#D30000"
    DARK_RED = "#8b0000"
    HOVER_LIGHT_RED = "#BF0000"
    HOVER_DARK_RED = "#610000"

    LIGHT_BLUE = "#3B8ED0"
    DARK_BLUE = "#1F6AA5"
    HOVER_LIGHT_BLUE = "#36719F"
    HOVER_DARK_BLUE = "#144870"


class AudioSource(Enum):
    FILE = "file"
    MIC = "mic"


AUDIO_FILE_EXTENSIONS = [
    ".mp3",
    ".mpeg",
    ".wav",
    ".wma",
    ".aac",
    ".flac",
    ".ogg",
    ".oga",
    ".opus",
]

# fmt: off
VIDEO_FILE_EXTENSIONS = [
    ".mp4", ".m4a", ".m4v", ".f4v", ".f4a", ".m4b", ".m4r", ".f4b", ".mov",  # MP4
    ".avi",  # AVI
    ".webm",  # WebM
    ".flv",  # FLV
    ".mkv",  # MKV
    ".3gp", ".3gp2", ".3g2", ".3gpp", ".3gpp2",  # 3GP
    ".ogv", ".ogx",  # OGG
    ".wmv", ".asf"  # AIFF / ASF
]
