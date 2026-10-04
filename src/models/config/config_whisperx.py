from dataclasses import dataclass
from enum import Enum
from typing import Literal

OutputFileTypes = Literal["aud", "json", "srt", "tsv", "txt", "vtt"]


@dataclass
class ConfigWhisperX:
    model_size: str
    batch_size: int
    compute_type: str
    use_cpu: bool
    can_use_gpu: bool
    output_file_types: list[OutputFileTypes]
    # Added in a later version, so they have defaults for older `config.ini` files
    diarize: bool = False
    # 0 lets the diarization model detect the number of speakers
    num_speakers: int = 0
    # Shows the text while recording from the microphone, transcribed with a
    # smaller model to keep up with the speech
    live_transcription: bool = True
    live_model_size: str = "small"

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
        DIARIZE = "diarize"
        NUM_SPEAKERS = "num_speakers"
        LIVE_TRANSCRIPTION = "live_transcription"
        LIVE_MODEL_SIZE = "live_model_size"
