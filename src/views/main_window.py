import locale
import tkinter
from pathlib import Path

import customtkinter as ctk
import utils.config_manager as cm
import utils.constants as c
import utils.dict_utils as du
import utils.path_helper as ph
from controllers.main_controller import MainController
from models.config.config_google_api import ConfigGoogleApi
from models.config.config_subtitles import ConfigSubtitles
from models.config.config_system import ConfigSystem
from models.config.config_whisperx import ConfigWhisperX
from models.transcription import Transcription
from PIL import Image
from utils.enums import AudioSource, Color, ComputeType, ModelSize, TranscriptionMethod

from .custom_widgets.ctk_input_dialog import CTkInputDialog
from .custom_widgets.ctk_scrollable_dropdown import CTkScrollableDropdown


class MainWindow(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        config_whisperx: ConfigWhisperX,
        config_google_api: ConfigGoogleApi,
        config_subtitles: ConfigSubtitles,
        config_system: ConfigSystem,
    ):
        super().__init__(parent)

        # Configure grid of the window
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Init the configs
        self._config_whisperx = config_whisperx
        self._config_google_api = config_google_api
        self._config_subtitles = config_subtitles
        self._config_system = config_system

        # Init the controller
        self._controller = None

        # Init the components of the window
        self._init_sidebar()
        self._init_main_content()

        # State
        self._transcribe_from_source = AudioSource.FILE
        self._is_transcribing_from_mic = False

        # To handle debouncing
        self._after_id = None  # To store the `after()` method ID

    # GETTERS AND SETTERS

    def set_controller(self, controller: MainController):
        """
        Set the controller of the window.

        :param controller: View controller
        :type controller: MainController
        """
        self._controller = controller

    def _get_language_code(self):
        """
        Retrieve the language code for the selected audio language.

        This function uses a helper function to find the corresponding language code
        from a dictionary of audio languages based on the currently selected audio
        language in the user interface.

        :return: The language code corresponding to the selected audio language.
        :rtype: str
        """
        return du.find_key_by_value(
            dictionary=c.AUDIO_LANGUAGES, target_value=self.omn_audio_language.get()
        )

    def _get_whisperx_args(self):
        """
        Retrieve arguments for WhisperX transcription options.

        This function checks the current state of user interface elements to determine
        if translation and subtitle options should be enabled for WhisperX transcription.
        It returns a dictionary with these options.

        :return: A dictionary containing WhisperX transcription options.
        :rtype: dict
        """
        whisperx_args = {}
        if self.radio_var.get() == TranscriptionMethod.WHISPERX.value:
            whisperx_args["should_translate"] = bool(
                self.chk_whisper_options_translate.get()
            )
            whisperx_args[
                "output_file_types"
            ] = self._config_whisperx.output_file_types.split(",")

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
        self.lbl_logo.grid(row=0, column=0, padx=20, pady=(19, 0))

        # ------------------

        # Shared options frame
        self.frm_shared_options = ctk.CTkFrame(master=self.frm_sidebar, border_width=2)
        self.frm_shared_options.grid(row=1, column=0, padx=20, pady=(20, 0))

        ## 'Audio language' option menu
        self.lbl_audio_language = ctk.CTkLabel(
            master=self.frm_shared_options,
            text="Audio language",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.lbl_audio_language.grid(row=0, column=0, padx=0, pady=(10, 0))

        self.omn_audio_language = ctk.CTkOptionMenu(master=self.frm_shared_options)
        CTkScrollableDropdown(
            attach=self.omn_audio_language,
            values=sorted(list(c.AUDIO_LANGUAGES.values())),
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
        self.lbl_transcribe_from = ctk.CTkLabel(
            master=self.frm_shared_options,
            text="Transcribe from",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.lbl_transcribe_from.grid(row=2, column=0, padx=0, pady=(15, 0))

        self.omn_transcribe_from = ctk.CTkOptionMenu(
            master=self.frm_shared_options,
            values=[e.value for e in AudioSource],
            command=self._on_transcribe_from_change,
        )
        self.omn_transcribe_from.grid(row=3, column=0, padx=20, pady=0, sticky=ctk.EW)
        self.omn_transcribe_from.set(AudioSource.FILE.value)

        ## 'Generate transcription' button
        self.btn_main_action = ctk.CTkButton(
            master=self.frm_shared_options,
            fg_color="green",
            hover_color="darkgreen",
            text="Generate transcription",
            command=lambda: self._on_main_action(),
        )
        self.btn_main_action.grid(
            row=4, column=0, padx=20, pady=(25, 20), sticky=ctk.EW
        )

        # ------------------

        # 'Transcribe using' frame
        self.frm_transcribe_using = ctk.CTkFrame(
            master=self.frm_sidebar, border_width=2
        )
        self.frm_transcribe_using.grid(row=2, column=0, padx=0, pady=(20, 0))

        # 'Transcribe using' label
        self.lbl_transcribe_using = ctk.CTkLabel(
            master=self.frm_transcribe_using,
            text="Transcribe using",
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

        # The "Subtitle options" comes before "Whisper options" to conditionally grid
        # `frm_subtitle_options` if the config.ini has a subtitle file in the
        # `output_file_types` key.

        # Subtitle options frame
        self.frm_subtitle_options = ctk.CTkFrame(
            master=self.frm_sidebar, border_width=2
        )
        self.frm_subtitle_options.grid(
            row=4, column=0, padx=20, pady=(20, 0), sticky=ctk.EW
        )
        # Hidden at first because subtitles are unchecked by default
        self.frm_subtitle_options.grid_remove()

        ## 'Subtitle options' label
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
            text="Max. line count",
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
            text="Max. line width",
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
            row=3, column=0, padx=(18, 20), pady=10, sticky=ctk.W
        )

        ## 'Only applicable to .srt and .vtt files' label
        self.lbl_subtitle_options_footnote = ctk.CTkLabel(
            master=self.frm_subtitle_options,
            text="Only applicable to \n.srt and .vtt files",
            font=ctk.CTkFont(size=12),
        )
        self.lbl_subtitle_options_footnote.grid(row=4, column=0, padx=20, pady=(0, 10))

        # ------------------

        # Whisper options frame
        self.frm_whisper_options = ctk.CTkFrame(master=self.frm_sidebar, border_width=2)
        self.frm_whisper_options.grid(row=3, column=0, padx=20, pady=(20, 0))

        ## 'WhisperX options' label
        self.lbl_whisper_options = ctk.CTkLabel(
            master=self.frm_whisper_options,
            text="WhisperX options",
            font=ctk.CTkFont(size=14, weight="bold"),  # 14 is the default size
        )
        self.lbl_whisper_options.grid(row=0, column=0, padx=10, pady=(10, 5))

        ## 'Output file types' label
        self.lbl_output_file_types = ctk.CTkLabel(
            master=self.frm_whisper_options,
            text="Output file types",
        )
        self.lbl_output_file_types.grid(row=1, column=0, padx=20, pady=0, sticky=ctk.W)

        ## 'Output file types' frame
        self.frm_output_file_types = ctk.CTkFrame(
            master=self.frm_whisper_options,
            fg_color="transparent",
        )
        self.frm_output_file_types.grid(row=2, column=0, padx=20, pady=(3, 17))

        ### '.srt' check box
        self.chk_output_file_srt = ctk.CTkCheckBox(
            master=self.frm_output_file_types,
            text=".srt",
            command=self._on_output_file_types_change,
        )
        self.chk_output_file_srt.grid(row=0, column=0, pady=0)

        ### '.vtt' check box
        self.chk_output_file_vtt = ctk.CTkCheckBox(
            master=self.frm_output_file_types,
            text=".vtt",
            width=25,
            command=self._on_output_file_types_change,
        )
        self.chk_output_file_vtt.grid(row=0, column=1, pady=0, sticky=ctk.W)

        self._toggle_frm_subtitle_options_visibility()

        ### '.txt' check box
        self.chk_output_file_txt = ctk.CTkCheckBox(
            master=self.frm_output_file_types,
            text=".txt",
            command=self._on_output_file_types_change,
        )
        self.chk_output_file_txt.grid(row=1, column=0, pady=(5, 0))
        if "txt" in self._config_whisperx.output_file_types:
            self.chk_output_file_txt.select()

        ### '.json' check box
        self.chk_output_file_json = ctk.CTkCheckBox(
            master=self.frm_output_file_types,
            text=".json",
            width=25,
            command=self._on_output_file_types_change,
        )
        self.chk_output_file_json.grid(row=1, column=1, pady=(5, 0), sticky=ctk.W)
        if "json" in self._config_whisperx.output_file_types:
            self.chk_output_file_json.select()

        ### '.tsv' check box
        self.chk_output_file_tsv = ctk.CTkCheckBox(
            master=self.frm_output_file_types,
            text=".tsv",
            command=self._on_output_file_types_change,
        )
        self.chk_output_file_tsv.grid(row=2, column=0, pady=(5, 0))
        if "tsv" in self._config_whisperx.output_file_types:
            self.chk_output_file_tsv.select()

        ### '.aud' check box
        self.chk_output_file_aud = ctk.CTkCheckBox(
            master=self.frm_output_file_types,
            text=".aud",
            width=25,
            command=self._on_output_file_types_change,
        )
        self.chk_output_file_aud.grid(row=2, column=1, pady=(5, 0), sticky=ctk.W)
        if "aud" in self._config_whisperx.output_file_types:
            self.chk_output_file_aud.select()

        ## 'Translate to English' checkbox
        self.chk_whisper_options_translate = ctk.CTkCheckBox(
            master=self.frm_whisper_options,
            text="Translate to English",
        )
        self.chk_whisper_options_translate.grid(
            row=3, column=0, padx=20, pady=0, sticky=ctk.W
        )

        ## 'Show advanced options' button
        self.btn_whisperx_show_advanced_options = ctk.CTkButton(
            master=self.frm_whisper_options,
            text="Show advanced options",
            command=self._on_show_advanced_options,
        )
        self.btn_whisperx_show_advanced_options.grid(
            row=4, column=0, padx=20, pady=16, sticky=ctk.EW
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

        ## 'Google API options' label
        self.lbl_google_api_options = ctk.CTkLabel(
            master=self.frm_google_api_options,
            text="Google API options",
            font=ctk.CTkFont(size=14, weight="bold"),  # 14 is the default size
        )
        self.lbl_google_api_options.grid(row=0, column=0, padx=10, pady=(10, 12.5))

        ## 'Set API key' button
        self.btn_set_google_api_key = ctk.CTkButton(
            master=self.frm_google_api_options,
            text="Set API key",
            command=self._on_google_api_key_set,
        )
        self.btn_set_google_api_key.grid(
            row=1, column=0, padx=20, pady=(0, 20), sticky=ctk.EW
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

        ## 'Advanced options' label
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
            text="Appearance mode",
            anchor=ctk.W,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.lbl_appearance_mode.grid(row=12, column=0, padx=20, pady=(50, 0))

        self.omn_appearance_mode = ctk.CTkOptionMenu(
            master=self.frm_sidebar,
            values=["System", "Light", "Dark"],
            command=self._change_appearance_mode_event,
        )
        self.omn_appearance_mode.set(self._config_system.appearance_mode)
        self.omn_appearance_mode.grid(row=13, column=0, padx=20, pady=0, sticky=ctk.EW)

        ## Info label
        self.lbl_info = ctk.CTkLabel(
            master=self.frm_sidebar,
            text="v2.2.3 | Made by HenestrosaDev",
            font=ctk.CTkFont(size=12),
        )
        self.lbl_info.grid(row=14, column=0, padx=20, pady=(5, 10))

    def _init_main_content(self):
        # Main entry frame
        self.frm_main_entry = ctk.CTkFrame(master=self, fg_color="transparent")
        self.frm_main_entry.grid(row=0, column=1, padx=20, pady=(20, 0), sticky=ctk.EW)
        self.frm_main_entry.grid_columnconfigure(1, weight=1)

        ## 'Path' entry
        self.lbl_path = ctk.CTkLabel(
            master=self.frm_main_entry,
            text="Path",
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
            command=self._on_select_path,
        )
        self.btn_file_explorer.grid(row=0, column=2, padx=(15, 0), sticky=ctk.E)

        ## Textbox
        self.tbx_transcription = ctk.CTkTextbox(master=self, wrap=ctk.WORD)
        self.tbx_transcription.grid(row=2, column=1, padx=20, pady=20, sticky=ctk.NSEW)

        ## Progress bar
        self.progress_bar = ctk.CTkProgressBar(master=self)
        self.progress_bar.configure(mode="indeterminate")

        # Save options frame
        self.frm_save_options = ctk.CTkFrame(master=self, fg_color="transparent")
        self.frm_save_options.grid(
            row=3, column=1, padx=20, pady=(0, 20), sticky=ctk.EW
        )
        self.frm_save_options.grid_columnconfigure(0, weight=1)

        ## 'Save transcription' button
        self.btn_save = ctk.CTkButton(
            master=self.frm_save_options,
            fg_color="green",
            hover_color="darkgreen",
            text="Save transcription",
            command=self._on_save_transcription,
        )
        self.btn_save.grid(row=0, column=0, padx=0, pady=0, sticky=ctk.EW)

        ## 'Autosave' checkbox
        self.chk_autosave = ctk.CTkCheckBox(
            master=self.frm_save_options,
            text="Autosave",
            command=self._on_autosave_change,
        )
        self.chk_autosave.grid(row=0, column=1, padx=(20, 10), pady=0)

        ## 'Overwrite files' checkbox
        self.chk_overwrite_files = ctk.CTkCheckBox(
            master=self.frm_save_options,
            text="Overwrite existing files",
        )
        self.chk_overwrite_files.grid(row=0, column=2, padx=0, pady=0)
        self.chk_overwrite_files.configure(state=ctk.DISABLED)

    # PUBLIC METHODS (called by the controller)

    def on_select_path_success(self, filepath: str):
        """
        Handles the successful selection of a file or directory path by updating the
        entry field with the selected file or directory path.

        :param filepath: The selected file or directory path.
        :type filepath: str
        """
        self.ent_path.configure(textvariable=ctk.StringVar(self, filepath))

    def on_processing_transcription(self):
        """
        Prepares the UI for processing a transcription. Disables action buttons to avoid
        multiple requests at the same time. It also shows a progress bar and removes any
        previous text from the display.
        """
        # Disable action buttons to avoid multiple requests at the same time
        self.ent_path.configure(state=ctk.DISABLED)
        self.omn_transcribe_from.configure(state=ctk.DISABLED)
        self.omn_audio_language.configure(state=ctk.DISABLED)

        if not self._is_transcribing_from_mic:
            self.btn_main_action.configure(state=ctk.DISABLED)

        # Show progress bar
        self._toggle_progress_bar_visibility(should_show=True)

        # Remove previous text
        self.display_text("")

    def on_processed_transcription(self):
        """
        Re-enables disabled widgets after transcription processing is complete.
        """
        self.ent_path.configure(state=ctk.NORMAL)
        self.omn_transcribe_from.configure(state=ctk.NORMAL)
        self.omn_audio_language.configure(state=ctk.NORMAL)
        self.btn_main_action.configure(state=ctk.NORMAL)

        self._toggle_progress_bar_visibility(should_show=False)

    def stop_recording_from_mic(self):
        """
        Updates the state to indicate that recording from the microphone has
        stopped, notified by the controller. It also updates the button appearance to
        indicate that recording can be started again.

        Additionally, it delegates the task of stopping the recording to the controller.
        """
        self._is_transcribing_from_mic = False

        self.btn_main_action.configure(
            fg_color="green",
            hover_color="darkgreen",
            text="Start recording",
            state=ctk.DISABLED,
        )

        self._controller.stop_recording_from_mic()

    def display_text(self, text):
        """
        Clears any existing text in the transcription text box to display the provided
        text.

        :param text: The text to be displayed in the transcription text box.
        :type text: str
        """
        self.tbx_transcription.delete("1.0", ctk.END)
        self.tbx_transcription.insert("0.0", text)

    # PRIVATE METHODS

    def _setup_debounced_change(
        self,
        section: str,
        key: str,
        variable: ctk.Variable,
        callback: callable,
        *unused: tuple,
    ):
        """
        Sets up a debounced callback for a variable change.

        This function attaches a debounced callback to a CTk variable. When the
        variable changes, the debounced function `_on_change_debounced` is triggered,
        which will delay the execution of the callback to avoid excessive calls.

        :param section: The configuration section associated with the variable.
        :type section: str
        :param key: The specific key within the configuration section.
        :type key: str
        :param variable: The tkinter variable to watch for changes.
        :type variable: tkinter.Variable
        :param callback: The callback function to be executed after the debounce delay.
        :type callback: function
        :param unused: Additional unused arguments that must be kept to prevent
                        exceptions.
        :type unused: tuple
        """
        variable.trace_add(
            mode="write",
            callback=lambda *args: self._on_change_debounced(
                section, key, variable, callback
            ),
        )

    def _on_change_debounced(
        self,
        section: str,
        key: str,
        variable: ctk.Variable,
        callback: callable,
        delay: int = 600,
    ):
        """
        Handles debounced changes to a variable.

        This function ensures that the provided callback is executed after a specified
        delay when a variable changes, avoiding immediate or excessive calls. If another
        change occurs within the delay period, the previous callback is cancelled and
        rescheduled.

        :param section: The configuration section associated with the variable.
        :type section: str
        :param key: The specific key within the configuration section.
        :type key: str
        :param variable: The tkinter variable being monitored for changes.
        :type variable: tkinter.Variable
        :param callback: The function to be executed after the debounce delay.
        :type callback: callable
        :param delay: The debounce delay in milliseconds before executing the callback.
        :type delay: int, optional
        """
        # Cancel the previously scheduled after call
        if self._after_id is not None:
            self.after_cancel(self._after_id)

        # Schedule a new after call with the specified delay
        self._after_id = self.after(
            delay, lambda: callback(section, key, variable.get())
        )

    def _on_transcribe_from_change(self, option: str):
        """
        Handles changes to `omn_transcribe_from`.

        Updates the transcription source based on the selected option. It also adjusts
        the GUI elements accordingly, such as configuring buttons, labels, and entry
        fields based on the chosen transcription source.

        :param option: The selected transcription source option.
        :type option: str
        """
        self._transcribe_from_source = AudioSource(option)
        self.ent_path.configure(textvariable=ctk.StringVar(self, ""))

        if self._transcribe_from_source != AudioSource.DIRECTORY:
            self.chk_autosave.configure(state=ctk.NORMAL)
            self.btn_save.configure(state=ctk.NORMAL)

        if self._transcribe_from_source in [AudioSource.FILE, AudioSource.DIRECTORY]:
            self.btn_main_action.configure(text="Generate transcription")
            self.lbl_path.configure(text="Path")
            self.btn_file_explorer.grid()
            self.frm_main_entry.grid()

            if self._transcribe_from_source == AudioSource.DIRECTORY:
                self.chk_autosave.select()
                self.chk_autosave.configure(state=ctk.DISABLED)
                self.chk_overwrite_files.configure(state=ctk.NORMAL)
                self.btn_save.configure(state=ctk.DISABLED)

        elif self._transcribe_from_source == AudioSource.MIC:
            self.btn_main_action.configure(text="Start recording")
            self.frm_main_entry.grid_remove()

        elif self._transcribe_from_source == AudioSource.YOUTUBE:
            self.btn_main_action.configure(text="Generate transcription")
            self.lbl_path.configure(text="YouTube video URL")
            self.btn_file_explorer.grid_remove()
            self.frm_main_entry.grid()

    def _on_select_path(self):
        """
        Triggers when `btn_file_explorer` is clicked to select the path of the file or
        directory to transcribe.
        """
        if self._transcribe_from_source == AudioSource.FILE:
            self._controller.select_file()
        elif self._transcribe_from_source == AudioSource.DIRECTORY:
            self._controller.select_directory()

    def _on_transcribe_from_mic(self):
        """
        Triggers when `btn_main_action` is clicked and the value of
        `omn_transcribe_from` is "Microphone". Depending on the value of the
        `_is_transcribing_from_mic` flag, it will stop or start the recording.
        """
        if self._is_transcribing_from_mic:
            self.stop_recording_from_mic()
        else:
            self._start_recording_from_mic()

    def _start_recording_from_mic(self):
        """
        Updates the UI and notifies the controller that the user has clicked the
        `btn_main_action` with the value of `omn_transcribe_from` to Microphone.
        """
        self._is_transcribing_from_mic = True

        self.btn_main_action.configure(
            fg_color=(Color.LIGHT_RED.value, Color.DARK_RED.value),
            hover_color=(
                Color.HOVER_LIGHT_RED.value,
                Color.HOVER_DARK_RED.value,
            ),
            text="Stop recording",
        )

        transcription = Transcription(
            source_type=AudioSource.MIC,
            language_code=self._get_language_code(),
            method=self.radio_var.get(),
            should_autosave=self.chk_autosave.get() == 1,
            should_overwrite=self.chk_overwrite_files.get() == 1,
            **self._get_whisperx_args(),
        )
        self._controller.prepare_for_transcription(transcription)

    def _on_main_action(self):
        """
        Triggers when `btn_main_action` is clicked.

        Prepares and initiates the transcription process based on the user's input and
        selections in the user interface. It disables certain UI elements during the
        transcription process to prevent further user input until the transcription
        is complete.
        """
        self.ent_path.configure(state=ctk.DISABLED)
        self.omn_transcribe_from.configure(state=ctk.DISABLED)
        self.omn_audio_language.configure(state=ctk.DISABLED)

        transcription = Transcription(
            language_code=self._get_language_code(),
            method=self.radio_var.get(),
            should_autosave=self.chk_autosave.get() == 1,
            should_overwrite=self.chk_overwrite_files.get() == 1,
            **self._get_whisperx_args(),
        )

        if self._transcribe_from_source == AudioSource.FILE:
            transcription.source_type = AudioSource.FILE
            transcription.source_path = Path(self.ent_path.get())
            self._controller.prepare_for_transcription(transcription)

        elif self._transcribe_from_source == AudioSource.DIRECTORY:
            transcription.source_type = AudioSource.DIRECTORY
            transcription.source_path = Path(self.ent_path.get())
            self._controller.prepare_for_transcription(transcription)

        elif self._transcribe_from_source == AudioSource.MIC:
            self._on_transcribe_from_mic()

        elif self._transcribe_from_source == AudioSource.YOUTUBE:
            transcription.source_type = AudioSource.YOUTUBE
            transcription.youtube_url = self.ent_path.get()
            self._controller.prepare_for_transcription(transcription)

    def _on_save_transcription(self):
        """
        Triggers when `btn_save_transcription` is clicked. Prompts the user with the
        file explorer to select a directory and enter the name of the transcription
        file.
        """
        self._controller.save_transcription(
            file_path=Path(self.ent_path.get()),
            should_autosave=False,
            should_overwrite=False,
        )

    def _on_transcribe_using_change(self):
        """
        Handles changes to the radio buttons of the "Transcribe using" option.

        Updates the user interface based on the chosen transcription method. It displays
        or hides specific options depending on whether WhisperX or Google API
        transcription method is selected.
        """
        if self.radio_var.get() == TranscriptionMethod.WHISPERX.value:
            self.frm_whisper_options.grid()
            self._toggle_frm_subtitle_options_visibility()
            self.frm_google_api_options.grid_remove()
        elif self.radio_var.get() == TranscriptionMethod.GOOGLE_API.value:
            self.frm_whisper_options.grid_remove()
            self.frm_whisperx_advanced_options.grid_remove()
            self.frm_subtitle_options.grid_remove()
            self.btn_whisperx_show_advanced_options.configure(
                text="Show advanced options"
            )
            self.frm_google_api_options.grid()

    def _on_google_api_key_set(self):
        """
        Handles the setting of the Google API key.

        Prompts the user to input a new Google API key through a dialog window. If a new
        API key is provided, and it differs from the existing one, it updates the
        configuration with the new API key.
        """
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

    def _on_show_advanced_options(self):
        """
        Handle clicks on `btn_whisperx_show_advanced_options`.

        Toggles the visibility of advanced options for WhisperX transcription. If the
        advanced options frame is currently displayed, it hides the frame and updates
        the button text to "Show advanced options". If the advanced options frame is
        currently hidden, it displays the frame and updates the button text to
        "Hide advanced options".
        """
        if self.frm_whisperx_advanced_options.winfo_ismapped():
            self.frm_whisperx_advanced_options.grid_remove()
            self.btn_whisperx_show_advanced_options.configure(
                text="Show advanced options"
            )
        else:
            self.frm_whisperx_advanced_options.grid()
            self.btn_whisperx_show_advanced_options.configure(
                text="Hide advanced options"
            )

    def _on_autosave_change(self):
        """
        Handles changes to `chk_autosave`.

        Adjusts the state of the `chk_overwrite_files` checkbox based on whether the
        autosave option is selected or deselected. If `chk_autosave` is selected, it
        enables `chk_overwrite_files`. If `chk_autosave` is deselected, it deselects
        and disables `chk_overwrite_files`.
        """
        if self.chk_autosave.get():
            self.chk_overwrite_files.configure(state=ctk.NORMAL)
        else:
            self.chk_overwrite_files.deselect()
            self.chk_overwrite_files.configure(state=ctk.DISABLED)

    def _on_output_file_types_change(self):
        """
        Handles changes to the output file types by updating the configuration and
        displaying the appropriate subtitle options.
        """
        # Dictionary mapping checkboxes to their corresponding file types
        checkbox_to_file_type = {
            self.chk_output_file_vtt: "vtt",
            self.chk_output_file_srt: "srt",
            self.chk_output_file_txt: "txt",
            self.chk_output_file_json: "json",
            self.chk_output_file_tsv: "tsv",
            self.chk_output_file_aud: "aud",
        }

        # List comprehension to gather selected file types
        output_file_types = [
            file_type for chk, file_type in checkbox_to_file_type.items() if chk.get()
        ]

        # Show or hide the subtitle options frame based on the selected subtitle file types
        if any(file_type in output_file_types for file_type in {"vtt", "srt"}):
            self.frm_subtitle_options.grid()
        else:
            self.frm_subtitle_options.grid_remove()

        # Convert the list to a comma-separated string and update the configuration
        output_file_types_str = ",".join(output_file_types)
        self._config_whisperx.output_file_types = output_file_types_str

        # Notify the config change
        self._on_config_change(
            section=ConfigSubtitles.Key.SECTION,
            key=ConfigWhisperX.Key.OUTPUT_FILE_TYPES,
            new_value=output_file_types_str,
        )

    def _toggle_progress_bar_visibility(self, should_show):
        """
        Toggles the visibility of the progress bar based on the specified parameter.

        :param should_show: A boolean indicating whether to show or hide the bar.
        """
        if should_show:
            self.progress_bar.grid(row=2, column=1, padx=40, pady=0, sticky=ctk.EW)
            self.progress_bar.start()
        else:
            self.progress_bar.grid_forget()

    def _toggle_frm_subtitle_options_visibility(self):
        if (
            "srt" in self._config_whisperx.output_file_types
            or "vtt" in self._config_whisperx.output_file_types
        ):
            if "srt" in self._config_whisperx.output_file_types:
                self.chk_output_file_srt.select()
            if "vtt" in self._config_whisperx.output_file_types:
                self.chk_output_file_vtt.select()

            self.frm_subtitle_options.grid()
        else:
            self.frm_subtitle_options.grid_remove()

    def _change_appearance_mode_event(self, new_appearance_mode: str):
        """
        Changes the appearance mode of the application and stores it in the
        configuration file.

        :param new_appearance_mode: The new appearance mode to set for the application.
                                    It can be "Light", "Dark" or "System".
        :type new_appearance_mode: str
        """
        ctk.set_appearance_mode(new_appearance_mode)

        self._on_config_change(
            section=ConfigSystem.Key.SECTION,
            key=ConfigSystem.Key.APPEARANCE_MODE,
            new_value=new_appearance_mode,
        )

    @staticmethod
    def _on_config_change(section: str, key: str, new_value: str):
        """
        Updates a configuration value. It modifies the specified value in the
        configuration file using the `ConfigManager.modify_value` method.

        :param section: The section of the configuration where the value is located.
        :type section: str
        :param key: The key corresponding to the value to be updated.
        :type key: str
        :param new_value: The new value to replace the existing one.
        :type new_value: str
        """
        cm.ConfigManager.modify_value(section, key, new_value)
