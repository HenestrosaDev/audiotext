from pathlib import Path
from typing import Any, Callable, Union

import customtkinter as ctk
import utils.constants as c
import utils.dict_utils as du
import utils.path_helper as ph
from controllers.main_controller import MainController
from models.config.config_subtitles import ConfigSubtitles
from models.config.config_system import ConfigSystem
from models.config.config_transcription import ConfigTranscription
from models.config.config_whisper_api import ConfigWhisperApi
from models.config.config_whisperx import ConfigWhisperX
from models.transcription import Transcription
from PIL import Image
from utils.config_manager import ConfigManager
from utils.enums import (
    AudioSource,
    Color,
    ComputeType,
    ModelSize,
    TimestampGranularities,
    TranscriptionMethod,
    WhisperApiResponseFormats,
)
from utils.env_keys import EnvKeys

from .custom_widgets.ctk_input_dialog import CTkInputDialog
from .custom_widgets.ctk_scrollable_dropdown import CTkScrollableDropdown


class MainWindow(ctk.CTkFrame):  # type: ignore[misc]
    def __init__(
        self,
        parent: Any,
        config_subtitles: ConfigSubtitles,
        config_system: ConfigSystem,
        config_transcription: ConfigTranscription,
        config_whisper_api: ConfigWhisperApi,
        config_whisperx: ConfigWhisperX,
    ):
        super().__init__(parent)

        # Configure grid of the window
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Init the configs
        self._config_subtitles = config_subtitles
        self._config_system = config_system
        self._config_transcription = config_transcription
        self._config_whisper_api = config_whisper_api
        self._config_whisperx = config_whisperx

        # Init the controller
        self._controller: Union[MainController, None] = None

        # Init the components of the window
        self._init_sidebar()
        self._init_main_content()

        # Update the state of the UI based on the configuration after setup
        self._on_audio_source_change(self._config_transcription.audio_source)

        # State
        self._audio_source = AudioSource(self._config_transcription.audio_source)
        self._is_transcribing_from_mic = False

        # To handle debouncing
        self._after_id = None  # To store the `after()` method ID

    # GETTERS AND SETTERS

    def set_controller(self, controller: MainController) -> None:
        """
        Set the controller of the window.

        :param controller: View controller
        :type controller: MainController
        :return: None
        """
        self._controller = controller

    # WIDGETS INITIALIZATION

    def _init_sidebar(self) -> None:
        """
        Initializes the sidebar widgets.

        :return: None
        """
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

        ## 'Transcription language' option menu
        self.lbl_transcription_language = ctk.CTkLabel(
            master=self.frm_shared_options,
            text="Transcription language",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.lbl_transcription_language.grid(row=0, column=0, padx=0, pady=(10, 0))

        self.omn_transcription_language = ctk.CTkOptionMenu(
            master=self.frm_shared_options
        )
        CTkScrollableDropdown(
            attach=self.omn_transcription_language,
            values=sorted(list(c.AUDIO_LANGUAGES.values())),
            alpha=1,
            command=self._on_transcription_language_change,
        )
        self.omn_transcription_language.grid(
            row=1, column=0, padx=20, pady=0, sticky=ctk.EW
        )
        self.omn_transcription_language.set(self._config_transcription.language)

        ## 'Audio source' option menu
        self.lbl_audio_source = ctk.CTkLabel(
            master=self.frm_shared_options,
            text="Audio source",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.lbl_audio_source.grid(row=2, column=0, padx=0, pady=(15, 0))

        self.omn_audio_source = ctk.CTkOptionMenu(
            master=self.frm_shared_options,
            values=[e.value for e in AudioSource],
            command=self._on_audio_source_change,
        )
        self.omn_audio_source.grid(row=3, column=0, padx=20, pady=0, sticky=ctk.EW)
        self.omn_audio_source.set(self._config_transcription.audio_source)

        ## 'Transcription method' option menu

        self.lbl_transcription_method = ctk.CTkLabel(
            master=self.frm_shared_options,
            text="Transcription method",
            font=ctk.CTkFont(size=14, weight="bold"),  # 14 is the default size
        )
        self.lbl_transcription_method.grid(row=4, column=0, padx=0, pady=(15, 0))

        self.omn_transcription_method = ctk.CTkOptionMenu(
            master=self.frm_shared_options,
            values=[e.value for e in TranscriptionMethod],
            command=self._on_transcription_method_change,
        )
        self.omn_transcription_method.grid(
            row=5, column=0, padx=20, pady=0, sticky=ctk.EW
        )
        self.omn_transcription_method.set(self._config_transcription.method)

        ## 'Generate transcription' button
        self.btn_main_action = ctk.CTkButton(
            master=self.frm_shared_options,
            fg_color="green",
            hover_color="darkgreen",
            text="Generate transcription",
            command=lambda: self._on_main_action(),
        )
        self.btn_main_action.grid(
            row=6, column=0, padx=20, pady=(30, 20), sticky=ctk.EW
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
            command=self._on_highlight_words_change,
        )
        self.chk_highlight_words.grid(row=1, column=0, padx=20, pady=10, sticky=ctk.W)

        if self._config_subtitles.highlight_words:
            self.chk_highlight_words.select()

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

        if self._config_transcription.method != TranscriptionMethod.WHISPERX.value:
            self.frm_whisper_options.grid_remove()

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

        if self._config_transcription.method != TranscriptionMethod.GOOGLE_API.value:
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
            command=lambda: self._on_set_api_key(
                env_key=EnvKeys.GOOGLE_API_KEY, title="Google API key"
            ),
        )
        self.btn_set_google_api_key.grid(
            row=1, column=0, padx=20, pady=(0, 20), sticky=ctk.EW
        )

        # ------------------

        # 'Whisper API options' frame
        self.frm_whisper_api_options = ctk.CTkFrame(
            master=self.frm_sidebar, border_width=2
        )
        self.frm_whisper_api_options.grid(
            row=3, column=0, padx=20, pady=(20, 0), sticky=ctk.EW
        )

        if self._config_transcription.method != TranscriptionMethod.WHISPER_API.value:
            self.frm_whisper_api_options.grid_remove()

        ## 'Whisper API options' label
        self.lbl_whisper_api_options = ctk.CTkLabel(
            master=self.frm_whisper_api_options,
            text="Whisper API options",
            font=ctk.CTkFont(size=14, weight="bold"),  # 14 is the default size
        )
        self.lbl_whisper_api_options.grid(row=0, column=0, padx=10, pady=(10, 5))

        ## 'Response format' option menu
        self.lbl_response_format = ctk.CTkLabel(
            master=self.frm_whisper_api_options,
            text="Response format",
        )
        self.lbl_response_format.grid(row=1, column=0, padx=20, pady=0, sticky=ctk.W)

        self.omn_response_format = ctk.CTkOptionMenu(
            master=self.frm_whisper_api_options,
            values=[rf.value for rf in WhisperApiResponseFormats],
            command=self._on_response_format_change,
        )
        self.omn_response_format.grid(
            row=2, column=0, padx=20, pady=(3, 18), sticky=ctk.EW
        )
        self.omn_response_format.set(self._config_whisper_api.response_format)

        ## 'Temperature' entry
        self.lbl_temperature = ctk.CTkLabel(
            master=self.frm_whisper_api_options,
            text="Temperature",
        )
        self.lbl_temperature.grid(row=3, column=0, padx=(65, 0), pady=0, sticky=ctk.W)

        self.temperature = ctk.StringVar(
            self, str(self._config_whisper_api.temperature)
        )
        self._setup_debounced_change(
            section=ConfigWhisperApi.Key.SECTION,
            key=ConfigWhisperApi.Key.TEMPERATURE,
            variable=self.temperature,
            callback=self._on_config_change,
        )

        self.ent_temperature = ctk.CTkEntry(
            master=self.frm_whisper_api_options,
            width=40,
            textvariable=self.temperature,
        )
        command = self.ent_temperature.register(self._validate_temperature)
        self.ent_temperature.configure(
            validate="key",
            validatecommand=(command, "%P"),
        )
        self.ent_temperature.grid(row=3, column=0, padx=(18, 20), pady=0, sticky=ctk.W)

        ## 'Timestamp granularities' radio button
        self.lbl_timestamp_granularities = ctk.CTkLabel(
            master=self.frm_whisper_api_options,
            text="Timestamp granularities",
        )
        self.lbl_timestamp_granularities.grid(row=4, column=0, padx=0, pady=(10, 5))

        self.chk_timestamp_granularities_segment = ctk.CTkCheckBox(
            master=self.frm_whisper_api_options,
            text=TimestampGranularities.SEGMENT.value.capitalize(),
            command=self._on_timestamp_granularities_change,
        )
        self.chk_timestamp_granularities_segment.grid(
            row=5, column=0, padx=20, pady=0, sticky=ctk.W
        )
        if (
            TimestampGranularities.SEGMENT.value
            in self._config_whisper_api.timestamp_granularities
        ):
            self.chk_timestamp_granularities_segment.select()

        self.chk_timestamp_granularities_word = ctk.CTkCheckBox(
            master=self.frm_whisper_api_options,
            text=TimestampGranularities.WORD.value.capitalize(),
            command=self._on_timestamp_granularities_change,
        )
        self.chk_timestamp_granularities_word.grid(
            row=6, column=0, padx=20, pady=(5, 0), sticky=ctk.W
        )
        if (
            TimestampGranularities.WORD.value
            in self._config_whisper_api.timestamp_granularities
        ):
            self.chk_timestamp_granularities_word.select()

        self._toggle_chk_timestamp_granularities()  # Disable if response format is not `verbose_json`

        ## 'Set OpenAI API key' button
        self.btn_set_openai_api_key = ctk.CTkButton(
            master=self.frm_whisper_api_options,
            text="Set OpenAI API key",
            command=lambda: self._on_set_api_key(
                env_key=EnvKeys.OPENAI_API_KEY, title="OpenAI API key"
            ),
        )

        self.btn_set_openai_api_key.grid(
            row=7, column=0, padx=20, pady=(16, 20), sticky=ctk.EW
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
                new_value=args[0],
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
                new_value=args[0],
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
            command=self._on_use_cpu_change,
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
        self.lbl_appearance_mode.grid(row=6, column=0, padx=20, pady=(20, 0))

        self.omn_appearance_mode = ctk.CTkOptionMenu(
            master=self.frm_sidebar,
            values=["System", "Light", "Dark"],
            command=self._change_appearance_mode_event,
        )
        self.omn_appearance_mode.set(self._config_system.appearance_mode)
        self.omn_appearance_mode.grid(row=7, column=0, padx=20, pady=0, sticky=ctk.EW)

        ## Info label
        self.lbl_info = ctk.CTkLabel(
            master=self.frm_sidebar,
            text="v2.3.0 | Made by HenestrosaDev",
            font=ctk.CTkFont(size=12),
        )
        self.lbl_info.grid(row=8, column=0, padx=20, pady=(5, 10))

    def _init_main_content(self) -> None:
        """
        Initializes the widgets on the right side of the main window.

        :return: None
        """
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

        if self._config_transcription.autosave:
            self.chk_autosave.select()

            if self._config_transcription.audio_source == AudioSource.DIRECTORY.value:
                self.chk_autosave.configure(state=ctk.DISABLED)

        ## 'Overwrite files' checkbox
        self.chk_overwrite_files = ctk.CTkCheckBox(
            master=self.frm_save_options,
            text="Overwrite existing files",
            command=lambda: self._on_config_change(
                section=ConfigTranscription.Key.SECTION,
                key=ConfigTranscription.Key.OVERWRITE_FILES,
                new_value=str(bool(self.chk_overwrite_files.get())),
            ),
        )
        self.chk_overwrite_files.grid(row=0, column=2, padx=0, pady=0)

        if not self._config_transcription.autosave:
            self.chk_overwrite_files.configure(state=ctk.DISABLED)

        if self._config_transcription.overwrite_files:
            self.chk_overwrite_files.select()

    # PUBLIC METHODS (called by the controller)

    def on_select_path_success(self, path: str) -> None:
        """
        Handles the successful selection of a file or directory path by updating the
        entry field with the selected file or directory path.

        :param path: The selected file or directory path.
        :type path: str
        :return: None
        """
        self.ent_path.configure(textvariable=ctk.StringVar(self, path))

    def on_processed_transcription(self) -> None:
        """
        Re-enables disabled widgets after transcription processing is complete.

        :return: None
        """
        self.ent_path.configure(state=ctk.NORMAL)
        self.omn_transcription_language.configure(state=ctk.NORMAL)
        self.omn_audio_source.configure(state=ctk.NORMAL)
        self.omn_transcription_method.configure(state=ctk.NORMAL)
        self.btn_main_action.configure(state=ctk.NORMAL)

        self._toggle_progress_bar_visibility(should_show=False)

    def on_stop_recording_from_mic(self) -> None:
        """
        Updates the state to indicate that recording from the microphone has
        stopped, notified by the controller. It also updates the button appearance to
        indicate that recording can be started again.

        Additionally, it delegates the task of stopping the recording to the controller.

        :return: None
        """
        self._is_transcribing_from_mic = False

        self.btn_main_action.configure(
            fg_color="green",
            hover_color="darkgreen",
            text="Start recording",
            state=ctk.DISABLED,
        )

    def display_text(self, text) -> None:
        """
        Clears any existing text in the transcription text box to display the provided
        text.

        :param text: The text to be displayed in the transcription text box.
        :type text: str
        :return: None
        """
        self.tbx_transcription.delete("1.0", ctk.END)
        self.tbx_transcription.insert("0.0", text)

    # PRIVATE METHODS

    def _get_transcription_properties(self) -> dict[str, Any]:
        """
        Checks the current state of user interface elements to determine the
        transcription properties.

        :return: A dictionary containing the transcription properties.
        :rtype: dict[str, Any]
        """
        language_code = du.find_key_by_value(
            dictionary=c.AUDIO_LANGUAGES,
            target_value=self.omn_transcription_language.get(),
        )

        properties = {
            "audio_source": self._audio_source,
            "language_code": language_code,
            "method": TranscriptionMethod(self.omn_transcription_method.get()),
            "should_autosave": self.chk_autosave.get() == 1,
            "should_overwrite": self.chk_overwrite_files.get() == 1,
        }

        if self.omn_transcription_method.get() == TranscriptionMethod.GOOGLE_API.value:
            properties["should_translate"] = False
            properties["output_file_types"] = ["txt"]
        if self.omn_transcription_method.get() == TranscriptionMethod.WHISPER_API.value:
            properties["should_translate"] = False
            properties["output_file_types"] = [self.omn_response_format.get()]
        if self.omn_transcription_method.get() == TranscriptionMethod.WHISPERX.value:
            properties["should_translate"] = bool(
                self.chk_whisper_options_translate.get()
            )
            properties[
                "output_file_types"
            ] = self._config_whisperx.output_file_types.split(",")

        return properties

    def _setup_debounced_change(
        self,
        section: ConfigManager.KeyType,
        key: ConfigManager.KeyType,
        variable: ctk.Variable,
        callback: Callable[[ConfigManager.KeyType, ConfigManager.KeyType, str], None],
        *unused: tuple,
    ) -> None:
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
        :type callback: Callable[[cm.ConfigManager.KeyType, cm.ConfigManager.KeyType, str], None]
        :param unused: Additional unused arguments that must be kept to prevent
                        exceptions.
        :type unused: tuple
        :return: None
        """
        variable.trace_add(
            mode="write",
            callback=lambda *args: self._on_change_debounced(
                section, key, variable, callback
            ),
        )

    def _on_change_debounced(
        self,
        section: ConfigManager.KeyType,
        key: ConfigManager.KeyType,
        variable: ctk.Variable,
        callback: Callable[[ConfigManager.KeyType, ConfigManager.KeyType, str], None],
        delay: int = 600,
    ) -> None:
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
        :type callback: Callable[[cm.ConfigManager.KeyType, cm.ConfigManager.KeyType, str], None]
        :param delay: Debounce delay in milliseconds before executing the callback.
        :type delay: int, optional
        :return: None
        """
        # Cancel the previously scheduled after call
        if self._after_id is not None:
            self.after_cancel(self._after_id)

        # Schedule a new after call with the specified delay
        self._after_id = self.after(
            delay, lambda: callback(section, key, variable.get())
        )

    def _on_transcription_language_change(self, option: str) -> None:
        """
        Handles changes to `omn_transcription_language`.

        Updates the configuration entry for the transcription language and sets the
        value in the `omn_transcription_language`.

        :param option: The selected transcription language.
        :type option: str
        :return: None
        """
        self._on_config_change(
            section=ConfigTranscription.Key.SECTION,
            key=ConfigTranscription.Key.LANGUAGE,
            new_value=option,
        )
        self.omn_transcription_language.set(option)

    def _on_audio_source_change(self, option: str) -> None:
        """
        Handles changes to `omn_audio_source`.

        Updates the transcription source based on the selected option. It also adjusts
        the GUI elements accordingly, such as configuring buttons, labels, and entry
        fields based on the chosen transcription source.

        :param option: The selected transcription source option.
        :type option: str
        """
        self._audio_source = AudioSource(option)
        self.ent_path.configure(textvariable=ctk.StringVar(self, ""))
        self._on_config_change(
            section=ConfigTranscription.Key.SECTION,
            key=ConfigTranscription.Key.AUDIO_SOURCE,
            new_value=option,
        )

        if self._audio_source != AudioSource.DIRECTORY:
            self.chk_autosave.configure(state=ctk.NORMAL)
            self.btn_save.configure(state=ctk.NORMAL)

        if self._audio_source in [AudioSource.FILE, AudioSource.DIRECTORY]:
            self.btn_main_action.configure(text="Generate transcription")
            self.lbl_path.configure(text="Path")
            self.btn_file_explorer.grid()
            self.frm_main_entry.grid()

            if self._audio_source == AudioSource.DIRECTORY:
                self.chk_autosave.select()
                self._on_autosave_change()
                self.chk_autosave.configure(state=ctk.DISABLED)
                self.chk_overwrite_files.configure(state=ctk.NORMAL)
                self.btn_save.configure(state=ctk.DISABLED)

        elif self._audio_source == AudioSource.MIC:
            self.btn_main_action.configure(text="Start recording")
            self.frm_main_entry.grid_remove()

        elif self._audio_source == AudioSource.YOUTUBE:
            self.btn_main_action.configure(text="Generate transcription")
            self.lbl_path.configure(text="YouTube video URL")
            self.btn_file_explorer.grid_remove()
            self.frm_main_entry.grid()

    def _on_select_path(self) -> None:
        """
        Triggers when `btn_file_explorer` is clicked to select the path of the file or
        directory to transcribe.

        :return: None
        """
        if self._audio_source == AudioSource.FILE:
            self._controller.select_file()
        elif self._audio_source == AudioSource.DIRECTORY:
            self._controller.select_directory()

    @staticmethod
    def _validate_temperature(temperature: str) -> bool:
        """
        Validates the input value of temperature to ensure that it is within the correct
        range (0.0 and 1.0).

        :param temperature: The input temperature to validate.
        :type temperature: str
        :return: True if the temperature is valid or False if it is not.
        :rtype: bool
        """
        if temperature == "":
            return True

        try:
            value = float(temperature)
            return 0 <= value <= 1
        except ValueError:
            return False

    def _on_highlight_words_change(self) -> None:
        new_value = "True" if self.chk_highlight_words.get() else "False"

        self._on_config_change(
            section=ConfigSubtitles.Key.SECTION,
            key=ConfigSubtitles.Key.HIGHLIGHT_WORDS,
            new_value=new_value,
        )

    def _on_start_recording_from_mic(self) -> None:
        """
        Updates the UI when the user has clicked the `btn_main_action` with the audio
        source set to Microphone.

        :return: None
        """
        self._is_transcribing_from_mic = True

        self.btn_main_action.configure(
            fg_color=(Color.LIGHT_RED.value, Color.DARK_RED.value),
            hover_color=(
                Color.HOVER_LIGHT_RED.value,
                Color.HOVER_DARK_RED.value,
            ),
            text="Stop recording",
            state=ctk.NORMAL,
        )

    def _prepare_ui_for_transcription(self) -> None:
        """
        Disables fields, shows the progress bar and removes the text of the previous
        transcription.

        :return: None
        """
        self.ent_path.configure(state=ctk.DISABLED)
        self.omn_transcription_language.configure(state=ctk.DISABLED)
        self.omn_audio_source.configure(state=ctk.DISABLED)
        self.omn_transcription_method.configure(state=ctk.DISABLED)

        if not self._is_transcribing_from_mic:
            self.btn_main_action.configure(state=ctk.DISABLED)

        self._toggle_progress_bar_visibility(should_show=True)

        self.display_text("")

    def _on_main_action(self) -> None:
        """
        Triggers when `btn_main_action` is clicked.

        Prepares and initiates the transcription process based on the user's input and
        selections in the user interface. It disables certain UI elements during the
        transcription process to prevent further user input until the transcription
        is complete.

        :return: None
        """
        self._prepare_ui_for_transcription()

        transcription = Transcription(**self._get_transcription_properties())

        if self._audio_source in [AudioSource.FILE, AudioSource.DIRECTORY]:
            transcription.audio_source_path = Path(self.ent_path.get())
        elif self._audio_source == AudioSource.MIC:
            if self._is_transcribing_from_mic:
                self._controller.stop_recording_from_mic()
                return
            else:
                self._on_start_recording_from_mic()
        elif self._audio_source == AudioSource.YOUTUBE:
            transcription.youtube_url = self.ent_path.get()

        self._controller.prepare_for_transcription(transcription)

    def _on_save_transcription(self) -> None:
        """
        Triggers when `btn_save` is clicked. Prompts the user with the file explorer to
        select a directory and enter the name of the transcription file.

        :return: None
        """
        self._controller.save_transcription(
            file_path=Path(self.ent_path.get()),
            should_autosave=False,
            should_overwrite=False,
        )

    def _on_transcription_method_change(self, option: str) -> None:
        """
        Handles changes to `omn_transcription_method`.

        Updates the user interface based on the chosen transcription method. It displays
        or hides specific options depending on whether WhisperX or Google API
        transcription method is selected.

        :param option: Selected transcription method.
        :type option: str
        :return: None
        """
        self._on_config_change(
            section=ConfigTranscription.Key.SECTION,
            key=ConfigTranscription.Key.METHOD,
            new_value=option,
        )

        if option == TranscriptionMethod.WHISPERX.value:
            self.frm_whisper_options.grid()
            self._toggle_frm_subtitle_options_visibility()
            self.frm_google_api_options.grid_remove()
            self.frm_whisper_api_options.grid_remove()

        elif option == TranscriptionMethod.GOOGLE_API.value:
            self.frm_whisper_options.grid_remove()
            self.frm_whisperx_advanced_options.grid_remove()
            self.frm_subtitle_options.grid_remove()
            self.btn_whisperx_show_advanced_options.configure(
                text="Show advanced options"
            )
            self.frm_google_api_options.grid()
            self.frm_whisper_api_options.grid_remove()

        elif option == TranscriptionMethod.WHISPER_API.value:
            self.frm_whisper_options.grid_remove()
            self.frm_whisperx_advanced_options.grid_remove()
            self.frm_subtitle_options.grid_remove()
            self.btn_whisperx_show_advanced_options.configure(
                text="Show advanced options"
            )
            self.frm_google_api_options.grid_remove()
            self.frm_whisper_api_options.grid()

    @staticmethod
    def _on_set_api_key(env_key: EnvKeys, title: str) -> None:
        """
        Opens a dialog window to store the API key in the environment variables, if
        applicable.

        :param env_key: Environment key to set the value.
        :type env_key: EnvKeys
        :param title: Title of the dialog window.
        :type title: str
        :return: None
        """
        old_api_key = env_key.get_value()

        dialog = CTkInputDialog(
            title=title,
            label_text="Type in the API key:",
            entry_text=old_api_key,
        )

        new_api_key = dialog.get_input()

        if new_api_key and old_api_key != new_api_key:
            env_key.set_value(new_api_key.strip())

    def _on_show_advanced_options(self) -> None:
        """
        Handle clicks on `btn_whisperx_show_advanced_options`.

        Toggles the visibility of advanced options for WhisperX transcription. If the
        advanced options frame is currently displayed, it hides the frame and updates
        the button text to "Show advanced options". If the advanced options frame is
        currently hidden, it displays the frame and updates the button text to
        "Hide advanced options".

        :return: None
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

    def _on_autosave_change(self) -> None:
        """
        Handles changes to `chk_autosave`.

        Adjusts the state of the `chk_overwrite_files` checkbox based on whether the
        autosave option is selected or deselected. If `chk_autosave` is selected, it
        enables `chk_overwrite_files`. If `chk_autosave` is deselected, it deselects
        and disables `chk_overwrite_files`.

        :return: None
        """
        self._on_config_change(
            section=ConfigTranscription.Key.SECTION,
            key=ConfigTranscription.Key.AUTOSAVE,
            new_value=str(bool(self.chk_autosave.get())),
        )

        if self.chk_autosave.get():
            self.chk_overwrite_files.configure(state=ctk.NORMAL)
        else:
            if self.chk_overwrite_files.get():
                self._on_config_change(
                    section=ConfigTranscription.Key.SECTION,
                    key=ConfigTranscription.Key.OVERWRITE_FILES,
                    new_value="False",
                )

            self.chk_overwrite_files.deselect()
            self.chk_overwrite_files.configure(state=ctk.DISABLED)

    def _on_output_file_types_change(self) -> None:
        """
        Handles changes to the output file types by updating the configuration and
        displaying the appropriate subtitle options if any of the selected output file
        types is a subtitle file type.

        :return: None
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
            section=ConfigWhisperX.Key.SECTION,
            key=ConfigWhisperX.Key.OUTPUT_FILE_TYPES,
            new_value=output_file_types_str,
        )

    def _toggle_chk_timestamp_granularities(self) -> None:
        """
        Toggles timestamp granularities checkboxes visibility depending on the selected
        response format.

        :return: None
        """
        if self.omn_response_format.get() != "verbose_json":
            self.chk_timestamp_granularities_segment.configure(state=ctk.DISABLED)
            self.chk_timestamp_granularities_word.configure(state=ctk.DISABLED)

            self.chk_timestamp_granularities_segment.deselect()
            self.chk_timestamp_granularities_word.deselect()
        else:
            self.chk_timestamp_granularities_segment.configure(state=ctk.NORMAL)
            self.chk_timestamp_granularities_word.configure(state=ctk.NORMAL)

            if (
                TimestampGranularities.SEGMENT.value
                in self._config_whisper_api.timestamp_granularities
            ):
                self.chk_timestamp_granularities_segment.select()

            if (
                TimestampGranularities.WORD.value
                in self._config_whisper_api.timestamp_granularities
            ):
                self.chk_timestamp_granularities_word.select()

    def _on_response_format_change(self, option: str) -> None:
        """
        Handles changes to the response format by updating the configuration and
        toggling the timestamp granularities checkboxes.

        :param option: Selected response format.
        :type option: str
        :return: None
        """
        self._on_config_change(
            section=ConfigWhisperApi.Key.SECTION,
            key=ConfigWhisperApi.Key.RESPONSE_FORMAT,
            new_value=option,
        )

        self._toggle_chk_timestamp_granularities()

    def _on_timestamp_granularities_change(self) -> None:
        """
        Handles changes to the timestamp granularities by updating the configuration.

        :return: None
        """
        # Dictionary mapping checkboxes to their corresponding file types
        chk_to_timestamp_granularity = {
            self.chk_timestamp_granularities_segment: TimestampGranularities.SEGMENT.value,
            self.chk_timestamp_granularities_word: TimestampGranularities.WORD.value,
        }

        # List comprehension to gather selected file types
        selected_timestamp_granularities = [
            timestamp_granularity
            for chk, timestamp_granularity in chk_to_timestamp_granularity.items()
            if chk.get()
        ]

        # Convert the list to a comma-separated string and update the configuration
        selected_timestamp_granularities_str = ",".join(
            selected_timestamp_granularities
        )
        self._config_whisper_api.timestamp_granularities = (
            selected_timestamp_granularities_str
        )

        # Notify the config change
        self._on_config_change(
            section=ConfigWhisperApi.Key.SECTION,
            key=ConfigWhisperApi.Key.TIMESTAMP_GRANULARITIES,
            new_value=selected_timestamp_granularities_str,
        )

    def _toggle_progress_bar_visibility(self, should_show: bool) -> None:
        """
        Toggles the visibility of the progress bar based on the specified parameter.

        :param should_show: A boolean indicating whether to show or hide the bar.
        :type should_show: bool
        :return: None
        """
        if should_show:
            self.progress_bar.grid(row=2, column=1, padx=40, pady=0, sticky=ctk.EW)
            self.progress_bar.start()
        else:
            self.progress_bar.grid_forget()

    def _toggle_frm_subtitle_options_visibility(self) -> None:
        """
        Toggle the visibility of `frm_subtitle_options` depending on whether the
        transcription method allows to configure subtitle generation and whether
        any of the selected output file types is a subtitle file type.

        :return: None
        """
        if (
            self._config_transcription.method == TranscriptionMethod.WHISPERX.value
            and (
                "srt" in self._config_whisperx.output_file_types
                or "vtt" in self._config_whisperx.output_file_types
            )
        ):
            if "srt" in self._config_whisperx.output_file_types:
                self.chk_output_file_srt.select()
            if "vtt" in self._config_whisperx.output_file_types:
                self.chk_output_file_vtt.select()

            self.frm_subtitle_options.grid()
        else:
            self.frm_subtitle_options.grid_remove()

    def _on_use_cpu_change(self) -> None:
        new_value = "True" if self.chk_use_cpu.get() else "False"

        self._on_config_change(
            section=ConfigWhisperX.Key.SECTION,
            key=ConfigWhisperX.Key.USE_CPU,
            new_value=new_value,
        )

    def _change_appearance_mode_event(self, new_appearance_mode: str) -> None:
        """
        Changes the appearance mode of the application and stores it in the
        configuration file.

        :param new_appearance_mode: The new appearance mode to set for the application.
                                    It can be "Light", "Dark" or "System".
        :type new_appearance_mode: str
        :return: None
        """
        ctk.set_appearance_mode(new_appearance_mode)

        self._on_config_change(
            section=ConfigSystem.Key.SECTION,
            key=ConfigSystem.Key.APPEARANCE_MODE,
            new_value=new_appearance_mode,
        )

    @staticmethod
    def _on_config_change(
        section: ConfigManager.KeyType, key: ConfigManager.KeyType, new_value: str
    ) -> None:
        """
        Updates a configuration value. It modifies the specified value in the
        configuration file using the `ConfigManager.modify_value` method.

        :param section: The section of the configuration where the value is located.
        :type section: str
        :param key: The key corresponding to the value to be updated.
        :type key: str
        :param new_value: The new value to replace the existing one.
        :type new_value: str
        :return: None
        """
        ConfigManager.modify_value(section, key, new_value)
