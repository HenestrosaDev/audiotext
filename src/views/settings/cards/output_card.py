from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog
from typing import Any

import customtkinter as ctk

from handlers.openai_api_handler import get_api_model
from models.config.config_transcription import ConfigTranscription
from models.config.config_whisper_api import ConfigWhisperApi
from models.config.config_whisperx import ConfigWhisperX
from models.transcription_settings import TranscriptionSettings, TranslationMode
from utils.enums import TranscriptionMethod
from utils.i18n import _
from views.settings.cards.base import SettingsCard
from views.settings.option_labels import save_config
from views.style import theme
from views.widgets.bindings import bind_wraplength
from views.widgets.option_menu import CTkOptionMenu

# Order of the output file type checkboxes
OUTPUT_FILE_TYPES = ["txt", "srt", "vtt", "json", "tsv", "aud"]


class OutputCard(SettingsCard):
    """The files saved for each file of a folder, and where they're saved."""

    def __init__(
        self,
        master: Any,
        on_change: Callable[[], None],
        config_transcription: ConfigTranscription,
        config_whisperx: ConfigWhisperX,
        config_whisper_api: ConfigWhisperApi,
        output_dir: str = "",
    ) -> None:
        super().__init__(master, _("Output"), on_change)
        # Files are saved next to the folder unless another one is chosen
        self._output_dir: Path | None = Path(output_dir) if output_dir else None

        self._field_label(2, _("File types"))
        self.frm_file_types = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_file_types.grid(row=3, column=0, columnspan=2, padx=18, sticky=ctk.W)
        self._file_type_checkboxes: dict[str, ctk.CTkCheckBox] = {}
        for idx, file_type in enumerate(OUTPUT_FILE_TYPES):
            checkbox = ctk.CTkCheckBox(
                self.frm_file_types,
                text=f".{file_type}",
                width=70,
                font=theme.font(13),
                command=self._on_file_types_change,
            )
            checkbox.grid(row=idx // 3, column=idx % 3, pady=3, sticky=ctk.W)
            if file_type in config_whisperx.output_file_types:
                checkbox.select()
            self._file_type_checkboxes[file_type] = checkbox
            self.interactive_widgets.append(checkbox)

        self.omn_response_format = CTkOptionMenu(
            self,
            values=[config_whisper_api.response_format],
            command=lambda value: save_config(
                ConfigWhisperApi.Key.RESPONSE_FORMAT, value
            ),
            dynamic_resizing=False,
        )
        self.omn_response_format.set(config_whisper_api.response_format)
        self.omn_response_format.grid(
            row=4, column=0, columnspan=2, padx=18, sticky=ctk.EW
        )
        self.interactive_widgets.append(self.omn_response_format)
        self.lbl_file_types_hint = self._hint(5)

        self.frm_location = ctk.CTkFrame(self, fg_color="transparent")
        self.frm_location.grid(
            row=7, column=0, columnspan=2, padx=18, pady=(8, 0), sticky=ctk.EW
        )
        self.frm_location.grid_columnconfigure(0, weight=1)
        self.lbl_location = ctk.CTkLabel(
            self.frm_location,
            text="",
            font=theme.font(12),
            text_color=theme.HINT_TEXT,
            anchor=ctk.W,
            justify=ctk.LEFT,
        )
        self.lbl_location.grid(row=0, column=0, sticky=ctk.EW)
        bind_wraplength(self.lbl_location)
        self.btn_location = ctk.CTkButton(
            self.frm_location,
            text=_("Change…"),
            width=80,
            height=26,
            command=self._on_choose_output_dir,
            **theme.SECONDARY_BUTTON,
        )
        self.btn_location.grid(row=0, column=1, padx=(8, 0))
        self.btn_reset_location = ctk.CTkButton(
            self.frm_location,
            text=_("Next to the source"),
            height=26,
            command=self._on_reset_output_dir,
            **theme.GHOST_BUTTON,
        )
        self.btn_reset_location.grid(row=1, column=0, pady=(4, 0), sticky=ctk.W)
        self.interactive_widgets.extend([self.btn_location, self.btn_reset_location])

        self.swi_overwrite = self._switch(
            8,
            _("Overwrite existing files"),
            config_transcription.overwrite_files,
            ConfigTranscription.Key.OVERWRITE_FILES,
        )
        self._hint(9, _("The files of a folder are always saved."), (4, 16))

    def update_settings(self, settings: TranscriptionSettings) -> None:
        settings.output_file_types = [
            file_type
            for file_type, checkbox in self._file_type_checkboxes.items()
            if checkbox.get()
        ]
        settings.response_format = self.omn_response_format.get()
        settings.overwrite = bool(self.swi_overwrite.get())
        settings.output_dir = str(self._output_dir) if self._output_dir else ""

    def refresh(self, settings: TranscriptionSettings) -> None:
        method = settings.transcription_method
        if method == TranscriptionMethod.WHISPERX:
            self.frm_file_types.grid()
            self.omn_response_format.grid_remove()
            self.lbl_file_types_hint.configure(text="")
            self.lbl_file_types_hint.grid_remove()
        elif method == TranscriptionMethod.WHISPER_API:
            self.frm_file_types.grid_remove()
            self._refresh_response_formats(settings)
            self.omn_response_format.grid()
            self.lbl_file_types_hint.grid()
        else:
            self.frm_file_types.grid_remove()
            self.omn_response_format.grid_remove()
            self.lbl_file_types_hint.configure(
                text=_("The Google API returns plain text (.txt).")
            )
            self.lbl_file_types_hint.grid()

        if self._output_dir:
            location = _("Saved in {folder}").format(folder=self._output_dir)
            self.btn_reset_location.grid()
        else:
            location = _("Saved next to the source")
            self.btn_reset_location.grid_remove()
        self.lbl_location.configure(text=location)

    def _refresh_response_formats(self, settings: TranscriptionSettings) -> None:
        """Offers the formats of the model, since some need the timestamps."""
        is_whisper_translation = (
            settings.effective_translation_mode == TranslationMode.WHISPER
        )
        # Whisper translates, whichever model is chosen
        model = get_api_model(None if is_whisper_translation else settings.openai_model)
        formats = model.response_formats
        self.omn_response_format.configure(values=formats)

        if settings.response_format not in formats:
            self.omn_response_format.set(formats[0])
            save_config(ConfigWhisperApi.Key.RESPONSE_FORMAT, formats[0])

        if model.has_timestamps:
            hint = _("Format of the files.")
        else:
            hint = _(
                "The {model} model doesn't return timestamps, so it can't save "
                "subtitles."
            ).format(model=model.name)
        self.lbl_file_types_hint.configure(text=hint)

    # EVENT HANDLERS

    def _on_file_types_change(self) -> None:
        save_config(
            ConfigWhisperX.Key.OUTPUT_FILE_TYPES,
            ",".join(
                file_type
                for file_type, checkbox in self._file_type_checkboxes.items()
                if checkbox.get()
            ),
        )
        self._on_change()

    def _on_choose_output_dir(self) -> None:
        folder = filedialog.askdirectory(
            title=_("Choose where to save the transcriptions"),
            initialdir=str(self._output_dir or Path.home()),
        )
        if folder:
            self._output_dir = Path(folder)
            self._on_change()

    def _on_reset_output_dir(self) -> None:
        self._output_dir = None
        self._on_change()
