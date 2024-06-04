from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass
class ConfigGoogleApi:
    api_key: str

    class Key(Enum):
        """
        Enum class for keys associated with the Google API configuration.
        """

        SECTION = "google_api"
        API_KEY = "api_key"

        def value_type(self) -> Optional[str]:
            """
            Get the value type associated with the ConfigKey.
            """
            type_mapping = {
                self.API_KEY: "str",
            }

            return type_mapping.get(self, None)
