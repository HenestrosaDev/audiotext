import os
from enum import Enum
from typing import Optional

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())


class EnvKeys(Enum):
    GOOGLE_API_KEY = "GOOGLE_API_KEY"
    OPENAI_API_KEY = "OPENAI_API_KEY"

    @property
    def value(self) -> Optional[str]:
        return os.getenv(self._value_)

    def get_value(self, default: Optional[str] = None) -> str:
        value = os.getenv(self._value_)

        if value is not None:
            return value
        elif default is not None:
            return default
        else:
            raise EnvironmentError(
                f"Environment variable {self._value_} not set and no default value "
                "provided."
            )

    def set_value(self, value: str) -> None:
        os.environ[self._value_] = value
