"""
Builds the interface and goes through its views, as a user would, failing if any
callback of the interface raises an error. They're skipped without a display.
"""

import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import keyring
import pytest

import utils.constants as c
import utils.env_keys as env_keys
import utils.update_checker as update_checker
from models.config.config_system import ConfigSystem
from models.history import EntryStatus, HistoryEntry
from models.summary import Chapter, TranscriptSummary
from models.transcript_segment import TranscriptSegment, TranscriptWord
from models.transcription_settings import TranscriptionSettings
from tests.conftest import MemoryKeyring, make_tone
from utils.config_manager import ConfigManager
from utils.enums import AudioSource
from views.main_window.transcription_jobs import Job
from views.settings.cards.context_card import ContextCard
from views.settings.cards.engine_card import EngineCard
from views.settings.cards.output_card import OutputCard
from views.transcript.edit_dialogs import Replacement


def has_display() -> bool:
    # Creating a window to find out would prevent creating the one of the app
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


pytestmark = pytest.mark.skipif(not has_display(), reason="No display available")

SEGMENTS = [
    TranscriptSegment(
        0.0,
        1.0,
        "Hello wisper",
        "SPEAKER_00",
        (TranscriptWord(0.0, 0.5, "Hello"), TranscriptWord(0.5, 1.0, "wisper")),
    ),
    TranscriptSegment(1.5, 3.0, "Nice to meet you.", "SPEAKER_01"),
    TranscriptSegment(3.5, 5.0, "Bye wisper.", "SPEAKER_00"),
]


def translated(*texts: str) -> tuple[TranscriptSegment, ...]:
    """The segments of the transcription, translated with the texts."""
    return tuple(
        TranscriptSegment(segment.start, segment.end, text, segment.speaker)
        for segment, text in zip(SEGMENTS, texts, strict=True)
    )


TEXT = (
    "[SPEAKER_00]: Hello wisper\n\n[SPEAKER_01]: Nice to meet you.\n\n"
    "[SPEAKER_00]: Bye wisper."
)


class Ui:
    """The app, with helpers to let it process its events."""

    def __init__(self, app: Any, errors: list[BaseException]) -> None:
        self.app = app
        self.store = app._history_store
        self.errors = errors

    @property
    def window(self) -> Any:
        # It's rebuilt when the interface language changes
        return self.app._view

    def pump(self, seconds: float = 0.2) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.update()
            time.sleep(0.01)
        if self.errors:
            raise self.errors[0]

    def add(self, **kwargs: Any) -> HistoryEntry:
        values: dict[str, Any] = {
            "kind": AudioSource.FILE.value,
            "source": "/missing.mp3",
            "title": "Entry",
            "status": EntryStatus.DONE,
        }
        entry = self.store.add(HistoryEntry(**(values | kwargs)))
        self.window.sidebar.refresh()
        return entry


@pytest.fixture(scope="module")
def app(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    """
    The app, shared by the tests, since Tk can only create its window once per
    process. Its settings, history and keys are kept apart from the real ones.
    """
    config_dir = tmp_path_factory.mktemp("config")
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("AUDIOTEXT_CONFIG_DIR", str(config_dir))
        monkeypatch.setattr(ConfigManager, "user_file_path", config_dir / "config.ini")
        monkeypatch.setattr(env_keys, "ENV_FILE_PATH", config_dir / ".env")
        # The check for updates at startup doesn't reach GitHub
        monkeypatch.setattr(
            update_checker,
            "fetch_latest_release",
            lambda: update_checker.Release(c.APP_VERSION, update_checker.RELEASES_URL),
        )
        previous_keyring = keyring.get_keyring()
        keyring.set_keyring(MemoryKeyring())
        import app as app_module

        application = app_module.App()
        yield application
        application.destroy()
        keyring.set_keyring(previous_keyring)


@pytest.fixture
def ui(app: Any) -> Iterator[Ui]:
    errors: list[BaseException] = []
    app.report_callback_exception = lambda _type, value, _tb: errors.append(value)
    ui = Ui(app, errors)
    ui.pump()

    yield ui

    # Each test starts from the welcome page and an empty history
    ui.window.show_welcome()
    for entry in ui.store.top_level():
        ui.store.delete(entry.id)
    ui.window.sidebar.refresh()
    ui.pump()


@pytest.fixture
def audio_file(tmp_path: Path) -> Path:
    path = tmp_path / "talk.wav"
    make_tone(duration_ms=5000).export(path, format="wav")
    return path


def test_the_views_of_the_entries(ui: Ui, audio_file: Path) -> None:
    entries = [
        ui.add(title="Failed", status=EntryStatus.FAILED, error="Boom"),
        ui.add(title="Queued", status=EntryStatus.QUEUED),
        ui.add(title="Plain", kind=AudioSource.YOUTUBE.value, text="Only text."),
        ui.add(
            title="Talk",
            segments=SEGMENTS,
            text=TEXT,
            media_path=str(audio_file),
        ),
    ]
    folder = ui.add(
        title="Folder", kind=AudioSource.DIRECTORY.value, source=str(audio_file.parent)
    )
    ui.add(title="talk.wav", parent_id=folder.id, text="x")

    for entry in [*entries, folder]:
        ui.window.select_entry(entry.id)
        ui.pump()

    # Going through the list creates and destroys many views
    for _idx in range(10):
        for entry in entries[2:]:
            ui.window.select_entry(entry.id)
            ui.pump(0.12)


def test_the_transcript_can_be_searched_and_corrected(
    ui: Ui, audio_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import views.transcript.corrections as corrections

    entry = ui.add(segments=SEGMENTS, text=TEXT, media_path=str(audio_file))
    ui.window.select_entry(entry.id)
    ui.pump(0.8)
    view = ui.window._entry_view

    view._search_variable.set("wisper")
    ui.pump()
    assert view.text.match_status == (0, 2)

    for label in ("Plain text", "Summary", "Transcript"):
        view._on_mode_change(label)
        ui.pump()

    view.player.toggle_playback()
    ui.pump(0.4)
    view.player.toggle_playback()

    monkeypatch.setattr(
        corrections.ReplaceDialog,
        "get_result",
        lambda _self: Replacement("wisper", "Whisper", match_case=False),
    )
    view._find_and_replace()
    ui.pump()
    assert [s.text for s in entry.segments] == [
        "Hello Whisper",
        "Nice to meet you.",
        "Bye Whisper.",
    ]
    assert entry.segments[0].words[1].text == "Whisper"
    assert entry.text == TEXT.replace("wisper", "Whisper")

    monkeypatch.setattr(
        corrections.SpeakersDialog, "get_result", lambda _self: {"SPEAKER_00": "Ana"}
    )
    view._rename_speakers()
    ui.pump()
    assert entry.text.startswith("[Ana]: Hello Whisper")

    monkeypatch.setattr(corrections.TextDialog, "get_input", lambda _self: "Hi there")
    view._edit_segment(0)
    ui.pump()
    assert entry.segments[0].text == "Hi there"
    assert entry.text.startswith("[Ana]: Hi there")


def test_a_summary_is_generated_and_exported(
    ui: Ui, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import views.main_window.entry_actions as entry_actions
    import views.transcript.transcript_view as transcript_view

    summary = TranscriptSummary(
        "A short talk.", ("They greet",), (Chapter(0, "Greeting"),), "model", ""
    )
    monkeypatch.setattr(
        entry_actions.SummaryHandler,
        "summarize",
        staticmethod(lambda _text, _segments: summary),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    entry = ui.add(segments=SEGMENTS, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view

    view._on_mode_change("Summary")
    view._generate_summary()
    ui.pump(0.5)

    assert entry.summary == summary.to_dict()
    for file_type in ("md", "docx", "srt"):
        target = tmp_path / f"export.{file_type}"
        monkeypatch.setattr(
            transcript_view.filedialog,
            "asksaveasfilename",
            lambda target=target, **_kwargs: str(target),
        )
        view.export(file_type)
        assert target.exists()
    assert "A short talk." in (tmp_path / "export.md").read_text(encoding="utf-8")


def test_the_summary_without_a_key_leads_to_the_settings(ui: Ui) -> None:
    from views.settings.preferences_dialog import AI_TAB

    entry = ui.add(segments=SEGMENTS, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view

    view._on_mode_change("Summary")
    ui.pump()
    import customtkinter as ctk

    def buttons(widget: Any) -> list[str]:
        texts = [widget.cget("text")] if isinstance(widget, ctk.CTkButton) else []
        for child in widget.winfo_children():
            texts += buttons(child)
        return texts

    button_texts = buttons(view.summary_panel)
    assert "Set API key…" in button_texts
    assert "Settings" in button_texts

    view._delegate.show_preferences(AI_TAB)
    ui.pump()
    preferences = ui.window._preferences
    assert preferences.tabs.get() == "AI"
    preferences.destroy()
    ui.pump()


def test_a_translation_is_shown_next_to_the_transcript(
    ui: Ui, audio_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import views.main_window.entry_actions as entry_actions
    import views.transcript.transcript_view as transcript_view
    from models.translation import TranscriptTranslation
    from views.transcript.translation_panel import TranslationRequest

    translation = TranscriptTranslation(
        "es", "Hola\n\nAdiós", translated("Hola", "Encantado.", "Adiós."), "deepl"
    )
    requests: list[tuple[str, str]] = []

    def translate(
        _text: str,
        _segments: list[TranscriptSegment],
        _is_text_edited: bool,
        language: str,
        provider: str,
        _model: str,
    ) -> TranscriptTranslation:
        requests.append((language, provider))
        return translation

    monkeypatch.setattr(
        entry_actions.TranslationHandler, "translate", staticmethod(translate)
    )
    monkeypatch.setattr(
        transcript_view.TranslateDialog,
        "get_result",
        lambda _self: TranslationRequest("es", "deepl"),
    )
    entry = ui.add(segments=SEGMENTS, text=TEXT, media_path=str(audio_file))
    ui.window.select_entry(entry.id)
    ui.pump(0.5)
    view = ui.window._entry_view
    assert not view.translation_panel.winfo_ismapped()

    view._on_translate_button()
    ui.pump(0.5)

    assert requests == [("es", "deepl")]
    assert entry.translation == translation.to_dict()
    assert view.translation_panel.winfo_ismapped()
    assert "Encantado." in view.translation_panel.text.tbx_transcript.get("1.0", "end")
    assert ConfigManager.get_config_ai().translation_provider == "deepl"

    # It follows the mode and the playback of the transcript
    for label in ("Plain text", "Summary", "Transcript"):
        view._on_mode_change(label)
        ui.pump()
    view.player.toggle_playback()
    ui.pump(0.3)
    view.player.toggle_playback()
    view._on_translation_splitter_drag(view.frm_texts.winfo_rootx() + 100)
    view._reset_translation_ratio()

    view._set_translation_visible(False)
    ui.pump()
    assert not view.translation_panel.winfo_ismapped()

    view._delete_translation()
    ui.pump()
    assert entry.translation == {}


def test_a_translation_can_be_edited(ui: Ui, monkeypatch: pytest.MonkeyPatch) -> None:
    import views.transcript.transcript_view as transcript_view
    from models.translation import TranscriptTranslation

    translation = TranscriptTranslation(
        "es",
        "[SPEAKER_00]: Hola wisper\n\n[SPEAKER_01]: Encantado.\n\n"
        "[SPEAKER_00]: Adiós wisper.",
        translated("Hola wisper", "Encantado.", "Adiós wisper."),
        "deepl",
    )
    entry = ui.add(segments=SEGMENTS, text=TEXT, translation=translation.to_dict())
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view

    # A segment, whose change follows to the text
    monkeypatch.setattr(
        transcript_view.TextDialog, "get_input", lambda _self: "Hola Whisper"
    )
    view._edit_translation_segment(0)
    ui.pump()
    edited = TranscriptTranslation.from_dict(entry.translation)
    assert edited is not None
    assert edited.segments[0].text == "Hola Whisper"
    assert edited.text.startswith("[SPEAKER_00]: Hola Whisper")
    assert not edited.is_text_edited
    assert "Hola Whisper" in view.translation_panel.text.tbx_transcript.get(
        "1.0", "end"
    )

    # The plain text, which then keeps the changes of the user
    view._on_mode_change("Plain text")
    ui.pump()
    plain = view.translation_panel.text.tbx_plain
    plain.delete("1.0", "end")
    plain.insert("1.0", "Hola a todos")
    view.translation_panel.text._schedule_text_save()
    view.translation_panel.save_pending_text()
    edited = TranscriptTranslation.from_dict(entry.translation)
    assert edited is not None
    assert edited.text == "Hola a todos"
    assert edited.is_text_edited

    view._edit_translation_segment(1)
    ui.pump()
    edited = TranscriptTranslation.from_dict(entry.translation)
    assert edited is not None
    assert edited.segments[1].text == "Hola Whisper"
    assert edited.text == "Hola a todos"


def test_a_transcription_can_be_translated_from_scratch(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    import views.transcript.transcript_view as transcript_view
    from models.translation import TranscriptTranslation
    from views.transcript.translation_panel import TranslationRequest

    monkeypatch.setattr(
        transcript_view.TranslateDialog,
        "get_result",
        lambda _self: TranslationRequest("es", "manual"),
    )
    entry = ui.add(segments=SEGMENTS, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view

    view._on_translate_button()
    ui.pump()

    # Each segment keeps its timestamps, with an empty text to fill in
    translation = TranscriptTranslation.from_dict(entry.translation)
    assert translation is not None
    assert translation.provider == "manual"
    assert translation.segments == translated("", "", "")
    assert translation.text == ""
    panel = view.translation_panel
    assert view.translation_panel.winfo_ismapped()
    assert "Not translated yet" in panel.text.tbx_transcript.get("1.0", "end")
    assert "3" in panel.lbl_details.cget("text")
    # The transcript on its left already explains how to use the segments
    assert not panel.text.lbl_hint.cget("text")

    monkeypatch.setattr(transcript_view.TextDialog, "get_input", lambda _self: "Adiós")
    view._edit_translation_segment(2)
    ui.pump()
    translation = TranscriptTranslation.from_dict(entry.translation)
    assert translation is not None
    assert translation.segments == translated("", "", "Adiós")
    assert translation.text == "[SPEAKER_00]: Adiós"
    assert "2" in panel.lbl_details.cget("text")


def test_the_segments_of_a_translation_have_their_own_timing(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    import views.transcript.transcript_view as transcript_view
    from models.translation import TranscriptTranslation
    from views.transcript.edit_dialogs import Timing

    translation = TranscriptTranslation(
        "es",
        "",
        translated("Hola wisper", "Encantado.", "Adiós wisper."),
        "deepl",
    )
    entry = ui.add(segments=SEGMENTS, text=TEXT, translation=translation.to_dict())
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    played: list[float] = []
    monkeypatch.setattr(view.player, "play_from", played.append)

    def segments() -> tuple[TranscriptSegment, ...]:
        edited = TranscriptTranslation.from_dict(entry.translation)
        assert edited is not None
        return edited.segments

    # Its timing changes, keeping the segments sorted by their start
    monkeypatch.setattr(
        transcript_view.TimingDialog, "get_result", lambda _self: Timing(4.0, 6.0)
    )
    view._edit_translation_timing(0)
    ui.pump()
    assert [(s.start, s.end, s.text) for s in segments()] == [
        (1.5, 3.0, "Encantado."),
        (3.5, 5.0, "Adiós wisper."),
        (4.0, 6.0, "Hola wisper"),
    ]
    # The transcription keeps its timing
    assert entry.segments == SEGMENTS
    assert "00:04 – 00:06" in view.translation_panel.text.tbx_transcript.get(
        "1.0", "end"
    )
    view._on_translation_segment_click(2)
    assert played == [4.0]

    # A segment is added, and translated right away, showing the original text
    # said meanwhile
    messages: list[str] = []

    def type_text(dialog: Any) -> str:
        messages.append(dialog.children["!ctklabel"].cget("text"))
        return "¿Qué tal?"

    monkeypatch.setattr(
        transcript_view.TimingDialog, "get_result", lambda _self: Timing(0.5, 1.4)
    )
    monkeypatch.setattr(transcript_view.TextDialog, "get_input", type_text)
    view._add_translation_segment(0)
    ui.pump()
    assert segments()[0] == TranscriptSegment(0.5, 1.4, "¿Qué tal?", "SPEAKER_01")
    assert "Hello wisper" in messages[0]
    edited = TranscriptTranslation.from_dict(entry.translation)
    assert edited is not None
    assert edited.text.startswith("[SPEAKER_01]: ¿Qué tal? Encantado.")

    # A segment is deleted, once confirmed
    monkeypatch.setattr(transcript_view.messagebox, "askyesno", lambda *_a, **_k: True)
    view._delete_translation_segment(0)
    ui.pump()
    assert len(segments()) == 3
    assert "¿Qué tal?" not in segments()


def test_the_timestamps_can_be_precise(ui: Ui) -> None:
    from models.translation import TranscriptTranslation

    translation = TranscriptTranslation(
        "es", "Hola", translated("Hola", "Encantado.", "Adiós.")
    )
    entry = ui.add(segments=SEGMENTS, text=TEXT, translation=translation.to_dict())
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    transcript = view.text.tbx_transcript
    translated_text = view.translation_panel.text.tbx_transcript
    # They show when each segment starts and ends
    # On their own line, with the speaker, above the text
    assert "00:01 – 00:03   SPEAKER_01\nNice to meet you." in transcript.get(
        "1.0", "end"
    )

    view._toggle_precise_timestamps()
    ui.pump()
    assert "00:00:01,500 – 00:00:03,000   SPEAKER_01\n" in transcript.get("1.0", "end")
    assert "00:00:01,500 – 00:00:03,000   SPEAKER_01\n" in translated_text.get(
        "1.0", "end"
    )
    assert ConfigManager.get_config_system().precise_timestamps

    view._toggle_precise_timestamps()
    ui.pump()
    assert "00:00:01,500" not in transcript.get("1.0", "end")


def test_the_precise_timestamps_option_is_checked_when_they_are_shown(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    import gc

    from views.transcript.transcript_view import TranscriptView

    entry = ui.add(segments=SEGMENTS, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    view._toggle_precise_timestamps()
    monkeypatch.setattr(TranscriptView, "_popup_below", lambda *_args: None)

    view._show_more_menu()
    gc.collect()
    assert view._precise_variable is not None
    assert view._precise_variable.get()


def test_the_source_and_the_date_of_the_translation_are_next_to_its_language(
    ui: Ui,
) -> None:
    from models.translation import TranscriptTranslation

    translation = TranscriptTranslation(
        "es", "Hola", provider="deepl", created_at="2026-10-04T13:30:00+00:00"
    )
    entry = ui.add(segments=SEGMENTS, text=TEXT, translation=translation.to_dict())
    ui.window.select_entry(entry.id)
    ui.pump()
    panel = ui.window._entry_view.translation_panel
    source = panel.lbl_source.cget("text")
    assert source.startswith("DeepL · ")
    assert "Oct " in source
    assert "October" not in source
    assert not panel.lbl_details.winfo_ismapped()


def test_the_dialog_to_translate_asks_for_the_key_of_the_provider(ui: Ui) -> None:
    from views.transcript.translation_panel import TranslateDialog

    dialog = TranslateDialog(
        ui.window,
        source_language="en",
        on_set_api_key=lambda _key: None,
        on_settings=lambda: None,
    )
    ui.pump()
    dialog.omn_provider.set("DeepL")
    dialog._refresh()
    assert dialog.btn_ok.cget("state") == "disabled"

    dialog.omn_provider.set("Ollama (local)")
    dialog._refresh()
    assert dialog.btn_ok.cget("state") == "normal"
    dialog._ok()
    assert dialog._result is not None
    assert dialog._result.provider == "ollama"
    # The interface is in English, as is the transcription
    assert dialog._result.language == "es"
    ui.pump()


def test_the_settings_follow_the_method_and_the_model(ui: Ui, tmp_path: Path) -> None:
    for source in AudioSource:
        if source != AudioSource.WATCH:
            ui.window.show_source(source)
            ui.pump()

    folder_view = ui.window._new_views[AudioSource.DIRECTORY]
    folder_view.set_source(str(tmp_path), should_advance=True)
    ui.pump()
    form = folder_view.frm_settings
    engine = next(card for card in form._cards if isinstance(card, EngineCard))
    context = next(card for card in form._cards if isinstance(card, ContextCard))
    output = next(card for card in form._cards if isinstance(card, OutputCard))

    engine.seg_method.set("Whisper API")
    engine._on_method_change("Whisper API")
    engine.omn_api_model.set("gpt-transcribe")
    engine._on_api_model_change("gpt-transcribe")
    context.ent_keywords.insert(0, "Audiotext, WhisperX")
    # The placeholder of the context isn't taken as its text
    assert context.tbx_prompt.get_text() == ""
    context.tbx_prompt._textbox.event_generate("<FocusIn>")
    context.tbx_prompt.insert("1.0", "  A talk.\n  About speech. ")
    ui.pump()
    context._save_text_fields()
    assert ConfigManager.get_config_transcription().prompt == ("A talk.\nAbout speech.")

    # The model has no timestamps, so it can't save subtitles
    assert output.omn_response_format.cget("values") == ["text", "json"]
    settings = form.get_settings()
    assert settings.openai_model == "gpt-transcribe"
    assert settings.response_format in ("text", "json")
    assert settings.keywords == "Audiotext, WhisperX"
    assert settings.prompt == "A talk.\n  About speech."
    assert context.ent_keywords.cget("state") == "normal"
    assert not context.lbl_unavailable.winfo_ismapped()

    # The diarization model doesn't accept a prompt nor keywords
    engine.omn_api_model.set("gpt-4o-transcribe-diarize")
    engine._on_api_model_change("gpt-4o-transcribe-diarize")
    ui.pump()
    assert context.ent_keywords.cget("state") == "disabled"
    assert context.tbx_prompt.cget("state") == "disabled"
    assert context.lbl_unavailable.winfo_ismapped()

    for method in ("Google API", "WhisperX"):
        engine.seg_method.set(method)
        engine._on_method_change(method)
        ui.pump()


def test_a_failed_transcription_goes_back_to_its_settings(
    ui: Ui, audio_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ui.window, "_run_next", lambda: None)
    settings = TranscriptionSettings(diarize=True, keywords="Audiotext")
    entry = ui.add(
        source=str(audio_file),
        status=EntryStatus.FAILED,
        error="A Hugging Face token is required.",
        settings=settings.to_dict(),
    )
    ui.window.select_entry(entry.id)
    ui.pump()

    back_button = next(
        widget
        for widget in ui.window._entry_view.card.frm_actions.winfo_children()
        if widget.cget("text") == "Back"
    )
    back_button.invoke()
    ui.pump()

    # The settings are those of the failed transcription
    view = ui.window._back_view
    assert view.winfo_ismapped()
    form = view.frm_settings
    assert form.get_settings().diarize
    assert form.get_settings().keywords == "Audiotext"

    options = form._cards[3]
    options.swi_diarize.deselect()
    view.trigger_primary()
    ui.pump()

    # The same entry is transcribed again with the new settings
    assert ui.window._back_view is None
    assert [e.id for e in ui.store.top_level()] == [entry.id]
    entry = ui.store.get(entry.id)
    assert entry.status == EntryStatus.QUEUED
    assert not entry.settings["diarize"]
    assert ui.window._queue[-1] == entry.id
    ui.window._queue.clear()


def test_the_preferences_and_the_interface_language(ui: Ui) -> None:
    ui.window.show_preferences()
    ui.pump()
    ui.window._preferences.destroy()

    ui.app._on_ui_language_change("es")
    ui.pump()
    ui.app._on_ui_language_change("en")
    ui.pump()


def test_a_new_version_is_shown_when_checking_for_updates(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No new version was found at startup
    assert not ui.window.top_bar.btn_update.winfo_ismapped()

    ui.window.show_preferences()
    ui.pump()
    preferences = ui.window._preferences
    preferences._on_update_button()
    ui.pump(0.5)
    assert preferences.lbl_update.cget("text") == "You have the latest version."

    release = update_checker.Release("99.0.0", update_checker.RELEASES_URL)
    monkeypatch.setattr(update_checker, "fetch_latest_release", lambda: release)
    preferences._on_update_button()
    ui.pump(0.5)
    assert preferences.lbl_update.cget("text") == "Version 99.0.0 is available"
    assert preferences.btn_update.cget("text") == "Download"
    preferences.destroy()

    # The new version is still shown after the window is rebuilt
    ui.app._on_ui_language_change("en")
    ui.pump()
    assert ui.window.top_bar.btn_update.winfo_ismapped()
    assert "99.0.0" in ui.window.top_bar.btn_update.cget("text")


def test_a_notification_is_sent_when_a_transcription_is_ready(
    ui: Ui,
    monkeypatch: pytest.MonkeyPatch,
    sent_notifications: list[tuple[str, str]],
) -> None:
    monkeypatch.setattr(ui.window, "_run_next", lambda: None)

    def finish(title: str, is_cancel_requested: bool = False) -> None:
        entry = ui.add(title=title, status=EntryStatus.PROCESSING)
        ui.window._job = Job(
            entry_id=entry.id,
            is_folder=False,
            is_mic=False,
            is_cancel_requested=is_cancel_requested,
        )
        ui.window._finish_job(None)

    finish("talk.mp3")
    finish("cancelled.mp3", is_cancel_requested=True)
    ConfigManager.modify_value(
        ConfigSystem.Key.SECTION, ConfigSystem.Key.NOTIFY_WHEN_DONE, "False"
    )
    finish("muted.mp3")

    assert sent_notifications == [("Transcription ready", "talk.mp3")]


def test_each_file_of_a_watched_folder_is_notified(
    ui: Ui, tmp_path: Path, sent_notifications: list[tuple[str, str]]
) -> None:
    def transcribe_file(kind: AudioSource, file_name: str) -> None:
        entry = ui.add(
            kind=kind.value, source=str(tmp_path), status=EntryStatus.PROCESSING
        )
        ui.window._job = Job(entry_id=entry.id, is_folder=True, is_mic=False)
        ui.window.on_file_transcribed(tmp_path / file_name, "Hello", [], "en")
        ui.window._job = None

    transcribe_file(AudioSource.WATCH, "new.mp3")
    # A folder that isn't watched is notified once all its files are done
    transcribe_file(AudioSource.DIRECTORY, "listed.mp3")

    assert sent_notifications == [("Transcription ready", "new.mp3")]


def test_the_timing_dialog_only_accepts_valid_times(ui: Ui) -> None:
    from views.transcript.edit_dialogs import Timing, TimingDialog

    dialog = TimingDialog(ui.window, "Timing", "Save", "“Hola”", Timing(1.5, 3.0))
    # On Windows, the window hides and shows again to change the color of its title
    # bar when it's idle, and Tk crashes later if it's destroyed before that
    ui.pump()
    start, end = dialog._variables
    assert start.get() == "00:00:01,500"
    assert dialog.btn_ok.cget("state") == "normal"

    end.set("00:01")
    assert dialog.btn_ok.cget("state") == "disabled"
    assert dialog.lbl_error.cget("text")
    end.set("abc")
    assert dialog.btn_ok.cget("state") == "disabled"

    end.set("1:05,9")
    dialog._ok()
    assert dialog._result == Timing(1.5, 65.9)
    ui.pump()


def test_a_translation_is_exported_like_the_transcription(
    ui: Ui, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tkinter as tk

    import views.transcript.transcript_view as transcript_view
    from models.translation import TranscriptTranslation
    from views.transcript.transcript_view import TranscriptView

    translation = TranscriptTranslation(
        "es", "Hola wisper Adiós.", translated("Hola wisper", "", "Adiós."), "manual"
    )
    entry = ui.add(segments=SEGMENTS, text=TEXT, translation=translation.to_dict())
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view

    # The export menu has the formats of the translation in a submenu
    menus: list[tk.Menu] = []
    monkeypatch.setattr(
        TranscriptView,
        "_popup_below",
        staticmethod(lambda menu, _widget: menus.append(menu)),
    )
    view.show_export_menu()
    assert menus[0].entrycget("end", "label") == "Translation into Spanish"
    submenu = menus[0].nametowidget(menus[0].entrycget("end", "menu"))
    assert submenu.entrycget("end", "label") == "JSON (.json)"
    view.show_translation_export_menu(view.translation_panel.btn_export)
    assert menus[1].index("end") == submenu.index("end")
    # On Windows, Tk crashes if a menu with a cascade is destroyed before it has
    # been built, which happens when it's idle, as the menus aren't shown here
    ui.pump()
    for menu in menus:
        menu.destroy()
    ui.pump()

    initial_files: list[str] = []

    def save_as(**kwargs: Any) -> str:
        initial_files.append(kwargs["initialfile"])
        return str(tmp_path / kwargs["initialfile"])

    monkeypatch.setattr(transcript_view.filedialog, "asksaveasfilename", save_as)
    view.export_translation("srt")
    view.export_translation("txt")

    # Named like the subtitles that the video players load with the video
    assert initial_files[0].endswith(".es.srt")
    srt = (tmp_path / initial_files[0]).read_text(encoding="utf-8")
    # With the timing of the translation, without the segments not translated yet
    assert "00:00:03,500 --> 00:00:05,000\n[SPEAKER_00]: Adiós." in srt
    assert srt.count(" --> ") == 2
    txt = (tmp_path / initial_files[1]).read_text(encoding="utf-8")
    assert txt == "Hola wisper Adiós.\n"


def test_the_video_can_be_subtitled_with_the_translation(ui: Ui) -> None:
    from models.translation import TranscriptTranslation

    translation = TranscriptTranslation(
        "es", "", translated("Hola", "Encantado.", "Adiós."), "deepl"
    )
    entry = ui.add(segments=SEGMENTS, text=TEXT, translation=translation.to_dict())
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    video = view.video
    assert video.has_translation_subtitles
    video._position = 2.0

    view._toggle_translation_subtitles()
    config = ConfigManager.get_config_system()
    assert config.show_subtitles
    assert config.subtitle_track == "translation"
    assert video._subtitle_text == "Encantado."

    video.show_translation(False)
    assert video._subtitle_text == "Nice to meet you."

    # Without a translation, the subtitles show the transcription
    video.show_translation(True)
    view._delete_translation()
    ui.pump()
    assert not video.has_translation_subtitles
    assert video._subtitle_text == "Nice to meet you."
