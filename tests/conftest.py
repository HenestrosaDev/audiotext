import shutil
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError
from pydub import AudioSegment
from pydub.generators import Sine

import utils.env_keys as env_keys
import utils.notifications as notifications
from models.summary import TranscriptSummary
from models.transcript_segment import TranscriptSegment
from models.translation import TranscriptTranslation
from utils.config_manager import ConfigManager

PROJECT_ROOT = Path(__file__).parent.parent


class MemoryKeyring(KeyringBackend):
    """Credential store kept in memory, so tests never touch the real one."""

    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.passwords: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if self.passwords.pop((service, username), None) is None:
            raise PasswordDeleteError(username)


@pytest.fixture(autouse=True)
def memory_keyring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[MemoryKeyring]:
    """
    Replaces the credential store and the `.env` files of the API keys, and
    removes the keys of the environment, so tests never read the real keys.
    """
    previous_backend = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    env_keys.clear_cache()

    monkeypatch.setattr(env_keys, "ENV_FILE_PATH", tmp_path / "keys" / ".env")
    monkeypatch.setattr(env_keys, "LEGACY_ENV_FILE_PATH", tmp_path / "legacy.env")
    for env_key in env_keys.EnvKeys:
        monkeypatch.delenv(env_key.value, raising=False)

    yield backend

    keyring.set_keyring(previous_backend)
    env_keys.clear_cache()


@pytest.fixture
def user_config_file(tmp_path: Path) -> Path:
    """The file with the settings changed by the user. It doesn't exist initially."""
    return tmp_path / "user" / "config.ini"


@pytest.fixture(autouse=True)
def config_file(
    tmp_path: Path, user_config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """
    Points the ConfigManager to a copy of the default settings and to an empty
    user configuration, so tests never modify the real ones.
    """
    path = tmp_path / "config.ini"
    shutil.copy(PROJECT_ROOT / "config.ini", path)
    monkeypatch.setattr(ConfigManager, "defaults_file_path", path)
    monkeypatch.setattr(ConfigManager, "user_file_path", user_config_file)
    # The formats of the dates are read again from these settings
    monkeypatch.setattr("views.history.formatting._formats", None)

    return path


@pytest.fixture(autouse=True)
def sent_notifications(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Records the notifications instead of showing them on the desktop."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        notifications, "notify", lambda title, message: sent.append((title, message))
    )
    return sent


class FakeView:
    """Records the calls the controller makes to the view."""

    def __init__(self) -> None:
        self.displayed_texts: list[str] = []
        self.processed_statuses: list[str | None] = []
        self.progress_updates: list[tuple[str, float | None]] = []
        self.statuses: list[str] = []
        self.errors: list[str] = []
        self.recording_updates: list[tuple[float, float]] = []
        self.saved_folders: list[Path] = []
        self.stop_recording_calls = 0
        self.live_texts: list[str] = []
        self.live_statuses: list[str] = []
        self.queued_files: list[list[Path]] = []
        self.started_files: list[Path] = []
        self.transcribed_files: list[tuple[Path, str, list[Any], str | None]] = []
        self.failed_files: list[tuple[Path, str]] = []
        self.downloaded_media: list[Path] = []

    def run_on_ui_thread(self, callback: Callable[..., Any], *args: Any) -> None:
        callback(*args)

    def display_text(self, text: str) -> None:
        self.displayed_texts.append(text)

    def on_processed_transcription(self, status: str | None = None) -> None:
        self.processed_statuses.append(status)

    def show_error(self, message: str) -> None:
        self.errors.append(message)

    def on_recording_progress(self, elapsed_seconds: float, level: float) -> None:
        self.recording_updates.append((elapsed_seconds, level))

    def on_transcription_saved(self, folder: Path) -> None:
        self.saved_folders.append(folder)

    def on_transcription_progress(self, message: str, fraction: float | None) -> None:
        self.progress_updates.append((message, fraction))

    def show_status(self, message: str) -> None:
        self.statuses.append(message)

    def on_stop_recording_from_mic(self) -> None:
        self.stop_recording_calls += 1

    def on_live_text(self, text: str) -> None:
        self.live_texts.append(text)

    def on_live_status(self, message: str) -> None:
        self.live_statuses.append(message)

    def on_files_queued(self, files: list[Path]) -> None:
        self.queued_files.append(files)

    def on_file_started(self, file_path: Path) -> None:
        self.started_files.append(file_path)

    def on_file_transcribed(
        self, file_path: Path, text: str, segments: list[Any], language: str | None
    ) -> None:
        self.transcribed_files.append((file_path, text, segments, language))

    def on_file_failed(self, file_path: Path, error: str) -> None:
        self.failed_files.append((file_path, error))

    def on_media_downloaded(self, file_path: Path) -> None:
        self.downloaded_media.append(file_path)


@pytest.fixture
def fake_view() -> FakeView:
    return FakeView()


class FakeSummarizer:
    """Returns its summary, or raises its error, and records what it summarizes."""

    def __init__(self) -> None:
        self.summary = TranscriptSummary("A short talk.", (), (), "model", "")
        self.error: Exception | None = None
        self.texts: list[str] = []
        # Set when it's called, since it's called from a background thread
        self.has_summarized = threading.Event()

    def summarize(
        self, text: str, segments: list[TranscriptSegment]
    ) -> TranscriptSummary:
        self.texts.append(text)
        self.has_summarized.set()
        if self.error:
            raise self.error
        return self.summary


class FakeTranslator:
    """
    Returns its translation, or raises its error, and records the language and
    the provider of each request.
    """

    def __init__(self) -> None:
        self.translation = TranscriptTranslation("es", "Hola", (), "deepl")
        self.error: Exception | None = None
        self.requests: list[tuple[str, str]] = []

    def translate(
        self,
        text: str,
        segments: list[TranscriptSegment],
        is_text_edited: bool,
        language: str,
        provider: str,
        model: str,
    ) -> TranscriptTranslation:
        self.requests.append((language, provider))
        if self.error:
            raise self.error
        return self.translation


def make_tone(duration_ms: int = 600) -> AudioSegment:
    return Sine(440).to_audio_segment(duration=duration_ms).set_channels(1)


@pytest.fixture
def speech_with_pauses() -> AudioSegment:
    """Three tones separated by one-second silences."""
    silence = AudioSegment.silent(duration=1000, frame_rate=44100)
    return make_tone() + silence + make_tone() + silence + make_tone()
