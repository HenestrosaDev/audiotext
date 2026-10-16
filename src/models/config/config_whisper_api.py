from dataclasses import dataclass
from enum import Enum
from typing import Literal

TimestampGranularitiesType = Literal["word", "segment"]


@dataclass
class ConfigWhisperApi:
    temperature: float
    timestamp_granularities: list[TimestampGranularitiesType]
    # Added in a later version, so they have defaults for older `config.ini` files
    model: str = "whisper-1"

    class Key(Enum):
        """
        Enum class for keys associated with the Whisper API configuration.
        """

        SECTION = "whisper_api"
        TEMPERATURE = "temperature"
        TIMESTAMP_GRANULARITIES = "timestamp_granularities"
        MODEL = "model"
