import locale
import tkinter

import customtkinter as ctk
import utils.config_manager as cm
import utils.constants as c
import utils.dict_utils as du
import utils.path_helper as ph
from controller.main_controller import MainController
from model.config.config_google_api import ConfigGoogleApi
from model.config.config_subtitles import ConfigSubtitles
from model.config.config_whisperx import ConfigWhisperX
from PIL import Image
from utils.enums import AudioSource, Color, ComputeType, ModelSize, TranscriptionMethod
from utils.i18n import _

from .custom_widgets.ctk_input_dialog import CTkInputDialog
from .custom_widgets.ctk_scrollable_dropdown import CTkScrollableDropdown


class MainWindow(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        config_whisperx: ConfigWhisperX,
        config_google_api: ConfigGoogleApi,
        config_subtitles: ConfigSubtitles,
    ):
        super().__init__(parent)

        # Configure grid of the window
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Init the configs
        self._config_whisperx = config_whisperx
        self._config_google_api = config_google_api
        self._config_subtitles = config_subtitles

        # Init the controller
        self._controller = None

        # Init the components of the window
        self._init_sidebar()
        self._init_main_content()

        # State
        self._is_transcribing_from_mic = False
        self._is_file_selected = False

        # To handle debouncing
        self._debouncing_delay = 600  # In milliseconds
        self._after_id = None  # To store the after method ID

    def set_controller(self, controller: MainController):
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
        self.frm_sidebar = ctk.CTkScrollableFrame(
            master=self, width=230, corner_radius=0
        )
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

        ## 'Audio language' option menu
        self.lbl_audio_language = ctk.CTkLabel(
            master=self.frm_shared_options,
            text=_("Audio language"),
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.lbl_audio_language.grid(row=0, column=0, padx=0, pady=10)

        self.omn_audio_language = ctk.CTkOptionMenu(master=self.frm_shared_options)
        CTkScrollableDropdown(
            attach=self.omn_audio_language,
            values=list(c.AUDIO_LANGUAGES.values()),
            alpha=1,
        )
        self.omn_audio_language.grid(row=1, column=0, padx=20, pady=0, sticky=ctk.EW)
        try:
            self.omn_audio_language.set(
                c.AUDIO_LANGUAGES[locale.getdefaultlocale()[0][:2]]
            )
        except Exception:
            self.omn_audio_language.set("English")

        ## 'Transcribe from' option menu
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

        ## 'Generate transcription' button
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

				# 'Transcribe using' label
        self.lbl_transcribe_using = ctk.CTkLabel(
            master=self.frm_transcribe_using,
            text=_("Transcribe using"),
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

        # ------------------

        # Whisper options frame
        self.frm_whisper_options = ctk.CTkFrame(master=self.frm_sidebar, border_width=2)
        self.frm_whisper_options.grid(row=3, column=0, padx=20, pady=(20, 0))

        ## Title label
        self.lbl_whisper_options = ctk.CTkLabel(
            master=self.frm_whisper_options,
            text="WhisperX options",
            font=ctk.CTkFont(size=14, weight="bold"),  # 14 is the default size
        )
        self.lbl_whisper_options.grid(row=0, column=0, padx=10, pady=(10, 12.5))

        ## 'Translate to English' checkbox
        self.chk_whisper_options_translate = ctk.CTkCheckBox(
            master=self.frm_whisper_options,
            text="Translate to English",
            command=self._on_chk_whisper_options_translate_change,
        )
        self.chk_whisper_options_translate.grid(
            row=1, column=0, padx=20, pady=0, sticky=ctk.W
        )

        ## 'Subtitles' checkbox
        self.chk_whisper_options_subtitles = ctk.CTkCheckBox(
            master=self.frm_whisper_options,
            text="Generate subtitles",
            command=self._on_whisper_options_subtitles_change,
        )
        self.chk_whisper_options_subtitles.grid(
            row=2, column=0, padx=20, pady=(10, 0), sticky=ctk.W
        )

				## 'Show advanced options' button
        self.btn_whisperx_show_advanced_options = ctk.CTkButton(
            master=self.frm_whisper_options,
            text=_("Show advanced options"),
            command=self._on_show_advanced_options,
        )
        self.btn_whisperx_show_advanced_options.grid(
            row=3, column=0, padx=20, pady=16, sticky=ctk.EW
        )

        # ------------------

        # 'Google API options' frame
        self.frm_google_api_options = ctk.CTkFrame(
            master=self.frm_sidebar, border_width=2
        )
        self.frm_google_api_options.grid(
            row=3, column=0, padx=20, pady=(20, 0), sticky=ctk.EW
        )
        # Hidden at first because WhisperX is the default transcription method
        self.frm_google_api_options.grid_remove()

				## Title label
        self.lbl_google_api_options = ctk.CTkLabel(
            master=self.frm_google_api_options,
            text="Google API options",
            font=ctk.CTkFont(size=14, weight="bold"),  # 14 is the default size
        )
        self.lbl_google_api_options.grid(row=0, column=0, padx=10, pady=(10, 12.5))

				## 'Set API key' button
        self.btn_set_google_api_key = ctk.CTkButton(
            master=self.frm_google_api_options,
            text=_("Set API key"),
            command=self._on_set_google_api_key,
        )
        self.btn_set_google_api_key.grid(
            row=1, column=0, padx=20, pady=(0, 20), sticky=ctk.EW
        )

        # ------------------

        # Subtitle options frame
        self.frm_subtitle_options = ctk.CTkFrame(
            master=self.frm_sidebar, border_width=2
        )
        self.frm_subtitle_options.grid(
            row=4, column=0, padx=20, pady=(20, 0), sticky=ctk.EW
        )
        self.frm_subtitle_options.grid_remove()  # Hidden by default

        ## Title label
        self.lbl_subtitle_options = ctk.CTkLabel(
            master=self.frm_subtitle_options,
            text="Subtitle options",
            font=ctk.CTkFont(size=14, weight="bold"),  # 14 is the default size
        )
        self.lbl_subtitle_options.grid(
            row=0, column=0, padx=40, pady=(10, 0), sticky=ctk.EW
        )

        ## 'Highlight words' check box
        self.chk_highlight_words = ctk.CTkCheckBox(
            master=self.frm_subtitle_options,
            text="Highlight words",
            command=lambda: self._on_config_change(
                section=ConfigSubtitles.Key.SECTION,
                key=ConfigSubtitles.Key.HIGHLIGHT_WORDS,
                new_value="True" if self.chk_highlight_words.get() else "False",
            ),
        )
        self.chk_highlight_words.grid(row=1, column=0, padx=20, pady=10, sticky=ctk.W)

        ## 'Max. line count' entry
        self.lbl_max_line_count = ctk.CTkLabel(
            master=self.frm_subtitle_options,
            text=_("Max. line count"),
        )
        self.lbl_max_line_count.grid(
            row=2, column=0, padx=(52, 0), pady=0, sticky=ctk.W
        )

        self.max_line_count = ctk.StringVar(
            self, str(self._config_subtitles.max_line_count)
        )
        self._setup_debounced_change(
            section=ConfigSubtitles.Key.SECTION,
            key=ConfigSubtitles.Key.MAX_LINE_COUNT,
            variable=self.max_line_count,
            callback=self._on_config_change,
        )

        self.ent_max_line_count = ctk.CTkEntry(
            master=self.frm_subtitle_options,
            width=28,
            textvariable=self.max_line_count,
        )
        self.ent_max_line_count.grid(
            row=2, column=0, padx=(18, 20), pady=0, sticky=ctk.W
        )

        ## 'Max. line width' entry
        self.lbl_max_line_width = ctk.CTkLabel(
            master=self.frm_subtitle_options,
            text=_("Max. line width"),
        )
        self.lbl_max_line_width.grid(
            row=3, column=0, padx=(52, 0), pady=(10, 14), sticky=ctk.W
        )

        self.max_line_width = ctk.StringVar(
            self, str(self._config_subtitles.max_line_width)
        )
        self._setup_debounced_change(
            section=ConfigSubtitles.Key.SECTION,
            key=ConfigSubtitles.Key.MAX_LINE_WIDTH,
            variable=self.max_line_width,
            callback=self._on_config_change,
        )

        self.ent_max_line_width = ctk.CTkEntry(
            master=self.frm_subtitle_options,
            width=28,
            textvariable=self.max_line_width,
        )
        self.ent_max_line_width.grid(
            row=3, column=0, padx=(18, 20), pady=(10, 14), sticky=ctk.W
        )

        # ------------------

        # WhisperX advanced options frame
        self.frm_whisperx_advanced_options = ctk.CTkFrame(
            master=self.frm_sidebar, border_width=2
        )
        self.frm_whisperx_advanced_options.grid(
            row=5, column=0, padx=20, pady=(20, 0), sticky=ctk.EW
        )
        self.frm_whisperx_advanced_options.grid_remove()  # Hidden by default

        ## Title label
        self.lbl_advanced_options = ctk.CTkLabel(
            master=self.frm_whisperx_advanced_options,
            text="Advanced options",
            font=ctk.CTkFont(size=14, weight="bold"),  # 14 is the default size
        )
        self.lbl_advanced_options.grid(
            row=0, column=0, padx=10, pady=(10, 5), sticky=ctk.EW
        )

        ## 'Model size' option menu
        self.lbl_model_size = ctk.CTkLabel(
            master=self.frm_whisperx_advanced_options,
            text="Model size",
        )
        self.lbl_model_size.grid(row=1, column=0, padx=20, pady=0, sticky=ctk.W)

        self.omn_model_size = ctk.CTkOptionMenu(
            master=self.frm_whisperx_advanced_options,
            values=[model_size.value for model_size in ModelSize.__members__.values()],
            command=lambda *args: self._on_config_change(
                section=ConfigWhisperX.Key.SECTION,
                key=ConfigWhisperX.Key.MODEL_SIZE,
                new_value=self.omn_model_size.get(),
            ),
        )
        self.omn_model_size.grid(row=2, column=0, padx=20, pady=(3, 10), sticky=ctk.EW)
        self.omn_model_size.set(self._config_whisperx.model_size)

        ## 'Compute type' option menu
        self.lbl_compute_type = ctk.CTkLabel(
            master=self.frm_whisperx_advanced_options,
            text="Compute type",
        )
        self.lbl_compute_type.grid(row=3, column=0, padx=20, pady=0, sticky=ctk.W)

        self.omn_compute_type = ctk.CTkOptionMenu(
            master=self.frm_whisperx_advanced_options,
            values=[
                compute_type.value for compute_type in ComputeType.__members__.values()
            ],
            command=lambda *args: self._on_config_change(
                section=ConfigWhisperX.Key.SECTION,
                key=ConfigWhisperX.Key.COMPUTE_TYPE,
                new_value=self.omn_compute_type.get(),
            ),
        )
        self.omn_compute_type.grid(
            row=4, column=0, padx=20, pady=(3, 17), sticky=ctk.EW
        )
        self.omn_compute_type.set(self._config_whisperx.compute_type)

        ## 'Batch size' entry
        self.lbl_batch_size = ctk.CTkLabel(
            master=self.frm_whisperx_advanced_options,
            text="Batch size",
        )
        self.lbl_batch_size.grid(row=5, column=0, padx=(50, 0), pady=0, sticky=ctk.W)

        self.batch_size = ctk.StringVar(self, str(self._config_whisperx.batch_size))
        self._setup_debounced_change(
            section=ConfigWhisperX.Key.SECTION,
            key=ConfigWhisperX.Key.BATCH_SIZE,
            variable=self.batch_size,
            callback=self._on_config_change,
        )

        self.ent_batch_size = ctk.CTkEntry(
            master=self.frm_whisperx_advanced_options,
            width=28,
            textvariable=self.batch_size,
        )
        self.ent_batch_size.grid(row=5, column=0, padx=(18, 20), pady=0, sticky=ctk.W)

        ## 'Use CPU' checkbox
        self.chk_use_cpu = ctk.CTkCheckBox(
            master=self.frm_whisperx_advanced_options,
            text="Use CPU",
            command=lambda: self._on_config_change(
                section=ConfigWhisperX.Key.SECTION,
                key=ConfigWhisperX.Key.USE_CPU,
                new_value="True" if self.chk_use_cpu.get() else "False",
            ),
        )
        self.chk_use_cpu.grid(row=6, column=0, padx=20, pady=(10, 16), sticky=ctk.W)

        if self._config_whisperx.use_cpu:
            self.chk_use_cpu.select()

        if not self._config_whisperx.can_use_gpu:
            self.chk_use_cpu.select()
            self.chk_use_cpu.configure(state=ctk.DISABLED)

        # ------------------

        ## 'Appearance mode' option menu
        self.lbl_appearance_mode = ctk.CTkLabel(
            master=self.frm_sidebar,
            text=_("Appearance mode"),
            anchor=ctk.W,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.lbl_appearance_mode.grid(row=12, column=0, padx=20, pady=(50, 0))

        self.omn_appearance_mode = ctk.CTkOptionMenu(
            master=self.frm_sidebar,
            values=[_("System"), _("Light"), _("Dark")],
            command=self._change_appearance_mode_event,
        )
        self.omn_appearance_mode.grid(row=13, column=0, padx=20, pady=0, sticky=ctk.EW)

        ## 'Version' label
        self.lbl_version = ctk.CTkLabel(
            master=self.frm_sidebar,
            text="v2.2.0",
            font=ctk.CTkFont(size=12),
        )
        self.lbl_version.grid(row=14, column=0, padx=20, pady=(5, 10))

    def _init_main_content(self):
        # Main entry frame
        self.frm_main_entry = ctk.CTkFrame(master=self, fg_color="transparent")
        self.frm_main_entry.grid(row=0, column=1, padx=20, pady=(20, 0), sticky=ctk.EW)
        self.frm_main_entry.grid_columnconfigure(1, weight=1)

        ## 'Path' entry
        self.lbl_path = ctk.CTkLabel(
            master=self.frm_main_entry,
            text="File path",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.lbl_path.grid(row=0, column=0, padx=(0, 15), sticky=ctk.W)

        self.ent_path = ctk.CTkEntry(master=self.frm_main_entry)
        self.ent_path.grid(row=0, column=1, padx=0, sticky=ctk.EW)

        ## File explorer image button
        self.img_file_explorer = ctk.CTkImage(
            Image.open(ph.ROOT_PATH / ph.IMG_RELATIVE_PATH / "file-explorer.png"),
            size=(24, 24),
        )
        self.btn_file_explorer = ctk.CTkButton(
            self.frm_main_entry,
            image=self.img_file_explorer,
            text="",
            width=32,
            command=self._on_select_file,
        )
        self.btn_file_explorer.grid(row=0, column=2, padx=(15, 0), sticky=ctk.E)

        ## Textbox
        self.tbx_transcription = ctk.CTkTextbox(master=self, wrap=ctk.WORD)
        self.tbx_transcription.grid(row=2, column=1, padx=20, pady=20, sticky=ctk.NSEW)

        ## Progress bar
        self.progress_bar = ctk.CTkProgressBar(master=self)
        self.progress_bar.configure(mode="indeterminate")

        ## 'Save transcription' button
        self.btn_save = ctk.CTkButton(
            master=self,
            fg_color="green",
            hover_color="darkgreen",
            text=_("Save transcription"),
            command=self._on_save_transcription,
        )
        self.btn_save.grid(row=3, column=1, padx=20, pady=(0, 20), sticky=ctk.EW)
        self.btn_save.grid_remove()  # hidden at start

    # WIDGET EVENT HANDLER METHODS

    def _setup_debounced_change(self, section, key, variable, callback, *unused):
        variable.trace_add(
            mode="write",
            callback=lambda *args: self._on_change_debounced(
                section, key, variable, callback
            ),
        )

    def _on_change_debounced(self, section, key, variable, callback):
        # Cancel the previously scheduled after call
        if self._after_id is not None:
            self.after_cancel(self._after_id)

        # Schedule a new after call with the specified delay
        self._after_id = self.after(
            self._debouncing_delay, lambda: callback(section, key, variable.get())
        )

    def _on_change_app_language(self, language_name: str):
        self._controller.change_app_language(language_name)

    def _on_select_file(self):
        self._controller.select_file()

    def _on_transcribe_from_mic(self):
        is_recording = Color.LIGHT_RED.value in self.btn_transcribe_from_mic.cget(
            "fg_color"
        )

        if is_recording:
            self._stop_recording_from_mic()
        else:
            self._start_recording_from_mic()

    def _start_recording_from_mic(self):
        self.btn_transcribe_from_mic.configure(
            fg_color=(Color.LIGHT_RED.value, Color.DARK_RED.value),
            hover_color=(
                Color.HOVER_LIGHT_RED.value,
                Color.HOVER_DARK_RED.value,
            ),
            text=_("Stop recording"),
        )

        self._controller.prepare_for_transcription(
            source=AudioSource.MIC,
            language_code=self._get_language_code(),
            transcription_method=self.radio_var.get(),
            **self._get_whisperx_args(),
        )

        self._is_transcribing_from_mic = True
        self.btn_generate_transcription.configure(state=ctk.DISABLED)

    def _stop_recording_from_mic(self):
        self._is_transcribing_from_mic = False

        self.btn_transcribe_from_mic.configure(
            fg_color=(Color.LIGHT_BLUE.value, Color.DARK_BLUE.value),
            hover_color=(
                Color.HOVER_LIGHT_BLUE.value,
                Color.HOVER_DARK_BLUE.value,
            ),
            text=_("Transcribe from mic."),
        )

        self._controller.stop_recording_from_mic()

        if self._is_file_selected:
            self.btn_generate_transcription.configure(state=ctk.NORMAL)

    def _on_generate_transcription(self):
        self._controller.prepare_for_transcription(
            source=AudioSource.FILE,
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
            self.frm_whisperx_advanced_options.grid_remove()
            self.btn_whisperx_show_advanced_options.configure(
                text=_("Show advanced options")
            )
            self.frm_google_api_options.grid()

    def _on_set_google_api_key(self):
        old_api_key = self._config_google_api.api_key

        dialog = CTkInputDialog(
            title="Google API key",
            label_text="Type in the API key:",
            entry_text=old_api_key,
        )

        new_api_key = dialog.get_input()

        if new_api_key is not None and old_api_key != new_api_key:
            self._on_config_change(
                section=ConfigGoogleApi.Key.SECTION,
                key=ConfigGoogleApi.Key.API_KEY,
                new_value=new_api_key.strip(),
            )

    def _on_chk_whisper_options_translate_change(self):
        if self.chk_whisper_options_translate.get():
            self.chk_whisper_options_subtitles.deselect()
            self.chk_whisper_options_subtitles.configure(state=ctk.DISABLED)
            self.frm_subtitle_options.grid_remove()
        else:
            self.chk_whisper_options_subtitles.configure(state=ctk.NORMAL)

    def _on_whisper_options_subtitles_change(self):
        if self.chk_whisper_options_subtitles.get():
            self.frm_subtitle_options.grid()
        else:
            self.frm_subtitle_options.grid_remove()

    def _on_show_advanced_options(self):
        if self.frm_whisperx_advanced_options.winfo_ismapped():
            self.frm_whisperx_advanced_options.grid_remove()
            self.btn_whisperx_show_advanced_options.configure(
                text=_("Show advanced options")
            )
        else:
            self.frm_whisperx_advanced_options.grid()
            self.btn_whisperx_show_advanced_options.configure(
                text=_("Hide advanced options")
            )

    @staticmethod
    def _on_config_change(section, key, new_value):
        cm.ConfigManager.modify_value(section, key, new_value)

    # PUBLIC HANDLERS

    def handle_select_file_success(self, filepath):
        self.ent_path.configure(textvariable=ctk.StringVar(self, filepath))

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
