from dataclasses import dataclass
from enum import Enum
from typing import Literal

TimestampGranularitiesType = Literal["word", "segment"]


@dataclass
class ConfigWhisperApi:
    response_format: Literal["json", "text", "srt", "verbose_json", "vtt"]
    temperature: float
    timestamp_granularities: list[TimestampGranularitiesType]

    class Key(Enum):
        """
        Enum class for keys associated with the WhisperX configuration.
        """

        SECTION = "whisper_api"
        RESPONSE_FORMAT = "response_format"
        TEMPERATURE = "temperature"
        TIMESTAMP_GRANULARITIES = "timestamp_granularities"

        def value_type(self) -> str:
            """
            Get the value type associated with the ConfigKey.

            :return: The type of the value as a string, or None if the key is not found.
            :rtype: str
            """
            type_mapping = {
                ConfigWhisperApi.Key.RESPONSE_FORMAT: "str",
                ConfigWhisperApi.Key.TEMPERATURE: "float",
                ConfigWhisperApi.Key.TIMESTAMP_GRANULARITIES: "list",
            }

            return str(type_mapping.get(self))
