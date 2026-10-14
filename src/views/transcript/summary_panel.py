import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from typing import Any

import customtkinter as ctk

from models.summary import TranscriptSummary
from utils.i18n import L_, _
from utils.time_format import format_timestamp
from views.history.formatting import format_full_date
from views.localization import localize
from views.style import icons, theme
from views.transcript.transcript_text import find_matches
from views.widgets.bindings import bind_wraplength
from views.widgets.button import icon_button, set_button_state
from views.widgets.option_menu import skip_scrollbar_forced_layout
from views.widgets.scrollable_frame import CTkScrollableFrame
from views.widgets.textbox import CTkTextbox

# (light, dark) colors of the matches of a search, like in the transcript
MATCH_COLOR = ("#FFF3B0", "#5C4B00")
CURRENT_MATCH_COLOR = ("#FFC94D", "#A07800")


class SummaryText(CTkTextbox):
    """
    The summary, its key points and its chapters, which can be selected and
    searched, but not edited. Clicking the start of a chapter plays it.
    """

    def __init__(self, master: Any, on_chapter: Callable[[float], None]) -> None:
        super().__init__(
            master,
            wrap=ctk.WORD,
            font=theme.font(14),
            fg_color="transparent",
            border_spacing=10,
            activate_scrollbars=True,
            state=ctk.DISABLED,
        )
        self._on_chapter = on_chapter
        self._matches: list[tuple[str, str]] = []
        self._current_match: int | None = None

        self._textbox.configure(spacing1=2, spacing3=2)
        self.tag_config("bullet", lmargin1=8, lmargin2=26, spacing3=4)
        self.tag_config("chapter_start", foreground=self._color(theme.ACCENT_TEXT))
        self.tag_config("match", background=self._color(MATCH_COLOR))
        self.tag_config("current_match", background=self._color(CURRENT_MATCH_COLOR))
        self._tag_fonts()

    def _set_scaling(
        self, new_widget_scaling: float, new_window_scaling: float
    ) -> None:
        super()._set_scaling(new_widget_scaling, new_window_scaling)
        # The size of the interface changed (see `PreferencesDialog`)
        self._tag_fonts()

    def _color(self, pair: tuple[str, str]) -> str:
        value: str = self._apply_appearance_mode(pair)
        return value

    def _tag_fonts(self) -> None:
        # CTkTextbox forbids fonts in the tags, since they don't follow its
        # scaling, so they're set on the Tk widget with the scaled size
        self._textbox.tag_config(
            "heading",
            font=self._apply_font_scaling(theme.font(15, "bold")),
            spacing1=16,
            spacing3=6,
        )
        self._textbox.tag_config(
            "chapter_start",
            font=self._apply_font_scaling(
                theme.font(12, family=theme.MONOSPACE_FAMILY)
            ),
        )

    def set_summary(self, summary: TranscriptSummary) -> None:
        self.configure(state=ctk.NORMAL)
        self.delete("1.0", ctk.END)
        for tag in self.tag_names():
            if tag.startswith("chapter_") and tag != "chapter_start":
                self.tag_delete(tag)

        # Its title is the one of the panel
        self.insert(ctk.END, summary.summary)
        if summary.key_points:
            self.insert(ctk.END, "\n" + _("Key points"), "heading")
            for point in summary.key_points:
                self.insert(ctk.END, f"\n•  {point}", "bullet")
        if summary.chapters:
            self.insert(ctk.END, "\n" + _("Chapters"), "heading")
            for idx, chapter in enumerate(summary.chapters):
                tag = f"chapter_{idx}"
                self.insert(ctk.END, "\n")
                self.insert(
                    ctk.END, format_timestamp(chapter.start), ("chapter_start", tag)
                )
                self.insert(ctk.END, f"  {chapter.title}")
                self.tag_bind(
                    tag,
                    "<ButtonRelease-1>",
                    lambda _event, start=chapter.start: self._on_chapter(start),
                )
                self.tag_bind(
                    tag, "<Enter>", lambda _event: self.configure(cursor="hand2")
                )
                self.tag_bind(tag, "<Leave>", lambda _event: self.configure(cursor=""))
        self.configure(state=ctk.DISABLED)
        self._matches, self._current_match = [], None

    # SEARCH (see `SearchableText`)

    @property
    def match_status(self) -> tuple[int | None, int]:
        return self._current_match, len(self._matches)

    def search(
        self, query: str, match_case: bool = False, current: int | None = None
    ) -> None:
        self.tag_remove("match", "1.0", ctk.END)
        self.tag_remove("current_match", "1.0", ctk.END)
        # Its own `search` is the one of the find dialog
        self._matches = find_matches(self._textbox, query, match_case)
        self._current_match = None
        if self._matches:
            if current is None:
                self.go_to_match(1)
            else:
                self._current_match = min(current, len(self._matches) - 1)
                self.go_to_match(0)

    def go_to_match(self, step: int) -> None:
        if not self._matches:
            return
        if self._current_match is None:
            self._current_match = 0 if step > 0 else len(self._matches) - 1
        else:
            self._current_match = (self._current_match + step) % len(self._matches)
        start, end = self._matches[self._current_match]
        self.tag_remove("current_match", "1.0", ctk.END)
        self.tag_add("current_match", start, end)
        self.see(start)

    def selected_text(self) -> str:
        try:
            return str(self.get(ctk.SEL_FIRST, ctk.SEL_LAST))
        except tk.TclError:
            return ""


class SummaryPanel(ctk.CTkFrame):  # type: ignore[misc]
    """
    The summary of a transcription: its summary, key points and chapters, which
    play the audio from where they start. Without a summary, it offers to
    generate it, and to choose the provider that generates it.
    """

    def __init__(
        self,
        master: Any,
        on_generate: Callable[[], None],
        on_regenerate: Callable[[], None],
        on_chapter: Callable[[float], None],
        on_search: Callable[[], None],
        on_copy: Callable[[], None],
        on_export: Callable[[Any], None],
        on_settings: Callable[[], None],
        on_set_api_key: Callable[[], None],
    ) -> None:
        super().__init__(
            master,
            fg_color=theme.CARD_BG,
            border_color=theme.CARD_BORDER,
            border_width=1,
            corner_radius=12,
        )
        self._on_generate = on_generate
        self._on_settings = on_settings
        self._on_set_api_key = on_set_api_key

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Like the header of the transcript and of its translation
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=(16, 8), pady=(8, 0), sticky=ctk.EW)
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            header, text="", image=icons.icon("text", 15, theme.ICON_MUTED)
        ).grid(row=0, column=0, padx=(0, 6))
        localize(
            ctk.CTkLabel(header, font=theme.font(14, "bold"), anchor=ctk.W),
            text=L_("Summary"),
        ).grid(row=0, column=1, sticky=ctk.W)
        self.btn_search = icon_button(
            header,
            "search",
            on_search,
            lambda: _("Find ({shortcut})").format(
                shortcut=f"{theme.SHORTCUT_MODIFIER_LABEL}F"
            ),
        )
        self.btn_copy = icon_button(header, "copy", on_copy, L_("Copy"))
        self.btn_export = icon_button(
            header, "export", lambda: on_export(self.btn_export), L_("Export")
        )
        self.btn_regenerate = icon_button(
            header, "refresh", on_regenerate, L_("Regenerate the summary")
        )
        self._buttons = (self.btn_search, self.btn_copy, self.btn_export)
        for column, button in enumerate((*self._buttons, self.btn_regenerate), start=2):
            button.grid(row=0, column=column, padx=(2, 0))

        # Who generated it and when, in the row of the hints of the transcript
        self.lbl_details = ctk.CTkLabel(
            self,
            text="",
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
            justify=ctk.LEFT,
        )
        self.lbl_details.grid(row=1, column=0, padx=16, pady=(2, 0), sticky=ctk.EW)
        bind_wraplength(self.lbl_details, minimum=150)

        self.frm_content = CTkScrollableFrame(self, fg_color="transparent")
        skip_scrollbar_forced_layout(self.frm_content)
        self.frm_content.grid(row=2, column=0, padx=2, pady=(0, 2), sticky=ctk.NSEW)
        self.frm_content.grid_columnconfigure(0, weight=1)
        # Shown instead of the messages, once there is a summary
        self.text = SummaryText(self, on_chapter)

    def show(
        self,
        summary: TranscriptSummary | None,
        provider: str,
        is_loading: bool = False,
        error: str = "",
        can_generate: bool = True,
    ) -> None:
        """
        :param provider: The name of the provider that generates the summaries.
        :param is_loading: Whether the summary is being generated.
        :param error: Why the last summary couldn't be generated, if it failed.
        :param can_generate: Whether a summary can be generated (the API key of
                             the provider is set).
        """
        for widget in self.frm_content.winfo_children():
            widget.destroy()

        has_summary = summary is not None and not is_loading
        for button in self._buttons:
            set_button_state(button, ctk.NORMAL if has_summary else ctk.DISABLED)
        # Shown only when there is a summary to generate again
        if has_summary:
            self.btn_regenerate.grid()
        else:
            self.btn_regenerate.grid_remove()
        if has_summary:
            self.frm_content.grid_remove()
            self.text.grid(row=2, column=0, padx=2, pady=(0, 2), sticky=ctk.NSEW)
        else:
            self.lbl_details.grid_remove()
            self.text.grid_remove()
            self.frm_content.grid()

        if is_loading:
            self._show_message(
                _("Summarizing…"),
                _("{provider} is reading the transcription. It takes a moment.").format(
                    provider=provider
                ),
            )
        elif summary is None and can_generate:
            self._show_message(
                _("No summary yet"),
                _(
                    "Generate a summary, the key points and the chapters of the "
                    "transcription with {provider}."
                ).format(provider=provider),
                error=error,
                actions=[
                    (_("Generate summary"), self._on_generate),
                    (_("Settings"), self._on_settings),
                ],
            )
        elif summary is None:
            self._show_message(
                _("No summary yet"),
                _(
                    "Set the API key of {provider} to summarize, or choose another "
                    "provider in the settings."
                ).format(provider=provider),
                error=error,
                actions=[
                    (_("Set API key…"), self._on_set_api_key),
                    (_("Settings"), self._on_settings),
                ],
            )
        else:
            self._show_details(summary, error)
            self.text.set_summary(summary)

    # STATES

    def _show_message(
        self,
        title: str,
        message: str,
        error: str = "",
        actions: list[tuple[str, Callable[[], None]]] | None = None,
    ) -> None:
        """
        :param actions: The text and the command of the buttons. The first one is
                        the main action.
        """
        frame = ctk.CTkFrame(self.frm_content, fg_color="transparent")
        frame.grid(row=0, column=0, padx=24, pady=48, sticky=ctk.EW)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame, text="", image=icons.icon("text", 36, theme.ICON_MUTED)
        ).grid(row=0, column=0)
        ctk.CTkLabel(frame, text=title, font=theme.font(16, "bold")).grid(
            row=1, column=0, pady=(10, 4)
        )
        lbl_message = ctk.CTkLabel(
            frame,
            text=message,
            font=theme.font(13),
            text_color=theme.HINT_TEXT,
            justify=ctk.CENTER,
        )
        lbl_message.grid(row=2, column=0, sticky=ctk.EW)
        bind_wraplength(lbl_message, minimum=200)

        if error:
            lbl_error = ctk.CTkLabel(
                frame,
                text=error,
                font=theme.font(12),
                text_color=theme.ERROR_TEXT,
                justify=ctk.CENTER,
            )
            lbl_error.grid(row=3, column=0, pady=(8, 0), sticky=ctk.EW)
            bind_wraplength(lbl_error, minimum=200)

        if actions:
            buttons = ctk.CTkFrame(frame, fg_color="transparent")
            buttons.grid(row=4, column=0, pady=(16, 0))
            for column, (text, command) in enumerate(actions):
                ctk.CTkButton(
                    buttons,
                    text=text,
                    image=None if column == 0 else icons.icon("gear", 14),
                    compound=ctk.LEFT,
                    width=0,
                    height=34,
                    command=command,
                    **(theme.PRIMARY_BUTTON if column == 0 else theme.SECONDARY_BUTTON),
                ).grid(row=0, column=column, padx=4)

    def _show_details(self, summary: TranscriptSummary, error: str) -> None:
        """Shows who generated it and when, or why it couldn't be regenerated."""
        if error:
            text, color = error, theme.ERROR_TEXT
        else:
            text, color = self._describe(summary), theme.HINT_TEXT
            if summary.is_partial:
                text += "\n" + _(
                    "The transcription is very long, so only its beginning was "
                    "summarized."
                )
        self.lbl_details.configure(text=text, text_color=color)
        self.lbl_details.grid()

    @staticmethod
    def _describe(summary: TranscriptSummary) -> str:
        """The model that generated the summary and when."""
        try:
            date = format_full_date(datetime.fromisoformat(summary.created_at))
        except ValueError:
            date = ""

        if summary.model and date:
            return _("Generated by {model} · {date}").format(
                model=summary.model, date=date
            )
        return summary.model or date
