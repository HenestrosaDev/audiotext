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

            :return
            :rtype: str
            """
            type_mapping = {
                self.MODEL_SIZE: "str",
                self.BATCH_SIZE: "int",
                self.COMPUTE_TYPE: "str",
                self.USE_CPU: "bool",
                self.CAN_USE_GPU: "bool",
                self.OUTPUT_FILE_TYPES: "str",
            }

            return type_mapping.get(self, None)
