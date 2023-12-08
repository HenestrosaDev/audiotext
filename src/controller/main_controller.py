import asyncio
import os
import shutil
import threading
import traceback
from pathlib import Path
from tkinter import filedialog

import speech_recognition as sr
from model.transcription import Transcription
from moviepy.video.io.VideoFileClip import VideoFileClip
from pydub import AudioSegment
from pydub.silence import split_on_silence
from utils import constants as c
from utils.i18n import _
from utils.path_helper import ROOT_PATH


class MainController:
    def __init__(self, transcription: Transcription, view):
        self.view = view
        self.transcription = transcription

    def select_file(self):
        """
        Prompts a file explorer to determine the audio/video file path to transcribe.
        Stores the filepath in the class variable filepath_to_transcribe.
        """
        filepath = filedialog.askopenfilename(
            initialdir="/",
            title=_("Select a file"),
            filetypes=[
                (
                    _("All supported files"),
                    c.AUDIO_FILE_EXTENSIONS + c.VIDEO_FILE_EXTENSIONS,
                ),
                (_("Audio files"), c.AUDIO_FILE_EXTENSIONS),
                (_("Video files"), c.VIDEO_FILE_EXTENSIONS),
            ],
        )

        self.transcription.filepath_to_transcribe = Path(filepath)

        if filepath:
            self.view.handle_select_file_success(filepath)

    def _is_file_valid(self, source):
        if source == c.AudioSource.MIC:
            return True

        filepath = self.transcription.filepath_to_transcribe
        is_audio = filepath.suffix in c.AUDIO_FILE_EXTENSIONS
        is_video = filepath.suffix in c.VIDEO_FILE_EXTENSIONS

        return filepath.is_file() and (is_audio or is_video)

    def generate_transcription(self, source: str, language_name: str):
        """
        Checks if the filepath is valid and executes an async task if it is.
        If it is not, then it displays an error message in the textbox.

        :param language_name: Language of the audio to transcribe.
        :type language_name: str
        :param source: The source of the audio, either from a file or the microphone.
        :type source: str

        :raises: IndexError if the selected language code is not valid.
        """
        if not self._is_file_valid(source):
            self.view.display_text(
                _(
                    "Error: No audio file selected, please select one before "
                    "generating text."
                )
            )
        else:
            try:
                self.view.toggle_ent_selected_file(should_show=False)

                self.transcription.language_code = [
                    key
                    for key, value in c.AUDIO_LANGUAGES.items()
                    if value.lower() == language_name
                ][0]

                self.transcription.source = source

                threading.Thread(
                    target=lambda loop: loop.run_until_complete(
                        self.async_get_transcription()
                    ),
                    args=(asyncio.new_event_loop(),),
                ).start()
            except IndexError:
                self.view.display_text(
                    _("Error: The selected audio language is not valid.")
                )
            except Exception:
                self.view.display_text(
                    _("Error generating the file transcription. Please try again.")
                )

    async def async_get_transcription(self):
        """
        Asynchronous function transcribes audio data from either a file or microphone,
        depending on the value of the source argument. It updates the transcription
        display, progress bar and action buttons accordingly.
        """
        self.view.handle_processing_transcription()

        # Get transcription
        self.view.handle_transcription_process_finish(is_transcription_empty)


    async def generate_file_transcription(self):
        """
        Splits a large audio file into chunks
        and applies speech recognition on each one.
        """
        file_path = self.transcription.filepath_to_transcribe

        # Can be the transcription or an error text
        transcription_text = ""

        # Create a directory to store the audio chunks
        chunks_directory = ROOT_PATH / "audio-chunks"
        chunks_directory.mkdir(exist_ok=True)

        try:
            # Get file extension
            content_type = Path(file_path).suffix

            sound = None
            # Open the audio file using pydub
            if content_type in c.AUDIO_FILE_EXTENSIONS:
                sound = AudioSegment.from_file(file_path)

            elif content_type in c.VIDEO_FILE_EXTENSIONS:
                clip = VideoFileClip(str(file_path))
                video_audio_path = chunks_directory / f"{Path(file_path).stem}.wav"
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
                        text = r.recognize_google(
                            audio_listened, language=self.transcription.language_code
                        )

                        text = f"{text.capitalize()}. "
                        transcription_text += text
                        print(f"text: {text}")
                    except Exception:
                        continue

            self.transcription.text = transcription_text

        except Exception:
            print(traceback.format_exc())
            self.view.display_text(
                _("Error generating the file transcription. Please try again.")
            )

        finally:
            # Delete temporal directory and files
            shutil.rmtree(chunks_directory)

            # Hide progress bar
            self.view.toggle_progress_bar_visibility(should_show=False)

            if self.transcription.text:
                self.view.display_text(self.transcription.text)

    async def generate_mic_transcription(self):
        """
        Generates the transcription from a microphone as
        the source of the audio.

        :returns: Transcription.
        :rtype: str
        """
        with sr.Microphone() as mic:
            try:
                r = sr.Recognizer()
                r.adjust_for_ambient_noise(mic)
                audio = r.listen(mic, timeout=3, phrase_time_limit=3)

                self.transcription.text = r.recognize_google(
                    audio, language=self.transcription.language_code
                )

                self.view.display_text(self.transcription.text)
                self.view.toggle_ent_selected_file(should_show=False)
            except OSError:
                self.view.display_text(_("Error: No microphone detected."))
            except sr.WaitTimeoutError:
                self.view.display_text(
                    _("Error: Listening timed out while waiting for phrase to start.")
                )
            except sr.UnknownValueError:
                self.view.display_text(
                    _("Sorry, I cannot clarify what you are saying. Please try again.")
                )
            except Exception:
                print(traceback.format_exc())
                self.view.display_text(_("Unexpected error. Please try again."))

    def save_transcription(self):
        """
        Prompts a file explorer to determine the file to save the
        generated transcription.
        """
        filepath = self.transcription.filepath_to_transcribe

        file = filedialog.asksaveasfile(
            mode="w",
            initialdir=Path(filepath).parent,
            initialfile=f"{Path(filepath).stem}.txt",
            title=_("Save as"),
            defaultextension=".txt",
            filetypes=[(_("Text file"), "*.txt"), (_("All Files"), "*.*")],
        )

        if file:
            file.write(self.transcription.text)
            file.close()
