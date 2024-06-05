import asyncio
import os
import threading
import traceback
from pathlib import Path
from tkinter import filedialog

import speech_recognition as sr
import utils.audio_utils as au
from handlers.google_api_handler import GoogleApiHandler
from handlers.whisperx_handler import WhisperXHandler
from handlers.youtube_handler import YouTubeHandler
from models.transcription import Transcription
from utils import constants as c
from utils.enums import AudioSource, TranscriptionMethod
from utils.i18n import _


class MainController:
    def __init__(self, transcription: Transcription, view):
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
            title=_("Select a file"),
            filetypes=[
                (_("All supported files"), c.SUPPORTED_FILE_EXTENSIONS),
                (_("Audio files"), c.AUDIO_FILE_EXTENSIONS),
                (_("Video files"), c.VIDEO_FILE_EXTENSIONS),
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
        self.transcription = transcription

        try:
            self.view.on_processing_transcription()

            if transcription.source_type == AudioSource.FILE:
                self._prepare_for_file_transcription(transcription.source_path)
            elif transcription.source_type == AudioSource.DIRECTORY:
                self.transcription.source_path = transcription.source_path
            elif transcription.source_type == AudioSource.MIC:
                threading.Thread(target=self._start_recording_from_mic).start()
                return
            elif transcription.source_type == AudioSource.YOUTUBE:
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

    def save_transcription(
        self, file_path: Path, should_autosave: bool, should_overwrite: bool
    ):
        """
        Save the transcription to a text file and optionally generate the subtitles.

        :param file_path: The path where the text file will be saved.
        :type file_path: Path
        :param should_autosave: Indicates whether the text file should be saved
                                automatically without showing a file dialog.
        :type should_autosave: bool
        :param should_overwrite: Indicates whether existing files should be overwritten
                                 if they exist.
        :type should_overwrite: bool
        """
        file_dir = file_path.parent
        txt_file_name = f"{file_path.stem}.txt"

        if should_autosave:
            txt_file_path = file_path.parent / txt_file_name
        else:
            txt_file_path = filedialog.asksaveasfilename(
                initialdir=file_dir,
                initialfile=txt_file_name,
                title=_("Save as"),
                defaultextension=".txt",
                filetypes=[(_("Text file"), "*.txt"), (_("All Files"), "*.*")],
            )

        if not txt_file_path:
            return

        if should_overwrite or not os.path.exists(txt_file_path):
            with open(txt_file_path, "w", encoding="utf-8") as txt_file:
                txt_file.write(self.transcription.text)

        if self.transcription.should_subtitle:
            self._whisperx_handler.generate_subtitles(
                Path(txt_file_path), should_overwrite
            )

    # PRIVATE METHODS

    def _prepare_for_file_transcription(self, file_path: Path):
        is_file_supported = file_path.suffix in c.SUPPORTED_FILE_EXTENSIONS
        if file_path.is_file() and is_file_supported:
            self.transcription.source_path = file_path
        else:
            raise ValueError("Error: No valid file selected.")

    def _prepare_for_youtube_video_transcription(self):
        self.transcription.source_path = YouTubeHandler.download_audio_from_video(
            self.transcription.youtube_url
        )

        if not self.transcription.source_path:
            raise ValueError("Please make sure the URL you entered is correct.")

    async def _handle_transcription_process(self):
        try:
            path = self.transcription.source_path

            if self.transcription.source_type == AudioSource.DIRECTORY:
                await self._transcribe_directory(path)
            else:
                await self._transcribe_file(path)

        except Exception as e:
            self._handle_exception(e)

        finally:
            is_transcription_empty = not self.transcription.text
            self.view.on_processed_transcription(success=is_transcription_empty)

    async def _transcribe_directory(self, dir_path: Path):
        """
        Transcribe supported files from a directory.

        :param dir_path: The path to the directory containing the audio files.
        :type dir_path: Path
        :raises ValueError: If the directory path is invalid or doesn't contain valid
                            file types to transcribe.
        """
        if files := self._get_transcribable_files_from_dir(dir_path):
            # Create a list of coroutines for each file transcription task
            tasks = [self._transcribe_file(file) for file in files]

            # Run all tasks concurrently
            await asyncio.gather(*tasks)

            self.view.display_text(
                f"Files from '{dir_path}' successfully " f"transcribed."
            )
        else:
            raise ValueError(
                "Error: The directory path is invalid or doesn't contain valid "
                "file types to transcribe. Please choose another one."
            )

    async def _transcribe_file(self, file_path: Path):
        """
        Transcribe audio from a file using the specified transcription method.

        :param file_path: The path to the audio file to transcribe.
        :type file_path: Path
        """
        transcription = self.transcription
        transcription.source_path = file_path

        if self.transcription.method == TranscriptionMethod.WHISPERX.value:
            self.transcription.text = await self._whisperx_handler.transcribe_file(
                transcription
            )
        elif self.transcription.method == TranscriptionMethod.GOOGLE_API.value:
            self.transcription.text = await GoogleApiHandler.transcribe_file(
                transcription
            )

        if self.transcription.source_type in [AudioSource.MIC, AudioSource.YOUTUBE]:
            self.transcription.source_path.unlink()  # Remove tmp file

        if self.transcription.source_type != AudioSource.DIRECTORY:
            self.view.display_text(self.transcription.text)

        if self.transcription.should_autosave:
            self.save_transcription(
                file_path,
                should_autosave=True,
                should_overwrite=self.transcription.should_overwrite,
            )

    @staticmethod
    def _get_transcribable_files_from_dir(dir_path: Path) -> list[Path]:
        """
        Retrieve a list of transcribable files from a directory.

        :param dir_path: The path to the directory containing the files.
        :type dir_path: Path
        :return: A list of paths to transcribable files found in the directory.
        :rtype: list[Path]
        """
        matching_files = []
        for root, _, files in os.walk(dir_path):
            for file in files:
                if any(file.endswith(ext) for ext in c.SUPPORTED_FILE_EXTENSIONS):
                    matching_files.append(Path(root) / file)

        return matching_files

    def _start_recording_from_mic(self):
        """
        Record audio from the microphone and initiate transcription process.

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
                self.transcription.source_path = Path(filename)

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
            self.view.stop_recording_from_mic()
            self._handle_exception(e)

    def _handle_exception(self, e: Exception):
        print(traceback.format_exc())
        self.view.on_processed_transcription(success=False)
        self.view.display_text(repr(e))
