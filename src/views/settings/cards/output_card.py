from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog
from typing import Any

import customtkinter as ctk

from models.config.config_transcription import ConfigTranscription
from models.config.config_whisperx import ConfigWhisperX
from models.transcription_settings import TranscriptionSettings
from utils.enums import TranscriptionMethod
from utils.i18n import L_, _
from views.localization import localize
from views.settings.cards.base import SettingsCard
from views.settings.option_labels import save_config
from views.style import theme
from views.widgets.bindings import bind_wraplength

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
        output_dir: str = "",
    ) -> None:
        super().__init__(master, L_("Output"), on_change)
        # Files are saved next to the folder unless another one is chosen
        self._output_dir: Path | None = Path(output_dir) if output_dir else None
        # The file types chosen, kept while some can't be saved with the model of
        # the Whisper API (and are unchecked), so they're restored with another one
        self._file_types: set[str] = set(config_whisperx.output_file_types)

        self._field_label(2, L_("File types"))
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
            self._file_type_checkboxes[file_type] = checkbox
            self.interactive_widgets.append(checkbox)
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
        self.btn_location = localize(
            ctk.CTkButton(
                self.frm_location,
                width=80,
                height=26,
                command=self._on_choose_output_dir,
                **theme.SECONDARY_BUTTON,
            ),
            text=L_("Change…"),
        )
        self.btn_location.grid(row=0, column=1, padx=(8, 0))
        self.btn_reset_location = localize(
            ctk.CTkButton(
                self.frm_location,
                height=26,
                command=self._on_reset_output_dir,
                **theme.GHOST_BUTTON,
            ),
            text=L_("Next to the source"),
        )
        self.btn_reset_location.grid(row=1, column=0, pady=(4, 0), sticky=ctk.W)
        self.interactive_widgets.extend([self.btn_location, self.btn_reset_location])
        self._spacer(8)

    def update_settings(self, settings: TranscriptionSettings) -> None:
        settings.output_file_types = self._chosen_file_types()
        settings.output_dir = str(self._output_dir) if self._output_dir else ""

    def refresh(self, settings: TranscriptionSettings) -> None:
        method = settings.transcription_method
        if method == TranscriptionMethod.GOOGLE_API:
            self.frm_file_types.grid_remove()
            self.lbl_file_types_hint.configure(
                text=_("The Google API returns plain text (.txt).")
            )
            self.lbl_file_types_hint.grid()
        else:
            self.frm_file_types.grid()
            self._refresh_file_types(settings)

        if self._output_dir:
            location = _("Saved in {folder}").format(folder=self._output_dir)
            self.btn_reset_location.grid()
        else:
            location = _("Saved next to the source")
            self.btn_reset_location.grid_remove()
        self.lbl_location.configure(text=location)

    def _refresh_file_types(self, settings: TranscriptionSettings) -> None:
        """
        Offers the file types that can be saved, since some models of the Whisper
        API don't return the timestamps that the subtitles need.
        """
        model = (
            settings.api_model
            if settings.transcription_method == TranscriptionMethod.WHISPER_API
            else None
        )

        for file_type, checkbox in self._file_type_checkboxes.items():
            can_save = model is None or model.can_save(file_type)
            if can_save and file_type in self._file_types:
                checkbox.select()
            else:
                checkbox.deselect()
            checkbox.configure(state=ctk.NORMAL if can_save else ctk.DISABLED)

        if model is None or model.has_timestamps:
            self.lbl_file_types_hint.configure(text="")
            self.lbl_file_types_hint.grid_remove()
        else:
            self.lbl_file_types_hint.configure(
                text=_(
                    "The {model} model doesn't return timestamps, so it can't save "
                    "subtitles."
                ).format(model=model.name)
            )
            self.lbl_file_types_hint.grid()

    def _chosen_file_types(self) -> list[str]:
        """The file types chosen, in the order of the checkboxes."""
        return [t for t in self._file_type_checkboxes if t in self._file_types]

    # EVENT HANDLERS

    def _on_file_types_change(self) -> None:
        # The disabled checkboxes keep their file types chosen
        for file_type, checkbox in self._file_type_checkboxes.items():
            if checkbox.cget("state") == ctk.DISABLED:
                continue
            if checkbox.get():
                self._file_types.add(file_type)
            else:
                self._file_types.discard(file_type)

        save_config(
            ConfigWhisperX.Key.OUTPUT_FILE_TYPES, ",".join(self._chosen_file_types())
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
