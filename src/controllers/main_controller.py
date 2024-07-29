import asyncio
import os
import threading
import traceback
from pathlib import Path
from tkinter import filedialog

import speech_recognition as sr
import utils.audio_utils as au
from handlers.audio_handler import AudioHandler
from handlers.google_api_handler import GoogleApiHandler
from handlers.openai_api_handler import OpenAiApiHandler
from handlers.whisperx_handler import WhisperXHandler
from handlers.youtube_handler import YouTubeHandler
from models.transcription import Transcription
from utils import constants as c
from utils.enums import AudioSource, TranscriptionMethod
from views.main_window import MainWindow


class MainController:
    def __init__(self, transcription: Transcription, view: MainWindow):
        self.view = view
        self.transcription = transcription
        self._is_mic_recording = False

        self._whisperx_handler = WhisperXHandler()

    # PUBLIC METHODS

    def select_file(self):
        """
        Prompts a file explorer to determine the audio/video file path to transcribe.
        """
        file_path = filedialog.askopenfilename(
            initialdir="/",
            title="Select a file",
            filetypes=[
                ("All supported files", c.SUPPORTED_FILE_EXTENSIONS),
                ("Audio files", c.AUDIO_FILE_EXTENSIONS),
                ("Video files", c.VIDEO_FILE_EXTENSIONS),
            ],
        )

        if file_path:
            self.view.on_select_path_success(file_path)

    def select_directory(self):
        """
        Prompts a file explorer to determine the folder path to transcribe.
        """
        dir_path = filedialog.askdirectory()

        if dir_path:
            self.view.on_select_path_success(dir_path)

    def prepare_for_transcription(self, transcription: Transcription):
        """
        Prepares to transcribe based on the specified source type of the transcription
        object provided. It sets up the necessary configurations and starts the
        transcription process.

        :param transcription: An instance of the Transcription class containing
                              information about the audio to transcribe.
        :type transcription: Transcription
        """
        try:
            if not transcription.output_file_types:
                raise ValueError(
                    "No output file types selected. Please select at least one."
                )

            self.transcription = transcription

            if transcription.audio_source == AudioSource.FILE:
                self._prepare_for_file_transcription(transcription.audio_source_path)
            elif transcription.audio_source == AudioSource.MIC:
                threading.Thread(target=self._start_recording_from_mic).start()
                return
            elif transcription.audio_source == AudioSource.YOUTUBE:
                self._prepare_for_youtube_video_transcription()

            threading.Thread(
                target=lambda loop: loop.run_until_complete(
                    self._handle_transcription_process()
                ),
                args=(asyncio.new_event_loop(),),
            ).start()

        except Exception as e:
            self._handle_exception(e)

    def stop_recording_from_mic(self):
        self._is_mic_recording = False
        self.view.on_stop_recording_from_mic()

    def save_transcription(
        self, file_path: Path, should_autosave: bool, should_overwrite: bool
    ):
        """
        Saves the transcription to a text file and optionally generate subtitles.

        :param file_path: The path where the text file will be saved.
        :type file_path: Path
        :param should_autosave: Indicates whether the text file should be saved
                                automatically without showing a file dialog.
        :type should_autosave: bool
        :param should_overwrite: Indicates whether existing files should be overwritten
                                 if they exist.
        :type should_overwrite: bool
        """
        save_file_path = self._get_save_path(file_path, should_autosave)

        if not save_file_path:
            return

        if self.transcription.method == TranscriptionMethod.WHISPERX:
            self._whisperx_handler.save_transcription(
                file_path=Path(save_file_path),
                output_file_types=self.transcription.output_file_types,
                should_overwrite=should_overwrite,
            )
        elif self.transcription.method in [
            TranscriptionMethod.GOOGLE_API,
            TranscriptionMethod.WHISPER_API,
        ]:
            if should_overwrite or not os.path.exists(save_file_path):
                with open(save_file_path, "w", encoding="utf-8") as file:
                    file.write(self.transcription.text)
        else:
            exception = ValueError(
                "Incorrect transcription method. Please check the `config.ini` file."
            )
            self._handle_exception(exception)

    # PRIVATE METHODS

    def _prepare_for_file_transcription(self, file_path: Path):
        """
        Prepares the system for transcription from a file by verifying if the file
        exists and is supported for transcription. If the file is valid, it updates the
        source path in the transcription object; otherwise, it raises a ValueError.

        :param file_path: The path to the file for transcription.
        :raises ValueError: If the provided file path does not exist or is not supported
                            for transcription.
        """
        is_file_supported = file_path.suffix in c.SUPPORTED_FILE_EXTENSIONS
        if file_path.is_file() and is_file_supported:
            self.transcription.audio_source_path = file_path
        else:
            raise ValueError("Error: No valid file selected.")

    def _prepare_for_youtube_video_transcription(self):
        """
        Prepares the system for transcription from a YouTube video by downloading
        the audio from the video using the YouTubeHandler. It updates the source path
        in the transcription object with the downloaded audio file path. If the source
        path is not obtained successfully, it raises a ValueError.

        :raises ValueError: If the YouTube video URL is incorrect or the audio download fails.
        """
        self.transcription.audio_source_path = YouTubeHandler.download_audio_from_video(
            self.transcription.youtube_url
        )

        if not self.transcription.audio_source_path:
            raise ValueError("Please make sure the URL you entered is correct.")

    async def _handle_transcription_process(self):
        """
        Handles the transcription process based on the type of source specified in the
        transcription object. It asynchronously transcribes either a single file or
        multiple files in a directory. Upon completion or error, it notifies the view
        that the transcription process has been processed.
        """
        try:
            if self.transcription.audio_source == AudioSource.DIRECTORY:
                await self._transcribe_directory(self.transcription.audio_source_path)
            else:
                await self._transcribe_file(self.transcription.audio_source_path)
        except Exception as e:
            self._handle_exception(e)
        finally:
            self.view.on_processed_transcription()

    async def _transcribe_directory(self, dir_path: Path):
        """
        Transcribes supported files from a directory.

        :param dir_path: The directory path selected by the user.
        :type dir_path: Path

        :raises ValueError: If the directory path is invalid or doesn't contain valid
                            file types to transcribe.
        """
        if files := self._get_files_to_transcribe_from_directory():
            # Create a list of coroutines for each file transcription task
            tasks = [self._transcribe_file(file) for file in files]

            # Run all tasks concurrently
            await asyncio.gather(*tasks)

            self.view.display_text(f"Files from '{dir_path}' successfully transcribed.")
        else:
            raise ValueError(
                "Error: The directory path is invalid or doesn't contain valid "
                "file types to transcribe. Please choose another one."
            )

    async def _transcribe_file(self, file_path: Path):
        """
        Transcribes audio from a file based on the specified transcription method.
        It updates the transcription object with the transcribed text. If the source
        type is microphone or YouTube, it removes the temporary file after
        transcription. It also displays the transcribed text and saves it if autosave
        is enabled.

        :param file_path: The path of the audio file for transcription.
        """
        transcription = self.transcription
        transcription.audio_source_path = file_path

        if self.transcription.method == TranscriptionMethod.GOOGLE_API:
            self.transcription.text = AudioHandler.get_transcription(
                transcription=transcription,
                transcription_func=GoogleApiHandler.transcribe,
                should_split_on_silence=True,
            )
        elif self.transcription.method == TranscriptionMethod.WHISPER_API:
            self.transcription.text = AudioHandler.get_transcription(
                transcription=transcription,
                transcription_func=OpenAiApiHandler.transcribe,
                should_split_on_silence=False,
            )
        elif self.transcription.method == TranscriptionMethod.WHISPERX:
            self.transcription.text = await self._whisperx_handler.transcribe_file(
                transcription
            )

        if self.transcription.audio_source in [AudioSource.MIC, AudioSource.YOUTUBE]:
            self.transcription.audio_source_path.unlink()  # Remove tmp file

        if self.transcription.audio_source != AudioSource.DIRECTORY:
            self.view.display_text(self.transcription.text)

        if self.transcription.should_autosave:
            self.save_transcription(
                file_path,
                should_autosave=True,
                should_overwrite=self.transcription.should_overwrite,
            )

    def _get_files_to_transcribe_from_directory(self) -> list[Path]:
        """
        Retrieves a list of files to transcribe from a directory.

        :return: A list of file paths to transcribe in the directory.
        :rtype: list[Path]
        """
        matching_files = []

        for root, _, files in os.walk(self.transcription.audio_source_path):
            for file in files:
                if any(file.endswith(ext) for ext in c.SUPPORTED_FILE_EXTENSIONS):
                    file_path = Path(root) / file
                    if not self.transcription.should_overwrite and any(
                        (file_path.with_suffix(f".{ext}")).exists()
                        for ext in self.transcription.output_file_types
                    ):
                        print(f"{file_path} already has transcription(s). Skipping.")
                        continue

                    matching_files.append(file_path)
                    print(f"{file_path} added to the list of files to transcribe!")

        return matching_files

    def _start_recording_from_mic(self):
        """
        Records the audio from the microphone and starts the transcription process when
        finished recording.

        This function continuously records audio from the microphone until stopped.
        The recorded audio is then saved to a WAV file and used for transcription.
        """
        self._is_mic_recording = True
        audio_data = []

        try:
            r = sr.Recognizer()

            with sr.Microphone() as mic:
                while self._is_mic_recording:
                    audio_chunk = r.listen(mic, timeout=5)
                    audio_data.append(audio_chunk)

            if audio_data:
                filename = "mic-output.wav"
                au.save_audio_data(audio_data, filename=filename)
                self.transcription.audio_source_path = Path(filename)

                threading.Thread(
                    target=lambda loop: loop.run_until_complete(
                        self._handle_transcription_process()
                    ),
                    args=(asyncio.new_event_loop(),),
                ).start()
            else:
                e = ValueError("No audio detected")
                self._handle_exception(e)

        except Exception as e:
            self.stop_recording_from_mic()
            self._handle_exception(e)

    def _get_save_path(self, file_path: Path, should_autosave: bool) -> Path:
        """
        Determines the save path for a file, either automatically or via a save dialog.

        :param file_path: The initial file path.
        :type file_path: Path

        :param should_autosave: If True, saves the file automatically with a generated
                                name.
        :type should_autosave: bool

        :return: The path where the file should be saved.
        :rtype: Path
        """
        file_dir = file_path.parent
        file_type = ""
        initial_file_name = file_path.stem
        is_one_output_file_type = len(self.transcription.output_file_types) == 1

        if is_one_output_file_type:
            file_type = c.FORMATS_TO_FILE_TYPES.get(
                self.transcription.output_file_types[0]
            )
            initial_file_name += f".{file_type}"

        if should_autosave:
            return file_dir / initial_file_name
        else:
            default_extension = (
                f".{file_type}" if self.transcription.output_file_types else None
            )

            file_types = [("All Files", "*.*")]

            if is_one_output_file_type:
                file_types.insert(0, (f"{file_type.upper()} file", f"*.{file_type}"))

            return Path(
                filedialog.asksaveasfilename(
                    initialdir=file_dir,
                    initialfile=initial_file_name,
                    title="Save as",
                    defaultextension=default_extension,
                    filetypes=file_types,
                )
            )

    def _handle_exception(self, e: Exception):
        """
        Prints the traceback of the exception, notifies the view that the transcription
        process has been processed, and displays a representation of the exception.

        :param e: The exception that occurred during the transcription process.
        :type e: Exception
        """
        print(traceback.format_exc())
        self.view.on_processed_transcription()
        self.view.display_text(repr(e))
