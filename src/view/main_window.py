import locale

import customtkinter as ctk
import utils.constants as c
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

    def set_controller(self, controller):
        """
        Set the controller of the window.

        :param controller: View controller
        :type controller: MainController
        """
        self._controller = controller

    # WIDGETS INITIALIZATION

    def _init_sidebar(self):
        # Sidebar frame
        self.frm_sidebar = ctk.CTkFrame(self, width=140, corner_radius=0)
        self.frm_sidebar.grid(row=0, column=0, rowspan=4, sticky="nsew")
        self.frm_sidebar.grid_rowconfigure(6, weight=1)

        # Logo label
        self.lbl_logo = ctk.CTkLabel(
            self.frm_sidebar,
            text=c.APP_NAME,
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.lbl_logo.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Audio language
        self.lbl_audio_language = ctk.CTkLabel(
            self.frm_sidebar, text=f'{_("Audio language")}:', anchor="w"
        )
        self.lbl_audio_language.grid(row=1, column=0, padx=20, pady=(20, 0))

        self.cbx_audio_language = ctk.CTkComboBox(
            self.frm_sidebar, values=list(c.AUDIO_LANGUAGES.values())
        )
        self.cbx_audio_language.grid(row=2, column=0, padx=20, pady=10)
        self.cbx_audio_language.set(c.AUDIO_LANGUAGES[locale.getdefaultlocale()[0]])

        # Select file button
        self.btn_select_file = ctk.CTkButton(
            self.frm_sidebar, text=_("Select file"), command=self._on_select_file
        )
        self.btn_select_file.grid(row=3, column=0, padx=20, pady=(30, 20))

        # Transcribe from microphone button
        self.btn_transcribe_from_mic = ctk.CTkButton(
            self.frm_sidebar,
            text=_("Transcribe from microphone"),
            command=lambda: self._on_generate_transcription(c.MIC),
        )
        self.btn_transcribe_from_mic.grid(row=4, column=0, padx=20, pady=(20, 30))

        # Generate text button
        self.btn_generate_transcription = ctk.CTkButton(
            self.frm_sidebar,
            fg_color="green",
            text=_("Generate transcription"),
            command=lambda: self._on_generate_transcription(c.FILE),
        )
        self.btn_generate_transcription.grid(row=5, column=0, padx=20, pady=10)
        self.btn_generate_transcription.grid_remove()  # hidden at start

        # App language
        self.lbl_app_language = ctk.CTkLabel(
            self.frm_sidebar, text=f'{_("App language")}:', anchor="w"
        )
        self.lbl_app_language.grid(row=7, column=0, padx=20, pady=(20, 0))

        self.omn_app_language = ctk.CTkOptionMenu(
            self.frm_sidebar,
            values=list(c.APP_LANGUAGES.values()),
            command=self._on_change_app_language,
        )
        self.omn_app_language.grid(row=8, column=0, padx=20, pady=10)
        self.omn_app_language.set(
            c.APP_LANGUAGES.get(locale.getdefaultlocale()[0].split("_")[0], "English")
        )

        # Appearance mode
        self.lbl_appearance_mode = ctk.CTkLabel(
            self.frm_sidebar, text=f'{_("Appearance mode")}:', anchor="w"
        )
        self.lbl_appearance_mode.grid(row=9, column=0, padx=20, pady=(10, 0))

        self.omn_appearance_mode = ctk.CTkOptionMenu(
            self.frm_sidebar,
            values=[_("System"), _("Light"), _("Dark")],
            command=self._change_appearance_mode_event,
        )
        self.omn_appearance_mode.grid(row=10, column=0, padx=20, pady=10)

    def _init_main_content(self):
        # Selected file entry
        self.ent_selected_file = ctk.CTkEntry(self, state="disabled")
        self.ent_selected_file.grid(
            row=0, column=1, padx=20, pady=(20, 0), sticky="new"
        )
        self.ent_selected_file.grid_remove()  # hidden at start

        # Text audio textbox
        self.tbx_transcription = ctk.CTkTextbox(self, wrap="word")
        self.tbx_transcription.grid(row=1, column=1, padx=20, pady=20, sticky="nsew")

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.configure(mode="indeterminnate")

        # Save text button
        self.btn_save = ctk.CTkButton(
            self,
            fg_color="green",
            text=_("Save transcription"),
            command=self._on_save_transcription,
        )
        self.btn_save.grid(row=2, column=1, padx=20, pady=(0, 20), sticky="sew")
        self.btn_save.grid_remove()  # hidden at start

    # EVENT HANDLER METHODS

    def _on_change_app_language(self, language_name: str):
        self._controller.change_app_language(language_name)

    def _on_select_file(self):
        self._controller.select_file()

    def _on_generate_transcription(self, source):
        self._controller.generate_transcription(
            source, self.cbx_audio_language.get().strip().lower()
        )

    def _on_save_transcription(self):
        self._controller.save_transcription()

    # WIDGET METHODS

    @staticmethod
    def _toggle_widget_state(widget, should_enable):
        if should_enable:
            widget.configure(state="enabled")
        else:
            widget.configure(state="disabled")

    def toggle_btn_generate_transcription_state(self, should_enable: bool):
        self._toggle_widget_state(self.btn_generate_transcription, should_enable)

    def toggle_btn_transcribe_from_mic_state(self, should_enable: bool):
        self._toggle_widget_state(self.btn_transcribe_from_mic, should_enable)

    @staticmethod
    def _toggle_widget_visibility(widget, should_show):
        if should_show:
            widget.grid()
        else:
            widget.grid_remove()

    def toggle_ent_selected_file(self, should_show):
        self._toggle_widget_visibility(self.ent_selected_file, should_show)

    def toggle_btn_generate_transcription(self, should_show):
        self._toggle_widget_visibility(self.btn_generate_transcription, should_show)

    def toggle_progress_bar(self, should_show):
        if should_show:
            self.progress_bar.grid(row=1, column=1, padx=40, pady=0, sticky="ew")
            self.progress_bar.start()
        else:
            self.progress_bar.grid_forget()

    def toggle_btn_save(self, should_show):
        self._toggle_widget_visibility(self.btn_save, should_show)

    def set_ent_selected_file_text(self, text):
        self.ent_selected_file.configure(textvariable=ctk.StringVar(self, text))

    def display_text(self, message):
        self.tbx_transcription.delete("1.0", "end")
        self.tbx_transcription.insert("0.0", message)

    def refresh_widgets(self):
        from utils.i18n import _

        self.lbl_audio_language.configure(text=f'{_("Audio language")}:')
        self.btn_select_file.configure(text=_("Select file"))
        self.btn_transcribe_from_mic.configure(text=_("Transcribe from microphone"))
        self.btn_generate_transcription.configure(text=_("Generate transcription"))
        self.lbl_app_language.configure(text=f'{_("App language")}:')
        self.lbl_appearance_mode.configure(text=f'{_("Appearance mode")}:')
        self.omn_appearance_mode.configure(values=[_("System"), _("Light"), _("Dark")])
        self.omn_appearance_mode.set(_("System"))
        self.btn_save.configure(text=_("Save transcription"))
        ctk.set_appearance_mode(_(self.omn_appearance_mode.get()))

    @staticmethod
    def _change_appearance_mode_event(new_appearance_mode: str):
        appearance_mode_map = {
            _("Dark"): "Dark",
            _("Light"): "Light",
            _("System"): "System",
        }
        appearance_mode = appearance_mode_map.get(new_appearance_mode, "System")
        ctk.set_appearance_mode(appearance_mode)
