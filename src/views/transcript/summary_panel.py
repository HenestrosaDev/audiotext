from collections.abc import Callable
from datetime import datetime
from typing import Any

import customtkinter as ctk

from models.summary import TranscriptSummary
from utils.i18n import _
from utils.time_format import format_timestamp
from views.history.formatting import format_full_date
from views.style import icons, theme
from views.widgets.bindings import bind_wraplength
from views.widgets.option_menu import skip_scrollbar_forced_layout
from views.widgets.scrollable_frame import CTkScrollableFrame


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
        on_chapter: Callable[[float], None],
        on_copy: Callable[[], None],
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
        self._on_chapter = on_chapter
        self._on_copy = on_copy
        self._on_settings = on_settings
        self._on_set_api_key = on_set_api_key

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.frm_content = CTkScrollableFrame(self, fg_color="transparent")
        skip_scrollbar_forced_layout(self.frm_content)
        self.frm_content.grid(row=0, column=0, padx=2, pady=2, sticky=ctk.NSEW)
        self.frm_content.grid_columnconfigure(0, weight=1)

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
            self._show_summary(summary, error)

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

    def _show_summary(self, summary: TranscriptSummary, error: str) -> None:
        row = 0

        def section(title: str) -> None:
            nonlocal row
            ctk.CTkLabel(
                self.frm_content, text=title, font=theme.font(15, "bold"), anchor=ctk.W
            ).grid(row=row, column=0, padx=18, pady=(16, 6), sticky=ctk.W)
            row += 1

        def paragraph(text: str, padx: Any = 18, pady: Any = 0) -> None:
            nonlocal row
            label = ctk.CTkLabel(
                self.frm_content,
                text=text,
                font=theme.font(14),
                anchor=ctk.W,
                justify=ctk.LEFT,
            )
            label.grid(row=row, column=0, padx=padx, pady=pady, sticky=ctk.EW)
            bind_wraplength(label, margin=10, minimum=200)
            row += 1

        section(_("Summary"))
        paragraph(summary.summary)
        if summary.is_partial:
            hint = ctk.CTkLabel(
                self.frm_content,
                text=_(
                    "The transcription is very long, so only its beginning was "
                    "summarized."
                ),
                font=theme.font(12),
                text_color=theme.HINT_TEXT,
                anchor=ctk.W,
            )
            hint.grid(row=row, column=0, padx=18, pady=(4, 0), sticky=ctk.EW)
            row += 1

        if summary.key_points:
            section(_("Key points"))
            for point in summary.key_points:
                paragraph(f"•  {point}", padx=(24, 18), pady=(0, 4))

        if summary.chapters:
            section(_("Chapters"))
            for chapter in summary.chapters:
                chapter_row = ctk.CTkFrame(self.frm_content, fg_color="transparent")
                chapter_row.grid(row=row, column=0, padx=14, sticky=ctk.EW)
                chapter_row.grid_columnconfigure(1, weight=1)
                ctk.CTkButton(
                    chapter_row,
                    text=format_timestamp(chapter.start),
                    width=64,
                    height=26,
                    font=theme.font(12, family=theme.MONOSPACE_FAMILY),
                    command=lambda start=chapter.start: self._on_chapter(start),
                    **theme.SECONDARY_BUTTON,
                ).grid(row=0, column=0, pady=2)
                ctk.CTkLabel(
                    chapter_row, text=chapter.title, font=theme.font(14), anchor=ctk.W
                ).grid(row=0, column=1, padx=(10, 0), sticky=ctk.W)
                row += 1

        footer = ctk.CTkFrame(self.frm_content, fg_color="transparent")
        footer.grid(row=row, column=0, padx=18, pady=(20, 16), sticky=ctk.EW)
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            footer,
            text=self._describe(summary),
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
        ).grid(row=0, column=0, sticky=ctk.W)
        ctk.CTkButton(
            footer,
            text=_("Copy"),
            image=icons.icon("copy", 14),
            compound=ctk.LEFT,
            width=0,
            height=28,
            command=self._on_copy,
            **theme.SECONDARY_BUTTON,
        ).grid(row=0, column=1, padx=(8, 0))
        ctk.CTkButton(
            footer,
            text=_("Regenerate"),
            image=icons.icon("refresh", 14),
            compound=ctk.LEFT,
            width=0,
            height=28,
            command=self._on_generate,
            **theme.SECONDARY_BUTTON,
        ).grid(row=0, column=2, padx=(8, 0))

        if error:
            ctk.CTkLabel(
                footer,
                text=error,
                font=theme.font(12),
                text_color=theme.ERROR_TEXT,
                anchor=ctk.W,
            ).grid(row=1, column=0, columnspan=3, pady=(6, 0), sticky=ctk.W)

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
