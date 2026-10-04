import speech_recognition as sr

from interfaces.transcribable import Transcribable
from models.transcription import Transcription
from utils.env_keys import EnvKeys


class GoogleApiHandler(Transcribable):
    @staticmethod
    def transcribe(audio_data: sr.AudioData, transcription: Transcription) -> str:
        recognizer = sr.Recognizer()

        # Without an API key, the free tier of the Google API is used
        api_key = EnvKeys.GOOGLE_API_KEY.get_value(default="") or None

        text = recognizer.recognize_google(
            audio_data, language=transcription.language_code, key=api_key
        )

        # The Google API doesn't punctuate sentences
        return f"{text}. "
