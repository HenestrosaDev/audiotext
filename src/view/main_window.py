import locale
import tkinter

import customtkinter as ctk
import utils.constants as c
import utils.dict_utils as du
import utils.path_helper as ph
from model.transcription_method import TranscriptionMethod
from PIL import Image
from utils.i18n import _


class MainWindow(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent)

        # Configure grid of the window
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Init the components of the window
        self._init_sidebar()
        self._init_main_content()

        # Init the controller
        self._controller = None

        # State
        self._is_transcribing_from_mic = False
        self._is_file_selected = False

    def set_controller(self, controller):
        """
        Set the controller of the window.

        :param controller: View controller
        :type controller: MainController
        """
        self._controller = controller

    def _get_language_code(self):
        return du.find_key_by_value(
            dictionary=c.AUDIO_LANGUAGES, target_value=self.omn_audio_language.get()
        )

    def _get_whisperx_args(self):
        whisperx_args = {}
        if self.radio_var.get() == TranscriptionMethod.WHISPERX.value:
            whisperx_args["should_translate"] = (
                self.chk_whisper_options_translate.get() == 1
            )
            whisperx_args["should_subtitle"] = (
                self.chk_whisper_options_subtitles.get() == 1
            )

        return whisperx_args

    # WIDGETS INITIALIZATION

    def _init_sidebar(self):
        # Sidebar frame
        self.frm_sidebar = ctk.CTkFrame(master=self, width=140, corner_radius=0)
        self.frm_sidebar.grid(row=0, column=0, rowspan=4, sticky=ctk.NSEW)
        self.frm_sidebar.grid_rowconfigure(10, weight=1)

        # Logo label
        self.logo_image = ctk.CTkImage(
            light_image=Image.open(
                ph.ROOT_PATH / ph.IMG_RELATIVE_PATH / "icon-light.png"
            ),
            dark_image=Image.open(
                ph.ROOT_PATH / ph.IMG_RELATIVE_PATH / "icon-dark.png"
            ),
            size=(32, 32),
        )

        self.lbl_logo = ctk.CTkLabel(
            master=self.frm_sidebar,
            text=f" {c.APP_NAME}",
            image=self.logo_image,
            compound=ctk.LEFT,
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        self.lbl_logo.grid(row=0, column=0, padx=20, pady=(25, 0))

        # ------------------

        # Shared options frame
        self.frm_shared_options = ctk.CTkFrame(master=self.frm_sidebar, border_width=2)
        self.frm_shared_options.grid(row=1, column=0, padx=20, pady=(20, 0))

        # Audio language
        self.lbl_audio_language = ctk.CTkLabel(
            master=self.frm_shared_options,
            text=f'{_("Audio language")}:',
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.lbl_audio_language.grid(row=0, column=0, padx=0, pady=10)

        self.omn_audio_language = ctk.CTkOptionMenu(
            master=self.frm_shared_options, values=list(c.AUDIO_LANGUAGES.values())
        )
        self.omn_audio_language.grid(row=1, column=0, padx=20, pady=0, sticky=ctk.EW)
        try:
            self.omn_audio_language.set(
                c.AUDIO_LANGUAGES[locale.getdefaultlocale()[0][:2]]
            )
        except Exception:
            self.omn_audio_language.set("English")

        # Transcribe from microphone button
        self.btn_transcribe_from_mic = ctk.CTkButton(
            master=self.frm_shared_options,
            text=_("Transcribe from mic."),
            command=lambda: self._on_transcribe_from_mic(),
        )
        self.btn_transcribe_from_mic.grid(
            row=2, column=0, padx=20, pady=(30, 0), sticky=ctk.EW
        )

        # Select file button
        self.btn_select_file = ctk.CTkButton(
            master=self.frm_shared_options,
            text=_("Select file"),
            command=self._on_select_file,
        )
        self.btn_select_file.grid(row=3, column=0, padx=20, pady=(30, 0), sticky=ctk.EW)

        # Generate text button
        self.btn_generate_transcription = ctk.CTkButton(
            master=self.frm_shared_options,
            fg_color="green",
            hover_color="darkgreen",
            text=_("Generate transcription"),
            command=lambda: self._on_generate_transcription(),
        )
        self.btn_generate_transcription.grid(
            row=4, column=0, padx=20, pady=20, sticky=ctk.EW
        )
        self.btn_generate_transcription.configure(state=ctk.DISABLED)

        # ------------------

        # 'Transcribe using' frame
        self.frm_transcribe_using = ctk.CTkFrame(
            master=self.frm_sidebar, border_width=2
        )
        self.frm_transcribe_using.grid(row=2, column=0, padx=0, pady=(20, 0))

        self.lbl_transcribe_using = ctk.CTkLabel(
            master=self.frm_transcribe_using,
            text=f'{_("Transcribe using")}:',
            font=ctk.CTkFont(size=14, weight="bold"),  # 14 is the default size
        )
        self.lbl_transcribe_using.grid(row=0, column=0, padx=0, pady=(10, 12.5))

        self.radio_var = tkinter.IntVar(value=TranscriptionMethod.WHISPERX.value)

        self.rbt_transcribe_using_whisper = ctk.CTkRadioButton(
            master=self.frm_transcribe_using,
            variable=self.radio_var,
            value=TranscriptionMethod.WHISPERX.value,
            text="WhisperX (local)",
            command=self._on_transcribe_using_change,
        )
        self.rbt_transcribe_using_whisper.grid(
            row=1, column=0, padx=20, pady=0, sticky=ctk.W
        )

        self.rbt_transcribe_using_google = ctk.CTkRadioButton(
            master=self.frm_transcribe_using,
            variable=self.radio_var,
            value=TranscriptionMethod.GOOGLE_API.value,
            text="Google API (remote)",
            command=self._on_transcribe_using_change,
        )
        self.rbt_transcribe_using_google.grid(
            row=2, column=0, padx=20, pady=(7.5, 16), sticky=ctk.W
        )

        # Whisper options frame
        self.frm_whisper_options = ctk.CTkFrame(master=self.frm_sidebar, border_width=2)
        self.frm_whisper_options.grid(row=3, column=0, padx=20, pady=(20, 0))

        self.lbl_whisper_options = ctk.CTkLabel(
            master=self.frm_whisper_options,
            text="WhisperX options:",
            font=ctk.CTkFont(size=14, weight="bold"),  # 14 is the default size
        )
        self.lbl_whisper_options.grid(row=0, column=0, padx=10, pady=(10, 12.5))

        self.chk_whisper_options_translate = ctk.CTkCheckBox(
            master=self.frm_whisper_options,
            text="Translate to English",
            command=self._on_chk_whisper_options_translate_change,
        )
        self.chk_whisper_options_translate.grid(
            row=1, column=0, padx=20, pady=0, sticky=ctk.W
        )
        self.chk_whisper_options_subtitles = ctk.CTkCheckBox(
            master=self.frm_whisper_options,
            text="Generate subtitles",
        )
        self.chk_whisper_options_subtitles.grid(
            row=2, column=0, padx=20, pady=(10, 16), sticky=ctk.W
        )

        # Google API options frame
        self.frm_google_api_options = ctk.CTkFrame(
            master=self.frm_sidebar, border_width=2
        )
        self.frm_google_api_options.grid(
            row=3, column=0, padx=20, pady=(20, 0), sticky=ctk.EW
        )
        # Hidden at first because WhisperX is the default transcription method
        self.frm_google_api_options.grid_remove()

        self.lbl_google_api_options = ctk.CTkLabel(
            master=self.frm_google_api_options,
            text="Google API options:",
            font=ctk.CTkFont(size=14, weight="bold"),  # 14 is the default size
        )
        self.lbl_google_api_options.grid(row=0, column=0, padx=10, pady=(10, 12.5))

        self.btn_set_google_api_key = ctk.CTkButton(
            master=self.frm_google_api_options,
            text=_("Set API key"),
            command=self._on_set_google_api_key,
        )
        self.btn_set_google_api_key.grid(
            row=1, column=0, padx=20, pady=(0, 20), sticky=ctk.EW
        )

        # ------------------

        # Appearance mode
        self.lbl_appearance_mode = ctk.CTkLabel(
            master=self.frm_sidebar,
            text=f'{_("Appearance mode")}:',
            anchor=ctk.W,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.lbl_appearance_mode.grid(row=12, column=0, padx=20, pady=(10, 0))

        self.omn_appearance_mode = ctk.CTkOptionMenu(
            master=self.frm_sidebar,
            values=[_("System"), _("Light"), _("Dark")],
            command=self._change_appearance_mode_event,
        )
        self.omn_appearance_mode.grid(
            row=13, column=0, padx=20, pady=(10, 20), sticky=ctk.EW
        )

    def _init_main_content(self):
        # Selected file entry
        self.ent_selected_file = ctk.CTkEntry(master=self, state=ctk.DISABLED)
        self.ent_selected_file.grid(
            row=0, column=1, padx=20, pady=(20, 0), sticky=ctk.EW
        )
        self.ent_selected_file.grid_remove()  # hidden at start

        # Text audio textbox
        self.tbx_transcription = ctk.CTkTextbox(master=self, wrap=ctk.WORD)
        self.tbx_transcription.grid(row=1, column=1, padx=20, pady=20, sticky=ctk.NSEW)

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(master=self)
        self.progress_bar.configure(mode="indeterminate")

        # Save text button
        self.btn_save = ctk.CTkButton(
            master=self,
            fg_color="green",
            hover_color="darkgreen",
            text=_("Save transcription"),
            command=self._on_save_transcription,
        )
        self.btn_save.grid(row=2, column=1, padx=20, pady=(0, 20), sticky=ctk.EW)
        self.btn_save.grid_remove()  # hidden at start

    # WIDGET EVENT HANDLER METHODS

    def _on_change_app_language(self, language_name: str):
        self._controller.change_app_language(language_name)

    def _on_select_file(self):
        self._controller.select_file()

    def _on_transcribe_from_mic(self):
        is_recording = c.Color.LIGHT_RED.value in self.btn_transcribe_from_mic.cget(
            "fg_color"
        )

        if is_recording:
            self._stop_recording_from_mic()
        else:
            self._start_recording_from_mic()

    def _start_recording_from_mic(self):
        self.btn_transcribe_from_mic.configure(
            fg_color=(c.Color.LIGHT_RED.value, c.Color.DARK_RED.value),
            hover_color=(
                c.Color.HOVER_LIGHT_RED.value,
                c.Color.HOVER_DARK_RED.value,
            ),
            text=_("Stop recording"),
        )

        self._controller.prepare_for_transcription(
            source=c.AudioSource.MIC,
            language_code=self._get_language_code(),
            transcription_method=self.radio_var.get(),
            **self._get_whisperx_args(),
        )

        self._is_transcribing_from_mic = True
        self.btn_generate_transcription.configure(state=ctk.DISABLED)

    def _stop_recording_from_mic(self):
        self._is_transcribing_from_mic = False

        self.btn_transcribe_from_mic.configure(
            fg_color=(c.Color.LIGHT_BLUE.value, c.Color.DARK_BLUE.value),
            hover_color=(
                c.Color.HOVER_LIGHT_BLUE.value,
                c.Color.HOVER_DARK_BLUE.value,
            ),
            text=_("Transcribe from mic."),
        )

        self._controller.stop_recording_from_mic()

        if self._is_file_selected:
            self.btn_generate_transcription.configure(state=ctk.NORMAL)

    def _on_generate_transcription(self):
        self._controller.prepare_for_transcription(
            source=c.AudioSource.FILE,
            language_code=self._get_language_code(),
            transcription_method=self.radio_var.get(),
            **self._get_whisperx_args(),
        )

    def _on_save_transcription(self):
        self._controller.save_transcription()

    def _on_transcribe_using_change(self):
        if self.radio_var.get() == TranscriptionMethod.WHISPERX.value:
            self.frm_whisper_options.grid()
            self.frm_google_api_options.grid_remove()
        elif self.radio_var.get() == TranscriptionMethod.GOOGLE_API.value:
            self.frm_whisper_options.grid_remove()
            self.frm_google_api_options.grid()


    def _on_chk_whisper_options_translate_change(self):
        if self.chk_whisper_options_translate.get():
            self.chk_whisper_options_subtitles.deselect()
            self.chk_whisper_options_subtitles.configure(state=ctk.DISABLED)
        else:
            self.chk_whisper_options_subtitles.configure(state=ctk.NORMAL)

    # PUBLIC HANDLERS

    def handle_select_file_success(self, filepath):
        self._is_file_selected = True

        self.ent_selected_file.grid()
        self.ent_selected_file.configure(textvariable=ctk.StringVar(self, filepath))

        if not self._is_transcribing_from_mic:
            self.btn_generate_transcription.configure(state=ctk.NORMAL)

    def handle_processing_transcription(self):
        # Show progress bar
        self.toggle_progress_bar_visibility(should_show=True)

        # Remove previous text
        self.display_text("")

        # Disable action buttons to avoid multiple requests at the same time
        self.btn_generate_transcription.configure(state=ctk.DISABLED)
        self.btn_transcribe_from_mic.configure(state=ctk.DISABLED)

    def handle_transcription_process_finish(self, is_transcription_empty):
        # Re-enable action buttons
        self.btn_transcribe_from_mic.configure(state=ctk.NORMAL)
        if self._is_file_selected:
            self.btn_generate_transcription.configure(state=ctk.NORMAL)

        # Remove progress bar
        self.toggle_progress_bar_visibility(should_show=False)

        # Show save button if transcription is not empty
        if not is_transcription_empty:
            self.btn_save.grid()

    # HELPER METHODS

    def toggle_progress_bar_visibility(self, should_show):
        if should_show:
            self.progress_bar.grid(row=1, column=1, padx=40, pady=0, sticky=ctk.EW)
            self.progress_bar.start()
        else:
            self.progress_bar.grid_forget()

    def display_text(self, text):
        self.tbx_transcription.delete("1.0", ctk.END)
        self.tbx_transcription.insert("0.0", text)

    @staticmethod
    def _change_appearance_mode_event(new_appearance_mode: str):
        appearance_mode_map = {
            _("Dark"): "Dark",
            _("Light"): "Light",
            _("System"): "System",
        }
        appearance_mode = appearance_mode_map.get(new_appearance_mode, "System")
        ctk.set_appearance_mode(appearance_mode)
