from abc import abstractmethod
from typing import Protocol

import speech_recognition as sr
from models.transcription import Transcription


class Transcribable(Protocol):
    @staticmethod
    @abstractmethod
    def transcribe(audio_data: sr.AudioData, transcription: Transcription) -> str:
        raise NotImplementedError
