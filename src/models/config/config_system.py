from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass
class ConfigSystem:
    appearance_mode: str

    class Key(Enum):
        """
        Enum class for keys associated with the system configuration.
        """

        SECTION = "system"
        APPEARANCE_MODE = "appearance_mode"

        def value_type(self) -> Optional[str]:
            """Get the value type associated with the ConfigKey."""
            type_mapping = {self.APPEARANCE_MODE: "str"}

            return type_mapping.get(self, None)
