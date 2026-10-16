import webbrowser
from collections.abc import Callable
from datetime import datetime
from typing import Any

import customtkinter as ctk
from PIL import Image

import utils.constants as c
import utils.devices as devices
import utils.path_helper as ph
import utils.validators as validators
from handlers.ai_providers import PROVIDERS, AiProvider, get_provider
from handlers.translation_handler import get_ai_provider, translation_providers
from handlers.translation_handler import get_env_key as get_translation_env_key
from models.config.config_ai import ConfigAi
from models.config.config_subtitles import ConfigSubtitles
from models.config.config_system import (
    UI_SCALES,
    ConfigSystem,
    DateFormat,
    TimeFormat,
)
from models.config.config_whisper_api import ConfigWhisperApi
from models.config.config_whisperx import ConfigWhisperX
from utils.config_manager import ConfigManager
from utils.enums import ComputeType, TimestampGranularities
from utils.env_keys import EnvKeys
from utils.i18n import (
    L_,
    SYSTEM_LANGUAGE,
    UI_LANGUAGES,
    _,
    get_docs_url,
    get_language,
    sort_key,
)
from utils.update_checker import Release
from views.history.formatting import (
    format_clock_time,
    format_day,
    get_date_formats,
    set_date_formats,
)
from views.localization import (
    Text,
    localize,
    on_language_change,
    set_interface_language,
)
from views.settings.option_labels import save_config
from views.style import icons, theme
from views.widgets.bindings import bind_wraplength
from views.widgets.localized_options import LocalizedOptions
from views.widgets.option_menu import CTkOptionMenu, skip_scrollbar_forced_layout
from views.widgets.scrollable_frame import CTkScrollableFrame
from views.widgets.window import place_dialog

DEBOUNCE_DELAY_MS = 600
ABOUT_ICON_SIZE = 96
KEY_ICON_SIZE = 14

# Tabs that can be opened directly (see `PreferencesDialog`)
GENERAL_TAB = "general"
PROVIDERS_TAB = "providers"
API_KEYS_TAB = "api_keys"
TRANSCRIPTION_TAB = "transcription"
SUBTITLES_TAB = "subtitles"
ABOUT_TAB = "about"


def api_key_labels() -> dict[EnvKeys, tuple[str, str | None]]:
    """
    The title and the description of each API key. The keys whose use the
    subtitle of their group already explains have none.
    """
    return {
        EnvKeys.OPENAI_API_KEY: (
            _("OpenAI API key"),
            _("Also required for transcription with the Whisper API."),
        ),
        EnvKeys.ANTHROPIC_API_KEY: (_("Anthropic API key"), None),
        EnvKeys.DEEPSEEK_API_KEY: (_("DeepSeek API key"), None),
        # Often mistaken for the keys of Google Cloud
        EnvKeys.GEMINI_API_KEY: (
            _("Gemini API key"),
            _("Get it from Google AI Studio."),
        ),
        EnvKeys.MISTRAL_API_KEY: (_("Mistral API key"), None),
        EnvKeys.XAI_API_KEY: (_("xAI API key"), None),
        EnvKeys.DEEPL_API_KEY: (
            _("DeepL API key"),
            _("Required to translate with DeepL. Keys of the free plan work too."),
        ),
        EnvKeys.GOOGLE_API_KEY: (
            _("Google API key"),
            _(
                "Optional for Google Speech-to-Text: without it, the free tier is used. Required to translate with Google Translate (Cloud Translation API)."
            ),
        ),
        EnvKeys.HF_TOKEN: (
            _("Hugging Face token"),
            _(
                "Required to identify speakers with WhisperX (pyannote/speaker-diarization-community-1)."
            ),
        ),
    }


def api_key_groups() -> list[tuple[Text, Text | None, list[EnvKeys]]]:
    """
    The API keys grouped by what they're used for, with the title and the
    subtitle of each group.
    """
    return [
        (
            L_("LLM providers"),
            L_(
                "Needed to use these providers for summaries, questions, and "
                "translations."
            ),
            [
                EnvKeys.OPENAI_API_KEY,
                EnvKeys.ANTHROPIC_API_KEY,
                EnvKeys.DEEPSEEK_API_KEY,
                EnvKeys.GEMINI_API_KEY,
                EnvKeys.MISTRAL_API_KEY,
                EnvKeys.XAI_API_KEY,
            ],
        ),
        (L_("Translation"), None, [EnvKeys.DEEPL_API_KEY, EnvKeys.GOOGLE_API_KEY]),
        (L_("Transcription"), None, [EnvKeys.HF_TOKEN]),
    ]


def api_key_title(env_key: EnvKeys) -> Text:
    return lambda: api_key_labels()[env_key][0]


def api_key_description(env_key: EnvKeys) -> Text | None:
    if api_key_labels()[env_key][1] is None:
        return None
    return lambda: api_key_labels()[env_key][1] or ""


def engines_docs_url() -> str:
    """The page of the documentation that compares the engines and their models."""
    return get_docs_url(c.DOCS_URL, get_language()) + "reference/engines/"


class PreferencesDialog(ctk.CTkToplevel):  # type: ignore[misc]
    """The settings of the app that don't change with each transcription."""

    def __init__(
        self,
        master: Any,
        on_set_api_key: Callable[[EnvKeys, str], None],
        on_model_change: Callable[[], None],
        initial_tab: str | None = None,
        on_ai_change: Callable[[], None] | None = None,
        on_check_for_updates: (
            Callable[[Callable[[Release | None, bool], None]], None] | None
        ) = None,
        on_date_format_change: Callable[[], None] | None = None,
        on_subtitles_change: Callable[[], None] | None = None,
    ) -> None:
        """
        :param initial_tab: The tab shown first, e.g. `PROVIDERS_TAB`. Defaults to the
                            general one.
        :param on_ai_change: Called when the provider of the summaries or the
                             translations changes.
        :param on_date_format_change: Called when the format of the dates or
                                      the times changes, to show them again.
        :param on_subtitles_change: Called when the size of the subtitles
                                    changes, to split them again.
        :param on_check_for_updates: Checks whether a new version is available,
                                     calling back with it, if any, and whether
                                     the check failed.
        """
        super().__init__(master)
        # Shown by `place_dialog` once it's built, already in its place
        self.withdraw()
        self._on_set_api_key = on_set_api_key
        self._on_model_change = on_model_change
        self._on_ai_change = on_ai_change
        self._on_check_for_updates = on_check_for_updates
        self._on_date_format_change = on_date_format_change
        self._on_subtitles_change = on_subtitles_change
        self._available_update: Release | None = None
        self._debounce_after_ids: dict[Any, str] = {}

        self._config_system = ConfigManager.get_config_system()
        self._config_whisperx = ConfigManager.get_config_whisperx()
        self._config_subtitles = ConfigManager.get_config_subtitles()
        self._config_whisper_api = ConfigManager.get_config_whisper_api()
        self._config_ai = ConfigManager.get_config_ai()

        localize(self, title=L_("Preferences"))
        self.minsize(560, 440)
        self.transient(master.winfo_toplevel())
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # The background of the main window, so the cards of the sections stand
        # out from it as they do there
        self.tabs = ctk.CTkTabview(self, fg_color=theme.WINDOW_BG)
        self.tabs.grid(row=0, column=0, padx=16, pady=(8, 16), sticky=ctk.NSEW)

        self._key_buttons: dict[EnvKeys, list[ctk.CTkButton]] = {}
        self._key_width: float | None = None
        # The names of the tabs are their keys in the tab view, so they're
        # renamed when the language changes
        self._tab_texts: dict[str, Text] = {
            GENERAL_TAB: L_("General"),
            PROVIDERS_TAB: L_("Providers"),
            API_KEYS_TAB: L_("API keys"),
            TRANSCRIPTION_TAB: L_("Transcription"),
            SUBTITLES_TAB: L_("Subtitles"),
            ABOUT_TAB: L_("About"),
        }
        self._tab_names = {tab: text() for tab, text in self._tab_texts.items()}
        tabs = {tab: self.tabs.add(name) for tab, name in self._tab_names.items()}
        self._init_general(tabs[GENERAL_TAB])
        self._init_providers(tabs[PROVIDERS_TAB])
        self._init_api_keys(tabs[API_KEYS_TAB])
        self._init_transcription(tabs[TRANSCRIPTION_TAB])
        self._init_subtitles(tabs[SUBTITLES_TAB])
        self._init_about(tabs[ABOUT_TAB])
        self._refresh_key_buttons()
        on_language_change(self, self._rename_tabs)
        on_language_change(self, self._fit_key_buttons)
        if initial_tab:
            self.show_tab(initial_tab)

        self.bind("<Escape>", lambda _event: self.destroy())
        place_dialog(self, master, 640, 560)
        self.after(100, self._focus)

    def _focus(self) -> None:
        if self.winfo_exists():
            self.lift()
            self.focus_force()

    def destroy(self) -> None:
        for after_id in self._debounce_after_ids.values():
            self.after_cancel(after_id)
        super().destroy()

    def show_tab(self, tab: str) -> None:
        """Shows a tab, e.g. `PROVIDERS_TAB`."""
        if name := self._tab_names.get(tab):
            self.tabs.set(name)

    def _rename_tabs(self) -> None:
        current = next(
            (tab for tab, name in self._tab_names.items() if name == self.tabs.get()),
            GENERAL_TAB,
        )
        # The tab view refuses a name that another tab has, even for a moment, so
        # they're given temporary ones first
        for tab, name in self._tab_names.items():
            self.tabs.rename(name, f"\0{tab}")
        for tab, text in self._tab_texts.items():
            self._tab_names[tab] = text()
            self.tabs.rename(f"\0{tab}", self._tab_names[tab])
        self.show_tab(current)

    # HELPERS

    @staticmethod
    def _row(tab: Any, row: int, label: Text, hint: Text | None = None) -> ctk.CTkFrame:
        tab.grid_columnconfigure(0, weight=1)
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.grid(row=row, column=0, padx=8, pady=8, sticky=ctk.EW)
        frame.grid_columnconfigure(0, weight=1)
        localize(
            ctk.CTkLabel(frame, font=theme.font(13), anchor=ctk.W), text=label
        ).grid(row=0, column=0, sticky=ctk.W)
        if hint:
            hint_label = localize(
                ctk.CTkLabel(
                    frame,
                    font=theme.font(12),
                    text_color=theme.HINT_TEXT,
                    anchor=ctk.W,
                    justify=ctk.LEFT,
                    wraplength=300,
                ),
                text=hint,
            )
            # It takes the width that the control of the row leaves, which is
            # narrower inside the cards of the sections
            hint_label.grid(row=1, column=0, sticky=ctk.EW)
            bind_wraplength(hint_label, minimum=160)
        return frame

    @staticmethod
    def _section(
        tab: Any, row: int, title: Text, subtitle: Text | None = None
    ) -> ctk.CTkFrame:
        """
        A card with a title that groups some rows, so the groups of a tab stand
        apart, also while it scrolls. The rows go in the frame that it returns.
        """
        tab.grid_columnconfigure(0, weight=1)
        card = ctk.CTkFrame(
            tab,
            fg_color=theme.CARD_BG,
            border_color=theme.CARD_BORDER,
            border_width=1,
            corner_radius=10,
        )
        card.grid(row=row, column=0, padx=(0, 4), pady=(0, 12), sticky=ctk.EW)
        card.grid_columnconfigure(0, weight=1)
        localize(
            ctk.CTkLabel(card, font=theme.font(14, "bold"), anchor=ctk.W), text=title
        ).grid(row=0, column=0, padx=16, pady=(12, 0), sticky=ctk.W)
        if subtitle:
            subtitle_label = localize(
                ctk.CTkLabel(
                    card,
                    font=theme.font(12),
                    text_color=theme.HINT_TEXT,
                    anchor=ctk.W,
                    justify=ctk.LEFT,
                    wraplength=300,
                ),
                text=subtitle,
            )
            subtitle_label.grid(row=1, column=0, padx=16, sticky=ctk.EW)
            bind_wraplength(subtitle_label, minimum=160)
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=2, column=0, padx=8, pady=(0, 8), sticky=ctk.EW)
        return body

    @staticmethod
    def _link(frame: Any, row: int, text: Text, get_url: Callable[[], str]) -> None:
        """A text that opens a web page, below the label of a row."""
        label = localize(
            ctk.CTkLabel(
                frame,
                font=ctk.CTkFont(size=12, underline=True),
                text_color=theme.ACCENT_TEXT,
                anchor=ctk.W,
                cursor="hand2",
            ),
            text=text,
        )
        label.grid(row=row, column=0, sticky=ctk.W)
        label.bind("<Button-1>", lambda _event: webbrowser.open(get_url()))

    def _entry(
        self,
        frame: ctk.CTkFrame,
        initial: Any,
        key: ConfigManager.KeyType,
        validator: Callable[[str], bool],
        width: int = 70,
        on_save: Callable[[], None] | None = None,
    ) -> ctk.CTkEntry:
        """:param on_save: Called after the value is saved."""
        variable = ctk.StringVar(self, str(initial))
        entry = ctk.CTkEntry(frame, width=width, textvariable=variable)
        entry.configure(
            validate="key", validatecommand=(entry.register(validator), "%P")
        )
        entry.grid(row=0, column=1, rowspan=2, padx=(12, 0))
        variable.trace_add(
            "write",
            lambda *_args: self._debounce_save(key, variable.get(), on_save=on_save),
        )
        return entry

    def _switch(
        self, frame: ctk.CTkFrame, is_on: bool, command: Callable[[bool], None]
    ) -> ctk.CTkSwitch:
        switch = ctk.CTkSwitch(frame, text="", width=46)
        switch.configure(command=lambda: command(bool(switch.get())))
        switch.grid(row=0, column=1, rowspan=2, padx=(12, 0))
        if is_on:
            switch.select()
        return switch

    def _debounce_save(
        self,
        key: ConfigManager.KeyType,
        value: str,
        allow_empty: bool = False,
        on_save: Callable[[], None] | None = None,
    ) -> None:
        if after_id := self._debounce_after_ids.pop(key, None):
            self.after_cancel(after_id)
        if value or allow_empty:

            def save() -> None:
                save_config(key, value)
                if on_save:
                    on_save()

            self._debounce_after_ids[key] = self.after(DEBOUNCE_DELAY_MS, save)

    # TABS

    def _init_general(self, tab: Any) -> None:
        frame = self._row(tab, 0, L_("Appearance"))
        menu = ctk.CTkSegmentedButton(frame, values=[])
        LocalizedOptions(
            menu,
            lambda: {"System": _("System"), "Light": _("Light"), "Dark": _("Dark")},
            self._config_system.appearance_mode,
            command=self._on_appearance_change,
        )
        menu.grid(row=0, column=1, rowspan=2, padx=(12, 0))

        frame = self._row(tab, 1, L_("Interface size"))
        scale_menu = CTkOptionMenu(
            frame,
            values=[f"{scale}%" for scale in UI_SCALES],
            command=lambda label: self._on_scale_change(int(label.rstrip("%"))),
        )
        scale_menu.set(f"{self._config_system.ui_scale}%")
        scale_menu.grid(row=0, column=1, rowspan=2, padx=(12, 0))

        frame = self._row(tab, 2, L_("Interface language"))
        language_menu = CTkOptionMenu(frame, values=[])
        # The languages are named in their own language
        LocalizedOptions(
            language_menu,
            lambda: (
                {SYSTEM_LANGUAGE: _("System language")}
                | dict(sorted(UI_LANGUAGES.items(), key=lambda item: sort_key(item[1])))
            ),
            self._config_system.ui_language,
            command=self._on_language_change,
        )
        language_menu.grid(row=0, column=1, rowspan=2, padx=(12, 0))

        self._init_date_formats(tab)

        frame = self._row(
            tab,
            5,
            L_("Notifications"),
            L_("Shows a system notification when a transcription is ready."),
        )
        self._switch(
            frame,
            self._config_system.notify_when_done,
            lambda is_on: save_config(ConfigSystem.Key.NOTIFY_WHEN_DONE, str(is_on)),
        )

        frame = self._row(tab, 6, L_("Check for updates automatically"))
        self._switch(
            frame,
            self._config_system.check_for_updates,
            lambda is_on: save_config(ConfigSystem.Key.CHECK_FOR_UPDATES, str(is_on)),
        )

    def _init_date_formats(self, tab: Any) -> None:
        """The formats of the dates and the times, shown as examples of them."""
        date_format, time_format = get_date_formats()
        # An afternoon time, so the 12- and 24-hour clocks differ
        example = datetime.now().replace(hour=13, minute=30)

        # Formats that look the same in the language (e.g. the short and the
        # medium ones in Japanese) are shown once
        frame = self._row(tab, 3, L_("Date format"))
        date_menu = CTkOptionMenu(frame, values=[])
        LocalizedOptions(
            date_menu,
            lambda: {
                option.value: format_day(example, option) for option in DateFormat
            },
            date_format.value,
            command=lambda value: self._on_date_format_change_to(
                DateFormat(value), get_date_formats()[1]
            ),
        )
        date_menu.grid(row=0, column=1, rowspan=2, padx=(12, 0))

        frame = self._row(
            tab,
            4,
            L_("Time format"),
            L_("Automatic follows the time format of the interface language."),
        )
        time_menu = ctk.CTkSegmentedButton(frame, values=[])
        LocalizedOptions(
            time_menu,
            lambda: (
                {TimeFormat.AUTO.value: _("Automatic")}
                | {
                    option.value: format_clock_time(example, option)
                    for option in (TimeFormat.HOURS_12, TimeFormat.HOURS_24)
                }
            ),
            time_format.value,
            command=lambda value: self._on_date_format_change_to(
                get_date_formats()[0], TimeFormat(value)
            ),
        )
        time_menu.grid(row=0, column=1, rowspan=2, padx=(12, 0))

    def _on_date_format_change_to(
        self, date_format: DateFormat, time_format: TimeFormat
    ) -> None:
        set_date_formats(date_format, time_format)
        save_config(ConfigSystem.Key.DATE_FORMAT, date_format.value)
        save_config(ConfigSystem.Key.TIME_FORMAT, time_format.value)
        if self._on_date_format_change:
            self._on_date_format_change()

    def _scrollable(self, tab: Any) -> CTkScrollableFrame:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        frame = CTkScrollableFrame(tab, fg_color="transparent")
        skip_scrollbar_forced_layout(frame)
        frame.grid(row=0, column=0, sticky=ctk.NSEW)
        return frame

    @staticmethod
    def _key_icon(is_set: bool) -> ctk.CTkImage:
        """
        A check for the keys that are set, so they're told apart at a glance in a
        long list. Both buttons have an icon, so their texts line up.
        """
        if is_set:
            return icons.icon("check", KEY_ICON_SIZE, theme.SUCCESS_TEXT)
        return icons.icon("plus", KEY_ICON_SIZE, theme.ICON_MUTED)

    def _key_button(self, frame: Any, env_key: EnvKeys, column: int = 1) -> None:
        """A button that sets the API key, showing whether it's set."""
        button = ctk.CTkButton(
            frame,
            width=self._key_button_width(),
            compound=ctk.LEFT,
            command=lambda: self._set_key(env_key),
            **theme.SECONDARY_BUTTON,
        )
        button.grid(row=0, column=column, rowspan=2, padx=(12, 0))
        self._key_buttons.setdefault(env_key, []).append(button)

    def _init_api_keys(self, tab: Any) -> None:
        frame = self._scrollable(tab)
        for section_row, (title, subtitle, env_keys) in enumerate(api_key_groups()):
            section = self._section(frame, section_row, title, subtitle)
            for row, env_key in enumerate(env_keys):
                row_frame = self._row(
                    section, row, api_key_title(env_key), api_key_description(env_key)
                )
                self._key_button(row_frame, env_key)

    def _set_key(self, env_key: EnvKeys) -> None:
        self._on_set_api_key(env_key, api_key_labels()[env_key][0])
        if self.winfo_exists():
            self._refresh_key_buttons()

    def _refresh_key_buttons(self) -> None:
        for env_key, buttons in self._key_buttons.items():
            # The buttons of the providers are replaced when they change
            buttons[:] = [button for button in buttons if button.winfo_exists()]
            is_set = bool(env_key.get_value(default=""))
            text = L_("Change API key…") if is_set else L_("Set API key…")
            for button in buttons:
                button.configure(image=self._key_icon(is_set))
                localize(button, text=text)

    def _key_button_width(self) -> float:
        """
        The width of the buttons of the keys, the one of their longest text, so
        they're as wide as each other whether the key is set or not.
        """
        if self._key_width is None:
            # Measured with a button that isn't shown, so the others don't change
            probe = ctk.CTkButton(
                self, width=0, compound=ctk.LEFT, **theme.SECONDARY_BUTTON
            )
            widths = []
            for text, is_set in (
                (_("Set API key…"), False),
                (_("Change API key…"), True),
            ):
                probe.configure(text=text, image=self._key_icon(is_set))
                probe.update_idletasks()
                widths.append(probe.winfo_reqwidth())
            # In unscaled pixels, as the width of the buttons is given
            self._key_width = max(widths) / probe._get_widget_scaling()
            probe.destroy()
        return self._key_width

    def _fit_key_buttons(self) -> None:
        """Gives the buttons of the keys the width of their texts in the language."""
        self._key_width = None
        width = self._key_button_width()
        for buttons in self._key_buttons.values():
            for button in buttons:
                if button.winfo_exists():
                    button.configure(width=width)

    def _init_providers(self, tab: Any) -> None:
        frame = self._scrollable(tab)
        ai_names = {provider.value: info.name for provider, info in PROVIDERS.items()}

        def init_ai_rows(
            row: int,
            title: Text,
            provider: str,
            model: str,
            provider_key: ConfigAi.Key,
            model_key: ConfigAi.Key,
        ) -> None:
            self._init_provider_rows(
                frame,
                row=row,
                title=title,
                get_labels=lambda: dict(
                    sorted(ai_names.items(), key=lambda item: sort_key(item[1]))
                ),
                provider=get_provider(provider).value,
                model=model,
                provider_key=provider_key,
                model_key=model_key,
                get_env_key=lambda value: PROVIDERS[get_provider(value)].env_key,
                get_default_model=lambda value: (
                    PROVIDERS[get_provider(value)].default_model
                ),
            )

        init_ai_rows(
            0,
            L_("Summary"),
            self._config_ai.summary_provider,
            self._config_ai.summary_model,
            ConfigAi.Key.SUMMARY_PROVIDER,
            ConfigAi.Key.SUMMARY_MODEL,
        )
        ask_provider, ask_model = self._config_ai.ask_provider_and_model()
        # Until it's set, it's the provider of the summaries, which answered the
        # questions before they had their own. It's saved as shown, so changing
        # only the model keeps the provider
        if not self._config_ai.ask_provider:
            save_config(ConfigAi.Key.ASK_PROVIDER, ask_provider)
            save_config(ConfigAi.Key.ASK_MODEL, ask_model)
        init_ai_rows(
            1,
            L_("Ask"),
            ask_provider,
            ask_model,
            ConfigAi.Key.ASK_PROVIDER,
            ConfigAi.Key.ASK_MODEL,
        )

        translation_provider = self._config_ai.translation_provider
        if translation_provider not in translation_providers():
            translation_provider = AiProvider.OPENAI.value

        def default_translation_model(value: str) -> str:
            ai_provider = get_ai_provider(value)
            return PROVIDERS[ai_provider].default_model if ai_provider else ""

        self._init_provider_rows(
            frame,
            row=2,
            title=L_("Translation"),
            get_labels=translation_providers,
            provider=translation_provider,
            model=self._config_ai.translation_model,
            provider_key=ConfigAi.Key.TRANSLATION_PROVIDER,
            model_key=ConfigAi.Key.TRANSLATION_MODEL,
            get_env_key=get_translation_env_key,
            get_default_model=default_translation_model,
        )

        row_frame = self._row(
            self._section(frame, 3, L_("Ollama")),
            0,
            L_("Server URL"),
            L_("Ollama runs the models on your computer, without an API key."),
        )
        self._entry(
            row_frame,
            self._config_ai.ollama_url,
            ConfigAi.Key.OLLAMA_URL,
            lambda value: " " not in value,
            width=200,
        )

    def _init_provider_rows(
        self,
        frame: Any,
        row: int,
        title: Text,
        get_labels: Callable[[], dict[str, str]],
        provider: str,
        model: str,
        provider_key: ConfigAi.Key,
        model_key: ConfigAi.Key,
        get_env_key: Callable[[str], EnvKeys | None],
        get_default_model: Callable[[str], str],
    ) -> None:
        """
        A section to choose a provider and its model, with a button to set the API
        key of the provider. The model is the default one of the provider unless
        the user changes it.
        """
        section = self._section(frame, row, title)
        provider_frame = self._row(section, 0, L_("Provider"))
        key_buttons = ctk.CTkFrame(provider_frame, fg_color="transparent")
        key_buttons.grid(row=0, column=2, rowspan=2)

        model_frame = self._row(
            section,
            1,
            L_("Model"),
            L_("The default model of the provider if empty."),
        )
        model_entry = ctk.CTkEntry(model_frame, width=200)
        model_entry.grid(row=0, column=1, rowspan=2, padx=(12, 0))
        model_entry.insert(0, model or get_default_model(provider))
        model_entry.bind(
            "<KeyRelease>",
            lambda _event: self._debounce_save(
                model_key, model_entry.get().strip(), allow_empty=True
            ),
        )

        def show_provider(value: str) -> None:
            for widget in key_buttons.winfo_children():
                widget.destroy()
            # Without a key (e.g. Ollama), its space is removed too, as an empty
            # frame keeps the size of the button it had
            if env_key := get_env_key(value):
                self._key_button(key_buttons, env_key, column=0)
                key_buttons.grid()
            else:
                key_buttons.grid_remove()
            self._refresh_key_buttons()
            # DeepL and Google Translate have no models to choose
            has_models = bool(get_default_model(value))
            model_entry.configure(state=ctk.NORMAL if has_models else ctk.DISABLED)

        def on_provider_change(value: str) -> None:
            save_config(provider_key, value)
            # The models of a provider don't apply to the others
            save_config(model_key, "")
            model_entry.configure(state=ctk.NORMAL)
            model_entry.delete(0, ctk.END)
            model_entry.insert(0, get_default_model(value))
            show_provider(value)
            if self._on_ai_change:
                self._on_ai_change()

        menu = CTkOptionMenu(provider_frame, values=[], width=180)
        LocalizedOptions(menu, get_labels, provider, command=on_provider_change)
        menu.grid(row=0, column=1, rowspan=2, padx=(12, 0))
        show_provider(provider)

    def _init_transcription(self, tab: Any) -> None:
        frame = self._scrollable(tab)
        self._init_whisperx(self._section(frame, 0, lambda: "WhisperX"))
        self._init_whisper_api(self._section(frame, 1, lambda: "Whisper API"))

    def _init_whisperx(self, tab: Any) -> None:
        uses_mlx = self._config_whisperx.can_use_gpu and devices.is_mlx_available()

        def gpu_hint(text: Text) -> Text:
            """
            A hint of an option that MLX ignores (it's always in half precision,
            without batches), noted on the Macs that transcribe with it.
            """
            if not uses_mlx:
                return text
            return lambda: text() + "\n" + _("Doesn't apply on the Mac's GPU.")

        frame = self._row(
            tab,
            0,
            L_("Compute type"),
            gpu_hint(
                L_(
                    "The precision of the calculations. int8 uses the least "
                    "memory, float16 is the fastest on NVIDIA GPUs, and float32 "
                    "is the most precise but the slowest."
                )
            ),
        )
        menu = CTkOptionMenu(
            frame,
            values=[compute_type.value for compute_type in ComputeType],
            width=110,
            command=lambda value: self._on_model_option(
                ConfigWhisperX.Key.COMPUTE_TYPE, value
            ),
        )
        menu.set(self._config_whisperx.compute_type)
        menu.grid(row=0, column=1, rowspan=2, padx=(12, 0))

        frame = self._row(
            tab,
            1,
            L_("Batch size"),
            gpu_hint(
                L_(
                    "How many parts of the audio are transcribed at once. Higher "
                    "is faster but uses more memory, so lower it if you run out."
                )
            ),
        )
        self._entry(
            frame,
            self._config_whisperx.batch_size,
            ConfigWhisperX.Key.BATCH_SIZE,
            validators.is_valid_positive_int,
        )

        frame = self._row(
            tab,
            2,
            L_("Use CPU"),
            (
                L_(
                    "When off, transcription runs on your Mac's GPU thanks to "
                    "mlx-whisper, which is much faster. Models without an MLX "
                    "version run on the CPU regardless."
                )
                if uses_mlx
                else None
            )
            if self._config_whisperx.can_use_gpu
            else L_("No CUDA GPU was found, so WhisperX runs on the CPU."),
        )
        if uses_mlx:
            self._link(frame, 2, L_("Supported models"), engines_docs_url)
        switch = self._switch(
            frame,
            self._config_whisperx.use_cpu or not self._config_whisperx.can_use_gpu,
            lambda is_on: self._on_model_option(ConfigWhisperX.Key.USE_CPU, str(is_on)),
        )
        if not self._config_whisperx.can_use_gpu:
            switch.configure(state=ctk.DISABLED)

    def _init_subtitles(self, tab: Any) -> None:
        self._init_subtitle_lines(tab, 0)
        frame = self._row(
            tab,
            1,
            L_("Highlight words"),
            L_("Underlines each word as it's said (.srt and .vtt)."),
        )
        self._switch(
            frame,
            self._config_subtitles.highlight_words,
            lambda is_on: save_config(ConfigSubtitles.Key.HIGHLIGHT_WORDS, str(is_on)),
        )

    def _init_subtitle_lines(self, tab: Any, row: int) -> None:
        """
        The size of the subtitles, as a table of the landscape and the portrait
        videos.
        """
        config = self._config_subtitles
        key = ConfigSubtitles.Key
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.grid(row=row, column=0, padx=8, pady=8, sticky=ctk.EW)
        frame.grid_columnconfigure(0, weight=1)

        for column, text in ((1, L_("Landscape")), (2, L_("Portrait"))):
            localize(
                ctk.CTkLabel(frame, font=theme.font(12), text_color=theme.HINT_TEXT),
                text=text,
            ).grid(row=0, column=column, padx=(12, 0))

        rows = (
            (
                L_("Max. lines per subtitle"),
                (config.max_line_count, key.MAX_LINE_COUNT),
                (config.max_line_count_vertical, key.MAX_LINE_COUNT_VERTICAL),
            ),
            (
                L_("Max. characters per line"),
                (config.max_line_width, key.MAX_LINE_WIDTH),
                (config.max_line_width_vertical, key.MAX_LINE_WIDTH_VERTICAL),
            ),
            (
                L_("Chinese, Japanese and Korean"),
                (config.max_line_width_cjk, key.MAX_LINE_WIDTH_CJK),
                (config.max_line_width_vertical_cjk, key.MAX_LINE_WIDTH_VERTICAL_CJK),
            ),
        )
        for table_row, (label, *entries) in enumerate(rows, start=1):
            # The characters of these languages are a case of the ones per line
            is_nested = table_row == len(rows)
            localize(
                ctk.CTkLabel(frame, font=theme.font(13), anchor=ctk.W), text=label
            ).grid(
                row=table_row,
                column=0,
                padx=(16 if is_nested else 0, 0),
                pady=4,
                sticky=ctk.W,
            )
            for column, (value, config_key) in enumerate(entries, start=1):
                entry = self._entry(
                    frame,
                    value,
                    config_key,
                    validators.is_valid_positive_int,
                    on_save=self._on_subtitles_change,
                )
                entry.grid(row=table_row, column=column, rowspan=1, pady=4)

        localize(
            ctk.CTkLabel(
                frame,
                font=theme.font(12),
                text_color=theme.HINT_TEXT,
                anchor=ctk.W,
                justify=ctk.LEFT,
                wraplength=440,
            ),
            text=L_(
                "Chinese, Japanese and Korean characters are about twice as wide as "
                "Latin ones."
            ),
        ).grid(row=len(rows) + 1, column=0, columnspan=3, pady=(4, 0), sticky=ctk.W)

    def _init_whisper_api(self, tab: Any) -> None:
        frame = self._row(
            tab,
            0,
            L_("Temperature"),
            L_(
                "Between 0 and 1. Lower is more consistent and literal; higher is "
                "more varied and may introduce errors. 0 is recommended for most "
                "audio."
            ),
        )
        self._entry(
            frame,
            self._config_whisper_api.temperature,
            ConfigWhisperApi.Key.TEMPERATURE,
            validators.is_valid_temperature,
        )

        frame = self._row(
            tab,
            1,
            L_("Timestamps of the words"),
            L_("Highlights each word while playing (whisper-1 model). Takes longer."),
        )
        # The timestamps of the segments are always requested
        self._switch(
            frame,
            TimestampGranularities.WORD.value
            in self._config_whisper_api.timestamp_granularities,
            lambda is_on: save_config(
                ConfigWhisperApi.Key.TIMESTAMP_GRANULARITIES,
                ",".join(
                    [TimestampGranularities.SEGMENT.value]
                    + ([TimestampGranularities.WORD.value] if is_on else [])
                ),
            ),
        )

    def _init_about(self, tab: Any) -> None:
        tab.grid_columnconfigure(0, weight=1)
        # The light icon has dark strokes, for the light appearance, and vice versa
        logo = ctk.CTkImage(
            light_image=Image.open(ph.ROOT_PATH / "res/img/icon-light.png"),
            dark_image=Image.open(ph.ROOT_PATH / "res/img/icon-dark.png"),
            size=(ABOUT_ICON_SIZE, ABOUT_ICON_SIZE),
        )
        ctk.CTkLabel(tab, text="", image=logo).grid(row=0, column=0, pady=(24, 8))
        ctk.CTkLabel(tab, text=c.APP_NAME, font=theme.font(22, "bold")).grid(
            row=1, column=0
        )
        localize(
            ctk.CTkLabel(tab, text_color=theme.HINT_TEXT),
            text=lambda: _("Version {version}").format(version=c.APP_VERSION),
        ).grid(row=2, column=0)
        localize(
            ctk.CTkLabel(tab),
            text=lambda: _("Made by {author}").format(author="HenestrosaDev"),
        ).grid(row=3, column=0, pady=(14, 0))

        links = ctk.CTkFrame(tab, fg_color="transparent")
        links.grid(row=4, column=0, pady=(18, 0))
        localize(
            ctk.CTkButton(
                links,
                image=icons.icon("book", 14),
                compound=ctk.LEFT,
                width=120,
                command=lambda: webbrowser.open(
                    get_docs_url(c.DOCS_URL, get_language())
                ),
                **theme.SECONDARY_BUTTON,
            ),
            text=L_("Documentation"),
        ).grid(row=0, column=0, padx=6)
        ctk.CTkButton(
            links,
            text="GitHub",
            image=icons.icon("github", 14),
            compound=ctk.LEFT,
            width=120,
            command=lambda: webbrowser.open(c.GITHUB_URL),
            **theme.SECONDARY_BUTTON,
        ).grid(row=0, column=1, padx=6)
        localize(
            ctk.CTkButton(
                links,
                image=icons.icon("heart", 14, theme.ICON_ON_ACCENT),
                compound=ctk.LEFT,
                width=120,
                command=lambda: webbrowser.open(c.DONATION_URL),
                **theme.PRIMARY_BUTTON,
            ),
            text=L_("Donate"),
        ).grid(row=0, column=2, padx=6)

        if self._on_check_for_updates is None:
            return
        self.btn_update = localize(
            ctk.CTkButton(
                tab,
                image=icons.icon("refresh", 14),
                compound=ctk.LEFT,
                width=160,
                command=self._on_update_button,
                **theme.SECONDARY_BUTTON,
            ),
            text=L_("Check for updates"),
        )
        self.btn_update.grid(row=5, column=0, pady=(18, 0))
        self.lbl_update = ctk.CTkLabel(
            tab, text="", font=theme.font(12), text_color=theme.HINT_TEXT
        )
        self.lbl_update.grid(row=6, column=0, pady=(4, 0))

    # EVENT HANDLERS

    def _on_update_button(self) -> None:
        if self._available_update:
            webbrowser.open(self._available_update.url)
            return
        if self._on_check_for_updates is None:
            return

        self.btn_update.configure(state=ctk.DISABLED)
        self.lbl_update.configure(text_color=theme.HINT_TEXT)
        localize(self.lbl_update, text=L_("Checking for updates…"))
        self._on_check_for_updates(self._on_update_checked)

    def _on_update_checked(self, release: Release | None, has_error: bool) -> None:
        # The dialog may have been closed during the check
        if not self.winfo_exists():
            return

        self.btn_update.configure(state=ctk.NORMAL)
        if has_error:
            self.lbl_update.configure(text_color=theme.ERROR_TEXT)
            localize(self.lbl_update, text=L_("Could not check for updates."))
        elif release:
            self._available_update = release
            self.btn_update.configure(
                image=icons.icon("import", 14, theme.ICON_ON_ACCENT),
                border_width=0,
                text_color=theme.ICON_ON_ACCENT,
                **theme.PRIMARY_BUTTON,
            )
            localize(self.btn_update, text=L_("Download"))
            self.lbl_update.configure(text_color=theme.TEXT)
            localize(
                self.lbl_update,
                text=lambda: _("Version {version} is available").format(
                    version=release.version
                ),
            )
        else:
            self.lbl_update.configure(text_color=theme.HINT_TEXT)
            localize(self.lbl_update, text=L_("You have the latest version."))

    def _on_appearance_change(self, mode: str) -> None:
        ctk.set_appearance_mode(mode)
        save_config(ConfigSystem.Key.APPEARANCE_MODE, mode)

    def _on_scale_change(self, scale: int) -> None:
        ctk.set_widget_scaling(scale / 100)
        save_config(ConfigSystem.Key.UI_SCALE, str(scale))

    def _on_language_change(self, language: str) -> None:
        save_config(ConfigSystem.Key.UI_LANGUAGE, language)
        set_interface_language(language)

    def _on_model_option(self, key: ConfigWhisperX.Key, value: str) -> None:
        save_config(key, value)
        self._on_model_change()
