import os
import shutil
import traceback

import speech_recognition as sr
from models.transcription import Transcription
from moviepy.video.io.VideoFileClip import VideoFileClip
from pydub import AudioSegment
from pydub.silence import split_on_silence
from utils import constants as c
from utils.env_keys import EnvKeys
from utils.path_helper import ROOT_PATH


class GoogleApiHandler:
    @staticmethod
    async def transcribe_file(transcription: Transcription) -> str:
        """
        Transcribes audio from a file using the Google Speech-to-Text API.

        :param transcription: An instance of Transcription containing information
                              about the audio file.
        :return: The transcribed text or an error message if transcription fails.
        """
        # Can be the transcription or an error text
        text = ""

        file_path = transcription.source_path

        # Create a directory to store the audio chunks
        chunks_directory = ROOT_PATH / "audio-chunks"
        chunks_directory.mkdir(exist_ok=True)

        try:
            # Get file extension
            content_type = file_path.suffix

            sound = None
            # Open the audio file using pydub
            if content_type in c.AUDIO_FILE_EXTENSIONS:
                sound = AudioSegment.from_file(file_path)

            elif content_type in c.VIDEO_FILE_EXTENSIONS:
                clip = VideoFileClip(str(file_path))
                video_audio_path = chunks_directory / f"{file_path.stem}.wav"
                clip.audio.write_audiofile(video_audio_path)
                sound = AudioSegment.from_wav(video_audio_path)

            audio_chunks = split_on_silence(
                sound,
                # Minimum duration of silence required to consider a segment as a split point
                min_silence_len=500,
                # Audio with a level -X decibels below the original audio level will be considered as silence
                silence_thresh=sound.dBFS - 40,
                # Adds a buffer of silence before and after each split point
                keep_silence=100,
            )

            # Create a speech recognition object
            r = sr.Recognizer()

            # Get Google API key (if any)
            api_key = EnvKeys.GOOGLE_API_KEY.get_value()

            # Process each chunk
            for idx, audio_chunk in enumerate(audio_chunks):
                # Export audio chunk and save it in the `chunks_directory` directory.
                chunk_filename = os.path.join(chunks_directory, f"chunk{idx}.wav")
                audio_chunk.export(chunk_filename, bitrate="192k", format="wav")

                # Recognize the chunk
                with sr.AudioFile(chunk_filename) as source:
                    r.adjust_for_ambient_noise(source)
                    audio_listened = r.record(source)

                    try:
                        # Try converting it to text
                        chunk_text = r.recognize_google(
                            audio_listened,
                            language=transcription.language_code,
                            key=api_key,
                        )

                        chunk_text = f"{chunk_text.capitalize()}. "
                        text += chunk_text
                        print(f"chunk text: {chunk_text}")

                    except Exception:
                        continue

        except Exception:
            text = traceback.format_exc()

        finally:
            # Delete temporal directory and files
            shutil.rmtree(chunks_directory)

            return text
