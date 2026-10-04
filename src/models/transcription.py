from dataclasses import dataclass, field
from pathlib import Path

from models.transcript_segment import TranscriptSegment
from utils.enums import AudioSource, TranscriptionMethod


@dataclass
class Transcription:
    """
    What to transcribe and how. The controller doesn't modify it: each file is
    transcribed with a copy that points to it.
    """

    language_code: str | None = None
    audio_source: AudioSource | None = None
    audio_source_path: Path = Path("/")
    method: TranscriptionMethod | None = None
    output_file_types: list[str] = field(default_factory=list)
    should_translate: bool = False
    should_diarize: bool = False
    # None lets the diarization model detect the number of speakers
    num_speakers: int | None = None
    # Aligns the transcription to get the timings of each word (WhisperX)
    should_align_words: bool = False
    # Filters the audio to keep the voices, reducing music and background noise
    should_isolate_speech: bool = False
    should_autosave: bool = False
    should_overwrite: bool = False
    # URL of the audio or video to download (YouTube or a direct link to a file)
    url: str | None = None
    # Folder where the autosaved files are stored. If None, they're stored next to
    # the transcribed file
    output_dir: Path | None = None
    # Where the downloaded (URL) or recorded (microphone) audio is kept, so it can
    # be played later. If None, it's a temporary file removed after transcribing
    media_path: Path | None = None
    # Index of the input device to record from. If None, the default one is used
    mic_device_index: int | None = None
    # Model that transcribes the microphone while recording, to show the text as
    # it's said. If None, the text is only shown when the recording stops
    live_model_size: str | None = None
    # Response format of the Whisper API. If None, the configured one is used
    api_response_format: str | None = None
    # Model of the OpenAI API (e.g. "whisper-1"). If None, the configured one is used
    api_model: str | None = None
    # What the audio is about (e.g. its topic or setting)
    prompt: str = ""
    # Names, terms or acronyms said in the audio, so they're spelled right
    keywords: list[str] = field(default_factory=list)

    @property
    def whisper_prompt(self) -> str:
        """
        Whisper has no keywords, so they're written in the prompt before the
        context, which makes it spell them like that.
        """
        keywords = f"{', '.join(self.keywords)}." if self.keywords else ""
        return " ".join(part for part in (keywords, self.prompt.strip()) if part)


@dataclass(frozen=True)
class TranscriptionResult:
    """The result of transcribing a file."""

    text: str
    # The timestamps of the text, if the transcription method returns them
    segments: list[TranscriptSegment] = field(default_factory=list)
    # The language of the text (e.g. "en"), if known
    language: str | None = None
    # The duration of the audio in seconds, if known
    duration: float = 0.0


def split_keywords(text: str) -> list[str]:
    """Splits the keywords typed by the user, separated by commas."""
    return [keyword.strip() for keyword in text.split(",") if keyword.strip()]
