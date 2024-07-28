import os
import shutil
import traceback
from io import BytesIO
from typing import Callable, Optional

import speech_recognition as sr
from models.transcription import Transcription
from moviepy.video.io.VideoFileClip import VideoFileClip
from pydub import AudioSegment
from pydub.silence import split_on_silence
from utils import constants as c
from utils.path_helper import ROOT_PATH


class AudioHandler:
    @staticmethod
    def get_transcription(
        transcription: Transcription,
        should_split_on_silence: bool,
        transcription_func: Callable[[sr.AudioData, Transcription], str],
    ) -> str:
        """
        Transcribes audio from a file using the Google Speech-to-Text API.

        :param transcription: An instance of Transcription containing information
                              about the audio file.
        :type transcription: Transcription
        :param should_split_on_silence: A boolean flag indicating whether the audio
                                        should be split into chunks based on silence.
                                        If True, the audio will be split on silence
                                        and each chunk will be transcribed separately.
                                        If False, the entire audio will be transcribed
                                        as a single segment.
        :type should_split_on_silence: bool
        :param transcription_func: The function to use for transcription.
        :type transcription_func: Callable[[sr.AudioData, Transcription], str]
        :return: The transcribed text or an error message if transcription fails.
        :rtype: str
        """
        chunks_directory = ROOT_PATH / "audio-chunks"
        chunks_directory.mkdir(exist_ok=True)

        try:
            audio = AudioHandler.load_audio_file(
                transcription.audio_source_path, chunks_directory
            )
            if audio is None:
                raise ValueError("Unsupported file type")

            if should_split_on_silence:
                audio_chunks = AudioHandler.split_audio_into_chunks(audio)
            else:
                audio_chunks = [audio]

            text = AudioHandler.process_audio_chunks(
                audio_chunks, transcription, transcription_func, chunks_directory
            )

        except Exception:
            text = traceback.format_exc()

        finally:
            AudioHandler.cleanup(chunks_directory)

        return text

    @staticmethod
    def load_audio_file(file_path, chunks_directory) -> Optional[AudioSegment]:
        """
        Load the audio from the file or extract it from the video.

        :param file_path: Path to the file to be loaded.
        :param chunks_directory: Directory to store intermediate audio files.
        :return: Loaded AudioSegment object or None if unsupported file type.
        """
        content_type = file_path.suffix

        if content_type in c.AUDIO_FILE_EXTENSIONS:
            return AudioSegment.from_file(file_path)

        elif content_type in c.VIDEO_FILE_EXTENSIONS:
            clip = VideoFileClip(str(file_path))
            video_audio_path = chunks_directory / f"{file_path.stem}.wav"
            clip.audio.write_audiofile(video_audio_path)
            return AudioSegment.from_wav(video_audio_path)

        return None

    @staticmethod
    def split_audio_into_chunks(sound: AudioSegment) -> AudioSegment:
        """
        Split the audio into chunks based on silence.

        :param sound: The AudioSegment object to be split.
        :type sound: AudioSegment
        :return: List of audio chunks.
        :rtype: AudioSegment
        """
        return split_on_silence(
            sound,
            min_silence_len=500,  # Minimum duration of silence required to consider a segment as a split point
            silence_thresh=sound.dBFS
            - 40,  # Audio with a level -X decibels below the original audio level will be considered as silence
            keep_silence=100,  # Adds a buffer of silence before and after each split point
        )

    @staticmethod
    def process_audio_chunks(
        audio_chunks, transcription, transcription_func, chunks_directory
    ):
        """
        Process each audio chunk for transcription.

        :param audio_chunks: List of audio chunks.
        :param transcription: Transcription object containing transcription details.
        :param transcription_func: The function to use for transcription.
        :param chunks_directory: Directory to store intermediate audio files.
        :return: The combined transcribed text.
        """
        text = ""
        recognizer = sr.Recognizer()

        for idx, audio_chunk in enumerate(audio_chunks):
            chunk_filename = os.path.join(chunks_directory, f"chunk{idx}.wav")
            audio_chunk.export(chunk_filename, bitrate="64k", format="wav")

            with sr.AudioFile(chunk_filename) as source:
                recognizer.adjust_for_ambient_noise(source)
                audio_data = recognizer.record(source)

                try:
                    chunk_text = transcription_func(
                        audio_data=audio_data,
                        transcription=transcription,
                    )
                    text += chunk_text
                    print(f"chunk text: {chunk_text}")

                except Exception:
                    return traceback.format_exc()

        return text

    @staticmethod
    def cleanup(chunks_directory):
        """
        Clean up the `chunks` directory.

        :param chunks_directory: Directory to be deleted.
        """
        shutil.rmtree(chunks_directory)

    @staticmethod
    def compress_audio(audio_data: sr.AudioData) -> BytesIO:
        # Convert sr.AudioData to AudioSegment
        audio_segment = AudioSegment(
            data=audio_data.get_raw_data(),
            sample_width=audio_data.sample_width,
            frame_rate=audio_data.sample_rate,
            channels=1,
        )

        # Compress the audio: reduce frame rate and export as MP3
        compressed_audio = BytesIO()
        audio_segment.set_frame_rate(12000).export(
            compressed_audio, format="mp3", bitrate="32k"
        )
        compressed_audio.seek(0)

        # Set name to be treated as a file
        compressed_audio.name = "audiotext-audio.mp3"

        size_in_mb = len(compressed_audio.getvalue()) / (1024 * 1024)
        print(f"Compressed audio size: {size_in_mb:.2f} MB")

        return compressed_audio
