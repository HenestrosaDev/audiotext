from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass
class ConfigWhisperX:
    model_size: str
    batch_size: int
    compute_type: str
    use_cpu: bool
    can_use_gpu: bool
    output_file_types: str

    class Key(Enum):
        """
        Enum class for keys associated with the WhisperX configuration.
        """

        SECTION = "whisperx"
        MODEL_SIZE = "model_size"
        BATCH_SIZE = "batch_size"
        COMPUTE_TYPE = "compute_type"
        USE_CPU = "use_cpu"
        CAN_USE_GPU = "can_use_gpu"
        OUTPUT_FILE_TYPES = "output_file_types"

        def value_type(self) -> Optional[str]:
            """
            Get the value type associated with the ConfigKey.

            :return: The type of the value as a string, or None if the key is not found.
            :rtype: str
            """
            type_mapping = {
                ConfigWhisperX.Key.MODEL_SIZE: "str",
                ConfigWhisperX.Key.BATCH_SIZE: "int",
                ConfigWhisperX.Key.COMPUTE_TYPE: "str",
                ConfigWhisperX.Key.USE_CPU: "bool",
                ConfigWhisperX.Key.CAN_USE_GPU: "bool",
                ConfigWhisperX.Key.OUTPUT_FILE_TYPES: "str",
            }

            return str(type_mapping.get(self, None))
