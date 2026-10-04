import time
from collections.abc import Callable
from pathlib import Path

import speech_recognition as sr

import utils.audio_utils as au
from handlers.live_transcriber import LiveTranscriber
from models.transcription import Transcription

# How often the duration and the level of the recording are reported
PROGRESS_INTERVAL_SECONDS = 0.1

# Receives the duration of the recording in seconds and the level of the audio
RecordingProgressCallback = Callable[[float, float], None]


class MicRecorder:
    """
    Records the microphone until it's stopped. If the transcription has a live
    model, the recording is also transcribed while it's recorded.
    """

    def __init__(
        self,
        live_transcriber: LiveTranscriber,
        on_progress: RecordingProgressCallback,
    ) -> None:
        self._live_transcriber = live_transcriber
        self._on_progress = on_progress
        self._is_recording = False

    def stop(self) -> None:
        """Stops the recording in progress, which `record` saves right after."""
        self._is_recording = False

    def record(self, transcription: Transcription, output_path: Path) -> Path:
        """
        Records from the microphone of the transcription until `stop` is called.

        :param output_path: Where the recording is saved, as a WAV file.
        :raises ValueError: If no audio was recorded.
        :return: The path of the recording.
        """
        self._is_recording = True

        try:
            audio_data = self._record_until_stopped(transcription)
        finally:
            self._is_recording = False
            # The whole recording is transcribed now, which replaces the draft
            self._live_transcriber.stop()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        au.save_audio_data(audio_data, output_path)

        return output_path

    def _record_until_stopped(self, transcription: Transcription) -> sr.AudioData:
        frames = []
        live_model_size = transcription.live_model_size

        with au.Microphone(transcription.mic_device_index) as mic:
            start_time = last_report_time = time.monotonic()

            if live_model_size:
                self._live_transcriber.start(
                    live_model_size,
                    mic.sample_rate,
                    language=transcription.language_code,
                    should_translate=transcription.should_translate,
                    prompt=transcription.whisper_prompt,
                )

            while self._is_recording:
                chunk = mic.read()
                frames.append(chunk)

                if live_model_size:
                    self._live_transcriber.feed(chunk)

                now = time.monotonic()
                if now - last_report_time >= PROGRESS_INTERVAL_SECONDS:
                    last_report_time = now
                    self._on_progress(
                        now - start_time, au.get_audio_level(chunk, mic.SAMPLE_WIDTH)
                    )

            return sr.AudioData(b"".join(frames), mic.sample_rate, mic.SAMPLE_WIDTH)
