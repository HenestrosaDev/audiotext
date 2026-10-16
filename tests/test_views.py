"""
Builds the interface and goes through its views, as a user would, failing if any
callback of the interface raises an error. They're skipped without a display.
"""

import gettext
import os
import re
import sys
import time
import tkinter as tk
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from functools import cache, partial
from pathlib import Path
from typing import Any

import customtkinter as ctk
import keyring
import pytest

import utils.constants as c
import utils.env_keys as env_keys
import utils.i18n as i18n
import utils.update_checker as update_checker
import views.transcript.corrections as corrections
from controllers.transcription_queue import Job
from models.config.config_subtitles import ConfigSubtitles
from models.config.config_system import ConfigSystem
from models.history import EntryStatus, HistoryEntry
from models.question import TranscriptAnswer
from models.summary import Chapter, TranscriptSummary
from models.transcript_segment import TranscriptSegment, TranscriptWord
from models.transcription_settings import TranscriptionSettings
from tests.conftest import (
    FakeAnswerer,
    FakeSummarizer,
    FakeTranslator,
    MemoryKeyring,
    make_tone,
)
from utils.config_manager import ConfigManager
from utils.enums import AudioSource
from utils.i18n import DOMAIN, LOCALES_PATH, get_language
from views.localization import set_interface_language
from views.settings.cards.context_card import ContextCard
from views.settings.cards.engine_card import EngineCard
from views.settings.cards.language_card import LanguageCard
from views.settings.cards.output_card import OutputCard
from views.settings.preferences_dialog import AI_TAB, API_KEYS_TAB, GENERAL_TAB


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
def summarizer() -> FakeSummarizer:
    """Summarizes the entries instead of a language model. It's shared by the tests."""
    return FakeSummarizer()


@pytest.fixture(scope="module")
def translator() -> FakeTranslator:
    """Translates the entries instead of a provider. It's shared by the tests."""
    return FakeTranslator()


@pytest.fixture(scope="module")
def answerer() -> FakeAnswerer:
    """Answers the questions instead of a language model. It's shared by the tests."""
    return FakeAnswerer()


@pytest.fixture(scope="module")
def app(
    tmp_path_factory: pytest.TempPathFactory,
    summarizer: FakeSummarizer,
    translator: FakeTranslator,
    answerer: FakeAnswerer,
) -> Iterator[Any]:
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

        application = app_module.App(summarizer, translator, answerer)
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

    # A dialog left open, whose input was faked, would keep the clicks of the
    # next tests
    if dialog := app.grab_current():
        dialog.destroy()
    # Each test starts from the welcome page and an empty history
    ui.window.show_welcome()
    for entry in ui.store.top_level():
        ui.store.delete(entry.id)
    ui.window.sidebar.refresh()
    ui.pump()


@contextmanager
def interface_language(ui: Ui, language: str) -> Iterator[None]:
    """Shows the interface in a language, and in English again afterwards."""
    set_interface_language(language)
    ui.pump()
    try:
        yield
    finally:
        set_interface_language("en")
        ui.pump()


def untranslated_texts(root: Any) -> set[str]:
    """
    The texts shown in a window that are still in English, although they have a
    translation into the current interface language. The other windows (e.g.
    dialogs) are left out.
    """
    translation = gettext.translation(
        DOMAIN, LOCALES_PATH, languages=[get_language()], fallback=True
    )
    texts: set[str] = set()
    widgets = [root]
    while widgets:
        widget = widgets.pop()
        if not widget.winfo_viewable():
            continue
        widgets.extend(
            child for child in widget.winfo_children() if not isinstance(child, tk.Wm)
        )
        for option in ("text", "placeholder_text", "values"):
            try:
                value = widget.cget(option)
            except (tk.TclError, ValueError, AttributeError):
                continue
            texts.update([value] if isinstance(value, str) else value or [])
        if isinstance(widget, tk.Wm):
            texts.add(widget.title())
    patterns = english_patterns(get_language())
    return {
        text
        for text in texts
        if text
        and (
            translation.gettext(text) != text
            or any(pattern.search(text) for pattern in patterns)
        )
    }


@cache
def english_patterns(language: str) -> list[re.Pattern[str]]:
    """
    Patterns that find the English texts with a translation into a language in
    the texts built from them: filled in (e.g. "Transcribed 2 of 3 files.") or
    joined to others (e.g. "Translation into French · Done"). Single words are
    left out, since they're often part of other texts (e.g. names).
    """
    translation = gettext.translation(
        DOMAIN, LOCALES_PATH, languages=[language], fallback=True
    )
    patterns = []
    for message, translated_message in getattr(translation, "_catalog", {}).items():
        if not message or translated_message == message or " " not in message:
            continue
        # The placeholders (e.g. "{total}") match any text
        parts = re.split(r"\{[^{}]*\}", message)
        regex = r".+?".join(re.escape(part) for part in parts)
        # Not inside a word (e.g. "Done" in "Undone")
        patterns.append(re.compile(rf"(?<!\w){regex}(?!\w)"))
    return patterns


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


def test_the_actions_of_the_views_reach_the_history(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    import views.main_window.entry_dialogs as entry_dialogs

    monkeypatch.setattr(entry_dialogs.TextDialog, "get_input", lambda _self: "Renamed")
    monkeypatch.setattr(entry_dialogs.messagebox, "askyesno", lambda *_a, **_k: True)
    entry = ui.add(segments=SEGMENTS, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()

    # Renamed from the view of the entry, which asks for the name
    ui.window._entry_view._actions.prompts.ask_to_rename_entry(entry.id)
    ui.pump()
    assert ui.store.get(entry.id).title == "Renamed"
    assert ui.window._entry_view.header.lbl_title.cget("text") == "Renamed"

    # Pinned from the sidebar, which doesn't ask
    ui.window.sidebar.actions.history.toggle_pin(entry.id)
    ui.pump()
    assert ui.store.get(entry.id).is_pinned

    ui.window.sidebar.actions.prompts.confirm_delete_entry(entry.id)
    ui.pump()
    assert ui.store.get(entry.id) is None
    assert ui.window._entry_view is None


def test_the_sections_and_folders_of_the_sidebar_are_folded_in_place(
    ui: Ui, audio_file: Path
) -> None:
    sidebar = ui.window.sidebar
    group = ui.store.add_group("Work")
    try:
        entry = ui.add(title="Grouped", group_id=group.id)
        folder = ui.add(
            title="Folder",
            kind=AudioSource.DIRECTORY.value,
            source=str(audio_file.parent),
        )
        child = ui.add(title="talk.wav", parent_id=folder.id, text="x")
        ui.pump()
        row = sidebar._rows[entry.id]
        assert sidebar.visible_entry_ids == [entry.id, folder.id]

        # Clicked on its name and then on its chevron, the rows are hidden and
        # shown again, not built again
        header = sidebar._section_headers[group.id]
        lbl_title = header.grid_slaves(row=0, column=1)[0]
        lbl_title._label.event_generate("<Button-1>", x=2, y=2)
        ui.pump()
        assert not sidebar._section_bodies[group.id].winfo_ismapped()
        assert sidebar.visible_entry_ids == [folder.id]
        header.lbl_chevron._canvas.event_generate("<Button-1>", x=2, y=2)
        ui.pump()
        assert sidebar._section_bodies[group.id].winfo_ismapped()
        # Also on the empty space between its name and its count
        empty_space = {"x": header.winfo_width() // 2, "y": 2}
        header._canvas.event_generate("<Button-1>", **empty_space)
        ui.pump()
        assert sidebar.visible_entry_ids == [folder.id]
        header._canvas.event_generate("<Button-1>", **empty_space)
        ui.pump()
        assert sidebar._rows[entry.id] is row
        assert row.winfo_ismapped()
        assert sidebar.visible_entry_ids == [entry.id, folder.id]

        # The files of a folder are built when it's first expanded
        assert child.id not in sidebar._rows
        sidebar.toggle_folder(folder.id)
        ui.pump()
        child_row = sidebar._rows[child.id]
        assert child_row.winfo_ismapped()
        assert sidebar.visible_entry_ids == [entry.id, folder.id, child.id]
        sidebar.toggle_folder(folder.id)
        ui.pump()
        assert not child_row.winfo_ismapped()
        assert sidebar.visible_entry_ids == [entry.id, folder.id]

        # Selecting a file shows the files of its folder
        sidebar.set_selected(child.id)
        ui.pump()
        assert sidebar._rows[child.id] is child_row
        assert child_row.winfo_ismapped()
    finally:
        ui.store.delete_group(group.id)


def test_the_transcript_can_be_searched_and_corrected(
    ui: Ui, audio_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    entry = ui.add(segments=SEGMENTS, text=TEXT, media_path=str(audio_file))
    ui.window.select_entry(entry.id)
    ui.pump(0.8)
    view = ui.window._entry_view

    view.focus_search()
    ui.pump()
    dialog = view._find_dialog
    assert dialog is not None
    dialog._find.set("wisper")
    ui.pump()
    assert view.text.match_status == (0, 2)

    for label in ("Plain text", "Summary", "Subtitles"):
        view._on_mode_change(view._modes.value(label))
        ui.pump()

    view.player.toggle_playback()
    ui.pump(0.4)
    view.player.toggle_playback()

    # The summary hides the texts that are searched
    assert view._find_dialog is None
    view.focus_search()
    ui.pump()
    dialog = view._find_dialog
    assert dialog is not None
    dialog._find.set("wisper")
    dialog._replacement.set("Whisper")
    dialog._replace_all()
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
    view.transcript_editor.rename_speakers()
    ui.pump()
    assert entry.text.startswith("[Ana]: Hello Whisper")

    monkeypatch.setattr(corrections.TextDialog, "get_input", lambda _self: "Hi there")
    view.transcript_editor.edit_text(0)
    ui.pump()
    assert entry.segments[0].text == "Hi there"
    assert entry.text.startswith("[Ana]: Hi there")


def test_a_summary_is_generated_and_exported(
    ui: Ui,
    summarizer: FakeSummarizer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import views.transcript.transcript_view as transcript_view

    summary = TranscriptSummary(
        "A short talk.", ("They greet",), (Chapter(0, "Greeting"),), "model", ""
    )
    summarizer.summary = summary
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    entry = ui.add(segments=SEGMENTS, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view

    view._on_mode_change(view._modes.value("Summary"))
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

    # The panel shows who generated it above it, and exports it by itself
    panel = view.summary_panel
    assert panel.btn_regenerate.winfo_ismapped()
    assert panel.lbl_details.cget("text") == "model"
    assert panel.lbl_details.winfo_ismapped()
    assert panel.btn_export.cget("state") == ctk.NORMAL
    initial_files: list[str] = []

    def save_as(**kwargs: Any) -> str:
        initial_files.append(kwargs["initialfile"])
        return str(tmp_path / kwargs["initialfile"])

    monkeypatch.setattr(transcript_view.filedialog, "asksaveasfilename", save_as)
    view.export_summary("md")
    # Named so it doesn't replace the transcription
    assert initial_files[0].endswith(".summary.md")
    md = (tmp_path / initial_files[0]).read_text(encoding="utf-8")
    assert "A short talk." in md
    assert "Hello wisper" not in md


def test_the_summary_without_a_key_leads_to_the_settings(ui: Ui) -> None:

    entry = ui.add(segments=SEGMENTS, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view

    view._on_mode_change(view._modes.value("Summary"))
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
    # There is no summary to generate again
    assert not view.summary_panel.btn_regenerate.winfo_ismapped()

    view._actions.window.show_preferences(AI_TAB)
    ui.pump()
    preferences = ui.window._preferences
    assert preferences.tabs.get() == "AI"
    preferences.destroy()
    ui.pump()


def test_a_translation_is_shown_next_to_the_transcript(
    ui: Ui,
    translator: FakeTranslator,
    audio_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import views.transcript.transcript_view as transcript_view
    from models.translation import TranscriptTranslation
    from views.transcript.translation_panel import TranslationRequest

    translation = TranscriptTranslation(
        "es", "Hola\n\nAdiós", translated("Hola", "Encantado.", "Adiós."), "deepl"
    )
    translator.translation = translation
    translator.requests.clear()
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

    assert translator.requests == [("es", "deepl")]
    assert entry.translations == {"es": translation.to_dict()}
    assert view.translation_panel.winfo_ismapped()
    assert "Encantado." in view.translation_panel.text.tbx_transcript.get("1.0", "end")
    assert ConfigManager.get_config_ai().translation_provider == "deepl"

    # It follows the mode and the playback of the transcript
    for label in ("Plain text", "Summary", "Subtitles"):
        view._on_mode_change(view._modes.value(label))
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
    assert entry.translations == {}


def test_a_transcription_has_a_translation_into_each_language(
    ui: Ui, translator: FakeTranslator, monkeypatch: pytest.MonkeyPatch
) -> None:
    import views.transcript.transcript_view as transcript_view
    from models.translation import TranscriptTranslation
    from views.transcript.translation_panel import TranslationRequest

    spanish = TranscriptTranslation(
        "es", "", translated("Hola", "Encantado.", "Adiós."), "deepl"
    )
    french = TranscriptTranslation("fr", "", translated("Bonjour", "", ""), "manual")
    entry = ui.add(
        segments=SEGMENTS,
        text=TEXT,
        translations={"es": spanish.to_dict(), "fr": french.to_dict()},
    )
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    panel = view.translation_panel
    shown = panel.text.tbx_transcript

    # The last one made is shown, and the menu tells how much of each is done
    assert panel.omn_language.get() == "French · 25%"
    assert panel.omn_language.cget("values") == [
        "Spanish · 100%",
        "French · 25%",
        "Translate into another language…",
    ]
    assert "Bonjour" in shown.get("1.0", "end")

    panel._choose_option("Spanish · 100%")
    ui.pump()
    assert "Encantado." in shown.get("1.0", "end")
    # The segments of the translation shown are the ones edited
    monkeypatch.setattr(corrections.TextDialog, "get_input", lambda _self: "Chao")
    view.translation_editor.edit_text(2)
    ui.pump()
    edited = entry.get_translation("es")
    assert edited is not None
    assert edited.segments[2].text == "Chao"
    assert entry.get_translation("fr") == french

    # Another language is added, keeping the others
    translator.translation = spanish
    monkeypatch.setattr(
        transcript_view.TranslateDialog,
        "get_result",
        lambda _self: TranslationRequest("de", "deepl"),
    )
    panel._choose_option("Translate into another language…")
    ui.pump()
    assert list(entry.translations) == ["es", "fr", "de"]
    assert panel.omn_language.get() == "German · 100%"

    # Deleting one shows the last one left
    view._delete_translation()
    ui.pump()
    assert list(entry.translations) == ["es", "fr"]
    assert panel.winfo_ismapped()
    assert panel.omn_language.get() == "French · 25%"


def test_a_translation_can_be_edited(ui: Ui, monkeypatch: pytest.MonkeyPatch) -> None:
    from models.translation import TranscriptTranslation

    translation = TranscriptTranslation(
        "es",
        "[SPEAKER_00]: Hola wisper\n\n[SPEAKER_01]: Encantado.\n\n"
        "[SPEAKER_00]: Adiós wisper.",
        translated("Hola wisper", "Encantado.", "Adiós wisper."),
        "deepl",
    )
    entry = ui.add(
        segments=SEGMENTS,
        text=TEXT,
        translations={translation.language: translation.to_dict()},
    )
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view

    # A segment, whose change follows to the text
    monkeypatch.setattr(
        corrections.TextDialog, "get_input", lambda _self: "Hola Whisper"
    )
    view.translation_editor.edit_text(0)
    ui.pump()
    edited = entry.get_translation("es")
    assert edited is not None
    assert edited.segments[0].text == "Hola Whisper"
    assert edited.text.startswith("[SPEAKER_00]: Hola Whisper")
    assert not edited.is_text_edited
    assert "Hola Whisper" in view.translation_panel.text.tbx_transcript.get(
        "1.0", "end"
    )

    # The plain text, which then keeps the changes of the user
    view._on_mode_change(view._modes.value("Plain text"))
    ui.pump()
    plain = view.translation_panel.text.tbx_plain
    plain.delete("1.0", "end")
    plain.insert("1.0", "Hola a todos")
    view.translation_panel.text._schedule_text_save()
    view.translation_panel.save_pending_text()
    edited = entry.get_translation("es")
    assert edited is not None
    assert edited.text == "Hola a todos"
    assert edited.is_text_edited

    view.translation_editor.edit_text(1)
    ui.pump()
    edited = entry.get_translation("es")
    assert edited is not None
    assert edited.segments[1].text == "Hola Whisper"
    assert edited.text == "Hola a todos"


def test_a_transcription_can_be_translated_from_scratch(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    import views.transcript.transcript_view as transcript_view
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
    translation = entry.get_translation("es")
    assert translation is not None
    assert translation.provider == "manual"
    assert translation.segments == translated("", "", "")
    assert translation.text == ""
    panel = view.translation_panel
    assert view.translation_panel.winfo_ismapped()
    assert "Not translated yet" in panel.text.tbx_transcript.get("1.0", "end")
    # Above the text, in the row of its hints, so it's aligned with the transcript
    assert not panel.lbl_details.winfo_ismapped()
    hint = panel.text.lbl_hint.cget("text")
    assert "3" in hint
    # The transcript on its left already explains how to use the segments
    assert "Click a segment" not in hint
    assert panel.text.lbl_hint.winfo_ismapped()

    monkeypatch.setattr(corrections.TextDialog, "get_input", lambda _self: "Adiós")
    view.translation_editor.edit_text(2)
    ui.pump()
    translation = entry.get_translation("es")
    assert translation is not None
    assert translation.segments == translated("", "", "Adiós")
    assert translation.text == "[SPEAKER_00]: Adiós"
    assert "2" in panel.text.lbl_hint.cget("text")


def test_a_translation_from_scratch_has_the_timestamps_of_the_subtitles(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    import views.transcript.transcript_view as transcript_view
    from views.transcript.translation_panel import TranslationRequest

    ConfigManager.modify_value(
        ConfigSubtitles.Key.SECTION, ConfigSubtitles.Key.MAX_LINE_WIDTH, "10"
    )
    ConfigManager.modify_value(
        ConfigSubtitles.Key.SECTION, ConfigSubtitles.Key.MAX_LINE_COUNT, "1"
    )
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

    # A segment per subtitle of the transcript, e.g. "Nice to" and "meet you."
    translation = entry.get_translation("es")
    assert translation is not None
    assert [(s.start, s.end) for s in translation.segments] == [
        (part.segment.start, part.segment.end) for part in view._parts
    ]
    assert len(translation.segments) > len(SEGMENTS)
    assert all(not segment.text for segment in translation.segments)


def test_the_segments_of_a_translation_have_their_own_timing(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.translation import TranscriptTranslation
    from views.transcript.edit_dialogs import Timing

    translation = TranscriptTranslation(
        "es",
        "",
        translated("Hola wisper", "Encantado.", "Adiós wisper."),
        "deepl",
    )
    entry = ui.add(
        segments=SEGMENTS,
        text=TEXT,
        translations={translation.language: translation.to_dict()},
    )
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    played: list[float] = []
    monkeypatch.setattr(view.player, "play_from", played.append)

    def segments() -> tuple[TranscriptSegment, ...]:
        edited = entry.get_translation("es")
        assert edited is not None
        return edited.segments

    # Its timing changes, keeping the segments sorted by their start
    monkeypatch.setattr(
        corrections.TimingDialog, "get_result", lambda _self: Timing(4.0, 6.0)
    )
    view.translation_editor.edit_timing(0)
    ui.pump()
    assert [(s.start, s.end, s.text) for s in segments()] == [
        (1.5, 3.0, "Encantado."),
        (3.5, 5.0, "Adiós wisper."),
        (4.0, 6.0, "Hola wisper"),
    ]
    # The transcription keeps its timing
    assert entry.segments == SEGMENTS
    translated_text = view.translation_panel.text.tbx_transcript.get("1.0", "end")
    assert "00:00:04,000 – 00:00:06,000" in translated_text
    view._on_translation_segment_click(2)
    assert played == [4.0]

    # A segment is added, and translated right away, showing the original text
    # said meanwhile
    messages: list[str] = []

    def type_text(dialog: Any) -> str:
        messages.append(dialog.children["!ctklabel"].cget("text"))
        return "¿Qué tal?"

    monkeypatch.setattr(
        corrections.TimingDialog, "get_result", lambda _self: Timing(0.5, 1.4)
    )
    monkeypatch.setattr(corrections.TextDialog, "get_input", type_text)
    view.translation_editor.add_after(0)
    ui.pump()
    assert segments()[0] == TranscriptSegment(0.5, 1.4, "¿Qué tal?", "SPEAKER_01")
    assert "Hello wisper" in messages[0]
    edited = entry.get_translation("es")
    assert edited is not None
    assert edited.text.startswith("[SPEAKER_01]: ¿Qué tal? Encantado.")

    # A segment is deleted, once confirmed
    monkeypatch.setattr(corrections.messagebox, "askyesno", lambda *_a, **_k: True)
    view.translation_editor.delete(0)
    ui.pump()
    assert len(segments()) == 3
    assert "¿Qué tal?" not in segments()


def test_the_transcript_is_shown_as_subtitles(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:

    ConfigManager.modify_value(
        ConfigSubtitles.Key.SECTION, ConfigSubtitles.Key.MAX_LINE_WIDTH, "10"
    )
    ConfigManager.modify_value(
        ConfigSubtitles.Key.SECTION, ConfigSubtitles.Key.MAX_LINE_COUNT, "1"
    )
    entry = ui.add(segments=SEGMENTS, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    transcript = view.text.tbx_transcript

    # By default, each segment is split into the lines of its subtitles
    content = transcript.get("1.0", "end")
    assert "Nice to\n" in content
    assert "meet you.\n" in content
    assert "Nice to meet you." not in content

    # Each part is edited on its own, and the rest of the segment is kept
    meet_you = next(
        idx for idx, part in enumerate(view._parts) if part.segment.text == "meet you."
    )
    monkeypatch.setattr(corrections.TextDialog, "get_input", lambda _self: "you all.")
    view.transcript_editor.edit_text(meet_you)
    ui.pump()
    assert entry.segments[1].text == "Nice to you all."


def test_the_find_dialog_goes_through_the_matches_and_replaces_them(
    ui: Ui,
) -> None:
    from models.translation import TranscriptTranslation

    translation = TranscriptTranslation(
        "es", "", translated("Hola wisper", "Encantado.", "Adiós wisper."), "deepl"
    )
    entry = ui.add(
        segments=SEGMENTS,
        text=TEXT,
        translations={translation.language: translation.to_dict()},
    )
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    view.btn_search.invoke()
    ui.pump()
    dialog = view._find_dialog
    assert dialog is not None
    assert dialog.title() == "Find and replace in the transcription"

    # The timestamps and the speakers aren't searched
    dialog._find.set("00")
    ui.pump()
    assert view.text.match_status == (None, 0)
    assert dialog.lbl_matches.cget("text") == "No results"

    dialog._find.set("Wisper")
    ui.pump()
    assert dialog.lbl_matches.cget("text") == "1 of 2"
    dialog.go_to_match(1)
    assert dialog.lbl_matches.cget("text") == "2 of 2"
    dialog.go_to_match(1)
    assert dialog.lbl_matches.cget("text") == "1 of 2"
    dialog._match_case.set(True)
    dialog._search()
    assert dialog.lbl_matches.cget("text") == "No results"
    dialog._match_case.set(False)
    dialog._search()

    # Only the current match is replaced, and the next one becomes current
    dialog.go_to_match(1)
    dialog._replacement.set("Whisper")
    dialog._replace()
    ui.pump()
    assert [s.text for s in entry.segments] == [
        "Hello wisper",
        "Nice to meet you.",
        "Bye Whisper.",
    ]
    assert dialog.lbl_matches.cget("text") == "1 of 1"

    # The search icon of the translation searches it instead
    view.translation_panel.btn_search.invoke()
    ui.pump()
    assert view._find_dialog is dialog
    assert dialog.title() == "Find and replace in the translation into Spanish"
    assert view.text.match_status == (None, 0)
    assert view.translation_panel.text.match_status == (0, 2)
    dialog._replace_all()
    ui.pump()
    edited = entry.get_translation("es")
    assert edited is not None
    assert [s.text for s in edited.segments] == [
        "Hola Whisper",
        "Encantado.",
        "Adiós Whisper.",
    ]

    # Pinned, it stays above the main window
    assert dialog.wm_transient()
    dialog._toggle_pin()
    assert not dialog.wm_transient()
    assert not ConfigManager.get_config_system().is_find_pinned

    dialog.close()
    ui.pump()
    assert view._find_dialog is None
    assert view.translation_panel.text.match_status == (None, 0)


def test_the_subtitles_are_split_again_when_their_size_changes(ui: Ui) -> None:
    entry = ui.add(segments=SEGMENTS, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    transcript = view.text.tbx_transcript
    assert "Nice to meet you." in transcript.get("1.0", "end")

    # As if the user changed them in the preferences
    for key, value in (
        (ConfigSubtitles.Key.MAX_LINE_WIDTH, "10"),
        (ConfigSubtitles.Key.MAX_LINE_COUNT, "1"),
    ):
        ConfigManager.modify_value(ConfigSubtitles.Key.SECTION, key, value)
    ui.window._on_subtitles_change()
    ui.pump()
    assert "Nice to meet you." not in transcript.get("1.0", "end")
    assert view.video._cue_track.at(2.5).text == "meet you."


def test_the_transcript_is_copied_and_exported_from_its_card(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from views.transcript.transcript_view import TranscriptView

    entry = ui.add(segments=SEGMENTS, text=TEXT, language="en")
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    # Like its translation, its card is titled with its language
    assert view.lbl_transcript_title.cget("text") == "English"

    view.btn_copy.invoke()
    assert view.clipboard_get() == TEXT

    anchors: list[Any] = []
    monkeypatch.setattr(
        TranscriptView,
        "_popup_below",
        staticmethod(lambda menu, widget: anchors.append(widget) or menu.destroy()),
    )
    view.btn_export.invoke()
    assert anchors == [view.btn_export]
    # While the summary is shown, the transcript and its buttons are hidden
    view._on_mode_change("summary")
    ui.pump()
    view.show_export_menu()
    assert anchors[-1] is view.btn_more


def test_icon_buttons_show_what_they_do_on_hover(ui: Ui) -> None:
    from views.widgets.button import icon_button

    button = icon_button(ui.window, "copy", lambda: None, lambda: "Copy")
    button.place(x=0, y=0)
    ui.pump()
    tooltip = button._tooltip
    tooltip._show()
    assert tooltip._window is not None
    assert tooltip._window.winfo_children()[0].cget("text") == "Copy"

    tooltip.hide()
    assert tooltip._window is None
    button.destroy()


def test_the_parts_of_the_translation_are_changed_on_their_own(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.translation import TranscriptTranslation
    from views.transcript.edit_dialogs import Timing

    for key, value in (
        (ConfigSubtitles.Key.MAX_LINE_WIDTH, "10"),
        (ConfigSubtitles.Key.MAX_LINE_COUNT, "1"),
    ):
        ConfigManager.modify_value(ConfigSubtitles.Key.SECTION, key, value)
    translation = TranscriptTranslation(
        "es", "", translated("Hola wisper", "Encantado de conocerte.", ""), "deepl"
    )
    entry = ui.add(
        segments=SEGMENTS,
        text=TEXT,
        translations={translation.language: translation.to_dict()},
    )
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    panel_text = view.translation_panel.text.tbx_transcript

    def segments() -> list[tuple[float, float, str]]:
        edited = entry.get_translation("es")
        assert edited is not None
        return [(s.start, s.end, s.text) for s in edited.segments]

    # The long segment is shown as its subtitles, and the one not translated
    # yet is still shown
    texts = [part.segment.text for part in view._translation_parts()]
    assert texts == ["Hola", "wisper", "Encantado", "de", "conocerte.", ""]
    assert "00:00:03,500 – 00:00:05,000   SPEAKER_00\n" in panel_text.get("1.0", "end")

    # The text of a part is edited, keeping the rest of its segment
    monkeypatch.setattr(corrections.TextDialog, "get_input", lambda _self: "Feliz")
    view.translation_editor.edit_text(2)
    ui.pump()
    assert segments()[1][2] == "Feliz de conocerte."
    assert segments()[1][:2] == (1.5, 3.0)

    # Changing the timing of a part makes it a segment of its own
    monkeypatch.setattr(
        corrections.TimingDialog, "get_result", lambda _self: Timing(0.6, 0.9)
    )
    view.translation_editor.edit_timing(1)
    ui.pump()
    assert [text for _start, _end, text in segments()] == [
        "Hola",
        "wisper",
        "Feliz de conocerte.",
        "",
    ]
    assert segments()[1][:2] == (0.6, 0.9)
    assert segments()[0][0] == 0.0

    # Deleting a part only deletes it
    monkeypatch.setattr(corrections.messagebox, "askyesno", lambda *_a, **_k: True)
    view.translation_editor.delete(0)
    ui.pump()
    assert [text for _start, _end, text in segments()] == [
        "wisper",
        "Feliz de conocerte.",
        "",
    ]


def test_the_subtitles_of_a_vertical_video_are_narrower(ui: Ui) -> None:
    ConfigManager.modify_value(
        ConfigSubtitles.Key.SECTION, ConfigSubtitles.Key.MAX_LINE_WIDTH_VERTICAL, "10"
    )
    ConfigManager.modify_value(
        ConfigSubtitles.Key.SECTION, ConfigSubtitles.Key.MAX_LINE_COUNT_VERTICAL, "1"
    )
    entry = ui.add(segments=SEGMENTS, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    transcript = view.text.tbx_transcript
    assert "Nice to meet you." in transcript.get("1.0", "end")

    # Once the media is loaded and its video is vertical
    view._set_vertical()
    ui.pump()
    content = transcript.get("1.0", "end")
    assert "Nice to\n" in content
    assert "meet you.\n" in content
    assert view.video._cue_track.at(2.5).text == "meet you."


def test_the_timestamps_can_be_precise(ui: Ui) -> None:
    from models.translation import TranscriptTranslation

    translation = TranscriptTranslation(
        "es", "Hola", translated("Hola", "Encantado.", "Adiós.")
    )
    entry = ui.add(
        segments=SEGMENTS,
        text=TEXT,
        translations={translation.language: translation.to_dict()},
    )
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    transcript = view.text.tbx_transcript
    translated_text = view.translation_panel.text.tbx_transcript
    # They show when each segment starts and ends, precise by default
    # On their own line, with the speaker, above the text
    assert "00:00:01,500 – 00:00:03,000   SPEAKER_01\n" in transcript.get("1.0", "end")
    assert "00:00:01,500 – 00:00:03,000   SPEAKER_01\n" in translated_text.get(
        "1.0", "end"
    )

    view._toggle_precise_timestamps()
    ui.pump()
    assert "00:01 – 00:03   SPEAKER_01\nNice to meet you." in transcript.get(
        "1.0", "end"
    )
    assert "00:00:01,500" not in translated_text.get("1.0", "end")
    assert not ConfigManager.get_config_system().precise_timestamps

    view._toggle_precise_timestamps()
    ui.pump()
    assert "00:00:01,500" in transcript.get("1.0", "end")


def tagged_texts(textbox: Any, tag: str) -> list[str]:
    """The texts of a textbox with a tag."""
    ranges = textbox.tag_ranges(tag)
    return [
        textbox.get(start, end)
        for start, end in zip(ranges[::2], ranges[1::2], strict=True)
    ]


def test_the_low_confidence_words_are_highlighted(ui: Ui) -> None:
    words = (
        TranscriptWord(0.0, 0.5, "Hello", 0.9),
        TranscriptWord(0.5, 1.0, "wisper", 0.3),
    )
    segments = [replace(SEGMENTS[0], words=words), *SEGMENTS[1:]]
    entry = ui.add(segments=segments, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view

    def highlighted() -> list[str]:
        return tagged_texts(view.text.tbx_transcript, "low_confidence")

    # Only the words below the threshold (40% by default)
    assert highlighted() == ["wisper"]

    view._set_low_confidence_threshold(20)
    ui.pump()
    assert highlighted() == []
    assert ConfigManager.get_config_system().low_confidence_threshold == 20

    view._set_low_confidence_threshold(95)
    ui.pump()
    assert highlighted() == ["Hello", "wisper"]

    view._toggle_low_confidence()
    ui.pump()
    assert highlighted() == []
    assert not ConfigManager.get_config_system().highlight_low_confidence


def test_the_precise_timestamps_option_is_checked_when_they_are_shown(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    import gc

    from views.transcript.transcript_view import TranscriptView

    entry = ui.add(segments=SEGMENTS, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    monkeypatch.setattr(TranscriptView, "_popup_below", lambda *_args: None)

    view._show_more_menu()
    gc.collect()
    assert view._precise_variable is not None
    assert view._precise_variable.get()

    view._toggle_precise_timestamps()
    view._show_more_menu()
    gc.collect()
    assert not view._precise_variable.get()


def test_the_low_confidence_segments_are_highlighted_whole(ui: Ui) -> None:
    # The OpenAI API only scores the segments
    segments = [SEGMENTS[0], replace(SEGMENTS[1], score=0.2), SEGMENTS[2]]
    entry = ui.add(segments=segments, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    transcript = ui.window._entry_view.text.tbx_transcript

    assert tagged_texts(transcript, "low_confidence") == ["Nice to meet you."]


def test_the_low_confidence_texts_can_be_gone_through(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from views.transcript.transcript_text import PLAIN_TEXT_MODE, TRANSCRIPT_MODE

    words = (
        TranscriptWord(0.0, 0.5, "Hello", 0.9),
        TranscriptWord(0.5, 1.0, "wisper", 0.3),
    )
    segments = [
        replace(SEGMENTS[0], words=words),
        replace(SEGMENTS[1], score=0.2),
        SEGMENTS[2],
    ]
    entry = ui.add(segments=segments, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    clips: list[tuple[float, float]] = []
    seeks: list[float] = []
    monkeypatch.setattr(view.player, "play_clip", lambda *clip: clips.append(clip))
    monkeypatch.setattr(view.player, "seek", seeks.append)

    def go_to(step: int) -> str:
        ui.window.trigger_low_confidence(step)
        ui.pump()
        [text] = tagged_texts(view.text.tbx_transcript, "current_low_confidence")
        return text

    # They are only shown in the transcript, so it's shown
    view._on_mode_change(PLAIN_TEXT_MODE)
    assert go_to(1) == "wisper"
    assert view._mode == TRANSCRIPT_MODE
    assert go_to(1) == "Nice to meet you."
    # It goes around at the end and at the start
    assert go_to(1) == "wisper"
    assert go_to(-1) == "Nice to meet you."
    # Each one is played with a moment around it
    assert clips == [(-1.0, 2.5), (0.0, 4.5), (-1.0, 2.5), (0.0, 4.5)]

    # Without auto-play, the player only goes to them
    view.review_bar.chk_auto_play.toggle()
    assert not ConfigManager.get_config_system().review_auto_play
    assert go_to(1) == "wisper"
    assert seeks == [0.5]
    assert len(clips) == 4


def review_segments() -> list[TranscriptSegment]:
    """Three low confidence texts: a word, and two segments scored whole."""
    words = (
        TranscriptWord(0.0, 0.5, "Hello", 0.9),
        TranscriptWord(0.5, 1.0, "wisper", 0.3),
    )
    return [
        replace(SEGMENTS[0], words=words),
        replace(SEGMENTS[1], score=0.2),
        replace(SEGMENTS[2], score=0.1),
    ]


def open_review(ui: Ui, monkeypatch: pytest.MonkeyPatch) -> Any:
    """The view of a transcription to review, without playing its audio."""
    entry = ui.add(segments=review_segments(), text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    monkeypatch.setattr(view.player, "play_clip", lambda *_clip: None)
    return view


def current_text(view: Any) -> str | None:
    texts = tagged_texts(view.text.tbx_transcript, "current_low_confidence")
    return texts[0] if texts else None


def press_return(ui: Ui, view: Any) -> None:
    textbox = view.text.tbx_transcript._textbox
    textbox.focus_force()
    ui.pump()
    textbox.event_generate("<Return>")
    ui.pump()


def test_return_accepts_the_word_gone_to_and_goes_to_the_next(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = open_review(ui, monkeypatch)
    status = view.review_bar.lbl_status

    # Without a word gone to, it does nothing
    press_return(ui, view)
    assert status.cget("text") == "3 of 3 to review"

    view.go_to_low_confidence(1)
    press_return(ui, view)
    assert status.cget("text") == "2 of 3 to review"
    assert current_text(view) == "Nice to meet you."
    assert tagged_texts(view.text.tbx_transcript, "low_confidence") == [
        "Nice to meet you.",
        "Bye wisper.",
    ]

    press_return(ui, view)
    press_return(ui, view)
    # The last one ends the review, without going around
    assert status.cget("text") == "All reviewed · 3 of 3"
    assert current_text(view) is None
    assert view.reviewer.current is None
    press_return(ui, view)
    assert status.cget("text") == "All reviewed · 3 of 3"


def test_return_is_only_handled_by_the_transcript(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = open_review(ui, monkeypatch)
    view.go_to_low_confidence(1)

    # Typing in the plain text doesn't accept the word
    plain = view.text.tbx_plain._textbox
    view._on_mode_change("plain")
    plain.focus_force()
    ui.pump()
    plain.event_generate("<Return>")
    ui.pump()
    assert view.review_bar.review.remaining == 3


def test_reviewing_many_words_writes_once_and_doesnt_render_again(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from utils.history_store import HistoryStore
    from views.transcript.transcript_text import TranscriptText

    view = open_review(ui, monkeypatch)
    entry_id = view.entry_id
    renders: list[None] = []
    saves: list[None] = []
    render = TranscriptText._render_transcript
    save = HistoryStore.save
    monkeypatch.setattr(
        TranscriptText,
        "_render_transcript",
        lambda self: (renders.append(None), render(self))[1],
    )
    monkeypatch.setattr(
        HistoryStore, "save", lambda self: (saves.append(None), save(self))[1]
    )

    view.go_to_low_confidence(1)
    for _idx in range(3):
        assert view.reviewer.accept_current()
    ui.pump()

    assert renders == []
    # Written a moment later, once
    assert saves == []
    view.reviewer.save_reviews()
    assert len(saves) == 1

    # Showing another transcription writes the pending reviews
    view.go_to_low_confidence(1)
    view.reviewer.review_again()
    ui.window.select_entry(ui.add(segments=SEGMENTS, text=TEXT).id)
    ui.pump()
    assert len(saves) == 2
    reloaded = HistoryStore(ui.store.file_path, ui.store.media_dir).get(entry_id)
    assert reloaded is not None
    assert reloaded.segments[1].reviewed is None


def test_the_last_review_can_be_undone(ui: Ui, monkeypatch: pytest.MonkeyPatch) -> None:
    from models.transcript_segment import ReviewMark
    from utils.transcript_editing import edit_segment

    view = open_review(ui, monkeypatch)
    bar = view.review_bar

    view.go_to_low_confidence(1)
    assert not bar.btn_undo.grid_info()
    view.reviewer.accept_current()
    assert bar.btn_undo.grid_info()
    assert view.reviewer.undo()
    assert bar.lbl_status.cget("text") == "3 of 3 to review"
    assert current_text(view) == "wisper"
    assert not view.reviewer.undo()

    # Correcting the word gone to reviews it, and goes to the next one
    view.transcript_editor.update(
        edit_segment(view._entry.segments, 0, "Hello Whisper"), lambda text: text
    )
    ui.pump()
    word = view._entry.segments[0].words[1]
    assert (word.text, word.score, word.reviewed) == ("Whisper", 0.3, ReviewMark.EDITED)
    assert bar.lbl_status.cget("text") == "2 of 3 to review"
    assert current_text(view) == "Nice to meet you."
    # Undoing it brings back the word with its score, not reviewed
    assert view.reviewer.undo()
    assert view._entry.segments[0].words[1] == words_of_review()[1]
    assert current_text(view) == "wisper"


def words_of_review() -> tuple[TranscriptWord, ...]:
    return review_segments()[0].words


def test_reviewing_again_keeps_the_corrected_words(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from utils.transcript_editing import edit_segment

    view = open_review(ui, monkeypatch)
    view.transcript_editor.update(
        edit_segment(view._entry.segments, 0, "Hello Whisper"), lambda text: text
    )
    view.go_to_low_confidence(1)
    view.reviewer.accept_current()
    view.reviewer.accept_current()
    ui.pump()
    bar = view.review_bar
    assert bar.lbl_status.cget("text") == "All reviewed · 3 of 3"
    assert bar.btn_review_again.cget("text") == "Review accepted words again"

    bar.btn_review_again.invoke()
    ui.pump()
    # Not a full reset: the corrected word stays reviewed
    assert bar.lbl_status.cget("text") == "2 of 3 to review"


def test_the_low_confidence_options_need_the_scores_of_the_words(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from views.transcript.transcript_view import TranscriptView

    menus: list[tk.Menu] = []
    monkeypatch.setattr(
        TranscriptView,
        "_popup_below",
        staticmethod(lambda menu, _widget: menus.append(menu)),
    )

    def labels() -> list[str]:
        ui.window._entry_view._show_more_menu()
        menu = menus[-1]
        return [
            str(menu.entrycget(idx, "label"))
            for idx in range(int(menu.index("end")) + 1)
            if menu.type(idx) != "separator"
        ]

    def states() -> list[str]:
        menu = menus[-1]
        return [
            str(menu.entrycget(label, "state"))
            for label in ("Highlight low-confidence words", "Low-confidence threshold")
        ]

    # Its words were timed before the scores were kept
    entry = ui.add(segments=SEGMENTS, text=TEXT, method="WhisperX")
    ui.window.select_entry(entry.id)
    ui.pump()
    labels()
    # The highlighting can always be turned on and off
    assert states() == [tk.NORMAL, tk.DISABLED]
    # A note says why the threshold is disabled
    hint = "Transcribe it again to score its words"
    assert menus[-1].entrycget(hint, "state") == tk.DISABLED
    # Unless the user doesn't want to hear of the scores
    ui.window._entry_view._toggle_low_confidence()
    assert hint not in labels()
    assert states() == [tk.NORMAL, tk.DISABLED]
    ui.window._entry_view._toggle_low_confidence()

    words = (TranscriptWord(0.0, 1.0, "Hello", 0.1),)
    entry = ui.add(segments=[replace(SEGMENTS[0], words=words)], text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    shown = labels()
    assert states() == [tk.NORMAL] * 2
    assert hint not in shown
    # The review bar goes to the words
    assert "Next low-confidence word" not in shown
    assert "Previous low-confidence word" not in shown


def test_the_review_buttons_say_what_they_do_on_hover(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from views.style import theme
    from views.widgets import tooltip

    monkeypatch.setattr(tooltip, "TOOLTIP_DELAY_MS", 0)
    view = open_review(ui, monkeypatch)
    bar = view.review_bar
    modifier, shift = theme.SHORTCUT_MODIFIER_LABEL, theme.SHIFT_LABEL
    previous = f"{shift}{modifier}J" if theme.IS_MACOS else f"{modifier}{shift}J"

    for button, text in (
        (bar.btn_previous, f"Previous low-confidence word ({previous})"),
        (bar.btn_next, f"Next low-confidence word ({modifier}J)"),
    ):
        # Where the pointer is over the button, which handles it
        button._canvas.event_generate("<Enter>")
        ui.pump()
        window = button._tooltip._window
        assert window is not None
        [label] = window.winfo_children()
        assert label.cget("text") == text
        button._canvas.event_generate("<Leave>")
        ui.pump()


def test_the_remaining_words_can_be_accepted_at_once(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.transcript_segment import ReviewMark
    from utils.transcript_editing import edit_segment

    view = open_review(ui, monkeypatch)
    bar = view.review_bar
    # One corrected, which stays as it is
    view.transcript_editor.update(
        edit_segment(view._entry.segments, 0, "Hello Whisper"), lambda text: text
    )
    assert bar.btn_accept_remaining.grid_info()

    bar.btn_accept_remaining.invoke()
    ui.pump()
    assert bar.lbl_status.cget("text") == "All reviewed · 3 of 3"
    assert not bar.btn_accept_remaining.grid_info()
    assert current_text(view) is None
    segments = view._entry.segments
    assert segments[0].words[1].reviewed == ReviewMark.EDITED
    assert [segments[1].reviewed, segments[2].reviewed] == [ReviewMark.ACCEPTED] * 2
    assert view.text.tbx_transcript.tag_ranges("low_confidence") == ()

    # Undone at once too, back to the first of them
    assert view.reviewer.undo()
    assert bar.lbl_status.cget("text") == "2 of 3 to review"
    assert current_text(view) == "Nice to meet you."


def test_the_review_bar_shows_the_state_of_the_review(ui: Ui) -> None:
    from models.review import set_review
    from models.transcript_segment import ReviewMark
    from views.transcript.transcript_text import PLAIN_TEXT_MODE, TRANSCRIPT_MODE

    words = (
        TranscriptWord(0.0, 0.5, "Hello", 0.9),
        TranscriptWord(0.5, 1.0, "wisper", 0.3),
    )
    segments = [
        replace(SEGMENTS[0], words=words),
        replace(SEGMENTS[1], score=0.2),
        SEGMENTS[2],
    ]
    entry = ui.add(segments=segments, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    bar = view.review_bar

    def status() -> str:
        return str(bar.lbl_status.cget("text")) if bar.lbl_status.grid_info() else ""

    def is_shown(widget: Any) -> bool:
        return bool(widget.grid_info())

    assert status() == "2 of 2 to review"
    assert is_shown(bar.frm_arrows)
    assert bar.btn_next.cget("state") == tk.NORMAL

    # It's only above the subtitles
    view._on_mode_change(PLAIN_TEXT_MODE)
    assert not is_shown(bar)
    view._on_mode_change(TRANSCRIPT_MODE)
    assert is_shown(bar)

    # The threshold changes it right away
    view._set_low_confidence_threshold(20)
    assert status() == "No low-confidence words at this threshold"
    assert bar.btn_next.cget("state") == tk.DISABLED
    assert is_shown(bar.btn_adjust)
    view._set_low_confidence_threshold(40)
    assert status() == "2 of 2 to review"

    # Without the highlighting, the bar isn't shown
    view._toggle_low_confidence()
    assert not is_shown(bar)
    assert view.text.tbx_transcript.tag_ranges("low_confidence") == ()
    view._on_mode_change(PLAIN_TEXT_MODE)
    view._on_mode_change(TRANSCRIPT_MODE)
    assert not is_shown(bar)
    view._toggle_low_confidence()
    assert is_shown(bar)
    assert status() == "2 of 2 to review"
    assert tagged_texts(view.text.tbx_transcript, "low_confidence") == [
        "wisper",
        "Nice to meet you.",
    ]

    # The reviewed words are no longer highlighted
    view._actions.transcript.update_transcript(
        entry.id,
        set_review(
            view._entry.segments, view.reviewer.review.flagged, ReviewMark.ACCEPTED
        ),
        TEXT,
    )
    ui.pump()
    assert status() == "All reviewed · 2 of 2"
    assert is_shown(bar.btn_review_again)
    assert view.text.tbx_transcript.tag_ranges("low_confidence") == ()
    bar.btn_review_again.invoke()
    ui.pump()
    assert status() == "2 of 2 to review"
    # Which is kept with the transcription
    assert ui.store.get(entry.id).segments[0].words[1].reviewed is None


def test_the_review_bar_never_counts_without_scores(ui: Ui) -> None:
    entry = ui.add(segments=SEGMENTS, text=TEXT, method="WhisperX")
    ui.window.select_entry(entry.id)
    ui.pump()
    bar = ui.window._entry_view.review_bar

    assert bar.lbl_status.cget("text") == (
        "Confidence data isn’t available for this transcript"
    )
    assert not bar.frm_arrows.grid_info()

    # Not even that, without the highlighting
    ui.window._entry_view._toggle_low_confidence()
    assert not bar.grid_info()


def test_the_source_and_the_date_of_the_translation_are_next_to_its_language(
    ui: Ui,
) -> None:
    from models.translation import TranscriptTranslation

    translation = TranscriptTranslation(
        "es", "Hola", provider="deepl", created_at="2026-10-04T13:30:00+00:00"
    )
    entry = ui.add(
        segments=SEGMENTS,
        text=TEXT,
        translations={translation.language: translation.to_dict()},
    )
    ui.window.select_entry(entry.id)
    ui.pump()
    panel = ui.window._entry_view.translation_panel
    source = panel.lbl_source.cget("text")
    assert source.startswith("DeepL · ")
    assert "Oct " in source
    assert "October" not in source
    assert not panel.lbl_details.winfo_ismapped()


def test_the_dialog_to_translate_asks_for_the_key_of_the_provider(ui: Ui) -> None:
    from utils.env_keys import EnvKeys
    from views.transcript.translation_panel import TranslateDialog
    from views.widgets.window import place_dialog

    asked: list[EnvKeys] = []
    dialog = TranslateDialog(
        ui.window,
        source_language="en",
        on_set_api_key=asked.append,
        on_settings=lambda: None,
    )
    # Shown as `wait` does, without waiting for it to close
    place_dialog(dialog, ui.window)
    ui.pump()
    dialog.omn_provider.set("DeepL")
    dialog._refresh()
    ui.pump()
    assert dialog.btn_ok.cget("state") == "disabled"
    assert dialog.lbl_key.cget("text") == "No API key for DeepL."
    # The button to set it is next to the warning
    assert dialog.btn_key.winfo_ismapped()
    assert abs(dialog.btn_key.winfo_y() - dialog.lbl_key.winfo_y()) < 4
    dialog._set_api_key()
    assert asked == [EnvKeys.DEEPL_API_KEY]

    dialog.omn_provider.set("Ollama (local)")
    dialog._refresh()
    ui.pump()
    assert dialog.btn_ok.cget("state") == "normal"
    assert not dialog.frm_key.winfo_ismapped()
    assert dialog.lbl_hint.cget("text") == "Uses the model llama3.2."
    dialog._ok()
    assert dialog._result is not None
    assert dialog._result.provider == "ollama"
    # The interface is in English, as is the transcription
    assert dialog._result.language == "es"
    ui.pump()


def test_the_dialog_to_translate_explains_each_provider(ui: Ui) -> None:
    from views.transcript.translation_panel import TranslateDialog

    dialog = TranslateDialog(
        ui.window,
        source_language="en",
        on_set_api_key=lambda _key: None,
        on_settings=lambda: None,
    )
    heights = []
    hints = {}
    # Without a key, with one (it runs locally), and translated by the user
    for label in ("DeepL", "Ollama (local)", "Manual", "DeepL"):
        dialog.omn_provider.set(label)
        dialog._refresh()
        ui.pump()
        heights.append(dialog.winfo_height())
        hints[label] = dialog.lbl_hint.cget("text")

    assert hints["Manual"] == (
        "Creates empty segments with the original timestamps for you to fill in."
    )
    # The dialog keeps its size when the provider changes
    assert len(set(heights)) == 1
    dialog._close()
    ui.pump()


def test_the_button_of_the_key_is_shorter_if_its_warning_doesnt_fit(ui: Ui) -> None:
    from views.transcript.translation_panel import TranslateDialog

    def open_dialog() -> TranslateDialog:
        dialog = TranslateDialog(
            ui.window,
            source_language="en",
            on_set_api_key=lambda _key: None,
            on_settings=lambda: None,
        )
        dialog.omn_provider.set(dialog._providers.label("deepl"))
        dialog._refresh()
        ui.pump()
        return dialog

    dialog = open_dialog()
    assert dialog.btn_key.cget("text") == "Set API key…"
    dialog._close()
    # "API-Schlüssel festlegen…" leaves too little room for the warning
    with interface_language(ui, "de"):
        dialog = open_dialog()
        assert dialog.btn_key.cget("text") == "Festlegen…"
        # The warning isn't taller than the hints of the other providers
        assert dialog.lbl_key.winfo_height() <= 30
        dialog._close()


def test_the_languages_are_searched_in_a_dropdown_of_the_window(
    ui: Ui, tmp_path: Path
) -> None:
    ui.window.show_source(AudioSource.DIRECTORY)
    ui.pump()
    folder_view = ui.window._new_views[AudioSource.DIRECTORY]
    folder_view.set_source(str(tmp_path), should_advance=True)
    ui.pump()
    form = folder_view.frm_settings
    card = next(card for card in form._cards if isinstance(card, LanguageCard))
    menu = card.omn_input_language

    menu._clicked()
    ui.pump()
    dropdown = menu._dropdown
    assert dropdown.winfo_toplevel() is menu.winfo_toplevel()
    assert dropdown.winfo_ismapped()
    # It's inside the window
    assert dropdown.winfo_x() >= 0
    assert dropdown.winfo_x() + dropdown.winfo_width() <= ui.window.winfo_width()
    assert dropdown.winfo_y() >= 0
    assert dropdown.winfo_y() + dropdown.winfo_height() <= ui.window.winfo_height()

    dropdown._search_variable.set("spani")
    dropdown._select_highlighted()
    ui.pump()
    assert not dropdown.winfo_exists()
    assert menu.get() == "Spanish"

    # A click outside closes it, without selecting anything
    menu._clicked()
    ui.pump()
    dropdown = menu._dropdown
    ui.window.top_bar.event_generate("<Button-1>", x=1, y=1)
    ui.pump()
    assert not dropdown.winfo_exists()
    assert menu.get() == "Spanish"

    # Clicking the option menu again closes it too
    menu._clicked()
    ui.pump()
    dropdown = menu._dropdown
    menu._clicked()
    ui.pump()
    assert not dropdown.winfo_exists()


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
    srt = output._file_type_checkboxes["srt"]
    assert srt.cget("state") == "disabled"
    assert output._file_type_checkboxes["json"].cget("state") == "normal"
    assert output.lbl_file_types_hint.winfo_ismapped()
    settings = form.get_settings()
    assert settings.openai_model == "gpt-transcribe"
    assert "srt" not in settings.effective_output_file_types
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


def test_the_saved_description_is_shown_without_the_placeholder(ui: Ui) -> None:
    import dataclasses

    changes: list[None] = []
    config = dataclasses.replace(
        ConfigManager.get_config_transcription(), prompt="A talk about speech."
    )
    card = ContextCard(ui.window, lambda: changes.append(None), config)
    ui.pump()

    assert card.tbx_prompt.get("1.0", "end-1c") == "A talk about speech."
    assert card.tbx_prompt.get_text() == "A talk about speech."
    settings = TranscriptionSettings()
    card.update_settings(settings)
    assert settings.prompt == "A talk about speech."

    # Emptied, it shows the placeholder again, which isn't taken as its text
    card.tbx_prompt.set_text("")
    ui.pump()
    assert card.tbx_prompt.get("1.0", "end-1c")
    assert card.tbx_prompt.get_text() == ""
    assert not changes
    card.destroy()
    ui.pump()


def test_a_failed_transcription_goes_back_to_its_settings(
    ui: Ui, audio_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ui.window._jobs, "_run_next", lambda: None)
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
    assert ui.window._jobs._queue[-1] == entry.id
    ui.window._jobs._queue.clear()


def test_a_summary_finished_while_the_language_changes_is_shown_in_it(
    ui: Ui, summarizer: FakeSummarizer
) -> None:
    summary = TranscriptSummary("A short talk.", (), (), "model", "")
    summarizer.summary = summary
    summarizer.has_summarized.clear()
    entry = ui.add(segments=SEGMENTS, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()

    # The summary finishes, but its result isn't shown before the language
    # changes, since the events of Tk aren't processed in the meantime
    ui.window._history.summarize_entry(entry.id)
    assert summarizer.has_summarized.wait(5)
    time.sleep(0.1)
    with interface_language(ui, "es"):
        ui.pump(0.5)

        assert ui.store.get(entry.id).summary == summary.to_dict()
        assert not ui.window._history.is_summarizing(entry.id)
        assert ui.window.top_bar._status_message == "El resumen de «Entry» está listo."


def test_the_preferences_change_the_interface_language(ui: Ui) -> None:
    ui.window.show_preferences(GENERAL_TAB)
    ui.pump()
    preferences = ui.window._preferences
    try:
        # As if the user chose it in the menu of the languages
        preferences._on_language_change("es")
        ui.pump()

        # The dialog where it was changed stays open, in the new language
        assert ConfigManager.get_config_system().ui_language == "es"
        assert preferences.winfo_exists()
        assert preferences.title() == "Preferencias"
        assert preferences.tabs.get() == "General"
        preferences.show_tab(AI_TAB)
        assert preferences.tabs.get() == "IA"
        for tab in preferences._tab_names:
            preferences.show_tab(tab)
            ui.pump(0.3)
            assert not untranslated_texts(preferences), tab
    finally:
        preferences._on_language_change("en")
        preferences.destroy()
        ui.pump()

    assert ConfigManager.get_config_system().ui_language == "en"
    assert ui.window.sidebar.lbl_count.cget("text") == "0 transcriptions"


def test_the_buttons_of_the_api_keys_say_what_they_do(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from utils.env_keys import EnvKeys

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    ui.window.show_preferences(API_KEYS_TAB)
    ui.pump()
    preferences = ui.window._preferences
    try:
        buttons = preferences._key_buttons
        assert buttons[EnvKeys.OPENAI_API_KEY][0].cget("text") == "Change API key…"
        assert buttons[EnvKeys.DEEPL_API_KEY][0].cget("text") == "Set API key…"
        # They're as wide as each other, whatever they say
        widths = {button.winfo_width() for row in buttons.values() for button in row}
        assert len(widths) == 1
    finally:
        preferences.destroy()
        ui.pump()


def test_a_provider_without_a_key_leaves_no_space_for_its_button(ui: Ui) -> None:
    import tkinter

    from views.widgets.option_menu import CTkOptionMenu

    ui.window.show_preferences(AI_TAB)
    ui.pump()
    preferences = ui.window._preferences
    try:
        tab = preferences.tabs.tab(preferences._tab_names[AI_TAB])

        def menus(widget: Any) -> list[Any]:
            found = [widget] if isinstance(widget, CTkOptionMenu) else []
            for child in widget.winfo_children():
                found += menus(child)
            return found

        # The menu of the provider of the summaries
        menu = menus(tab)[0]
        row = menu.master

        def gap() -> int:
            ui.pump()
            return row.winfo_width() - (menu.winfo_x() + menu.winfo_width())

        assert gap() > 0
        menu._command("Ollama (local)")
        assert gap() == 0
        menu._command("OpenAI")
        assert gap() > 0

        # The buttons of the keys keep their size while the provider changes
        resized: list[int] = []
        for buttons in preferences._key_buttons.values():
            for button in buttons:
                tkinter.Misc.bind(
                    button, "<Configure>", lambda e: resized.append(e.width), "+"
                )
        menu._command("Claude")
        ui.pump()
        assert not resized
    finally:
        preferences.destroy()
        ui.pump()


def test_the_preferences_change_the_size_of_the_interface(ui: Ui) -> None:
    ui.window.show_preferences(GENERAL_TAB)
    ui.pump()
    preferences = ui.window._preferences
    default_scaling = ui.window.sidebar._get_widget_scaling()
    try:
        # As if the user chose it in the menu of the sizes
        preferences._on_scale_change(125)
        ui.pump()

        assert ConfigManager.get_config_system().ui_scale == 125
        assert ui.window.sidebar._get_widget_scaling() == default_scaling * 1.25
        assert preferences._get_widget_scaling() == default_scaling * 1.25
        assert not ui.errors
    finally:
        preferences._on_scale_change(100)
        preferences.destroy()
        ui.pump()

    assert ui.window.sidebar._get_widget_scaling() == default_scaling


def test_the_open_views_keep_their_state_in_another_language(
    ui: Ui, tmp_path: Path
) -> None:
    entry = ui.add(segments=SEGMENTS, text=TEXT)
    ui.window.show_source(AudioSource.DIRECTORY)
    view = ui.window._new_views[AudioSource.DIRECTORY]
    view.set_source(str(tmp_path), should_advance=True)
    ui.pump()
    form = view.frm_settings
    context = next(card for card in form._cards if isinstance(card, ContextCard))
    context.ent_keywords.delete(0, "end")
    context.ent_keywords.insert(0, "Audiotext")
    ui.window.show_preferences()
    ui.pump()

    with interface_language(ui, "es"):
        # The page, the history and the dialog are shown in Spanish
        assert view.btn_back.cget("text") == "Atrás"
        assert ui.window.sidebar.lbl_count.cget("text") == "1 transcripción"
        assert not untranslated_texts(ui.window)
        assert not untranslated_texts(ui.window._preferences)
        # What the user chose and typed is kept
        assert ui.window._new_views[AudioSource.DIRECTORY] is view
        assert view._step == 1
        assert context.ent_keywords.get() == "Audiotext"
        assert ui.window._preferences.winfo_exists()

        # The views opened afterwards, and their options, are in Spanish too
        ui.window.select_entry(entry.id)
        ui.pump()
        transcript = ui.window._entry_view
        assert transcript.seg_mode.cget("values") == [
            "Subtítulos",
            "Texto plano",
            "Resumen",
            "Preguntar",
        ]
        transcript._on_mode_change(transcript._modes.value("Resumen"))
        ui.pump()
        assert transcript._mode == "summary"
        assert not untranslated_texts(ui.window)

    # The mode chosen is kept when the language changes back
    assert transcript.seg_mode.get() == "Summary"
    assert transcript._modes.get() == "summary"
    ui.window._preferences.destroy()


def test_the_language_changes_while_a_transcription_runs(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ui.window._jobs, "_run_next", lambda: None)
    jobs = ui.window._jobs
    entry = ui.add(title="talk.mp3", status=EntryStatus.PROCESSING)
    jobs._job = Job(entry_id=entry.id, is_folder=False, is_mic=False)
    jobs.on_transcription_progress(i18n._("Isolating the speech…"), 0.25)
    ui.window.select_entry(entry.id)
    ui.window.show_preferences()
    ui.pump()
    preferences = ui.window._preferences
    try:
        preferences._on_language_change("es")
        ui.pump()

        # The progress reported next is in the new language
        jobs.on_transcription_progress(i18n._("Isolating the speech…"), 0.5)
        ui.pump()
        card = ui.window._entry_view.card
        assert card.lbl_message.cget("text") == "Aislando la voz…"
        assert not untranslated_texts(ui.window)
        assert not untranslated_texts(preferences)
        assert jobs.is_busy()
    finally:
        preferences._on_language_change("en")
        preferences.destroy()
        jobs._job = None
        ui.pump()


def test_every_page_is_shown_in_another_language(ui: Ui, audio_file: Path) -> None:
    from handlers.translation_handler import MANUAL
    from models.translation import TranscriptTranslation

    # A translation with a segment left to translate, which has a text in its place
    translation = TranscriptTranslation(
        "fr", "Bonjour\n\nAu revoir", translated("Bonjour", "", "Au revoir"), MANUAL
    )
    # Their titles aren't texts of the interface, which would be taken as such
    entries = [
        ui.add(title="Broken", status=EntryStatus.FAILED, error="Boom"),
        ui.add(title="Next", status=EntryStatus.QUEUED),
        ui.add(
            title="Talk",
            segments=SEGMENTS,
            text=TEXT,
            media_path=str(audio_file),
            translations={translation.language: translation.to_dict()},
        ),
        ui.add(
            title="Recordings",
            kind=AudioSource.DIRECTORY.value,
            source=str(audio_file.parent),
        ),
    ]
    ui.add(title="talk.wav", parent_id=entries[-1].id, text="x")
    pages: list[Callable[[], None]] = [ui.window.show_welcome]
    pages += [
        partial(ui.window.show_source, source)
        for source in AudioSource
        if source != AudioSource.WATCH
    ]
    pages += [partial(ui.window.select_entry, entry.id) for entry in entries]
    # Opened in English first, so the pages that are kept are translated in place
    for show_page in pages:
        show_page()
        ui.pump()
    # The summary is shown while the language changes
    ui.window.select_entry(entries[2].id)
    ui.pump()
    ui.window._entry_view._on_mode_change("summary")
    ui.pump()

    with interface_language(ui, "es"):
        assert ui.window._entry_view.summary_panel.winfo_ismapped()
        assert not untranslated_texts(ui.window)
        transcript = ui.window._entry_view
        transcript._on_mode_change("transcript")
        ui.pump()
        assert transcript.translation_panel.omn_language.get().startswith("Francés")
        assert (
            "Sin traducir todavía"
            in transcript.translation_panel.text.tbx_transcript.get("1.0", "end")
        )
        assert not untranslated_texts(ui.window)
        for show_page in pages:
            show_page()
            ui.pump(0.3)
            assert not untranslated_texts(ui.window)


def test_a_new_version_is_shown_when_checking_for_updates(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No new version was found at startup
    assert not ui.window.top_bar.btn_update.winfo_ismapped()

    # Nor is it shown when the scaling changes (e.g. on Windows, at startup)
    ctk.set_widget_scaling(1.25)
    ui.pump()
    ctk.set_widget_scaling(1.0)
    ui.pump()
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

    # The new version is shown in another language too
    with interface_language(ui, "es"):
        assert ui.window.top_bar.btn_update.winfo_ismapped()
        assert (
            ui.window.top_bar.btn_update.cget("text")
            == "La versión 99.0.0 está disponible"
        )
    assert ui.window.top_bar.btn_update.cget("text") == "Version 99.0.0 is available"


def test_a_notification_is_sent_when_a_transcription_is_ready(
    ui: Ui,
    monkeypatch: pytest.MonkeyPatch,
    sent_notifications: list[tuple[str, str]],
) -> None:
    monkeypatch.setattr(ui.window._jobs, "_run_next", lambda: None)

    def finish(title: str, is_cancel_requested: bool = False) -> None:
        entry = ui.add(title=title, status=EntryStatus.PROCESSING)
        ui.window._jobs._job = Job(
            entry_id=entry.id,
            is_folder=False,
            is_mic=False,
            is_cancel_requested=is_cancel_requested,
        )
        ui.window._jobs._finish_job(None)

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
        ui.window._jobs._job = Job(entry_id=entry.id, is_folder=True, is_mic=False)
        ui.window._jobs.on_file_transcribed(tmp_path / file_name, "Hello", [], "en")
        ui.window._jobs._job = None

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


def test_the_copy_buttons_show_a_tick_when_they_copy(ui: Ui) -> None:
    from models.translation import TranscriptTranslation

    translation = TranscriptTranslation(
        "es", "Hola", translated("Hola", "", ""), "manual"
    )
    entry = ui.add(
        segments=SEGMENTS,
        text=TEXT,
        translations={translation.language: translation.to_dict()},
    )
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view

    view._on_copy()
    view._copy_translation()
    assert ui.window.clipboard_get() == "Hola"
    # Each button shows it by itself
    assert set(view._copy_feedback_after_ids) == {
        view.btn_copy,
        view.translation_panel.btn_copy,
    }
    # As if its timer ran, which is cancelled so it doesn't run once the view is
    # destroyed, when its command no longer exists
    view.after_cancel(view._copy_feedback_after_ids[view.btn_copy])
    view._reset_copy_button(view.btn_copy)
    assert set(view._copy_feedback_after_ids) == {view.translation_panel.btn_copy}


def test_the_shortcuts_act_on_the_text_being_worked_on(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.translation import TranscriptTranslation
    from views.transcript.transcript_view import TranscriptView

    translation = TranscriptTranslation(
        "es", "Hola", translated("Hola", "", ""), "manual"
    )
    entry = ui.add(
        segments=SEGMENTS,
        text=TEXT,
        translations={translation.language: translation.to_dict()},
    )
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    anchors: list[Any] = []
    monkeypatch.setattr(
        TranscriptView,
        "_popup_below",
        staticmethod(lambda _menu, widget: anchors.append(widget)),
    )

    # The transcription, until the user works on the translation
    view.focus_search()
    ui.pump()
    assert view._find_dialog is not None
    assert view._find_dialog.target.text is view.text
    ui.window.trigger_save()
    assert anchors[-1] is view.btn_export

    view.translation_panel.text.tbx_transcript._textbox.event_generate("<FocusIn>")
    view.focus_search()
    ui.pump()
    assert view._find_dialog.target.text is view.translation_panel.text
    ui.window.trigger_save()
    assert anchors[-1] is view.translation_panel.btn_export

    # Not once the translation is hidden
    view._set_translation_visible(False)
    ui.pump()
    ui.window.trigger_save()
    assert anchors[-1] is view.btn_export

    view._set_translation_visible(True)
    ui.pump()
    view.text.tbx_transcript._textbox.event_generate("<ButtonPress-1>")
    view.focus_search()
    ui.pump()
    assert view._find_dialog is not None
    assert view._find_dialog.target.text is view.text


def test_the_texts_are_generated_again_from_their_headers(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.translation import TranscriptTranslation
    from views.transcript.transcript_view import TranscriptView

    translation = TranscriptTranslation(
        "es", "Hola", translated("Hola", "", ""), "deepl", model="m"
    )
    entry = ui.add(
        segments=SEGMENTS,
        text=TEXT,
        translations={translation.language: translation.to_dict()},
    )
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    panel = view.translation_panel

    translations: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        view._actions.transcript,
        "translate_entry",
        lambda *args: translations.append(args),
    )
    retried: list[str] = []
    monkeypatch.setattr(view._actions.jobs, "retry_entry", retried.append)
    summarized: list[str] = []
    monkeypatch.setattr(view._actions.transcript, "summarize_entry", summarized.append)
    # Each one only after confirming it, since the current one is replaced
    answers = iter([False, True] * 3)
    monkeypatch.setattr(
        corrections.messagebox, "askyesno", lambda *_a, **_k: next(answers)
    )

    assert panel.btn_regenerate.cget("state") == ctk.NORMAL
    panel.btn_regenerate.invoke()
    panel.btn_regenerate.invoke()
    assert translations == [(entry.id, "es", "deepl", "m")]

    view.btn_regenerate.invoke()
    view.btn_regenerate.invoke()
    assert retried == [entry.id]

    view._regenerate_summary()
    view._regenerate_summary()
    assert summarized == [entry.id]

    # Not in the menu anymore
    menus: list[tk.Menu] = []
    monkeypatch.setattr(
        TranscriptView,
        "_popup_below",
        staticmethod(lambda menu, _widget: menus.append(menu)),
    )
    view._show_more_menu()
    labels = [
        menus[0].entrycget(i, "label")
        for i in range(menus[0].index("end") + 1)
        if menus[0].type(i) != "separator"
    ]
    assert "Transcribe again" not in labels
    menus[0].destroy()


def test_the_summary_can_be_searched(ui: Ui) -> None:
    summary = TranscriptSummary(
        "A short talk.", ("They talk",), (Chapter(0, "Talk"),), "model", ""
    )
    entry = ui.add(segments=SEGMENTS, text=TEXT, summary=summary.to_dict())
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    view._on_mode_change(view._modes.value("Summary"))
    ui.pump()

    # ⌘F finds in the summary while it's shown, without replacing
    view.focus_search()
    ui.pump()
    dialog = view._find_dialog
    assert dialog is not None
    assert dialog.title() == "Find in the summary"
    assert not dialog.ent_replacement.winfo_ismapped()
    dialog._find.set("talk")
    ui.pump()
    assert view.summary_panel.text.match_status == (0, 3)
    dialog.go_to_match(1)
    assert view.summary_panel.text.match_status == (1, 3)

    # The text it searches is hidden with the summary
    view._on_mode_change(view._modes.value("Plain text"))
    ui.pump()
    assert view._find_dialog is None


def test_a_manual_translation_cant_be_generated_again(ui: Ui) -> None:
    from models.translation import TranscriptTranslation

    translation = TranscriptTranslation(
        "es", "Hola", translated("Hola", "", ""), "manual"
    )
    entry = ui.add(
        segments=SEGMENTS,
        text=TEXT,
        translations={translation.language: translation.to_dict()},
    )
    ui.window.select_entry(entry.id)
    ui.pump()
    # Hidden, rather than disabled
    assert not ui.window._entry_view.translation_panel.btn_regenerate.winfo_ismapped()


def test_the_translation_scrolls_with_the_transcription(ui: Ui) -> None:
    from models.translation import TranscriptTranslation

    segments = [
        TranscriptSegment(float(i), i + 1.0, f"Segment {i}", "SPEAKER_00")
        for i in range(80)
    ]
    # Shorter texts, so the same segment is at a different height
    translated_segments = tuple(
        TranscriptSegment(s.start, s.end, f"S{i}", s.speaker)
        for i, s in enumerate(segments)
    )
    translation = TranscriptTranslation("es", "S", translated_segments, "manual")
    entry = ui.add(
        segments=segments,
        text="text",
        translations={translation.language: translation.to_dict()},
    )
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    original = view.text
    copy = view.translation_panel.text

    original.tbx_transcript.yview_moveto(0.5)
    ui.pump()
    kind, time = original.scroll_anchor()
    assert kind == "time"
    assert time > 10
    assert copy.scroll_anchor()[1] == pytest.approx(time, abs=1)

    # From the button in the header of the translation, shown pressed while on
    button = view.btn_sync_scroll
    assert button.winfo_ismapped()
    # A circle inside the handle between the panels, so its corners don't cover
    # them
    splitter = view.translation_splitter
    assert button.winfo_width() == button.winfo_height()
    assert splitter.winfo_x() <= button.winfo_x()
    assert (
        button.winfo_x() + button.winfo_width()
        <= splitter.winfo_x() + splitter.winfo_width()
    )
    assert button.cget("fg_color") != "transparent"
    button.invoke()
    assert not view._config_system.sync_scroll
    assert button.cget("fg_color") == "transparent"
    original.tbx_transcript.yview_moveto(0)
    ui.pump()
    assert copy.scroll_anchor()[1] == pytest.approx(time, abs=1)
    view._toggle_sync_scroll()
    ui.pump()
    assert copy.scroll_anchor()[1] == pytest.approx(0, abs=1)


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
    entry = ui.add(
        segments=SEGMENTS,
        text=TEXT,
        translations={translation.language: translation.to_dict()},
    )
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view

    # Each panel exports its own text, with the same formats
    menus: list[tk.Menu] = []
    monkeypatch.setattr(
        TranscriptView,
        "_popup_below",
        staticmethod(lambda menu, _widget: menus.append(menu)),
    )
    view.show_export_menu()
    view.show_translation_export_menu(view.translation_panel.btn_export)
    for menu in menus:
        # The documents, and then the video with the subtitles
        last = int(menu.index("end"))
        assert menu.entrycget(last - 2, "label") == "Word document (.docx)"
        assert menu.type(last - 1) == "separator"
        assert menu.entrycget(last, "label") == "Video with subtitles (.mp4)…"
    assert menus[0].index("end") == menus[1].index("end")
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
    entry = ui.add(
        segments=SEGMENTS,
        text=TEXT,
        translations={translation.language: translation.to_dict()},
    )
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


class FakePlayer:
    """Plays nothing: its position only moves when it's set."""

    def __init__(self) -> None:
        self.position = 0.0
        self.is_playing = False
        self.duration = 60.0
        self.speed = 1.0

    def seek(self, seconds: float) -> None:
        self.position = seconds

    def play(self) -> None:
        self.is_playing = True

    def pause(self) -> None:
        self.is_playing = False

    def toggle(self) -> None:
        self.is_playing = not self.is_playing

    def close(self) -> None:
        pass


def test_a_clip_pauses_at_its_end_unless_the_user_takes_over(ui: Ui) -> None:
    from views.transcript.player_bar import PlayerBar

    bar = PlayerBar(
        ui.window,
        on_tick=lambda _position, _is_playing: None,
        on_toggle_subtitles=lambda: None,
        on_subtitle_menu=lambda _anchor: None,
    )
    player = FakePlayer()
    bar._player = player
    try:
        bar.play_clip(-1.0, 2.0)
        assert (player.position, player.is_playing) == (0.0, True)
        player.position = 1.0
        bar.refresh()
        assert player.is_playing
        player.position = 2.0
        bar.refresh()
        assert not player.is_playing

        # Another clip replaces it, instead of stopping at both ends
        bar.play_clip(5.0, 8.0)
        bar.play_clip(10.0, 13.0)
        player.position = 8.5
        bar.refresh()
        assert player.is_playing

        # Playing, pausing or moving the audio cancels the end of the clip
        for take_over in (
            lambda: (bar.toggle_playback(), bar.toggle_playback()),
            lambda: bar.seek_relative(1),
            lambda: bar.seek(11.0),
            lambda: bar.play_from(11.0),
        ):
            bar.play_clip(10.0, 13.0)
            take_over()
            player.play()
            player.position = 13.5
            bar.refresh()
            assert player.is_playing, take_over
    finally:
        bar._player = None
        bar.destroy()


def test_return_only_accepts_a_visible_word(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Long enough to scroll the word away
    filler = [
        TranscriptSegment(10.0 + idx, 10.5 + idx, f"Line {idx}.") for idx in range(80)
    ]
    entry = ui.add(segments=[*review_segments()[:1], *filler], text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    monkeypatch.setattr(view.player, "play_clip", lambda *_clip: None)
    view.go_to_low_confidence(1)
    ui.pump()

    view.text.tbx_transcript._textbox.yview_moveto(1.0)
    ui.pump()
    assert not view.text.is_flagged_visible(view.reviewer.current)
    # The first Return shows the word, without accepting it
    press_return(ui, view)
    assert view.review_bar.review.remaining == 1
    assert view.text.is_flagged_visible(view.reviewer.current)
    press_return(ui, view)
    assert view.review_bar.review.remaining == 0


def test_undoing_goes_back_to_the_word_and_plays_it(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = open_review(ui, monkeypatch)
    clips: list[tuple[float, float]] = []
    monkeypatch.setattr(view.player, "play_clip", lambda *clip: clips.append(clip))

    view.go_to_low_confidence(1)
    view.reviewer.accept_current()
    # It went on to the next one
    assert current_text(view) == "Nice to meet you."
    assert view.reviewer.undo()
    assert current_text(view) == "wisper"
    assert clips == [(-1.0, 2.5), (0.0, 4.5), (-1.0, 2.5)]


def test_replacing_from_the_find_window_reviews_quietly(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = open_review(ui, monkeypatch)
    clips: list[tuple[float, float]] = []
    focuses: list[None] = []
    view.go_to_low_confidence(1)
    monkeypatch.setattr(view.player, "play_clip", lambda *clip: clips.append(clip))
    monkeypatch.setattr(view.text, "focus_text", lambda: focuses.append(None))

    # Replacing the word gone to is a review: it can be undone
    view.text.search("wisper")
    view._replace_current("Whisper")
    ui.pump()
    assert view.review_bar.review.remaining == 2
    assert current_text(view) == "Nice to meet you."
    assert view.review_bar.btn_undo.grid_info()
    # But the window to find keeps the focus, and the audio isn't played
    assert (clips, focuses) == ([], [])
    assert view.reviewer.undo()
    assert current_text(view) == "wisper"

    # Replacing a text everywhere isn't, even if it corrects the word gone to
    clips.clear()
    view._replace_all("wisper", "Whisper", False)
    ui.pump()
    # The word, and the segment scored whole that says it
    assert view.review_bar.review.remaining == 1
    assert current_text(view) == "Nice to meet you."
    assert not view.review_bar.btn_undo.grid_info()
    assert not view.reviewer.undo()
    assert clips == []


def test_a_word_no_longer_flagged_cant_be_accepted(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = open_review(ui, monkeypatch)
    view.go_to_low_confidence(1)
    assert current_text(view) == "wisper"

    # Its score (0.3) is no longer below the threshold, unlike the others
    view._set_low_confidence_threshold(25)
    assert current_text(view) is None
    press_return(ui, view)
    review = view.review_bar.review
    assert (review.remaining, review.total) == (2, 2)
    assert not view.reviewer.accept_current()


def test_closing_the_app_writes_the_pending_reviews() -> None:
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app import App

    # Command + Q and the Quit item of the menu close it the same way
    app = SimpleNamespace(
        _history_store=MagicMock(),
        _save_window_state_job=None,
        _save_window_state=MagicMock(),
        destroy=MagicMock(),
    )

    App._on_close(app)  # type: ignore[arg-type]

    app._history_store.flush.assert_called_once()
    app.destroy.assert_called_once()


def shown_texts(view: Any) -> list[str]:
    """The texts of the segments that the filter doesn't hide."""
    text = view.text
    textbox = text.tbx_transcript._textbox
    return [
        segment.text
        for segment, (start, _end) in zip(
            text._segments, text._text_ranges, strict=True
        )
        if "hidden" not in textbox.tag_names(start)
    ]


def test_only_the_segments_with_words_to_review_can_be_shown(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from views.transcript.transcript_text import TranscriptText

    view = open_review(ui, monkeypatch)
    bar = view.review_bar
    renders: list[None] = []
    render = TranscriptText._render_transcript
    monkeypatch.setattr(
        TranscriptText,
        "_render_transcript",
        lambda self: (renders.append(None), render(self))[1],
    )
    all_texts = ["Hello wisper", "Nice to meet you.", "Bye wisper."]
    assert shown_texts(view) == all_texts

    bar.chk_only_flagged.toggle()
    view.go_to_low_confidence(1)
    view.reviewer.accept_current()
    # The segment just reviewed stays, until the user moves on
    assert shown_texts(view) == all_texts
    assert current_text(view) == "Nice to meet you."
    view.reviewer.accept_current()
    assert shown_texts(view) == ["Nice to meet you.", "Bye wisper."]
    view.go_to_low_confidence(1)
    assert shown_texts(view) == ["Bye wisper."]

    # None left
    view.reviewer.accept_current()
    assert shown_texts(view) == ["Bye wisper."]
    assert not view.frm_review_empty.winfo_ismapped()
    view.reviewer.set_only_flagged(True)
    ui.pump()
    assert shown_texts(view) == []
    assert view.frm_review_empty.winfo_ismapped()
    # Which can show all of them again
    [label, button] = view.frm_review_empty.winfo_children()
    assert label.cget("text") == "No low-confidence words left to review"
    button.invoke()
    ui.pump()
    assert shown_texts(view) == all_texts
    assert not view.frm_review_empty.winfo_ismapped()
    assert not bar._only_flagged_variable.get()

    # Without words to review, it doesn't hide anything
    view.reviewer.set_only_flagged(True)
    view._set_low_confidence_threshold(5)
    assert shown_texts(view) == all_texts
    # Filtering doesn't render the transcript again
    assert renders == []


def test_the_words_to_review_are_marked_on_the_timeline(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from views.transcript.player_bar import MarkKind

    view = open_review(ui, monkeypatch)

    def marks() -> list[tuple[float, MarkKind]]:
        return [(mark.seconds, mark.kind) for mark in view.player._marks]

    assert marks() == [
        (0.5, MarkKind.PENDING),
        (1.5, MarkKind.PENDING),
        (3.5, MarkKind.PENDING),
    ]
    view.go_to_low_confidence(1)
    view.reviewer.accept_current()
    assert marks() == [
        (0.5, MarkKind.DONE),
        (1.5, MarkKind.CURRENT),
        (3.5, MarkKind.PENDING),
    ]
    # Clicking a mark goes to its word
    view.reviewer.on_mark_click(2)
    assert current_text(view) == "Bye wisper."
    assert marks()[2] == (3.5, MarkKind.CURRENT)
    # They follow the threshold
    view._set_low_confidence_threshold(15)
    assert marks() == [(3.5, MarkKind.CURRENT)]
    view._toggle_low_confidence()
    assert marks() == []


def test_the_marks_are_drawn_by_kind_and_can_be_clicked(ui: Ui) -> None:
    from views.transcript.player_bar import MarkKind, PlayerBar, TimelineMark

    bar = PlayerBar(
        ui.window,
        on_tick=lambda _position, _is_playing: None,
        on_toggle_subtitles=lambda: None,
        on_subtitle_menu=lambda _anchor: None,
    )
    bar.grid(row=9, column=0, sticky="ew")
    bar._player = FakePlayer()
    clicked: list[int] = []
    try:
        ui.pump()
        bar.set_marks(
            [
                TimelineMark(15.0, MarkKind.DONE),
                TimelineMark(30.0, MarkKind.PENDING),
                TimelineMark(45.0, MarkKind.CURRENT),
            ],
            {kind: ("#000000", "#FFFFFF") for kind in MarkKind},
            clicked.append,
        )
        canvas = bar.cnv_marks
        heights = sorted(
            round(canvas.coords(item)[3] - canvas.coords(item)[1])
            for item in canvas.find_withtag("mark")
        )
        # They differ in height, not only in color
        assert heights == [6, 10, 16]

        x = bar._mark_x(30.0)
        assert x is not None
        bar._on_marks_click(type("Event", (), {"x": x + 3})())
        bar._on_marks_click(type("Event", (), {"x": x + 40})())
        assert clicked == [1]
    finally:
        bar._player = None
        bar.destroy()


def click_flagged(ui: Ui, view: Any, text: str) -> None:
    """Clicks a low confidence text, which opens its popover."""
    textbox = view.text.tbx_transcript._textbox
    [flagged] = [t for t in view.reviewer.review.unreviewed if t.text == text]
    start = view.text._flagged_ranges(flagged)[0][0]
    textbox.mark_set(tk.CURRENT, f"{start}+1c")
    view.text._on_click(0)
    ui.pump()


def test_a_word_can_be_corrected_where_it_is(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.transcript_segment import ReviewMark

    view = open_review(ui, monkeypatch)
    popover = view.word_popover
    segment_clicks: list[float] = []
    monkeypatch.setattr(view, "_play_from", segment_clicks.append)

    click_flagged(ui, view, "wisper")
    assert popover.is_open
    assert popover.winfo_ismapped()
    assert popover.ent_text.get() == "wisper"
    # The word is the one gone to, but it's the field that has the focus
    assert current_text(view) == "wisper"
    assert view.focus_get() is popover.ent_text._entry

    # Escape closes it without changes, back to the transcript
    popover.ent_text._entry.event_generate("<Escape>")
    ui.pump()
    assert not popover.is_open
    assert view.focus_get() is view.text.tbx_transcript._textbox
    assert view.review_bar.review.remaining == 3

    # Return saves the correction, which reviews it, and goes to the next word
    click_flagged(ui, view, "wisper")
    popover.ent_text.delete(0, "end")
    popover.ent_text.insert(0, "Whisper")
    popover.ent_text._entry.event_generate("<Return>")
    ui.pump()
    assert not popover.is_open
    word = view._entry.segments[0].words[1]
    assert (word.text, word.score, word.reviewed) == ("Whisper", 0.3, ReviewMark.EDITED)
    assert current_text(view) == "Nice to meet you."
    assert view.focus_get() is view.text.tbx_transcript._textbox
    # Which can be undone
    assert view.reviewer.undo()
    assert view._entry.segments[0].text == "Hello wisper"

    # Unchanged, Return accepts it
    click_flagged(ui, view, "wisper")
    popover.ent_text._entry.event_generate("<Return>")
    ui.pump()
    assert view._entry.segments[0].words[1].reviewed == ReviewMark.ACCEPTED

    # A segment scored whole can't be left without text
    click_flagged(ui, view, "Nice to meet you.")
    popover.ent_text.delete(0, "end")
    popover._on_return(None)
    assert popover.is_open
    popover.btn_accept.invoke()
    ui.pump()
    assert not popover.is_open
    assert view._entry.segments[1].reviewed == ReviewMark.ACCEPTED

    # Clicking away only closes it, without playing
    click_flagged(ui, view, "Bye wisper.")
    view._on_segment_click(0)
    assert not popover.is_open
    assert segment_clicks == []
    assert view.review_bar.review.remaining == 1


def test_the_popover_replays_the_word(ui: Ui, monkeypatch: pytest.MonkeyPatch) -> None:
    view = open_review(ui, monkeypatch)
    clips: list[tuple[float, float]] = []
    monkeypatch.setattr(view.player, "play_clip", lambda *clip: clips.append(clip))

    click_flagged(ui, view, "wisper")
    view.word_popover.btn_replay.invoke()
    # Played when it's opened (with auto-play on) and again
    assert clips == [(-1.0, 2.5), (-1.0, 2.5)]


def test_the_marks_stay_aligned_with_the_slider_when_it_resizes(ui: Ui) -> None:
    from views.transcript.player_bar import MarkKind, PlayerBar, TimelineMark

    window = ctk.CTkToplevel(ui.window)
    bar = PlayerBar(
        window,
        on_tick=lambda _position, _is_playing: None,
        on_toggle_subtitles=lambda: None,
        on_subtitle_menu=lambda _anchor: None,
    )
    bar.pack(fill="x")
    player = FakePlayer()
    bar._player = player
    bar.sld_position.configure(to=player.duration)
    slider = bar.sld_position
    try:
        bar.set_marks(
            [TimelineMark(seconds, MarkKind.PENDING) for seconds in (0, 30, 60)],
            {kind: ("#000000", "#FFFFFF") for kind in MarkKind},
            lambda _idx: None,
        )
        for width in (900, 1400, 640):
            window.geometry(f"{width}x160")
            ui.pump()
            assert bar.cnv_marks.winfo_x() == slider.winfo_x()
            assert bar.cnv_marks.winfo_width() == slider.winfo_width()
            drawn = sorted(
                (lambda coords: (coords[0] + coords[2]) / 2)(bar.cnv_marks.coords(item))
                for item in bar.cnv_marks.find_withtag("mark")
            )
            for seconds, mark_x in zip((0, 30, 60), drawn, strict=True):
                # Where the button of the slider is drawn at that moment
                slider.set(seconds)
                ui.pump()
                canvas = slider._canvas
                points = canvas.coords(canvas.find_withtag("slider_parts")[0])[0::2]
                assert mark_x == pytest.approx((min(points) + max(points)) / 2, abs=1)
    finally:
        bar._player = None
        window.destroy()


def test_a_search_shows_the_segment_it_goes_to(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = TranscriptSegment(6.0, 7.0, "Plain words here.")
    entry = ui.add(segments=[*review_segments(), plain], text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    monkeypatch.setattr(view.player, "play_clip", lambda *_clip: None)
    view.review_bar.chk_only_flagged.toggle()
    assert "Plain words here." not in shown_texts(view)

    view.text.search("Plain")
    assert "Plain words here." in shown_texts(view)
    # Until the user goes to another word
    view.go_to_low_confidence(1)
    assert "Plain words here." not in shown_texts(view)


def test_the_popover_doesnt_remove_words(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = open_review(ui, monkeypatch)
    popover = view.word_popover
    bells: list[None] = []
    monkeypatch.setattr(view, "bell", lambda: bells.append(None))

    click_flagged(ui, view, "wisper")
    popover.ent_text.delete(0, "end")
    popover._on_return(None)
    assert popover.is_open
    assert bells == [None]
    assert view._entry.segments[0].text == "Hello wisper"


def test_another_word_switches_the_popover_discarding_what_was_typed(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = open_review(ui, monkeypatch)
    popover = view.word_popover

    click_flagged(ui, view, "wisper")
    popover.ent_text.insert("end", "typed")
    click_flagged(ui, view, "Bye wisper.")

    assert popover.is_open
    assert popover.ent_text.get() == "Bye wisper."
    assert current_text(view) == "Bye wisper."
    assert view._entry.segments == review_segments()
    assert view.review_bar.review.remaining == 3
    # A whole segment takes a wider field
    assert popover.ent_text.cget("width") > 200


def test_the_popover_stays_inside_the_text(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = open_review(ui, monkeypatch)
    popover = view.word_popover
    anchor = view.text.text_widget
    click_flagged(ui, view, "wisper")
    width, height = anchor.winfo_width(), anchor.winfo_height()

    # At the bottom right of the text, it's shown above the word, inside it
    popover.place_at(anchor, (width - 5, height - 30, height - 10))
    ui.pump()
    info = popover.place_info()
    x, y = int(info["x"]), int(info["y"])
    assert x + popover.winfo_reqwidth() <= width
    assert y + popover.winfo_reqheight() <= height - 30
    assert x >= 0 and y >= 0


def test_the_popover_closes_when_its_word_moves_or_goes(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from views.transcript.transcript_text import PLAIN_TEXT_MODE

    view = open_review(ui, monkeypatch)
    popover = view.word_popover

    def reopen(case: str = "") -> None:
        click_flagged(ui, view, "wisper")
        assert popover.is_open, case

    window = ui.window.winfo_toplevel()

    def resize_window() -> None:
        # A maximized window (as the app opens by default) ignores a new size on
        # Windows, so it's restored first, like the user would
        size = (window.winfo_width(), window.winfo_height())
        window.state("normal")
        ui.pump()
        window.geometry(f"{window.winfo_width() - 40}x{window.winfo_height()}")
        ui.pump()
        assert (window.winfo_width(), window.winfo_height()) != size

    closes = {
        "switching to another tab": lambda: view._on_mode_change(PLAIN_TEXT_MODE),
        # Its word is no longer below the threshold
        "raising the threshold": lambda: view._set_low_confidence_threshold(25),
        "turning the highlighting off": view._toggle_low_confidence,
        "rendering the transcript again": view._toggle_precise_timestamps,
        # The text wraps again
        "resizing the window": resize_window,
    }
    for case, close in closes.items():
        view._on_mode_change("transcript")
        view._config_system.highlight_low_confidence = True
        view._set_low_confidence_threshold(40)
        # Shown before it's clicked
        ui.pump()
        reopen(case)
        close()
        ui.pump()
        assert not popover.is_open, case
        assert not popover.winfo_ismapped(), case

    # And with the transcription, when another one is shown
    view._on_mode_change("transcript")
    ui.pump()
    reopen()
    ui.window.select_entry(ui.add(segments=SEGMENTS, text=TEXT).id)
    ui.pump()
    assert not popover.winfo_exists()


def test_the_popover_replays_with_a_key(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    from views.style import theme

    view = open_review(ui, monkeypatch)
    clips: list[tuple[float, float]] = []
    click_flagged(ui, view, "wisper")
    monkeypatch.setattr(view.player, "play_clip", lambda *clip: clips.append(clip))

    field = view.word_popover.ent_text._entry
    field.focus_force()
    ui.pump()
    field.event_generate(f"<{theme.SHORTCUT_MODIFIER}-r>")
    ui.pump()
    assert clips == [(-1.0, 2.5)]
    # Without typing in the field
    assert view.word_popover.ent_text.get() == "wisper"


def _open_text_dialog(ui: Ui) -> Any:
    """Opens a dialog to type a text without waiting for it to close."""
    from views.widgets.text_dialog import TextDialog
    from views.widgets.window import place_dialog

    dialog = TextDialog(ui.window, "Title", "Message")
    place_dialog(dialog, ui.window)
    ui.pump()
    return dialog


def _position(window: Any) -> tuple[int, int]:
    from views.widgets.window import _parse_position

    position = _parse_position(window.wm_geometry())
    assert position
    return position


def test_a_dialog_opens_centered_over_the_main_window(ui: Ui) -> None:
    dialog = _open_text_dialog(ui)
    owner = ui.window.winfo_toplevel()
    x, y = _position(dialog)
    width = dialog.winfo_width()
    centered_x = owner.winfo_rootx() + (owner.winfo_width() - width) // 2
    # Moved into the screen when the main window is partly off it, like on the
    # small screen of the CI
    assert abs(x - min(centered_x, dialog.winfo_screenwidth() - width)) <= 2
    assert owner.winfo_rooty() < y < owner.winfo_rooty() + owner.winfo_height()
    dialog.destroy()
    # It wasn't moved, so its position isn't stored
    assert not ConfigManager.get_config_system().dialog_positions


def test_a_dialog_opens_where_it_was_moved(ui: Ui) -> None:
    from views.widgets.window import POSITION_SAVE_DELAY_MS

    dialog = _open_text_dialog(ui)
    dialog.geometry("+150+120")
    ui.pump(POSITION_SAVE_DELAY_MS / 1000 + 0.3)
    assert ConfigManager.get_config_system().dialog_positions == ["TextDialog+150+120"]
    dialog.destroy()

    dialog = _open_text_dialog(ui)
    assert _position(dialog) == (150, 120)
    dialog.destroy()


def test_a_dialog_closed_right_after_it_is_moved_keeps_its_position(ui: Ui) -> None:
    dialog = _open_text_dialog(ui)
    dialog.geometry("+-40+130")
    ui.pump(0.1)
    dialog.destroy()
    assert ConfigManager.get_config_system().dialog_positions == ["TextDialog+-40+130"]


def test_a_dialog_moved_off_the_screen_opens_centered(ui: Ui) -> None:
    ConfigManager.modify_value(
        ConfigSystem.Key.SECTION,
        ConfigSystem.Key.DIALOG_POSITIONS,
        "FindDialog+200+200, TextDialog+-90000+0",
    )
    dialog = _open_text_dialog(ui)
    assert _position(dialog)[0] > 0
    dialog.destroy()


def test_questions_are_answered_with_their_sources(
    ui: Ui, answerer: FakeAnswerer, monkeypatch: pytest.MonkeyPatch
) -> None:
    from views.transcript import transcript_view

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    entry = ui.add(segments=SEGMENTS, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    view._on_mode_change(view._modes.value("Ask"))
    ui.pump()
    panel = view.ask_panel
    assert panel.winfo_ismapped()
    assert not view.frm_texts.winfo_ismapped()
    # Nothing to clear yet
    assert panel.btn_clear.cget("state") == ctk.DISABLED

    panel.ent_question.insert(0, "  Who says hello?  ")
    panel.btn_ask.invoke()
    assert answerer.has_answered.wait(5)
    ui.pump(0.3)

    assert answerer.questions[-1] == ("Who says hello?", 0)
    assert entry.questions == [
        TranscriptAnswer(
            "Who says hello?", "They say hello.", answerer.sources, "model"
        ).to_dict()
    ]
    conversation = panel.text.get("1.0", "end")
    assert "Who says hello?" in conversation and "They say hello." in conversation
    assert panel.ent_question.get() == ""
    assert panel.btn_clear.cget("state") == ctk.NORMAL

    # Clicking its source plays the audio from where it's said
    played: list[float] = []
    monkeypatch.setattr(panel.text, "_on_source", played.append)
    textbox = panel.text._textbox
    start = textbox.tag_ranges("source_0_0")[0]
    x, y, _width, height = textbox.bbox(start)
    position = {"x": x + 2, "y": y + height // 2}
    # Tk sends the events of a tag to the text under the pointer, once it moves
    textbox.event_generate("<Motion>", **position)
    textbox.event_generate("<ButtonPress-1>", **position)
    textbox.event_generate("<ButtonRelease-1>", **position)
    assert played == [0.0]

    # A follow-up question gets the previous answers
    answerer.has_answered.clear()
    view._ask("And then?")
    assert answerer.has_answered.wait(5)
    ui.pump(0.3)
    assert answerer.questions[-1] == ("And then?", 1)
    assert len(entry.questions) == 2

    monkeypatch.setattr(
        transcript_view.messagebox, "askyesno", lambda *_args, **_kwargs: True
    )
    panel.btn_clear.invoke()
    ui.pump()
    assert ui.store.get(entry.id).questions == []
    assert panel.frm_message.winfo_ismapped()


def test_questions_need_the_api_key_of_the_provider(
    ui: Ui, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    entry = ui.add(segments=SEGMENTS, text=TEXT)
    ui.window.select_entry(entry.id)
    ui.pump()
    view = ui.window._entry_view
    view._on_mode_change(view._modes.value("Ask"))
    ui.pump()

    assert view.ask_panel.ent_question.cget("state") == ctk.DISABLED
    assert view.ask_panel.btn_ask.cget("state") == ctk.DISABLED


def test_the_video_is_exported_with_its_subtitles(
    ui: Ui, audio_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_subtitle_burner import make_sound_video
    from utils.subtitle_burner import BurnedVideo
    from views.transcript import transcript_view, video_export
    from views.transcript.transcript_view import TranscriptView

    menus: list[tk.Menu] = []
    monkeypatch.setattr(
        TranscriptView,
        "_popup_below",
        staticmethod(lambda menu, _widget: menus.append(menu)),
    )

    def video_item() -> tuple[str, str]:
        ui.window._entry_view.show_export_menu()
        last = int(menus[-1].index("end"))
        return (
            str(menus[-1].entrycget(last, "label")),
            str(menus[-1].entrycget(last, "state")),
        )

    # An audio has no video to add the subtitles to
    entry = ui.add(segments=SEGMENTS, text=TEXT, media_path=str(audio_file))
    ui.window.select_entry(entry.id)
    ui.pump(0.5)
    assert video_item() == ("Video with subtitles (.mp4)…", tk.DISABLED)

    video = make_sound_video(tmp_path / "talk.mp4")
    entry = ui.add(segments=SEGMENTS, text=TEXT, media_path=str(video))
    ui.window.select_entry(entry.id)
    deadline = time.monotonic() + 5
    while not ui.window._entry_view.layout.has_video:
        assert time.monotonic() < deadline, "The video wasn't loaded"
        ui.pump(0.1)
    assert video_item() == ("Video with subtitles (.mp4)…", tk.NORMAL)

    burned: list[tuple[Path, list[str], Path]] = []

    def burn(
        video_path: Path, cues: list[Any], output: Path, *_args: Any
    ) -> BurnedVideo:
        burned.append((video_path, [cue.text for cue in cues], output))
        return BurnedVideo(output)

    monkeypatch.setattr(video_export, "burn_subtitles", burn)
    monkeypatch.setattr(
        transcript_view.filedialog,
        "asksaveasfilename",
        lambda **kwargs: str(tmp_path / kwargs["initialfile"]),
    )
    menus[-1].invoke(int(menus[-1].index("end")))
    ui.pump(0.3)

    output = tmp_path / "Entry.subtitled.mp4"
    assert burned == [
        (video, ["Hello wisper", "Nice to meet you.", "Bye wisper."], output)
    ]
    assert ui.window.top_bar._status_message == f"Exported to {output}"
    assert not video_export.VideoExport.is_running()
