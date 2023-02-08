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
from utils.i18n import _, load_translation
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
        audio_file_extensions_list = [
            ext for value in c.AUDIO_FILE_EXTENSIONS.values() for ext in value
        ]

        filepath = filedialog.askopenfilename(
            initialdir="/",
            title=_("Select a file"),
            filetypes=[
                (_("Audio files"), audio_file_extensions_list),
                (_("Video files"), c.VIDEO_FILE_EXTENSIONS),
            ],
        )

        self.transcription.filepath_to_transcribe = Path(filepath)

        if filepath:
            self.view.toggle_ent_selected_file(should_show=True)
            self.view.set_ent_selected_file_text(filepath)
            self.view.toggle_btn_generate_transcription(should_show=True)

    def change_app_language(self, language_name: str):
        """
        Change the language of the application.
        The text properties of various GUI elements are then updated to reflect the
        new language.

        :param language_name: The name of the language to change to.
        :type language_name: str
        """
        language_code = [
            i for i in c.AUDIO_LANGUAGES if c.AUDIO_LANGUAGES[i] == language_name
        ][0]

        load_translation(language_code)

        self.view.refresh_widgets()

    def _is_file_valid(self, source):
        filepath = self.transcription.filepath_to_transcribe

        if source != c.FILE:
            return True

        audio_extensions = c.AUDIO_FILE_EXTENSIONS.values()
        is_audio = any(filepath.suffix in extensions for extensions in audio_extensions)
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
                    "Error: No audio file selected, please select one before generating text."
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
        # Show progress bar
        self.view.toggle_progress_bar(should_show=True)

        # Disable action buttons to avoid multiple requests at the same time
        self.view.toggle_btn_generate_transcription_state(should_enable=False)
        self.view.toggle_btn_transcribe_from_mic_state(should_enable=False)

        # Get transcription
        if self.transcription.source == c.FILE:
            await self.generate_file_transcription()
        elif self.transcription.source == c.MIC:
            await self.generate_mic_transcription()

        # Re-enable action buttons
        self.view.toggle_btn_generate_transcription_state(should_enable=True)
        self.view.toggle_btn_transcribe_from_mic_state(should_enable=True)
        self.view.toggle_btn_generate_transcription(should_show=False)

        # Remove progress bar
        self.view.toggle_progress_bar(should_show=False)

        # Show save button if transcription is not empty
        if self.transcription.text:
            self.view.toggle_btn_save(should_show=True)

    async def generate_file_transcription(self):
        """
        Splits a large audio file into chunks
        and applies speech recognition on each one.

        :returns: Audio transcription.
        :rtype: str
        """
        filepath = self.transcription.filepath_to_transcribe

        # Can be the transcription or an error text
        text_to_return = ""

        # Create a directory to store the audio chunks
        chunks_directory = ROOT_PATH / "audio-chunks"
        chunks_directory.mkdir(exist_ok=True)

        try:
            # Create a speech recognition object
            r = sr.Recognizer()

            # Get file extension
            content_type = Path(filepath).suffix

            # Open the audio file using pydub
            if content_type in c.AUDIO_FILE_EXTENSIONS["wav"]:
                sound = AudioSegment.from_wav(filepath)
            elif content_type in c.AUDIO_FILE_EXTENSIONS["ogg"]:
                sound = AudioSegment.from_ogg(filepath)
            elif content_type in c.AUDIO_FILE_EXTENSIONS["mp3"]:
                sound = AudioSegment.from_mp3(filepath)
            elif content_type in c.VIDEO_FILE_EXTENSIONS:
                clip = VideoFileClip(filepath)
                video_audio_path = chunks_directory / f"{Path(filepath).stem}.wav"
                clip.audio.write_audiofile(video_audio_path)
                sound = AudioSegment.from_wav(video_audio_path)

            # Split audio sound where silence is 500 milliseconds or more and get chunks
            chunks = split_on_silence(
                sound,
                # Experiment with this value for your target audio file
                min_silence_len=500,
                # Adjust this per requirement
                silence_thresh=sound.dBFS - 14,
                # Keep the silence for 1 second, adjustable as well
                keep_silence=500,
            )

            # Process each chunk
            for i, audio_chunk in enumerate(chunks, start=1):
                # Export audio chunk and save it in the `chunks_directory` directory.
                chunk_filename = os.path.join(chunks_directory, f"chunk{i}.wav")
                audio_chunk.export(chunk_filename, format="wav")

                # Recognize the chunk
                with sr.AudioFile(chunk_filename) as source:
                    audio_listened = r.record(source)

                    # Try converting it to text
                    text = r.recognize_google(
                        audio_listened, language=self.transcription.language_code
                    )

                    text = f"{text.capitalize()}. "
                    text_to_return += text

            self.transcription.text = text_to_return
        except Exception:
            print(traceback.format_exc())
            self.view.display_text(
                _("Error generating the file transcription. Please try again.")
            )
        finally:
            # Delete temporal directory and files
            shutil.rmtree(chunks_directory)

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
                    _(
                        "Error: Sorry, I cannot clarify what you are saying. Please try again."
                    )
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
