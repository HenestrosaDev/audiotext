import threading
from collections.abc import Callable
from enum import Enum, auto
from typing import Any

import customtkinter as ctk

from models.config.config_transcription import ConfigTranscription
from models.transcription_settings import TranscriptionSettings
from utils.audio_utils import (
    InputDevice,
    InputLevel,
    LevelMonitor,
    level_to_dbfs,
    list_input_devices,
)
from utils.config_manager import ConfigManager
from utils.enums import TranscriptionMethod
from utils.env_keys import EnvKeys
from utils.i18n import _
from utils.time_format import format_timestamp
from views.localization import Text, localize
from views.settings.settings_form import FormMode, SettingsForm
from views.style import icons, theme
from views.widgets.level_meter import LevelMeter
from views.widgets.localized_options import LocalizedOptions
from views.widgets.option_menu import CTkOptionMenu
from views.widgets.stepper import Stepper
from views.widgets.textbox import CTkTextbox

# Values of the device menu while the devices are loaded and when there's none
LOADING_DEVICES = "__loading__"
NO_DEVICES = "__none__"

RECORD_BUTTON_SIZE = 64
SETTINGS_WIDTH = 380


class MicState(Enum):
    IDLE = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    DONE = auto()
    FAILED = auto()


class MicrophoneView(ctk.CTkFrame):  # type: ignore[misc]
    """
    Records from a microphone and shows its transcription: the settings on the
    left, and the recorder (device, level, duration) and the text on the right.
    """

    def __init__(
        self,
        master: Any,
        on_start: Callable[[TranscriptionSettings, int | None], None],
        on_stop: Callable[[], None],
        on_open_entry: Callable[[], None],
        on_set_api_key: Callable[[EnvKeys, str], None],
        on_model_change: Callable[[], None],
        is_busy: Callable[[], bool],
        run_on_ui_thread: Callable[..., None],
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_open_entry = on_open_entry
        self._is_busy = is_busy
        self._run_on_ui_thread = run_on_ui_thread
        self._state = MicState.IDLE
        # Whether the text is shown while recording, as chosen in the settings
        self._is_live = False
        self._devices: list[InputDevice] = []
        # Name of the last device chosen, selected again while it's connected
        self._saved_device = ConfigManager.get_config_transcription().mic_device
        self._level_monitor = LevelMonitor()
        self._level_messages: dict[InputLevel, tuple[Any, Text]] = {
            InputLevel.NO_SIGNAL: (
                theme.STATUS_FAILED,
                lambda: _("No sound. Check that the microphone is on and allowed."),
            ),
            InputLevel.SILENCE: (theme.SUBTLE_BG, lambda: _("Waiting for speech…")),
            InputLevel.TOO_QUIET: (
                theme.STATUS_CANCELLED,
                lambda: _("Too quiet. Speak louder or closer to the microphone."),
            ),
            InputLevel.GOOD: (theme.STATUS_DONE, lambda: _("Good level")),
            InputLevel.TOO_LOUD: (
                theme.STATUS_FAILED,
                lambda: _("Too loud. Move away from the microphone."),
            ),
        }

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._init_header()

        self.frm_settings = SettingsForm(
            self,
            mode=FormMode.MIC,
            on_set_api_key=on_set_api_key,
            on_model_change=on_model_change,
            columns=1,
            width=SETTINGS_WIDTH,
            on_change=self._on_settings_change,
        )
        self.frm_settings.grid(
            row=2, column=0, padx=(26, 8), pady=(0, 20), sticky=ctk.NS
        )

        self._init_recorder()
        self._load_devices()
        self._on_settings_change()
        self._apply_state()

    # WIDGETS

    def _init_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, padx=32, pady=(26, 0), sticky=ctk.EW)
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            header,
            text="",
            image=icons.icon("mic", 22, theme.ICON_ON_ACCENT),
            width=40,
            height=40,
            corner_radius=10,
            fg_color=theme.ACCENT,
        ).grid(row=0, column=0, rowspan=2, padx=(0, 14))
        localize(
            ctk.CTkLabel(header, font=theme.font(22, "bold")),
            text=lambda: _("Transcribe from the microphone"),
        ).grid(row=0, column=1, sticky=ctk.W)
        localize(
            ctk.CTkLabel(header, font=theme.font(13), text_color=theme.HINT_TEXT),
            text=lambda: _(
                "Record yourself or a meeting. The recording is kept in your history."
            ),
        ).grid(row=1, column=1, sticky=ctk.W)

        self.stepper = Stepper(
            self,
            [lambda: _("Settings"), lambda: _("Record"), lambda: _("Transcribe")],
        )
        self.stepper.grid(
            row=1, column=0, columnspan=2, padx=32, pady=(22, 18), sticky=ctk.EW
        )

    def _init_recorder(self) -> None:
        card = ctk.CTkFrame(
            self,
            fg_color=theme.CARD_BG,
            border_color=theme.CARD_BORDER,
            border_width=1,
            corner_radius=14,
        )
        card.grid(row=2, column=1, padx=(8, 28), pady=(0, 20), sticky=ctk.NSEW)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(4, weight=1)

        # Microphone
        device_row = ctk.CTkFrame(card, fg_color="transparent")
        device_row.grid(row=0, column=0, padx=20, pady=(18, 0), sticky=ctk.EW)
        device_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            device_row, text="", image=icons.icon("mic", 16, theme.ICON_MUTED)
        ).grid(row=0, column=0, padx=(0, 8))
        self.omn_device = CTkOptionMenu(device_row, values=[], dynamic_resizing=False)
        # The devices by their name, which is kept in the configuration
        self._device_options = LocalizedOptions(
            self.omn_device,
            self._device_labels,
            LOADING_DEVICES,
            values=[LOADING_DEVICES],
            command=self._on_device_selected,
        )
        self.omn_device.grid(row=0, column=1, sticky=ctk.EW)
        self.btn_refresh_devices = ctk.CTkButton(
            device_row,
            text="",
            width=32,
            image=icons.icon("refresh", 15),
            command=self._load_devices,
            **theme.SECONDARY_BUTTON,
        )
        self.btn_refresh_devices.grid(row=0, column=2, padx=(8, 0))

        # Record button, duration and state
        recorder = ctk.CTkFrame(card, fg_color="transparent")
        recorder.grid(row=1, column=0, padx=20, pady=(20, 0), sticky=ctk.EW)
        recorder.grid_columnconfigure(1, weight=1)
        self.btn_record = ctk.CTkButton(
            recorder,
            text="",
            width=RECORD_BUTTON_SIZE,
            height=RECORD_BUTTON_SIZE,
            corner_radius=RECORD_BUTTON_SIZE // 2,
            command=self.trigger_primary,
        )
        self.btn_record.grid(row=0, column=0, rowspan=2, padx=(0, 18))
        self.lbl_duration = ctk.CTkLabel(
            recorder,
            text="00:00",
            font=theme.font(34, "bold", family=theme.MONOSPACE_FAMILY),
            anchor=ctk.W,
        )
        self.lbl_duration.grid(row=0, column=1, sticky=ctk.SW)
        self.lbl_state = ctk.CTkLabel(
            recorder,
            text="",
            font=theme.font(13),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
        )
        self.lbl_state.grid(row=1, column=1, sticky=ctk.NW)

        # Level meter
        meter = ctk.CTkFrame(card, fg_color="transparent")
        meter.grid(row=2, column=0, padx=20, pady=(18, 0), sticky=ctk.EW)
        meter.grid_columnconfigure(0, weight=1)
        self.level_meter = LevelMeter(meter)
        self.level_meter.grid(row=0, column=0, sticky=ctk.EW)
        speech_row = ctk.CTkFrame(meter, fg_color="transparent")
        speech_row.grid(row=1, column=0, pady=(8, 0), sticky=ctk.W)
        self.lbl_speech_dot = ctk.CTkLabel(
            speech_row,
            text="",
            width=10,
            height=10,
            corner_radius=5,
            fg_color=theme.SUBTLE_BG,
        )
        self.lbl_speech_dot.grid(row=0, column=0, padx=(0, 6))
        self.lbl_speech = ctk.CTkLabel(
            speech_row, text="", font=theme.font(12), text_color=theme.HINT_TEXT
        )
        self.lbl_speech.grid(row=0, column=1)

        # Transcription
        localize(
            ctk.CTkLabel(card, font=theme.font(15, "bold"), anchor=ctk.W),
            text=lambda: _("Transcription"),
        ).grid(row=3, column=0, padx=20, pady=(20, 6), sticky=ctk.W)
        self.tbx_text = CTkTextbox(
            card,
            wrap=ctk.WORD,
            font=theme.font(15),
            fg_color=theme.SUBTLE_BG,
            corner_radius=10,
            border_spacing=10,
        )
        self.tbx_text.grid(row=4, column=0, padx=20, sticky=ctk.NSEW)

        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.grid(row=5, column=0, padx=20, pady=14, sticky=ctk.EW)
        footer.grid_columnconfigure(0, weight=1)
        self.lbl_footer = ctk.CTkLabel(
            footer,
            text="",
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
        )
        self.lbl_footer.grid(row=0, column=0, sticky=ctk.EW)
        self.btn_copy = localize(
            ctk.CTkButton(
                footer,
                image=icons.icon("copy", 14),
                compound=ctk.LEFT,
                width=0,
                command=self._on_copy,
                **theme.SECONDARY_BUTTON,
            ),
            text=lambda: _("Copy"),
        )
        self.btn_copy.grid(row=0, column=1, padx=(8, 0))
        self.btn_open = localize(
            ctk.CTkButton(
                footer, width=0, command=self._on_open_entry, **theme.SECONDARY_BUTTON
            ),
            text=lambda: _("Open in history"),
        )
        self.btn_open.grid(row=0, column=2, padx=(8, 0))

    # PUBLIC METHODS

    @property
    def state(self) -> MicState:
        return self._state

    def trigger_primary(self) -> None:
        if self._state == MicState.RECORDING:
            self._on_stop()
        elif self._state in (MicState.IDLE, MicState.DONE, MicState.FAILED):
            if self._is_busy():
                self.lbl_footer.configure(text_color=theme.ERROR_TEXT)
                localize(
                    self.lbl_footer,
                    text=lambda: _(
                        "Wait until the current transcription finishes, or cancel it."
                    ),
                )
                return
            if error := self.frm_settings.validate():
                self.lbl_footer.configure(text=error, text_color=theme.ERROR_TEXT)
                return
            self._on_start(
                self.frm_settings.get_settings(), self._selected_device_index()
            )

    def set_state(self, state: MicState, message: str = "") -> None:
        self._state = state
        if state == MicState.RECORDING:
            self._level_monitor = LevelMonitor()
            self.tbx_text.delete("1.0", ctk.END)
            self.on_recording_progress(0, 0)
        self._apply_state(message)

    def on_recording_progress(self, elapsed_seconds: float, level: float) -> None:
        if self._state != MicState.RECORDING:
            return
        dbfs = level_to_dbfs(level)
        self.lbl_duration.configure(text=format_timestamp(elapsed_seconds))
        self.level_meter.set_level(dbfs)
        color, text = self._level_messages[self._level_monitor.update(dbfs)]
        self.lbl_speech_dot.configure(fg_color=color)
        localize(self.lbl_speech, text=text)

    def show_text(self, text: str) -> None:
        self.tbx_text.configure(text_color=theme.TEXT)
        self.tbx_text.delete("1.0", ctk.END)
        self.tbx_text.insert("1.0", text)

    def show_live_text(self, text: str) -> None:
        """Shows the draft transcribed while recording, until the final one."""
        if self._state not in (MicState.RECORDING, MicState.TRANSCRIBING):
            return
        # The draft is dimmed, since the final transcription replaces it
        self.tbx_text.configure(text_color=theme.HINT_TEXT)
        self.tbx_text.delete("1.0", ctk.END)
        self.tbx_text.insert("1.0", text)
        self.tbx_text.see(ctk.END)
        if self._state == MicState.RECORDING:
            self.lbl_footer.configure(text="", text_color=theme.HINT_TEXT)

    def show_live_status(self, message: str) -> None:
        """Shows what the live transcription is doing, e.g. loading its model."""
        if self._state != MicState.RECORDING:
            return
        has_text = bool(self.tbx_text.get("1.0", ctk.END).strip())
        if message:
            self.lbl_footer.configure(text=message, text_color=theme.HINT_TEXT)
        elif not has_text:
            self._show_placeholder()

    def refresh_api_keys(self) -> None:
        self.frm_settings.refresh_api_keys()

    # STATE

    def _apply_state(self, message: str = "") -> None:
        state = self._state
        is_recording = state == MicState.RECORDING

        self.btn_record.configure(
            image=icons.icon(
                "stop" if is_recording else "record", 24, theme.ICON_ON_ACCENT
            ),
            state=ctk.DISABLED if state == MicState.TRANSCRIBING else ctk.NORMAL,
            **theme.DANGER_BUTTON,
        )
        self.frm_settings.set_enabled(
            state not in (MicState.RECORDING, MicState.TRANSCRIBING)
        )
        self.omn_device.configure(
            state=ctk.DISABLED
            if state in (MicState.RECORDING, MicState.TRANSCRIBING) or not self._devices
            else ctk.NORMAL
        )
        self.btn_refresh_devices.configure(
            state=ctk.NORMAL if state != MicState.RECORDING else ctk.DISABLED
        )

        if state == MicState.IDLE:
            self.stepper.set_current(0)
            localize(
                self.lbl_state,
                text=lambda: _(
                    "Press the button to start recording ({shortcut})"
                ).format(shortcut=f"{theme.SHORTCUT_MODIFIER_LABEL}↩"),
            )
            self.level_meter.reset()
            localize(
                self.lbl_speech, text=lambda: _("The level is shown while recording")
            )
        elif state == MicState.RECORDING:
            self.stepper.set_current(1)
            localize(
                self.lbl_state,
                text=lambda: _("Recording… Press the button to stop and transcribe."),
            )
        elif state == MicState.TRANSCRIBING:
            self.stepper.set_current(2)
            if message:
                self.lbl_state.configure(text=message)
            else:
                localize(self.lbl_state, text=lambda: _("Transcribing…"))
            self.level_meter.reset()
            self.lbl_speech_dot.configure(fg_color=theme.SUBTLE_BG)
            self.lbl_speech.configure(text="")
        elif state == MicState.DONE:
            self.stepper.set_current(3)
            localize(
                self.lbl_state,
                text=lambda: _("Done. Press the button to record again."),
            )
        else:
            self.stepper.set_current(2, is_error=True)
            localize(self.lbl_state, text=lambda: _("Press the button to try again."))

        self.lbl_footer.configure(
            text=message if state == MicState.FAILED else "",
            text_color=theme.ERROR_TEXT,
        )
        has_result = state == MicState.DONE
        self.btn_open.configure(state=ctk.NORMAL if has_result else ctk.DISABLED)
        self.btn_copy.configure(state=ctk.NORMAL if has_result else ctk.DISABLED)
        has_text = bool(self.tbx_text.get("1.0", ctk.END).strip())
        if state in (MicState.IDLE, MicState.RECORDING) and not has_text:
            self._show_placeholder()
        elif state == MicState.TRANSCRIBING and has_text:
            self.lbl_footer.configure(text_color=theme.HINT_TEXT)
            localize(
                self.lbl_footer,
                text=lambda: _(
                    "Draft. It's replaced when the final transcription finishes."
                ),
            )

    def _show_placeholder(self) -> None:
        """Explains, below the empty text, when the text is shown."""
        is_live = self._is_live
        self.lbl_footer.configure(text_color=theme.HINT_TEXT)
        localize(
            self.lbl_footer,
            text=lambda: (
                _("The text will appear here as you speak.")
                if is_live
                else _("The transcription will appear here when you stop recording.")
            ),
        )

    def _on_settings_change(self) -> None:
        # Called while the settings are created, before the view is ready
        if not hasattr(self, "frm_settings") or not hasattr(self, "tbx_text"):
            return
        # The choice is kept while recording, when the settings are disabled
        if self._state in (MicState.RECORDING, MicState.TRANSCRIBING):
            return

        settings = self.frm_settings.get_settings()
        self._is_live = (
            settings.transcription_method == TranscriptionMethod.WHISPERX
            and settings.live_transcription
        )
        steps: list[Text]
        if self._is_live:
            steps = [
                lambda: _("Settings"),
                lambda: _("Record and transcribe"),
                lambda: _("Refine"),
            ]
        else:
            steps = [
                lambda: _("Settings"),
                lambda: _("Record"),
                lambda: _("Transcribe"),
            ]
        self.stepper.set_steps(steps)
        # Only the texts that depend on the choice are updated. `_apply_state`
        # refreshes the settings, which would call this again
        is_empty = not self.tbx_text.get("1.0", ctk.END).strip()
        if self._state == MicState.IDLE and is_empty:
            self._show_placeholder()

    def show_progress(self, message: str) -> None:
        if self._state == MicState.TRANSCRIBING:
            self.lbl_state.configure(text=message)

    # DEVICES

    def _load_devices(self) -> None:
        def load() -> None:
            devices = list_input_devices()
            self._run_on_ui_thread(self._on_devices_loaded, devices)

        threading.Thread(target=load, daemon=True).start()

    def _on_devices_loaded(self, devices: list[InputDevice]) -> None:
        if not self.winfo_exists():
            return
        self._devices = devices
        if not devices:
            self._device_options.show_values([NO_DEVICES])
            self._device_options.set(NO_DEVICES)
            self.omn_device.configure(state=ctk.DISABLED)
            return

        self._device_options.show_values([device.name for device in devices])
        # The saved device if it's still connected, or else the default one. The
        # saved device isn't replaced, so it's selected again when it's back
        selected = next(
            (d for d in devices if d.name == self._saved_device),
            next((d for d in devices if d.is_default), devices[0]),
        )
        self._device_options.set(selected.name)
        if self._state not in (MicState.RECORDING, MicState.TRANSCRIBING):
            self.omn_device.configure(state=ctk.NORMAL)

    def _device_labels(self) -> dict[str, str]:
        """The label of each device by its name, while loading or if there's none."""
        # Outside the f-string, so pybabel finds it on Python 3.10 and 3.11
        default = _("default")
        return {
            LOADING_DEVICES: _("Loading…"),
            NO_DEVICES: _("No microphone found"),
        } | {
            device.name: f"{device.name} ({default})"
            if device.is_default
            else device.name
            for device in self._devices
        }

    def _on_device_selected(self, name: str) -> None:
        if any(device.name == name for device in self._devices):
            self._saved_device = name
            ConfigManager.modify_value(
                ConfigTranscription.Key.SECTION,
                ConfigTranscription.Key.MIC_DEVICE,
                name,
            )

    def _selected_device_index(self) -> int | None:
        name = self._device_options.get()
        for device in self._devices:
            if device.name == name:
                return None if device.is_default else device.index
        return None

    # EVENT HANDLERS

    def _on_copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.tbx_text.get("1.0", ctk.END).strip())
