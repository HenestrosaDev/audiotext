import speech_recognition as sr
import utils.config_manager as cm
from handlers.audio_handler import AudioHandler
from interfaces.transcribable import Transcribable
from models.transcription import Transcription
from openai import OpenAI
from utils.enums import WhisperApiResponseFormats
from utils.env_keys import EnvKeys


class OpenAiApiHandler(Transcribable):
    @staticmethod
    def transcribe(audio_data: sr.AudioData, transcription: Transcription) -> str:
        if not transcription.language_code:
            raise ValueError(
                "The language provided is not correct. Please select one of the list."
            )

        config = cm.ConfigManager.get_config_whisper_api()
        compressed_audio = AudioHandler.compress_audio(audio_data)
        timestamp_granularities = (
            config.timestamp_granularities.split(",")
            if config.response_format == WhisperApiResponseFormats.VERBOSE_JSON.value
            else None
        )

        client = OpenAI(
            api_key=EnvKeys.OPENAI_API_KEY.get_value(), timeout=120.0  # 2 minutes
        )

        whisper_api_transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=compressed_audio,
            language=transcription.language_code,
            response_format=config.response_format,
            temperature=config.temperature,
            timestamp_granularities=timestamp_granularities,
        )

        if WhisperApiResponseFormats.JSON.value in config.response_format:
            return whisper_api_transcription.to_json()

        return str(whisper_api_transcription)
