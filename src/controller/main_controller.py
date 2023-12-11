import asyncio
import os
import shutil
import threading
import traceback
from pathlib import Path
from tkinter import filedialog

import speech_recognition as sr
import torch
import utils.audio_utils as au
import utils.google_api_key_helper as google_api_key_helper
import whisperx
from model.transcription import Transcription
from moviepy.video.io.VideoFileClip import VideoFileClip
from pydub import AudioSegment
from pydub.silence import split_on_silence
from utils import constants as c
from utils.enums import AudioSource, TranscriptionMethod
from utils.i18n import _
from utils.path_helper import ROOT_PATH


class MainController:
    def __init__(self, transcription: Transcription, view):
        self.view = view
        self.transcription = transcription
        self._is_mic_recording = False
        self._whisperx_result = None

    # PUBLIC METHODS

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

        if filepath:
            self.transcription.file_path_to_transcribe = Path(filepath)
            self.view.handle_select_file_success(filepath)

    def prepare_for_transcription(
        self,
        source: str,
        language_code: str,
        transcription_method: int,
        should_translate: bool = False,
        should_subtitle: bool = False,
    ):
        """
        Prepares the transcription process based on provided parameters.

        :param source: The source of the audio, either from a file or the microphone.
        :type source: str
        :param language_code: Language code of the audio to transcribe.
        :type language_code: str
        :param transcription_method: Either WhisperX or Google API.
        :type transcription_method: int
        :param should_translate: If True, translates from X language to English.
                                 Only for WhisperX.
        :type should_translate: bool
        :param should_subtitle: If True, generates .srt and .vtt files. Only for WhisperX.
        :type should_subtitle: bool

        :raises: IndexError if the selected language code is not valid.
        """
        if not self._is_file_valid(source):
            self.view.display_text(
                _(
                    "Error: No audio file selected, please select one before "
                    "generating text."
                )
            )
            return

        self.transcription.source = source
        self.transcription.language_code = language_code
        self.transcription.method = transcription_method
        self.transcription.should_translate = should_translate
        self.transcription.should_subtitle = should_subtitle

        try:
            if source == AudioSource.FILE:
                threading.Thread(
                    target=lambda loop: loop.run_until_complete(
                        self.handle_transcription_process()
                    ),
                    args=(asyncio.new_event_loop(),),
                ).start()
            elif source == AudioSource.MIC:
                threading.Thread(target=self._record_from_mic).start()

        except Exception:
            self.view.display_text(
                _("Error generating the file transcription. Please try again.")
            )

    async def handle_transcription_process(self):
        self.view.handle_processing_transcription()

        # Get transcription
        if self.transcription.method == TranscriptionMethod.WHISPERX.value:
            await self._transcribe_using_whisperx()
        elif self.transcription.method == TranscriptionMethod.GOOGLE_API.value:
            await self._transcribe_using_google_api()

        if self.transcription.source == AudioSource.MIC:
            self.transcription.file_path_to_transcribe.unlink()  # Remove tmp file

        is_transcription_empty = not self.transcription.text
        self.view.handle_transcription_process_finish(is_transcription_empty)

    def stop_recording_from_mic(self):
        self._is_mic_recording = False

    def save_transcription(self):
        """
        Prompts a file explorer to determine the file to save the
        generated transcription.
        """
        file_path = Path(self.transcription.file_path_to_transcribe)

        file = filedialog.asksaveasfile(
            mode="w",
            initialdir=file_path.parent,
            initialfile=f"{file_path.stem}.txt",
            title=_("Save as"),
            defaultextension=".txt",
            filetypes=[(_("Text file"), "*.txt"), (_("All Files"), "*.*")],
        )

        if file:
            file.write(self.transcription.text)
            file.close()

            if self.transcription.should_subtitle:
                self._generate_subtitles(Path(file.name))

    # PRIVATE METHODS

    def _is_file_valid(self, source):
        if source == c.AudioSource.MIC:
            return True

        filepath = self.transcription.file_path_to_transcribe
        is_audio = filepath.suffix in c.AUDIO_FILE_EXTENSIONS
        is_video = filepath.suffix in c.VIDEO_FILE_EXTENSIONS

        return filepath.is_file() and (is_audio or is_video)

    async def _transcribe_using_whisperx(self, batch_size=16):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if "cuda" else "int8"
        task = "translate" if self.transcription.should_translate else "transcribe"

        try:
            model = whisperx.load_model(
                "large-v3",
                device,
                compute_type=compute_type,
                task=task,
                language=self.transcription.language_code,
            )

            audio_path = str(self.transcription.file_path_to_transcribe)
            audio = whisperx.load_audio(audio_path)
            self._whisperx_result = model.transcribe(audio, batch_size=batch_size)

            text_combined = " ".join(
                segment["text"].strip() for segment in self._whisperx_result["segments"]
            )

            # Align output if should subtitle
            if self.transcription.should_subtitle:
                model_aligned, metadata = whisperx.load_align_model(
                    language_code=self.transcription.language_code, device=device
                )
                self._whisperx_result = whisperx.align(
                    self._whisperx_result["segments"],
                    model_aligned,
                    metadata,
                    audio,
                    device,
                    return_char_alignments=False,
                )

            self.transcription.text = text_combined
            self.view.display_text(self.transcription.text)

        except Exception:
            self.view.display_text(traceback.format_exc())

    async def _transcribe_using_google_api(self):
        """
        Splits a large audio file into chunks
        and applies speech recognition on each one.
        """
        file_path = self.transcription.file_path_to_transcribe

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
                        chunk_text = r.recognize_google(
                            audio_listened,
                            language=self.transcription.language_code,
                            key=google_api_key_helper.get_google_api_key(),
                        )

                        chunk_text = f"{chunk_text.capitalize()}. "
                        transcription_text += chunk_text
                        print(f"chunk text: {chunk_text}")
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

    def _record_from_mic(self):
        self._is_mic_recording = True
        audio_data = []
        r = sr.Recognizer()

        with sr.Microphone() as mic:
            while self._is_mic_recording:
                audio_chunk = r.listen(mic)
                audio_data.append(audio_chunk)

        if audio_data:
            self.view.toggle_progress_bar_visibility(should_show=True)

            filename = "mic-output.wav"
            au.save_audio_data(audio_data, filename=filename)
            self.transcription.file_path_to_transcribe = Path(filename)

            threading.Thread(
                target=lambda loop: loop.run_until_complete(
                    self.handle_transcription_process()
                ),
                args=(asyncio.new_event_loop(),),
            ).start()

    def _generate_subtitles(self, file_path):
        output_formats = ["srt", "vtt"]
        output_dir = file_path.parent

        for output_format in output_formats:
            writer = whisperx.transcribe.get_writer(output_format, output_dir)
            writer_args = {
                "highlight_words": False,
                "max_line_count": 2,
                "max_line_width": 42,
            }

            # https://github.com/m-bain/whisperX/issues/455#issuecomment-1707547704
            self._whisperx_result["language"] = "en"

            writer(self._whisperx_result, file_path, writer_args)
