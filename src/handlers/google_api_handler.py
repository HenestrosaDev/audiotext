import speech_recognition as sr
from interfaces.transcribable import Transcribable
from models.transcription import Transcription
from utils.env_keys import EnvKeys


class GoogleApiHandler(Transcribable):
    @staticmethod
    def transcribe(audio_data: sr.AudioData, transcription: Transcription) -> str:
        r = sr.Recognizer()

        text = r.recognize_google(
            audio_data,
            language=transcription.language_code,
            key=EnvKeys.GOOGLE_API_KEY.get_value() or None,
        )
        text = f"{text}. "

        return text
