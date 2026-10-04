import webbrowser
from collections.abc import Callable
from typing import Any

import customtkinter as ctk
from PIL import Image

import utils.constants as c
import utils.path_helper as ph
import utils.validators as validators
from handlers.ai_providers import PROVIDERS, AiProvider, get_provider
from handlers.translation_handler import get_ai_provider, translation_providers
from handlers.translation_handler import get_env_key as get_translation_env_key
from models.config.config_ai import ConfigAi
from models.config.config_subtitles import ConfigSubtitles
from models.config.config_system import ConfigSystem
from models.config.config_whisper_api import ConfigWhisperApi
from models.config.config_whisperx import ConfigWhisperX
from utils.config_manager import ConfigManager
from utils.enums import ComputeType, TimestampGranularities
from utils.env_keys import EnvKeys
from utils.i18n import (
    SYSTEM_LANGUAGE,
    UI_LANGUAGES,
    _,
    get_docs_url,
    get_language,
    sort_key,
)
from utils.update_checker import Release
from views.settings.option_labels import OptionLabels, save_config
from views.style import icons, theme
from views.widgets.option_menu import CTkOptionMenu, skip_scrollbar_forced_layout

DEBOUNCE_DELAY_MS = 600
ABOUT_ICON_SIZE = 96

# Tabs that can be opened directly (see `PreferencesDialog`)
GENERAL_TAB = "general"
AI_TAB = "ai"
API_KEYS_TAB = "api_keys"


def api_key_labels() -> dict[EnvKeys, tuple[str, str]]:
    """The title and the description of each API key."""
    return {
        EnvKeys.OPENAI_API_KEY: (
            _("OpenAI API key"),
            _(
                "Required by the Whisper API, and to summarize and translate with OpenAI."
            ),
        ),
        EnvKeys.ANTHROPIC_API_KEY: (
            _("Anthropic API key"),
            _("Required to summarize and translate with Claude."),
        ),
        EnvKeys.DEEPSEEK_API_KEY: (
            _("DeepSeek API key"),
            _("Required to summarize and translate with DeepSeek."),
        ),
        EnvKeys.GEMINI_API_KEY: (
            _("Gemini API key"),
            _(
                "Required to summarize and translate with Gemini (from Google AI Studio)."
            ),
        ),
        EnvKeys.MISTRAL_API_KEY: (
            _("Mistral API key"),
            _("Required to summarize and translate with Mistral."),
        ),
        EnvKeys.XAI_API_KEY: (
            _("xAI API key"),
            _("Required to summarize and translate with Grok."),
        ),
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


class PreferencesDialog(ctk.CTkToplevel):  # type: ignore[misc]
    """The settings of the app that don't change with each transcription."""

    def __init__(
        self,
        master: Any,
        on_set_api_key: Callable[[EnvKeys, str], None],
        on_ui_language_change: Callable[[str], None],
        on_model_change: Callable[[], None],
        can_change_language: bool,
        initial_tab: str | None = None,
        on_ai_change: Callable[[], None] | None = None,
        on_check_for_updates: (
            Callable[[Callable[[Release | None, bool], None]], None] | None
        ) = None,
    ) -> None:
        """
        :param initial_tab: The tab shown first, e.g. `AI_TAB`. Defaults to the
                            general one.
        :param on_ai_change: Called when the provider of the summaries or the
                             translations changes.
        :param on_check_for_updates: Checks whether a new version is available,
                                     calling back with it, if any, and whether
                                     the check failed.
        """
        super().__init__(master)
        self._on_set_api_key = on_set_api_key
        self._on_ui_language_change = on_ui_language_change
        self._on_model_change = on_model_change
        self._on_ai_change = on_ai_change
        self._on_check_for_updates = on_check_for_updates
        self._available_update: Release | None = None
        self._can_change_language = can_change_language
        self._debounce_after_ids: dict[Any, str] = {}

        self._config_system = ConfigManager.get_config_system()
        self._config_whisperx = ConfigManager.get_config_whisperx()
        self._config_subtitles = ConfigManager.get_config_subtitles()
        self._config_whisper_api = ConfigManager.get_config_whisper_api()
        self._config_ai = ConfigManager.get_config_ai()

        self.title(_("Preferences"))
        self.geometry("640x560")
        self.minsize(560, 440)
        self.transient(master.winfo_toplevel())
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=0, column=0, padx=16, pady=(8, 16), sticky=ctk.NSEW)

        self._key_buttons: dict[EnvKeys, list[ctk.CTkButton]] = {}
        self._tab_names = {
            GENERAL_TAB: _("General"),
            AI_TAB: _("AI"),
            API_KEYS_TAB: _("API keys"),
        }
        self._init_general(self.tabs.add(self._tab_names[GENERAL_TAB]))
        self._init_ai(self.tabs.add(self._tab_names[AI_TAB]))
        self._init_api_keys(self.tabs.add(self._tab_names[API_KEYS_TAB]))
        self._init_whisperx(self.tabs.add("WhisperX"))
        self._init_subtitles(self.tabs.add(_("Subtitles")))
        self._init_whisper_api(self.tabs.add("Whisper API"))
        self._init_about(self.tabs.add(_("About")))
        self._refresh_key_buttons()
        if initial_tab:
            self.show_tab(initial_tab)

        self.bind("<Escape>", lambda _event: self.destroy())
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
        """Shows a tab, e.g. `AI_TAB`."""
        if name := self._tab_names.get(tab):
            self.tabs.set(name)

    # HELPERS

    @staticmethod
    def _row(tab: Any, row: int, label: str, hint: str = "") -> ctk.CTkFrame:
        tab.grid_columnconfigure(0, weight=1)
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.grid(row=row, column=0, padx=8, pady=8, sticky=ctk.EW)
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=label, font=theme.font(13), anchor=ctk.W).grid(
            row=0, column=0, sticky=ctk.W
        )
        if hint:
            ctk.CTkLabel(
                frame,
                text=hint,
                font=theme.font(12),
                text_color=theme.HINT_TEXT,
                anchor=ctk.W,
                justify=ctk.LEFT,
                wraplength=340,
            ).grid(row=1, column=0, sticky=ctk.W)
        return frame

    def _entry(
        self,
        frame: ctk.CTkFrame,
        initial: Any,
        key: ConfigManager.KeyType,
        validator: Callable[[str], bool],
        width: int = 70,
    ) -> ctk.CTkEntry:
        variable = ctk.StringVar(self, str(initial))
        entry = ctk.CTkEntry(frame, width=width, textvariable=variable)
        entry.configure(
            validate="key", validatecommand=(entry.register(validator), "%P")
        )
        entry.grid(row=0, column=1, rowspan=2, padx=(12, 0))
        variable.trace_add(
            "write", lambda *_args: self._debounce_save(key, variable.get())
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
        self, key: ConfigManager.KeyType, value: str, allow_empty: bool = False
    ) -> None:
        if after_id := self._debounce_after_ids.pop(key, None):
            self.after_cancel(after_id)
        if value or allow_empty:
            self._debounce_after_ids[key] = self.after(
                DEBOUNCE_DELAY_MS, lambda: save_config(key, value)
            )

    # TABS

    def _init_general(self, tab: Any) -> None:
        appearance_labels = OptionLabels(
            {"System": _("System"), "Light": _("Light"), "Dark": _("Dark")}
        )
        frame = self._row(tab, 0, _("Appearance"))
        menu = ctk.CTkSegmentedButton(
            frame,
            values=appearance_labels.labels,
            command=lambda label: self._on_appearance_change(
                appearance_labels.value(label)
            ),
        )
        menu.set(appearance_labels.label(self._config_system.appearance_mode))
        menu.grid(row=0, column=1, rowspan=2, padx=(12, 0))

        language_labels = OptionLabels(
            {SYSTEM_LANGUAGE: _("System language")}
            | dict(sorted(UI_LANGUAGES.items(), key=lambda item: sort_key(item[1])))
        )
        frame = self._row(
            tab,
            1,
            _("Interface language"),
            ""
            if self._can_change_language
            else _("It can be changed when no transcription is in progress."),
        )
        language_menu = CTkOptionMenu(
            frame,
            values=language_labels.labels,
            command=lambda label: self._on_language_change(
                language_labels.value(label)
            ),
            state=ctk.NORMAL if self._can_change_language else ctk.DISABLED,
        )
        language_menu.set(language_labels.label(self._config_system.ui_language))
        language_menu.grid(row=0, column=1, rowspan=2, padx=(12, 0))

        frame = self._row(
            tab,
            2,
            _("Notifications"),
            _("Shows a notification of the system when a transcription is ready."),
        )
        self._switch(
            frame,
            self._config_system.notify_when_done,
            lambda is_on: save_config(ConfigSystem.Key.NOTIFY_WHEN_DONE, str(is_on)),
        )

        frame = self._row(
            tab, 3, _("Updates"), _("Checks for a new version when the app opens.")
        )
        self._switch(
            frame,
            self._config_system.check_for_updates,
            lambda is_on: save_config(ConfigSystem.Key.CHECK_FOR_UPDATES, str(is_on)),
        )

    def _scrollable(self, tab: Any) -> ctk.CTkScrollableFrame:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        skip_scrollbar_forced_layout(frame)
        frame.grid(row=0, column=0, sticky=ctk.NSEW)
        return frame

    def _key_button(self, frame: Any, env_key: EnvKeys, column: int = 1) -> None:
        """A button that sets the API key, showing whether it's set."""
        button = ctk.CTkButton(
            frame,
            width=110,
            command=lambda: self._set_key(env_key),
            **theme.SECONDARY_BUTTON,
        )
        button.grid(row=0, column=column, rowspan=2, padx=(12, 0))
        self._key_buttons.setdefault(env_key, []).append(button)

    def _init_api_keys(self, tab: Any) -> None:
        frame = self._scrollable(tab)
        for row, (env_key, (title, hint)) in enumerate(api_key_labels().items()):
            self._key_button(self._row(frame, row, title, hint), env_key)

    def _set_key(self, env_key: EnvKeys) -> None:
        self._on_set_api_key(env_key, api_key_labels()[env_key][0])
        if self.winfo_exists():
            self._refresh_key_buttons()

    def _refresh_key_buttons(self) -> None:
        for env_key, buttons in self._key_buttons.items():
            # The buttons of the providers are replaced when they change
            buttons[:] = [button for button in buttons if button.winfo_exists()]
            is_set = bool(env_key.get_value(default=""))
            for button in buttons:
                button.configure(text=("✓ " + _("Change…")) if is_set else _("Set…"))

    def _init_ai(self, tab: Any) -> None:
        frame = self._scrollable(tab)
        ai_names = {provider.value: info.name for provider, info in PROVIDERS.items()}
        ai_labels = OptionLabels(
            dict(sorted(ai_names.items(), key=lambda item: sort_key(item[1])))
        )
        self._init_provider_rows(
            frame,
            row=0,
            title=_("Summary"),
            labels=ai_labels,
            provider=get_provider(self._config_ai.summary_provider).value,
            model=self._config_ai.summary_model,
            provider_key=ConfigAi.Key.SUMMARY_PROVIDER,
            model_key=ConfigAi.Key.SUMMARY_MODEL,
            get_env_key=lambda value: PROVIDERS[get_provider(value)].env_key,
            get_default_model=lambda value: (
                PROVIDERS[get_provider(value)].default_model
            ),
        )

        translation_labels = OptionLabels(translation_providers())
        translation_provider = self._config_ai.translation_provider
        if translation_provider not in translation_providers():
            translation_provider = AiProvider.OPENAI.value

        def default_translation_model(value: str) -> str:
            ai_provider = get_ai_provider(value)
            return PROVIDERS[ai_provider].default_model if ai_provider else ""

        self._init_provider_rows(
            frame,
            row=3,
            title=_("Translation"),
            labels=translation_labels,
            provider=translation_provider,
            model=self._config_ai.translation_model,
            provider_key=ConfigAi.Key.TRANSLATION_PROVIDER,
            model_key=ConfigAi.Key.TRANSLATION_MODEL,
            get_env_key=get_translation_env_key,
            get_default_model=default_translation_model,
        )

        ctk.CTkLabel(
            frame, text=_("Ollama"), font=theme.font(14, "bold"), anchor=ctk.W
        ).grid(row=6, column=0, padx=8, pady=(18, 0), sticky=ctk.W)
        row_frame = self._row(
            frame,
            7,
            _("Server URL"),
            _("Ollama runs the models on your computer, without an API key."),
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
        title: str,
        labels: OptionLabels,
        provider: str,
        model: str,
        provider_key: ConfigAi.Key,
        model_key: ConfigAi.Key,
        get_env_key: Callable[[str], EnvKeys | None],
        get_default_model: Callable[[str], str],
    ) -> None:
        """
        The rows to choose a provider and its model, with a button to set the API
        key of the provider. The model is the default one of the provider unless
        the user changes it.
        """
        ctk.CTkLabel(frame, text=title, font=theme.font(14, "bold"), anchor=ctk.W).grid(
            row=row, column=0, padx=8, pady=(18 if row else 4, 0), sticky=ctk.W
        )
        provider_frame = self._row(frame, row + 1, _("Provider"))
        key_buttons = ctk.CTkFrame(provider_frame, fg_color="transparent")
        key_buttons.grid(row=0, column=2, rowspan=2)

        model_frame = self._row(
            frame,
            row + 2,
            _("Model"),
            _("The default model of the provider if empty."),
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
            if env_key := get_env_key(value):
                self._key_button(key_buttons, env_key, column=0)
            self._refresh_key_buttons()
            # DeepL and Google Translate have no models to choose
            has_models = bool(get_default_model(value))
            model_entry.configure(state=ctk.NORMAL if has_models else ctk.DISABLED)

        def on_provider_change(label: str) -> None:
            value = labels.value(label)
            save_config(provider_key, value)
            # The models of a provider don't apply to the others
            save_config(model_key, "")
            model_entry.configure(state=ctk.NORMAL)
            model_entry.delete(0, ctk.END)
            model_entry.insert(0, get_default_model(value))
            show_provider(value)
            if self._on_ai_change:
                self._on_ai_change()

        menu = CTkOptionMenu(
            provider_frame, values=labels.labels, width=180, command=on_provider_change
        )
        menu.set(labels.label(provider))
        menu.grid(row=0, column=1, rowspan=2, padx=(12, 0))
        show_provider(provider)

    def _init_whisperx(self, tab: Any) -> None:
        frame = self._row(
            tab,
            0,
            _("Compute type"),
            _("float16 is faster on GPUs. int8 uses less memory."),
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
            tab, 1, _("Batch size"), _("Lower it if you run out of memory.")
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
            _("Use CPU"),
            ""
            if self._config_whisperx.can_use_gpu
            else _("No CUDA GPU was found, so WhisperX runs on the CPU."),
        )
        switch = self._switch(
            frame,
            self._config_whisperx.use_cpu or not self._config_whisperx.can_use_gpu,
            lambda is_on: self._on_model_option(ConfigWhisperX.Key.USE_CPU, str(is_on)),
        )
        if not self._config_whisperx.can_use_gpu:
            switch.configure(state=ctk.DISABLED)

    def _init_subtitles(self, tab: Any) -> None:
        frame = self._row(
            tab,
            0,
            _("Highlight words"),
            _("Underlines each word as it's said (.srt and .vtt)."),
        )
        self._switch(
            frame,
            self._config_subtitles.highlight_words,
            lambda is_on: save_config(ConfigSubtitles.Key.HIGHLIGHT_WORDS, str(is_on)),
        )
        frame = self._row(tab, 1, _("Max. line count"))
        self._entry(
            frame,
            self._config_subtitles.max_line_count,
            ConfigSubtitles.Key.MAX_LINE_COUNT,
            validators.is_valid_positive_int,
        )
        frame = self._row(tab, 2, _("Max. line width"))
        self._entry(
            frame,
            self._config_subtitles.max_line_width,
            ConfigSubtitles.Key.MAX_LINE_WIDTH,
            validators.is_valid_positive_int,
        )

    def _init_whisper_api(self, tab: Any) -> None:
        frame = self._row(
            tab,
            0,
            _("Temperature"),
            _("Between 0 and 1. Higher values are more random."),
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
            _("Timestamps of the words"),
            _("Highlights each word while playing (whisper-1 model). Takes longer."),
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
        ctk.CTkLabel(
            tab,
            text=_("Version {version}").format(version=c.APP_VERSION),
            text_color=theme.HINT_TEXT,
        ).grid(row=2, column=0)
        ctk.CTkLabel(
            tab, text=_("Made by {author}").format(author="HenestrosaDev")
        ).grid(row=3, column=0, pady=(14, 0))

        links = ctk.CTkFrame(tab, fg_color="transparent")
        links.grid(row=4, column=0, pady=(18, 0))
        ctk.CTkButton(
            links,
            text=_("Documentation"),
            image=icons.icon("book", 14),
            compound=ctk.LEFT,
            width=120,
            command=lambda: webbrowser.open(get_docs_url(c.DOCS_URL, get_language())),
            **theme.SECONDARY_BUTTON,
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
        ctk.CTkButton(
            links,
            text=_("Donate"),
            image=icons.icon("heart", 14, theme.ICON_ON_ACCENT),
            compound=ctk.LEFT,
            width=120,
            command=lambda: webbrowser.open(c.DONATION_URL),
            **theme.PRIMARY_BUTTON,
        ).grid(row=0, column=2, padx=6)

        if self._on_check_for_updates is None:
            return
        self.btn_update = ctk.CTkButton(
            tab,
            text=_("Check for updates"),
            image=icons.icon("refresh", 14),
            compound=ctk.LEFT,
            width=160,
            command=self._on_update_button,
            **theme.SECONDARY_BUTTON,
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
        self.lbl_update.configure(
            text=_("Checking for updates…"), text_color=theme.HINT_TEXT
        )
        self._on_check_for_updates(self._on_update_checked)

    def _on_update_checked(self, release: Release | None, has_error: bool) -> None:
        # The dialog may have been closed during the check
        if not self.winfo_exists():
            return

        self.btn_update.configure(state=ctk.NORMAL)
        if has_error:
            self.lbl_update.configure(
                text=_("Could not check for updates."), text_color=theme.ERROR_TEXT
            )
        elif release:
            self._available_update = release
            self.btn_update.configure(
                text=_("Download"),
                image=icons.icon("import", 14, theme.ICON_ON_ACCENT),
                border_width=0,
                text_color=theme.ICON_ON_ACCENT,
                **theme.PRIMARY_BUTTON,
            )
            self.lbl_update.configure(
                text=_("Version {version} is available").format(
                    version=release.version
                ),
                text_color=theme.TEXT,
            )
        else:
            self.lbl_update.configure(
                text=_("You have the latest version."), text_color=theme.HINT_TEXT
            )

    def _on_appearance_change(self, mode: str) -> None:
        ctk.set_appearance_mode(mode)
        save_config(ConfigSystem.Key.APPEARANCE_MODE, mode)

    def _on_language_change(self, language: str) -> None:
        save_config(ConfigSystem.Key.UI_LANGUAGE, language)
        self.destroy()
        self._on_ui_language_change(language)

    def _on_model_option(self, key: ConfigWhisperX.Key, value: str) -> None:
        save_config(key, value)
        self._on_model_change()
