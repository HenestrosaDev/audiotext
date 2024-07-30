from dataclasses import dataclass
from enum import Enum


@dataclass
class ConfigSystem:
    appearance_mode: str

    class Key(Enum):
        """
        Enum class for keys associated with the system configuration.
        """

        SECTION = "system"
        APPEARANCE_MODE = "appearance_mode"

        def value_type(self) -> str:
            """
            Get the value type associated with the ConfigKey.

            :return: The type of the value as a string, or None if the key is not found.
            :rtype: str
            """
            type_mapping = {ConfigSystem.Key.APPEARANCE_MODE: "str"}

            return str(type_mapping.get(self))
