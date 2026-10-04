"""The translation of a transcription, shown next to it, and the dialog to ask for it."""

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

import customtkinter as ctk

import utils.constants as c
from handlers.translation_handler import (
    DEEPL,
    get_env_key,
    has_api_key,
    translation_providers,
)
from models.transcript_segment import TranscriptSegment
from models.translation import TranscriptTranslation
from utils.config_manager import ConfigManager
from utils.env_keys import EnvKeys
from utils.i18n import _, get_language, get_language_name
from views.history.formatting import format_full_date
from views.settings.option_labels import OptionLabels, get_language_labels
from views.style import icons, theme
from views.transcript.edit_dialogs import _Dialog
from views.transcript.transcript_text import TranscriptText
from views.widgets.bindings import bind_wraplength
from views.widgets.option_menu import CTkOptionMenu
from views.widgets.searchable_option_menu import CTkSearchableOptionMenu


def language_name(code: str) -> str:
    """The name of a language in the interface language, e.g. "Spanish"."""
    return get_language_name(code, fallback=c.AUDIO_LANGUAGES.get(code, code))


def translated_segments(
    translation: TranscriptTranslation, segments: list[TranscriptSegment]
) -> list[TranscriptSegment]:
    """
    The segments of the transcription with their translated text, so the
    translation keeps their timestamps. Empty if the translation doesn't match
    them (e.g. it's of the edited text).
    """
    if not translation.segments or len(translation.segments) != len(segments):
        return []

    return [
        replace(segment, text=text, words=())
        for segment, text in zip(segments, translation.segments, strict=True)
    ]


class TranslationPanel(ctk.CTkFrame):  # type: ignore[misc]
    """
    The translation of a transcription, shown on the right of its text: in the
    same mode (with timestamps or as plain text), highlighting the segment being
    played. Clicking a segment plays it. It can be edited like the transcription.
    """

    def __init__(
        self,
        master: Any,
        on_segment_click: Callable[[int], None],
        on_segment_menu: Callable[[Any, int], str | None],
        on_text_edit: Callable[[str], None],
        on_copy: Callable[[], None],
        on_translate: Callable[[], None],
        on_close: Callable[[], None],
    ) -> None:
        """
        :param on_segment_menu: Called with the event and the index of a segment
                                that is right-clicked.
        :param on_text_edit: Called with the plain text after the user edits it.
        :param on_translate: Called to translate it again, e.g. into another
                             language.
        :param on_close: Called to hide the panel.
        """
        super().__init__(
            master,
            fg_color=theme.CARD_BG,
            border_color=theme.CARD_BORDER,
            border_width=1,
            corner_radius=12,
        )
        self._on_translate = on_translate
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=(16, 8), pady=(8, 0), sticky=ctk.EW)
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            header, text="", image=icons.icon("globe", 15, theme.ICON_MUTED)
        ).grid(row=0, column=0, padx=(0, 6))
        self.lbl_title = ctk.CTkLabel(
            header, text="", font=theme.font(14, "bold"), anchor=ctk.W
        )
        self.lbl_title.grid(row=0, column=1, sticky=ctk.EW)

        self.btn_copy = self._icon_button(header, 2, "copy", on_copy)
        self.btn_translate = self._icon_button(header, 3, "refresh", on_translate)
        self._icon_button(header, 4, "x_circle", on_close)

        self.lbl_details = ctk.CTkLabel(
            self,
            text="",
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
            justify=ctk.LEFT,
        )
        self.lbl_details.grid(row=1, column=0, padx=16, sticky=ctk.EW)
        bind_wraplength(self.lbl_details, minimum=150)

        self.text = TranscriptText(
            self,
            on_segment_click=on_segment_click,
            on_segment_menu=on_segment_menu,
            on_text_edit=on_text_edit,
        )
        # It's inside the card of the panel
        self.text.configure(fg_color="transparent", border_width=0)

        self.frm_message = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_message.grid_columnconfigure(0, weight=1)

    # PUBLIC METHODS

    def show(
        self,
        translation: TranscriptTranslation | None,
        segments: list[TranscriptSegment],
        is_loading: bool,
        error: str,
        pending_language: str | None,
    ) -> None:
        """
        :param segments: The segments of the transcription.
        :param is_loading: Whether a translation is in progress.
        :param error: Why the last translation failed, if it did.
        :param pending_language: The language being translated into, if known.
        """
        if is_loading:
            language = pending_language or (translation and translation.language)
            self.lbl_title.configure(
                text=_("Translating into {language}…").format(
                    language=language_name(language)
                )
                if language
                else _("Translating…")
            )
            self._set_details(_("It takes a moment."))
            self._show_message(
                _("The transcription is being translated. It takes a moment.")
            )
        elif translation is None:
            self.lbl_title.configure(text=_("Translation"))
            self._set_details("")
            self._show_message(
                error or _("There is no translation yet."),
                is_error=bool(error),
                action=(_("Translate…"), self._on_translate),
            )
        else:
            self.lbl_title.configure(text=language_name(translation.language))
            self._set_details(error or self._describe(translation), bool(error))
            self.frm_message.grid_forget()
            self.text.grid(row=2, column=0, padx=2, pady=(0, 2), sticky=ctk.NSEW)
            self.text.set_content(
                translated_segments(translation, segments),
                translation.text,
                translation.is_text_edited,
            )

        has_translation = translation is not None and not is_loading
        self.btn_copy.configure(state=ctk.NORMAL if has_translation else ctk.DISABLED)
        self.btn_translate.configure(state=ctk.DISABLED if is_loading else ctk.NORMAL)

    def set_mode(self, mode: str) -> None:
        self.text.set_mode(mode)

    def save_pending_text(self) -> None:
        """Saves the edited text right away, if its saving is pending."""
        self.text.save_pending_text()

    def highlight(self, position: float, is_playing: bool) -> None:
        if self.text.winfo_ismapped():
            self.text.highlight(position, is_playing)

    # STATES

    @staticmethod
    def _icon_button(
        master: Any, column: int, icon_name: str, command: Callable[[], None]
    ) -> ctk.CTkButton:
        button = ctk.CTkButton(
            master,
            text="",
            width=28,
            height=28,
            image=icons.icon(icon_name, 14),
            command=command,
            **theme.GHOST_BUTTON,
        )
        button.grid(row=0, column=column, padx=(2, 0))
        return button

    def _set_details(self, text: str, is_error: bool = False) -> None:
        self.lbl_details.configure(
            text=text, text_color=theme.ERROR_TEXT if is_error else theme.HINT_TEXT
        )

    def _show_message(
        self,
        message: str,
        is_error: bool = False,
        action: tuple[str, Callable[[], None]] | None = None,
    ) -> None:
        self.text.grid_forget()
        for widget in self.frm_message.winfo_children():
            widget.destroy()
        self.frm_message.grid(row=2, column=0, padx=24, pady=32, sticky="new")

        label = ctk.CTkLabel(
            self.frm_message,
            text=message,
            font=theme.font(13),
            text_color=theme.ERROR_TEXT if is_error else theme.HINT_TEXT,
            justify=ctk.CENTER,
        )
        label.grid(row=0, column=0, sticky=ctk.EW)
        bind_wraplength(label, minimum=150)

        if action:
            text, command = action
            ctk.CTkButton(
                self.frm_message,
                text=text,
                height=32,
                command=command,
                **theme.SECONDARY_BUTTON,
            ).grid(row=1, column=0, pady=(14, 0))

    @staticmethod
    def _describe(translation: TranscriptTranslation) -> str:
        """The provider and the model that translated it, and when."""
        provider = translation_providers().get(
            translation.provider, translation.provider
        )
        parts = [provider]
        if translation.model:
            parts.append(translation.model)
        with contextlib.suppress(ValueError):
            parts.append(
                format_full_date(datetime.fromisoformat(translation.created_at))
            )

        return " · ".join(part for part in parts if part)


@dataclass(frozen=True)
class TranslationRequest:
    language: str
    provider: str


class TranslateDialog(_Dialog):
    """Chooses the language to translate a transcription into, and the provider."""

    def __init__(
        self,
        master: Any,
        source_language: str | None,
        on_set_api_key: Callable[[EnvKeys], None],
        on_settings: Callable[[], None],
    ) -> None:
        """
        :param source_language: The language of the transcription, if known, which
                                isn't offered first.
        :param on_set_api_key: Asks for the API key of a provider.
        :param on_settings: Opens the settings of the providers.
        """
        super().__init__(master, _("Translate"), _("Translate"))
        self._on_set_api_key = on_set_api_key
        self._on_settings = on_settings
        self._result: TranslationRequest | None = None

        config = ConfigManager.get_config_ai()
        language_labels = get_language_labels()
        self._language_labels = OptionLabels(language_labels)
        self._provider_labels = OptionLabels(translation_providers())

        ctk.CTkLabel(
            self.frm_body, text=_("Translate into:"), font=theme.font(13)
        ).grid(row=0, column=0, padx=(0, 10), pady=4, sticky=ctk.W)
        self.omn_language = CTkSearchableOptionMenu(
            self.frm_body,
            values=self._language_labels.labels,
            title=_("Language of the translation"),
            search_placeholder=_("Search language…"),
            no_results_text=_("No languages found."),
            search_terms={
                language_labels[code]: f"{name} {code}"
                for code, name in c.AUDIO_LANGUAGES.items()
            },
            width=260,
            dynamic_resizing=False,
        )
        self.omn_language.grid(row=0, column=1, pady=4, sticky=ctk.EW)
        self.omn_language.set(
            self._language_labels.label(
                self._default_language(config.translation_language, source_language)
            )
        )

        ctk.CTkLabel(self.frm_body, text=_("Provider:"), font=theme.font(13)).grid(
            row=1, column=0, padx=(0, 10), pady=4, sticky=ctk.W
        )
        provider = config.translation_provider
        if provider not in translation_providers():
            provider = DEEPL
        self.omn_provider = CTkOptionMenu(
            self.frm_body,
            values=self._provider_labels.labels,
            width=260,
            command=lambda _label: self._refresh(),
        )
        self.omn_provider.set(self._provider_labels.label(provider))
        self.omn_provider.grid(row=1, column=1, pady=4, sticky=ctk.EW)

        self.frm_key = ctk.CTkFrame(self.frm_body, fg_color="transparent")
        self.frm_key.grid(row=2, column=1, pady=(6, 0), sticky=ctk.EW)
        self.frm_key.grid_columnconfigure(0, weight=1)
        self.lbl_key = ctk.CTkLabel(
            self.frm_key,
            text="",
            font=theme.font(12),
            text_color=theme.ERROR_TEXT,
            anchor=ctk.W,
            justify=ctk.LEFT,
            wraplength=260,
        )
        self.lbl_key.grid(row=0, column=0, sticky=ctk.W)
        self.btn_key = ctk.CTkButton(
            self.frm_key,
            text=_("Set API key…"),
            width=0,
            height=28,
            command=self._set_api_key,
            **theme.SECONDARY_BUTTON,
        )
        self.btn_key.grid(row=1, column=0, pady=(6, 0), sticky=ctk.W)

        ctk.CTkButton(
            self.frm_body,
            text=_("More options in the settings"),
            image=icons.icon("gear", 14),
            compound=ctk.LEFT,
            width=0,
            height=28,
            command=self._open_settings,
            **theme.GHOST_BUTTON,
        ).grid(row=3, column=1, pady=(10, 0), sticky=ctk.W)

        self._refresh()

    def get_result(self) -> TranslationRequest | None:
        """Waits until the dialog is closed. :return: None if it was cancelled."""
        self.wait()
        return self._result

    @staticmethod
    def _default_language(last_language: str, source_language: str | None) -> str:
        """The last language translated into, or else the one of the interface."""
        if last_language in c.AUDIO_LANGUAGES:
            return last_language
        interface_language = get_language().split("_")[0]
        if interface_language != source_language:
            return interface_language
        return "en" if source_language != "en" else "es"

    @property
    def _provider(self) -> str:
        return self._provider_labels.value(self.omn_provider.get())

    def _refresh(self) -> None:
        provider = self._provider
        if has_api_key(provider):
            self.frm_key.grid_remove()
            self.btn_ok.configure(state=ctk.NORMAL)
        else:
            self.lbl_key.configure(
                text=_("Set the API key of {provider} to translate with it.").format(
                    provider=self._provider_labels.label(provider)
                )
            )
            self.frm_key.grid()
            self.btn_ok.configure(state=ctk.DISABLED)

    def _set_api_key(self) -> None:
        if env_key := get_env_key(self._provider):
            # The dialog of the key needs the input, so this one releases it
            self.grab_release()
            self._on_set_api_key(env_key)
            if self.winfo_exists():
                self.grab_set()
                self._refresh()

    def _open_settings(self) -> None:
        self._close()
        self._on_settings()

    def _focus_first(self) -> None:
        self.omn_language.focus_set()

    def _ok(self) -> None:
        if not has_api_key(self._provider):
            return
        self._result = TranslationRequest(
            language=self._language_labels.value(self.omn_language.get()),
            provider=self._provider,
        )
        self._close()
