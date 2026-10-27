from collections.abc import Callable
from datetime import datetime
from typing import Any

import customtkinter as ctk

from models.question import TranscriptAnswer
from utils.i18n import L_, _
from utils.time_format import format_timestamp
from views.history.formatting import format_full_date
from views.localization import localize
from views.style import icons, theme
from views.widgets.bindings import bind_wraplength
from views.widgets.button import icon_button, set_button_state
from views.widgets.textbox import CTkTextbox


class ConversationText(CTkTextbox):
    """
    The questions asked about the transcription and their answers, which can be
    selected and copied, but not edited. Clicking a source of an answer plays it.
    """

    def __init__(self, master: Any, on_source: Callable[[float], None]) -> None:
        super().__init__(
            master,
            wrap=ctk.WORD,
            font=theme.font(14),
            fg_color="transparent",
            border_spacing=10,
            activate_scrollbars=True,
            state=ctk.DISABLED,
        )
        self._on_source = on_source

        self._textbox.configure(spacing1=2, spacing3=2)
        self.tag_config("answer", lmargin1=0, lmargin2=0, spacing3=4)
        self.tag_config("source", lmargin1=8, lmargin2=8)
        self.tag_config("source_start", foreground=self._color(theme.ACCENT_TEXT))
        self.tag_config("details", foreground=self._color(theme.HINT_TEXT))
        self.tag_config("pending", foreground=self._color(theme.HINT_TEXT))
        self.tag_config("error", foreground=self._color(theme.ERROR_TEXT))
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
            "question",
            font=self._apply_font_scaling(theme.font(14, "bold")),
            spacing1=14,
            spacing3=4,
        )
        for tag, size in (("details", 11), ("source_start", 12)):
            self._textbox.tag_config(
                tag,
                font=self._apply_font_scaling(
                    theme.font(size, family=theme.MONOSPACE_FAMILY)
                    if tag == "source_start"
                    else theme.font(size)
                ),
            )

    def set_conversation(
        self,
        answers: list[TranscriptAnswer],
        pending: str | None,
        error: str,
        waiting_message: str,
    ) -> None:
        """
        :param pending: The question being answered, if any.
        :param error: Why the last question couldn't be answered, if it failed.
        :param waiting_message: Shown below the question being answered.
        """
        self.configure(state=ctk.NORMAL)
        self.delete("1.0", ctk.END)
        for tag in self.tag_names():
            if tag.startswith("source_") and tag != "source_start":
                self.tag_delete(tag)

        for idx, answer in enumerate(answers):
            self._insert_answer(idx, answer)
        if pending:
            self._insert_line(pending, "question")
            self._insert_line(waiting_message, "pending")
        if error:
            self._insert_line(error, "error")

        self.configure(state=ctk.DISABLED)
        self.see(ctk.END)

    def _insert_line(self, text: str, *tags: str) -> None:
        # The first line isn't preceded by a line break
        prefix = "\n" if self.get("1.0", "end-1c") else ""
        self.insert(ctk.END, prefix + text, tags)

    def _insert_answer(self, idx: int, answer: TranscriptAnswer) -> None:
        self._insert_line(answer.question, "question")
        self._insert_line(answer.answer, "answer")
        for source_idx, source in enumerate(answer.sources):
            tag = f"source_{idx}_{source_idx}"
            self._insert_line("", "source")
            self.insert(
                ctk.END, format_timestamp(source.start), ("source", "source_start", tag)
            )
            self.insert(ctk.END, f"  “{source.quote}”", "source")
            self.tag_bind(
                tag,
                "<ButtonRelease-1>",
                lambda _event, start=source.start: self._on_source(start),
            )
            self.tag_bind(tag, "<Enter>", lambda _event: self.configure(cursor="hand2"))
            self.tag_bind(tag, "<Leave>", lambda _event: self.configure(cursor=""))
        if details := describe(answer):
            self._insert_line(details, "details")


def describe(answer: TranscriptAnswer) -> str:
    """The model that answered and when."""
    try:
        date = format_full_date(datetime.fromisoformat(answer.created_at))
    except ValueError:
        date = ""
    return " · ".join(part for part in (answer.model, date) if part)


class AskPanel(ctk.CTkFrame):  # type: ignore[misc]
    """
    Questions about a transcription, answered by the language model of the
    summaries. The answers link to the parts of the transcription that support
    them, which play the audio from where they start.
    """

    def __init__(
        self,
        master: Any,
        on_ask: Callable[[str], None],
        on_clear: Callable[[], None],
        on_source: Callable[[float], None],
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
        self._on_ask = on_ask
        self._on_settings = on_settings
        self._on_set_api_key = on_set_api_key

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Like the header of the transcript and of its summary
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=(16, 8), pady=(8, 0), sticky=ctk.EW)
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            header, text="", image=icons.icon("chat", 15, theme.ICON_MUTED)
        ).grid(row=0, column=0, padx=(0, 6))
        localize(
            ctk.CTkLabel(header, font=theme.font(14, "bold"), anchor=ctk.W),
            text=L_("Ask"),
        ).grid(row=0, column=1, sticky=ctk.W)
        self.btn_clear = icon_button(
            header, "trash", on_clear, L_("Clear conversation")
        )
        self.btn_clear.grid(row=0, column=2, padx=(2, 0))

        self.frm_message = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_message.grid_columnconfigure(0, weight=1)
        self.text = ConversationText(self, on_source)

        frm_input = ctk.CTkFrame(self, fg_color="transparent")
        frm_input.grid(row=2, column=0, padx=12, pady=(4, 12), sticky=ctk.EW)
        frm_input.grid_columnconfigure(0, weight=1)
        self.ent_question = localize(
            ctk.CTkEntry(frm_input, height=34, font=theme.font(13)),
            placeholder_text=L_("Ask a question about the transcription…"),
        )
        self.ent_question.grid(row=0, column=0, sticky=ctk.EW)
        self.ent_question.bind("<Return>", lambda _event: self._ask())
        self.ent_question.bind("<KP_Enter>", lambda _event: self._ask())
        self.btn_ask = localize(
            ctk.CTkButton(
                frm_input,
                width=0,
                height=34,
                command=self._ask,
                **theme.PRIMARY_BUTTON,
            ),
            text=L_("Ask"),
        )
        self.btn_ask.grid(row=0, column=1, padx=(8, 0))

    def show(
        self,
        answers: list[TranscriptAnswer],
        provider: str,
        pending: str | None = None,
        error: str = "",
        can_ask: bool = True,
    ) -> None:
        """
        :param provider: The name of the provider that answers.
        :param pending: The question being answered, if any.
        :param error: Why the last question couldn't be answered, if it failed.
        :param can_ask: Whether questions can be asked (the API key of the
                        provider is set).
        """
        for widget in self.frm_message.winfo_children():
            widget.destroy()

        is_waiting = pending is not None
        input_state = ctk.NORMAL if can_ask and not is_waiting else ctk.DISABLED
        self.ent_question.configure(state=input_state)
        set_button_state(self.btn_ask, input_state)
        set_button_state(
            self.btn_clear, ctk.NORMAL if answers and not is_waiting else ctk.DISABLED
        )

        if answers or is_waiting:
            self.frm_message.grid_remove()
            self.text.grid(row=1, column=0, padx=2, pady=(0, 2), sticky=ctk.NSEW)
            self.text.set_conversation(
                answers,
                pending,
                error,
                _("{provider} is reading the transcription. It takes a moment.").format(
                    provider=provider
                ),
            )
            return

        self.text.grid_remove()
        self.frm_message.grid(row=1, column=0, padx=24, pady=32, sticky=ctk.NSEW)
        if can_ask:
            self._show_message(
                _(
                    "Ask {provider} about the transcription, such as what was "
                    "decided or who said something. The answers link to where "
                    "it's said."
                ).format(provider=provider),
                error,
                [(_("Settings"), self._on_settings)],
            )
        else:
            self._show_message(
                _(
                    "Set the API key of {provider} to ask about the transcription, "
                    "or choose another provider in the settings."
                ).format(provider=provider),
                error,
                [
                    (_("Set API key…"), self._on_set_api_key),
                    (_("Settings"), self._on_settings),
                ],
            )

    def _ask(self) -> None:
        question = self.ent_question.get().strip()
        if not question or self.ent_question.cget("state") == ctk.DISABLED:
            return
        self.ent_question.delete(0, ctk.END)
        self._on_ask(question)

    def _show_message(
        self,
        message: str,
        error: str,
        actions: list[tuple[str, Callable[[], None]]],
    ) -> None:
        """:param actions: The text and the command of the buttons."""
        frame = self.frm_message
        ctk.CTkLabel(
            frame, text="", image=icons.icon("chat", 36, theme.ICON_MUTED)
        ).grid(row=0, column=0)
        lbl_message = ctk.CTkLabel(
            frame,
            text=message,
            font=theme.font(13),
            text_color=theme.HINT_TEXT,
            justify=ctk.CENTER,
        )
        lbl_message.grid(row=1, column=0, pady=(10, 0), sticky=ctk.EW)
        bind_wraplength(lbl_message, minimum=200)

        if error:
            lbl_error = ctk.CTkLabel(
                frame,
                text=error,
                font=theme.font(12),
                text_color=theme.ERROR_TEXT,
                justify=ctk.CENTER,
            )
            lbl_error.grid(row=2, column=0, pady=(8, 0), sticky=ctk.EW)
            bind_wraplength(lbl_error, minimum=200)

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.grid(row=3, column=0, pady=(16, 0))
        for column, (text, command) in enumerate(actions):
            is_main = column == 0 and len(actions) > 1
            ctk.CTkButton(
                buttons,
                text=text,
                image=None if is_main else icons.icon("gear", 14),
                compound=ctk.LEFT,
                width=0,
                height=34,
                command=command,
                **(theme.PRIMARY_BUTTON if is_main else theme.SECONDARY_BUTTON),
            ).grid(row=0, column=column, padx=4)
