import logging
import threading
import tkinter as tk
from collections.abc import Callable
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk
import numpy as np

from handlers.ai_providers import PROVIDERS, get_provider, has_api_key
from handlers.summary_handler import format_summary
from handlers.translation_handler import MANUAL
from models.config.config_ai import ConfigAi
from models.config.config_system import ConfigSystem
from models.history import HistoryEntry
from models.summary import TranscriptSummary
from models.transcript_segment import TranscriptSegment, join_segments
from models.translation import TranscriptTranslation
from utils.config_manager import ConfigManager
from utils.exporters import ExportDocument, available_formats, export
from utils.history_store import sanitize_file_name
from utils.i18n import L_, _
from utils.media import (
    PLAYBACK_SAMPLE_RATE,
    MediaInfo,
    load_audio_samples,
    probe_media,
)
from utils.subtitle_cues import (
    CueTrack,
    SegmentPart,
    build_cues,
    line_limits,
    split_segments,
)
from utils.time_format import format_segment_time
from utils.transcript_editing import (
    delete_segment,
    edit_segment_part,
    insert_segment,
    overlapping_segments,
    set_segment_timing,
    speakers,
    split_segment,
)
from views.entries.delegates import EntryActions
from views.entries.entry_header import EntryHeader
from views.history.formatting import reveal_label
from views.localization import Text, localize, on_language_change
from views.settings.option_labels import save_config
from views.settings.preferences_dialog import AI_TAB
from views.style import icons, theme
from views.transcript.corrections import TranscriptCorrectionsMixin
from views.transcript.edit_dialogs import Timing, TimingDialog
from views.transcript.media_layout import MediaLayout
from views.transcript.player_bar import PlayerBar
from views.transcript.summary_panel import SummaryPanel
from views.transcript.transcript_text import (
    PLAIN_TEXT_MODE,
    TRANSCRIPT_MODE,
    TranscriptText,
)
from views.transcript.translation_panel import (
    TranslateDialog,
    TranslationPanel,
    format_ratio,
    has_timed_texts,
    language_name,
)
from views.transcript.video_pane import VideoPane
from views.widgets.button import set_button_state
from views.widgets.localized_options import LocalizedOptions
from views.widgets.search_entry import SearchEntry
from views.widgets.splitter import Splitter
from views.widgets.text_dialog import TextDialog

logger = logging.getLogger(__name__)

SUMMARY_MODE = "summary"
# Part of the width taken by the text when its translation is shown next to it
DEFAULT_TRANSLATION_RATIO = 0.5
MIN_TRANSLATION_RATIO = 0.2
TRANSLATION_SPLITTER_THICKNESS = 16
# How long a segment added to the translation lasts by default, if there is no gap
# to fill until the next one
NEW_SEGMENT_SECONDS = 2.0


def build_cue_track(segments: list[TranscriptSegment], is_vertical: bool) -> CueTrack:
    """
    The subtitles of the segments, as the user configured them.

    :param is_vertical: Whether the video is taller than it's wide.
    """
    config = ConfigManager.get_config_subtitles()
    return CueTrack(build_cues(segments, *line_limits(config, segments, is_vertical)))


def transcript_parts(
    segments: list[TranscriptSegment], is_vertical: bool
) -> list[SegmentPart]:
    """The parts of the segments shown in the transcript: their subtitles."""
    config = ConfigManager.get_config_subtitles()
    return split_segments(segments, *line_limits(config, segments, is_vertical))


def export_labels() -> dict[str, str]:
    return {
        "txt": _("Plain text (.txt)"),
        "md": _("Markdown (.md)"),
        "docx": _("Word document (.docx)"),
        "srt": _("Subtitles (.srt)"),
        "vtt": _("Web subtitles (.vtt)"),
        "tsv": _("Table (.tsv)"),
        "json": _("JSON (.json)"),
    }


class TranscriptView(TranscriptCorrectionsMixin, ctk.CTkFrame):  # type: ignore[misc]
    """
    Shows a finished transcription: its text, which can be searched and
    corrected, its translation next to it, its summary, and its audio (and
    video), which plays highlighting the segment (and the word) being said.
    Clicking a segment plays it.
    """

    def __init__(
        self,
        master: Any,
        entry: HistoryEntry,
        actions: EntryActions,
        run_on_ui_thread: Callable[..., None],
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.entry_id = entry.id
        self._entry = entry
        self._actions = actions
        self._run_on_ui_thread = run_on_ui_thread
        self._is_destroyed = False
        self._copy_feedback_after_id: str | None = None
        self._mode = TRANSCRIPT_MODE if entry.segments else PLAIN_TEXT_MODE
        # What the text shows, to render it again only when it changes
        self._shown_content: tuple[list[TranscriptSegment], str, bool] | None = None
        # The parts of the segments shown in the transcript (see `transcript_parts`)
        self._parts: list[SegmentPart] = []
        # Whether the video is taller than it's wide, which narrows the subtitles.
        # It's known once the media is loaded
        self._is_vertical = False
        # The language and the segments of the translation that the subtitles of
        # the video can show, to build them again only when they change
        self._subtitled_translation: tuple[str, tuple[TranscriptSegment, ...]] = (
            "",
            (),
        )
        translating = actions.transcript.translating_languages(entry.id)
        self._is_translation_visible = bool(entry.translations or translating)
        # The language of the translation shown, the last one made at first. It
        # may not have one yet, while it's translated into it or if that failed
        self._translation_language: str | None = next(
            reversed([*entry.translations, *translating]), None
        )
        self._translation_ratio = DEFAULT_TRANSLATION_RATIO

        self._config_system = ConfigManager.get_config_system()
        self._precise_variable: tk.BooleanVar | None = None
        self._subtitles_variable: tk.BooleanVar | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header = EntryHeader(self, entry, actions.prompts)
        self.header.grid(row=0, column=0, padx=28, pady=(22, 0), sticky=ctk.EW)
        self._init_body()
        self._init_toolbar()

        self.text = TranscriptText(
            self.frm_texts,
            on_segment_click=self._on_segment_click,
            on_segment_menu=self._show_segment_menu,
            on_text_edit=self._on_text_edit,
        )
        self.translation_panel = TranslationPanel(
            self.frm_texts,
            on_segment_click=self._on_translation_segment_click,
            on_segment_menu=self._show_translation_segment_menu,
            on_text_edit=self._on_translation_text_edit,
            on_copy=self._copy_translation,
            on_export=self.show_translation_export_menu,
            on_translate=self._open_translate_dialog,
            on_regenerate=self._translate_again,
            on_close=lambda: self._set_translation_visible(False),
            on_select=self._select_translation,
        )
        self.translation_splitter = Splitter(
            self.frm_texts,
            is_vertical=True,
            on_drag=self._on_translation_splitter_drag,
            on_reset=self._reset_translation_ratio,
            thickness=TRANSLATION_SPLITTER_THICKNESS,
        )
        self.summary_panel = SummaryPanel(
            self.frm_text_pane,
            on_generate=self._generate_summary,
            on_chapter=self._play_from,
            on_copy=self._copy_summary,
            on_settings=lambda: self._actions.window.show_preferences(AI_TAB),
            on_set_api_key=self._set_summary_api_key,
        )
        self.player = PlayerBar(
            self,
            on_tick=self._on_tick,
            on_toggle_subtitles=self.video.toggle_subtitles,
            on_subtitle_menu=self.video.show_subtitle_menu,
        )
        self.player.grid(row=2, column=0, sticky=ctk.EW)
        self._apply_precise_timestamps()

        self.layout.layout()
        self._show_content()
        self._layout_texts()
        self._refresh_translation()
        self._refresh_translation_subtitles()
        self._apply_mode()
        self._load_media()
        on_language_change(self, self._on_language_change)

    def _on_language_change(self) -> None:
        """Shows again the texts built from the transcription and its state."""
        self._refresh_match_widgets()
        if self._mode == SUMMARY_MODE:
            self._refresh_summary()
        self._refresh_translation()
        # The subtitles of the translation are named after its language
        self._subtitled_translation = ("", ())
        self._refresh_translation_subtitles()

    def destroy(self) -> None:
        self._is_destroyed = True
        if self._copy_feedback_after_id:
            self.after_cancel(self._copy_feedback_after_id)
        super().destroy()

    # PUBLIC METHODS

    def update_entry(self, entry: HistoryEntry) -> None:
        """Shows the changes of the entry, e.g. a correction or its summary."""
        self._entry = entry
        self.header.update_entry(entry)
        self._show_content()
        self._refresh_translation()
        self._refresh_translation_subtitles()
        if self._mode == SUMMARY_MODE:
            self._refresh_summary()

    def focus_search(self) -> None:
        self.ent_search.focus_set()
        self.ent_search.select_range(0, ctk.END)

    def handle_key(self, key: str) -> bool:
        """Handles the playback shortcuts. :return: Whether the key was handled."""
        return self.player.handle_key(key)

    def is_transcript_widget(self, widget: Any) -> bool:
        """Whether the widget is the text of the transcript, which can't be edited."""
        return self.text.contains_widget(widget)

    def show_export_menu(self) -> None:
        """
        The formats to export the transcription to. Each translation is exported
        from its panel.
        """
        menu = tk.Menu(self, tearoff=False)
        self._add_export_commands(menu, bool(self._entry.segments), self.export)
        self._popup_below(menu, self.btn_export)

    def show_translation_export_menu(self, anchor: Any) -> None:
        translation = self._translation()
        if translation is None:
            return
        menu = tk.Menu(self, tearoff=False)
        self._add_export_commands(
            menu, has_timed_texts(translation), self.export_translation
        )
        self._popup_below(menu, anchor)

    @staticmethod
    def _add_export_commands(
        menu: tk.Menu, has_segments: bool, command: Callable[[str], None]
    ) -> None:
        labels = export_labels()
        for file_type in available_formats(has_segments):
            menu.add_command(
                label=labels[file_type], command=partial(command, file_type)
            )

    def export(self, file_type: str) -> None:
        self.text.save_pending_text()
        entry = self._entry
        document = ExportDocument(
            title=entry.title,
            text=self.text.get_text(),
            segments=entry.segments,
            summary=TranscriptSummary.from_dict(entry.summary),
            is_text_edited=entry.is_text_edited,
            is_vertical=self._is_vertical,
        )
        self._export(file_type, document, _("Export transcription"))

    def export_translation(self, file_type: str) -> None:
        self.translation_panel.save_pending_text()
        translation = self._translation()
        if translation is None:
            return

        language = language_name(translation.language)
        document = ExportDocument(
            title=f"{self._entry.title} ({language})",
            text=translation.text,
            # The segments not translated yet are left out of the subtitles
            segments=[segment for segment in translation.segments if segment.text],
            is_text_edited=translation.is_text_edited,
            is_vertical=self._is_vertical,
        )
        self._export(
            file_type,
            document,
            _("Export translation into {language}").format(language=language),
            # Like `video.es.srt`, which the video players load with the video
            language_code=translation.language,
        )

    def _export(
        self,
        file_type: str,
        document: ExportDocument,
        title: str,
        language_code: str = "",
    ) -> None:
        """
        Asks where to export a document, next to the source file by default.

        :param language_code: Added to the name of the file, if given.
        """
        entry = self._entry
        source_path = entry.source_path
        initial_dir = str(source_path.parent) if source_path else str(Path.home())
        stem = sanitize_file_name(
            source_path.stem if source_path and source_path.is_file() else entry.title
        )
        if language_code:
            stem += f".{language_code}"

        selected = filedialog.asksaveasfilename(
            title=title,
            initialdir=initial_dir,
            initialfile=f"{stem}.{file_type}",
            defaultextension=f".{file_type}",
            filetypes=[(f".{file_type}", f"*.{file_type}"), (_("All files"), "*.*")],
        )
        if not selected:
            return

        try:
            path = export(Path(selected), file_type, document)
        except (OSError, ValueError) as e:
            self._actions.window.show_status(
                _("Could not export: {error}").format(error=e), is_error=True
            )
            return
        self._actions.window.show_status(_("Exported to {path}").format(path=path))

    # WIDGETS

    def _init_body(self) -> None:
        """
        The video (once loaded) and the text, with a handle between them to
        resize them. The text pane has the toolbar of the text above it.
        """
        self.frm_body = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_body.grid(row=1, column=0, padx=28, pady=(16, 0), sticky=ctk.NSEW)

        self.video = VideoPane(
            self.frm_body,
            self._config_system,
            build_cue_track(self._entry.segments, self._is_vertical),
            on_click=lambda: self.player.toggle_playback(),
            on_subtitles_change=lambda: self.player.set_subtitles_on(
                self.video.is_showing_subtitles
            ),
        )
        self.frm_text_pane = ctk.CTkFrame(self.frm_body, fg_color="transparent")
        self.frm_text_pane.grid_columnconfigure(0, weight=1)
        self.frm_text_pane.grid_rowconfigure(1, weight=1)
        # The text, and its translation on its right
        self.frm_texts = ctk.CTkFrame(self.frm_text_pane, fg_color="transparent")
        self.frm_texts.grid_rowconfigure(0, weight=1)
        self.layout = MediaLayout(
            self.frm_body, self.video, self.frm_text_pane, self._config_system
        )

    def _init_toolbar(self) -> None:
        """The search on the left and the actions of the text on the right."""
        toolbar = ctk.CTkFrame(self.frm_text_pane, fg_color="transparent")
        toolbar.grid(row=0, column=0, pady=(0, 10), sticky=ctk.EW)
        # The empty column between the search and the actions takes the free space
        toolbar.grid_columnconfigure(4, weight=1)

        self._init_search(toolbar)
        self._init_actions(toolbar)

    def _init_search(self, toolbar: ctk.CTkFrame) -> None:
        """The search entry, the number of matches and the buttons to go to them."""
        self._search_variable = ctk.StringVar(self)
        self._search_variable.trace_add("write", lambda *_args: self._search())
        search = SearchEntry(
            toolbar,
            width=230,
            textvariable=self._search_variable,
            placeholder_text=lambda: _("Search ({shortcut})").format(
                shortcut=f"{theme.SHORTCUT_MODIFIER_LABEL}F"
            ),
        )
        search.grid(row=0, column=0)
        self.ent_search = search.entry
        self.ent_search.bind("<Return>", lambda _event: self._go_to_match(1))
        self.ent_search.bind("<Shift-Return>", lambda _event: self._go_to_match(-1))
        self.ent_search.bind("<Escape>", lambda _event: self._clear_search())

        self.lbl_matches = ctk.CTkLabel(
            toolbar, text="", width=70, font=theme.font(12), text_color=theme.HINT_TEXT
        )
        self.lbl_matches.grid(row=0, column=1, padx=(8, 0))
        self.btn_previous_match = ctk.CTkButton(
            toolbar,
            text="",
            width=28,
            height=28,
            image=icons.icon("chevron_left", 12),
            command=lambda: self._go_to_match(-1),
            **theme.GHOST_BUTTON,
        )
        self.btn_previous_match.grid(row=0, column=2)
        self.btn_next_match = ctk.CTkButton(
            toolbar,
            text="",
            width=28,
            height=28,
            image=icons.icon("chevron_right", 12),
            command=lambda: self._go_to_match(1),
            **theme.GHOST_BUTTON,
        )
        self.btn_next_match.grid(row=0, column=3)

    def _init_actions(self, toolbar: ctk.CTkFrame) -> None:
        self.seg_mode = ctk.CTkSegmentedButton(toolbar, values=[""], height=30)
        # The modes shown depend on the transcription (see `_show_content`)
        self._modes = LocalizedOptions(
            self.seg_mode,
            lambda: {
                TRANSCRIPT_MODE: _("Subtitles"),
                PLAIN_TEXT_MODE: _("Plain text"),
                SUMMARY_MODE: _("Summary"),
            },
            values=[self._mode],
            command=self._on_mode_change,
        )
        self.seg_mode.grid(row=0, column=5, padx=(10, 0))

        self.btn_translate = self._create_action_button(
            toolbar, L_("Translate"), "globe", self._on_translate_button
        )
        self.btn_translate.grid(row=0, column=6, padx=(10, 0))
        self.btn_copy = self._create_action_button(
            toolbar, L_("Copy"), "copy", self._on_copy
        )
        self.btn_copy.grid(row=0, column=7, padx=(8, 0))
        self.btn_export = self._create_action_button(
            toolbar, L_("Export"), "export", self.show_export_menu
        )
        self.btn_export.grid(row=0, column=8, padx=(8, 0))
        self.btn_more = ctk.CTkButton(
            toolbar,
            text="",
            image=icons.icon("more", 16),
            width=32,
            height=30,
            command=self._show_more_menu,
            **theme.SECONDARY_BUTTON,
        )
        self.btn_more.grid(row=0, column=9, padx=(8, 0))

    @staticmethod
    def _create_action_button(
        toolbar: ctk.CTkFrame, text: Text, icon_name: str, command: Callable[[], Any]
    ) -> ctk.CTkButton:
        return localize(
            ctk.CTkButton(
                toolbar,
                image=icons.icon(icon_name, 15),
                compound=ctk.LEFT,
                width=0,
                height=30,
                command=command,
                **theme.SECONDARY_BUTTON,
            ),
            text=text,
        )

    # CONTENT AND MODES

    def _show_content(self) -> None:
        entry = self._entry
        content = (entry.segments, entry.text, entry.is_text_edited)
        if self._shown_content is not None and (
            content[0] is self._shown_content[0]
            and content[1:] == self._shown_content[1:]
        ):
            return

        has_new_segments = (
            self._shown_content is None or entry.segments is not self._shown_content[0]
        )
        if has_new_segments:
            self._parts = transcript_parts(entry.segments, self._is_vertical)
        self._shown_content = content
        self.text.set_content(
            [part.segment for part in self._parts], entry.text, entry.is_text_edited
        )
        if has_new_segments:
            self.video.set_cue_track(build_cue_track(entry.segments, self._is_vertical))

        modes = [PLAIN_TEXT_MODE, SUMMARY_MODE]
        if entry.segments:
            modes.insert(0, TRANSCRIPT_MODE)
        self._modes.show_values(modes)
        if self._mode not in modes:
            self._mode = PLAIN_TEXT_MODE
        self._modes.set(self._mode)

    def _apply_mode(self) -> None:
        self._modes.set(self._mode)
        is_summary = self._mode == SUMMARY_MODE

        if is_summary:
            self.frm_texts.grid_forget()
            self.summary_panel.grid(row=1, column=0, sticky=ctk.NSEW)
            self._refresh_summary()
        else:
            self.summary_panel.grid_forget()
            self.frm_texts.grid(row=1, column=0, sticky=ctk.NSEW)
            self.text.set_mode(self._mode)
            self.translation_panel.set_mode(self._mode)

        state = ctk.DISABLED if is_summary else ctk.NORMAL
        if self.ent_search.cget("state") != state:
            self.ent_search.configure(state=state)
        set_button_state(self.btn_translate, state)
        self._refresh_match_widgets()

    def _on_mode_change(self, mode: str) -> None:
        self._mode = mode
        self._apply_mode()

    def _toggle_precise_timestamps(self) -> None:
        is_precise = not self._config_system.precise_timestamps
        self._config_system.precise_timestamps = is_precise
        save_config(ConfigSystem.Key.PRECISE_TIMESTAMPS, str(is_precise))
        self._apply_precise_timestamps()
        self._refresh_match_widgets()

    def _apply_precise_timestamps(self) -> None:
        is_precise = self._config_system.precise_timestamps
        self.text.set_precise_timestamps(is_precise)
        self.translation_panel.set_precise_timestamps(is_precise)

    def _format_time(self, seconds: float) -> str:
        """Formats the start of a segment as the user chose to show them."""
        return format_segment_time(seconds, self._config_system.precise_timestamps)

    # SEARCH

    def _search(self) -> None:
        if self._mode != SUMMARY_MODE:
            self.text.search(self._search_variable.get())
        self._refresh_match_widgets()

    def _go_to_match(self, step: int) -> None:
        self.text.go_to_match(step)
        self._refresh_match_widgets()

    def _clear_search(self) -> None:
        self._search_variable.set("")
        self.text.focus_text()

    def _refresh_match_widgets(self) -> None:
        match_widgets = (self.lbl_matches, self.btn_previous_match, self.btn_next_match)
        if not self._search_variable.get().strip() or self._mode == SUMMARY_MODE:
            for widget in match_widgets:
                widget.grid_remove()
            return

        for widget in match_widgets:
            widget.grid()

        current, total = self.text.match_status
        if not total:
            text = _("No results")
        else:
            text = _("{current} of {total}").format(
                current=(current or 0) + 1, total=total
            )
        self.lbl_matches.configure(text=text)
        state = ctk.NORMAL if total > 1 else ctk.DISABLED
        self.btn_previous_match.configure(state=state)
        self.btn_next_match.configure(state=state)

    # CORRECTIONS

    def _on_text_edit(self, text: str) -> None:
        if text != self._entry.text:
            self._actions.transcript.save_text(self.entry_id, text)

    # SUMMARY

    def _refresh_summary(self) -> None:
        provider = get_provider(ConfigManager.get_config_ai().summary_provider)
        self.summary_panel.show(
            TranscriptSummary.from_dict(self._entry.summary),
            provider=PROVIDERS[provider].name,
            is_loading=self._actions.transcript.is_summarizing(self.entry_id),
            error=self._actions.transcript.get_summary_error(self.entry_id),
            can_generate=has_api_key(provider),
        )

    def _set_summary_api_key(self) -> None:
        provider = get_provider(ConfigManager.get_config_ai().summary_provider)
        if env_key := PROVIDERS[provider].env_key:
            self._actions.window.set_api_key(env_key)

    def _generate_summary(self) -> None:
        self.text.save_pending_text()
        self._actions.transcript.summarize_entry(self.entry_id)
        self._refresh_summary()

    def _copy_summary(self) -> None:
        if summary := TranscriptSummary.from_dict(self._entry.summary):
            self.clipboard_clear()
            self.clipboard_append(format_summary(summary))
            self._actions.window.show_status(_("Summary copied."))

    # TRANSLATION

    def _layout_texts(self) -> None:
        """Places the text and, if it's visible, its translation on its right."""
        frame = self.frm_texts
        self.text.grid(row=0, column=0, sticky=ctk.NSEW)

        if not self._is_translation_visible:
            self.translation_splitter.grid_forget()
            self.translation_panel.grid_forget()
            frame.grid_columnconfigure(0, weight=1, uniform="")
            frame.grid_columnconfigure(2, weight=0, uniform="")
            return

        self.translation_splitter.grid(row=0, column=1, sticky=ctk.NS)
        self.translation_panel.grid(row=0, column=2, sticky=ctk.NSEW)
        self._apply_translation_ratio()

    def _apply_translation_ratio(self) -> None:
        # The columns of a uniform group share the width in proportion to weights
        weight = round(self._translation_ratio * 1000)
        self.frm_texts.grid_columnconfigure(0, weight=weight, uniform="texts")
        self.frm_texts.grid_columnconfigure(2, weight=1000 - weight, uniform="texts")

    def _on_translation_splitter_drag(self, pointer_x: int) -> None:
        available = self.frm_texts.winfo_width() - TRANSLATION_SPLITTER_THICKNESS
        if available <= 1:
            return
        offset = pointer_x - self.frm_texts.winfo_rootx()
        ratio = (offset - TRANSLATION_SPLITTER_THICKNESS / 2) / available
        self._translation_ratio = min(
            max(ratio, MIN_TRANSLATION_RATIO), 1 - MIN_TRANSLATION_RATIO
        )
        self._apply_translation_ratio()

    def _reset_translation_ratio(self) -> None:
        self._translation_ratio = DEFAULT_TRANSLATION_RATIO
        self._apply_translation_ratio()

    def _set_translation_visible(self, is_visible: bool) -> None:
        if is_visible == self._is_translation_visible:
            return
        self._is_translation_visible = is_visible
        self._layout_texts()
        self._refresh_translation()

    def _translation(self) -> TranscriptTranslation | None:
        """The translation shown, if there is one into its language."""
        return self._entry.get_translation(self._translation_language)

    def _is_translating(self) -> bool:
        """Whether it's being translated into the language shown."""
        return self._translation_language is not None and (
            self._actions.transcript.is_translating(
                self.entry_id, self._translation_language
            )
        )

    def _translation_error(self) -> str:
        if self._translation_language is None:
            return ""
        return self._actions.transcript.get_translation_error(
            self.entry_id, self._translation_language
        )

    def _translation_labels(self, translating: list[str]) -> dict[str, str]:
        """
        The languages of the translations and how much of each is translated,
        then the ones being translated into, and the one shown if it failed.
        """
        labels: dict[str, str] = {}
        for language in self._entry.translations:
            if translation := self._entry.get_translation(language):
                ratio = translation.translated_ratio(self._entry.segments)
                labels[language] = f"{language_name(language)} · {format_ratio(ratio)}"
        shown = [self._translation_language] if self._translation_language else []
        for pending in [*translating, *shown]:
            if pending not in labels:
                labels[pending] = (
                    f"{language_name(pending)} · …"
                    if pending in translating
                    else language_name(pending)
                )
        return labels

    def _select_translation(self, language: str) -> None:
        """Shows the translation into another language."""
        if language == self._translation_language:
            return
        # The edits of the user are saved before another translation is shown
        self.translation_panel.save_pending_text()
        self._translation_language = language
        self._refresh_translation()
        self._refresh_translation_subtitles()

    def _refresh_translation(self) -> None:
        # The edits of the user are saved into their translation before another
        # one is shown, or before it's shown again
        self.translation_panel.save_pending_text()
        translating = self._actions.transcript.translating_languages(self.entry_id)
        # The translation shown is kept while it exists, is being made or shows
        # why it failed. Otherwise, the last one made is shown
        language = self._translation_language
        if (
            language not in self._entry.translations
            and language not in translating
            and not self._translation_error()
        ):
            self._translation_language = next(
                reversed([*self._entry.translations, *translating]), None
            )
        is_loading = self._is_translating()
        # A translation in progress is shown, e.g. when going back to its entry
        if is_loading:
            self._set_translation_visible(True)
        if not self._is_translation_visible:
            return

        self.translation_panel.show(
            self._translation_language,
            self._translation(),
            is_loading=is_loading,
            error=self._translation_error(),
            segments=[part.segment for part in self._translation_parts()],
            languages=self._translation_labels(translating),
        )
        self.translation_panel.set_mode(self._mode)

    def _on_translate_button(self) -> None:
        translation = self._translation()
        if translation is None and not self._is_translating():
            self._open_translate_dialog()
            return

        menu = tk.Menu(self, tearoff=False)
        if self._is_translation_visible:
            menu.add_command(
                label=_("Hide the translation"),
                command=lambda: self._set_translation_visible(False),
            )
        else:
            menu.add_command(
                label=_("Show the translation"),
                command=lambda: self._set_translation_visible(True),
            )
        menu.add_command(
            label=_("Translate into another language…"),
            command=self._open_translate_dialog,
        )
        if self.layout.has_video and self.video.has_translation_subtitles:
            # Kept while the menu is shown, like the one of the precise timestamps
            self._subtitles_variable = tk.BooleanVar(
                menu,
                value=self.video.is_showing_subtitles
                and self.video.is_showing_translation,
            )
            menu.add_checkbutton(
                label=_("Show it as the subtitles of the video"),
                variable=self._subtitles_variable,
                command=self._toggle_translation_subtitles,
            )
        if translation is not None:
            menu.add_separator()
            menu.add_command(
                label=_("Delete the translation"),
                command=self._delete_translation,
            )
        self._popup_below(menu, self.btn_translate)

    def _toggle_translation_subtitles(self) -> None:
        if self.video.is_showing_subtitles and self.video.is_showing_translation:
            self.video.toggle_subtitles()
        else:
            self.video.show_translation(True)

    def _refresh_translation_subtitles(self) -> None:
        """Gives the video the subtitles of the translation, if it has one."""
        translation = self._translation()
        subtitled = (
            (translation.language, translation.segments) if translation else ("", ())
        )
        if subtitled == self._subtitled_translation:
            return

        self._subtitled_translation = subtitled
        language, segments = subtitled
        self.video.set_translation_track(
            build_cue_track(list(segments), self._is_vertical) if segments else None,
            language_name(language) if language else "",
        )
        # The buttons of the subtitles are shown once the video has some
        if self.layout.has_video and self.video.has_subtitles:
            self.player.show_subtitle_buttons(self.video.is_showing_subtitles)

    def _open_translate_dialog(self) -> None:
        self.text.save_pending_text()
        request = TranslateDialog(
            self,
            source_language=self._entry.language,
            on_set_api_key=self._actions.window.set_api_key,
            on_settings=lambda: self._actions.window.show_preferences(AI_TAB),
        ).get_result()
        if request is None or self._is_destroyed:
            return
        if self._actions.transcript.is_translating(self.entry_id, request.language):
            # It's already being translated into it, so that one is shown
            self._select_translation(request.language)
            return
        # A translation into the same language is replaced, losing its edits
        if request.language in self._entry.translations and not (
            self._confirm_translate_again(request.language)
        ):
            return

        self.translation_panel.save_pending_text()
        save_config(ConfigAi.Key.TRANSLATION_LANGUAGE, request.language)
        if request.provider == MANUAL:
            # Like the transcript, a segment per subtitle, with its timestamps
            self._actions.transcript.start_manual_translation(
                self.entry_id,
                request.language,
                [part.segment for part in self._parts],
            )
            self._translation_language = request.language
            self._set_translation_visible(True)
            self._refresh_translation()
            return

        config = ConfigManager.get_config_ai()
        # The configured model only applies to its provider
        model = (
            config.translation_model
            if request.provider == config.translation_provider
            else ""
        )
        if request.provider != config.translation_provider:
            save_config(ConfigAi.Key.TRANSLATION_PROVIDER, request.provider)
            save_config(ConfigAi.Key.TRANSLATION_MODEL, "")

        self._translation_language = request.language
        self._actions.transcript.translate_entry(
            self.entry_id, request.language, request.provider, model
        )
        self._set_translation_visible(True)
        self._refresh_translation()
        self._refresh_translation_subtitles()

    def _on_translation_text_edit(self, text: str) -> None:
        translation = self._translation()
        if translation and text != translation.text:
            self._actions.transcript.save_translation_text(
                self.entry_id, translation.language, text
            )

    def _show_translation_segment_menu(self, event: Any, idx: int) -> str:
        parts = self._translation_parts()
        if idx >= len(parts):
            return "break"

        segment = parts[idx].segment
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(
            label=_("Play from here"), command=lambda: self._play_from(segment.start)
        )
        menu.add_command(
            label=_("Copy"),
            command=lambda: self._copy_text(segment.text),
            state=tk.NORMAL if segment.text else tk.DISABLED,
        )
        menu.add_command(
            label=_("Edit text…") if segment.text else _("Translate text…"),
            command=lambda: self._edit_translation_segment(idx),
        )
        menu.add_command(
            label=_("Edit the timing…"),
            command=lambda: self._edit_translation_timing(idx),
        )
        menu.add_command(
            label=_("Add a segment after…"),
            command=lambda: self._add_translation_segment(idx),
        )
        menu.add_separator()
        menu.add_command(
            label=_("Delete the segment"),
            command=lambda: self._delete_translation_segment(idx),
            # Without segments, the translation would have no timestamps
            state=tk.NORMAL if len(parts) > 1 else tk.DISABLED,
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _translation_segments(self) -> list[TranscriptSegment] | None:
        """The segments of the translation, after saving the edits of its text."""
        self.translation_panel.save_pending_text()
        translation = self._translation()
        return list(translation.segments) if translation else None

    def _translation_parts(self) -> list[SegmentPart]:
        """The parts of the segments of the translation shown in its panel."""
        translation = self._translation()
        if translation is None:
            return []
        return transcript_parts(list(translation.segments), self._is_vertical)

    def _split_translation_part(
        self, idx: int
    ) -> tuple[list[TranscriptSegment], int] | None:
        """
        Makes a part shown in the translation a segment of its own, to change its
        timing, add a segment after it or delete it, which are changes of what the
        user sees, not of the whole segment.

        :return: The segments of the translation, with the segment of the part
                 split into its parts, and the index of the part among them.
        """
        segments = self._translation_segments()
        parts = self._translation_parts()
        if segments is None or idx >= len(parts):
            return None

        part = parts[idx]
        pieces = [p for p in parts if p.segment_idx == part.segment_idx]
        if len(pieces) == 1:
            return segments, part.segment_idx
        segments = split_segment(
            segments, part.segment_idx, [piece.segment for piece in pieces]
        )
        return segments, part.segment_idx + pieces.index(part)

    def _save_translation_segments(self, segments: list[TranscriptSegment]) -> None:
        translation = self._translation()
        if translation is None:
            return
        # The edited text keeps the changes of the user, so only the segments change
        text = (
            translation.text if translation.is_text_edited else join_segments(segments)
        )
        self._actions.transcript.update_translation(
            self.entry_id, translation.language, segments, text
        )

    def _edit_translation_segment(self, idx: int) -> None:
        segments = self._translation_segments()
        parts = self._translation_parts()
        if segments is None or idx >= len(parts):
            return

        part = parts[idx]
        segment = part.segment
        # The original text said meanwhile is shown, to translate it
        original = " ".join(
            s.text
            for s in overlapping_segments(
                self._entry.segments, segment.start, segment.end
            )
        )
        start, end = self._format_time(segment.start), self._format_time(segment.end)
        text = TextDialog(
            self,
            _("Edit text") if segment.text else _("Translate text"),
            _("Translation of “{text}”, said from {start} to {end}:").format(
                text=original, start=start, end=end
            )
            if original
            else _("Translation of the segment from {start} to {end}:").format(
                start=start, end=end
            ),
            segment.text,
            is_multiline=True,
            allow_empty=False,
        ).get_input()
        if not text or not text.strip() or text == segment.text:
            return

        self._save_translation_segments(
            edit_segment_part(segments, part.segment_idx, part.first, part.last, text)
        )

    def _edit_translation_timing(self, idx: int) -> None:
        split = self._split_translation_part(idx)
        if split is None:
            return

        segments, idx = split
        segment = segments[idx]
        timing = TimingDialog(
            self,
            _("Edit the timing"),
            _("Save"),
            self._describe_translation_segment(segment),
            Timing(segment.start, segment.end),
        ).get_result()
        if timing is None or (timing.start, timing.end) == (segment.start, segment.end):
            return

        self._save_translation_segments(
            set_segment_timing(segments, idx, timing.start, timing.end)
        )

    def _add_translation_segment(self, idx: int) -> None:
        split = self._split_translation_part(idx)
        if split is None:
            return

        segments, idx = split

        # By default, it fills the gap until the next segment
        previous = segments[idx]
        start = previous.end
        following = segments[idx + 1].start if idx + 1 < len(segments) else start
        end = following if following > start else start + NEW_SEGMENT_SECONDS
        timing = TimingDialog(
            self,
            _("Add a segment"),
            _("Add"),
            _("The new segment goes after the one at {time}:").format(
                time=self._format_time(previous.start)
            ),
            Timing(start, end),
        ).get_result()
        if timing is None:
            return

        added = TranscriptSegment(timing.start, timing.end, "", previous.speaker)
        segments = insert_segment(segments, added)
        self._save_translation_segments(segments)
        # It's translated right away, or it's left to translate later
        added_idx = next(i for i, segment in enumerate(segments) if segment is added)
        self._edit_translation_segment(
            next(
                i
                for i, part in enumerate(self._translation_parts())
                if part.segment_idx == added_idx
            )
        )

    def _delete_translation_segment(self, idx: int) -> None:
        split = self._split_translation_part(idx)
        if split is None or len(split[0]) <= 1:
            return

        segments, idx = split

        segment = segments[idx]
        if segment.text and not messagebox.askyesno(
            _("Delete the segment"),
            _("Delete the segment “{text}”?").format(text=segment.text),
            icon=messagebox.WARNING,
            parent=self.winfo_toplevel(),
        ):
            return
        self._save_translation_segments(delete_segment(segments, idx))

    def _describe_translation_segment(self, segment: TranscriptSegment) -> str:
        """Its text, or the time it starts if it isn't translated yet."""
        if segment.text:
            return f"“{segment.text}”"
        return _("The segment at {time}, not translated yet.").format(
            time=self._format_time(segment.start)
        )

    def _delete_translation(self) -> None:
        """Deletes the translation shown, showing another one if there is one."""
        language = self._translation_language
        if language is None:
            return
        self.translation_panel.save_pending_text()
        if not set(self._entry.translations) - {language}:
            self._is_translation_visible = False
            self._layout_texts()
        self._actions.transcript.remove_translation(self.entry_id, language)

    def _translate_again(self) -> None:
        """Translates it again, into the same language and with the same model."""
        translation = self._translation()
        if (
            translation is None
            or translation.provider == MANUAL
            or self._is_translating()
            or not self._confirm_translate_again(translation.language)
        ):
            return
        self.text.save_pending_text()
        self._actions.transcript.translate_entry(
            self.entry_id, translation.language, translation.provider, translation.model
        )
        self._refresh_translation()

    def _confirm_translate_again(self, language: str) -> bool:
        """Asks before replacing a translation, since its edits are lost."""
        return bool(
            messagebox.askyesno(
                _("Translate again"),
                _(
                    "Translate the transcription into {language} again? The "
                    "changes made to the translation will be lost."
                ).format(language=language_name(language)),
                icon=messagebox.WARNING,
                parent=self.winfo_toplevel(),
            )
        )

    def _copy_translation(self) -> None:
        if translation := self._translation():
            self.clipboard_clear()
            self.clipboard_append(translation.text)
            self._actions.window.show_status(
                _("Translation into {language} copied.").format(
                    language=language_name(translation.language)
                )
            )

    # MEDIA

    def _load_media(self) -> None:
        media_path = Path(self._entry.media_path) if self._entry.media_path else None

        if media_path is None or not media_path.is_file():
            self.player.show_error(
                lambda: (
                    _(
                        "The audio isn't available: the source file was moved or deleted."
                    )
                    if media_path
                    else _("The audio isn't available.")
                )
            )
            return

        def load() -> None:
            try:
                info = probe_media(media_path)
            except OSError:
                info = MediaInfo(None, None)
            try:
                samples = load_audio_samples(media_path)
                error: Exception | None = None
            except OSError as e:
                samples, error = None, e
                # Videos without sound are played in silence
                if info.has_video and info.duration:
                    samples = np.zeros(
                        int(info.duration * PLAYBACK_SAMPLE_RATE), np.int16
                    )
            self._run_on_ui_thread(
                self._on_media_loaded, media_path, info, samples, error
            )

        threading.Thread(target=load, daemon=True).start()

    def _on_media_loaded(
        self, media_path: Path, info: MediaInfo, samples: Any, error: Exception | None
    ) -> None:
        if self._is_destroyed or not self.winfo_exists():
            return

        # The length of the decoded audio is preferred over the one reported by the
        # container, so the header shows the same duration as the player bar
        self.header.set_duration(
            len(samples) / PLAYBACK_SAMPLE_RATE
            if samples is not None
            else info.duration
        )

        if samples is None:
            logger.error("Could not load %s", media_path, exc_info=error)
            self.player.show_error(
                lambda: _("The audio can't be played: {error}").format(error=error)
            )
            return

        if info.is_portrait:
            self._set_vertical()

        if info.has_video:
            try:
                self.video.open(media_path)
                self.layout.show_video(bool(info.is_portrait))
                if self.video.has_subtitles:
                    self.player.show_subtitle_buttons(self.video.is_showing_subtitles)
            except OSError:
                logger.warning(
                    "Could not open the video of %s", media_path, exc_info=True
                )

        self.player.load(samples, PLAYBACK_SAMPLE_RATE, is_video=self.layout.has_video)

    def _set_vertical(self) -> None:
        """Splits the transcript and the subtitles again for a vertical video."""
        self._is_vertical = True
        self.refresh_subtitles()

    def refresh_subtitles(self) -> None:
        """
        Splits the transcript, its translation and the subtitles of the video
        again, e.g. after the user changes the size of the subtitles.
        """
        self._shown_content = None
        self._show_content()
        self._refresh_translation()
        self._subtitled_translation = ("", ())
        self._refresh_translation_subtitles()

    # PLAYBACK

    def _on_tick(self, position: float, is_playing: bool) -> None:
        self.text.highlight(position, is_playing)
        if self._is_translation_visible:
            self.translation_panel.highlight(position, is_playing)
        if self.layout.has_video:
            self.video.show_position(position)

    def _play_from(self, seconds: float) -> None:
        self.player.play_from(seconds)

    def _on_segment_click(self, idx: int) -> None:
        self._play_from(self._parts[idx].segment.start)

    def _on_translation_segment_click(self, idx: int) -> None:
        parts = self._translation_parts()
        if idx < len(parts):
            self._play_from(parts[idx].segment.start)

    # MENUS

    def _show_segment_menu(self, event: Any, idx: int) -> str:
        segment = self._parts[idx].segment
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(
            label=_("Play from here"), command=lambda: self._play_from(segment.start)
        )
        menu.add_command(label=_("Copy"), command=lambda: self._copy_text(segment.text))
        menu.add_command(label=_("Edit text…"), command=lambda: self._edit_segment(idx))
        if segment.speaker:
            menu.add_command(label=_("Rename speakers…"), command=self._rename_speakers)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _copy_text(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text.strip())

    def _show_more_menu(self) -> None:
        entry = self._entry
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label=_("Find and replace…"), command=self._find_and_replace)
        menu.add_command(
            label=_("Rename speakers…"),
            command=self._rename_speakers,
            state=tk.NORMAL if speakers(entry.segments) else tk.DISABLED,
        )
        # Kept while the menu is shown: a variable that is garbage collected is
        # unset in Tk, so the check mark wouldn't be shown
        self._precise_variable = tk.BooleanVar(
            menu, value=self._config_system.precise_timestamps
        )
        menu.add_checkbutton(
            label=_("Precise timestamps (HH:MM:SS,mmm)"),
            command=self._toggle_precise_timestamps,
            variable=self._precise_variable,
            state=tk.NORMAL if entry.segments else tk.DISABLED,
        )
        menu.add_separator()

        source_path = entry.source_path
        menu.add_command(
            label=reveal_label(),
            command=lambda: self._actions.files.reveal_entry(self.entry_id),
            state=tk.NORMAL if source_path and source_path.exists() else tk.DISABLED,
        )
        output_dir = Path(entry.output_dir) if entry.output_dir else None
        menu.add_command(
            label=_("Open the folder of the saved files"),
            command=lambda: (
                self._actions.files.open_folder(output_dir) if output_dir else None
            ),
            state=tk.NORMAL if output_dir and output_dir.is_dir() else tk.DISABLED,
        )
        menu.add_separator()
        menu.add_command(
            label=_("Rename…"),
            command=lambda: self._actions.prompts.ask_to_rename_entry(self.entry_id),
        )
        menu.add_command(
            label=_("Edit note…") if entry.note else _("Add note…"),
            command=lambda: self._actions.prompts.ask_for_note(self.entry_id),
        )
        if entry.note:
            menu.add_command(
                label=_("Delete note…"),
                command=lambda: self._actions.prompts.confirm_delete_note(
                    self.entry_id
                ),
            )
        menu.add_command(
            label=_("Edit tag…"),
            command=lambda: self._actions.prompts.ask_for_tag(self.entry_id),
        )
        if entry.parent_id is None:
            menu.add_command(
                label=_("Transcribe again"),
                command=lambda: self._actions.jobs.retry_entry(self.entry_id),
            )
        menu.add_separator()
        menu.add_command(
            label=_("Delete…"),
            command=lambda: self._actions.prompts.confirm_delete_entry(self.entry_id),
        )
        self._popup_below(menu, self.btn_more)

    @staticmethod
    def _popup_below(menu: tk.Menu, widget: Any) -> None:
        try:
            menu.tk_popup(
                widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height() + 2
            )
        finally:
            menu.grab_release()

    def _on_copy(self) -> None:
        if self._mode == SUMMARY_MODE:
            self._copy_summary()
            return

        self.clipboard_clear()
        self.clipboard_append(self.text.get_text())
        self.btn_copy.configure(image=icons.icon("check", 15, theme.STATUS_DONE))
        localize(self.btn_copy, text=L_("Copied"))
        if self._copy_feedback_after_id:
            self.after_cancel(self._copy_feedback_after_id)
        self._copy_feedback_after_id = self.after(1500, self._reset_copy_button)

    def _reset_copy_button(self) -> None:
        self._copy_feedback_after_id = None
        self.btn_copy.configure(image=icons.icon("copy", 15))
        localize(self.btn_copy, text=L_("Copy"))
