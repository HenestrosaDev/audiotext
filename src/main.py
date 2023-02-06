import asyncio
import locale
import threading
from pathlib import Path

import constants as c
import customtkinter
import logic as lgc
import utils as u


class App(customtkinter.CTk):
    def __init__(self):
        super().__init__()
        self.filepath = "/"
        self.transcription = None

        self.configure_window()
        self.create_sidebar()
        self.create_main_content()

    def configure_window(self):
        # Modes: "System" (standard), "Dark", "Light"
        customtkinter.set_appearance_mode("System")
        # Themes: "blue" (standard), "green", "dark-blue"
        customtkinter.set_default_color_theme("blue")

        self.title("Audiotext")
        self.wm_iconbitmap(u.ROOT_PATH / "res/img/icon.ico")
        self.geometry(f"{1000}x{700}")
        self.minsize(750, 550)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

    # VIEWS INITIALIZATION

    def create_sidebar(self):
        # Sidebar frame
        self.frm_sidebar = customtkinter.CTkFrame(self, width=140, corner_radius=0)
        self.frm_sidebar.grid(row=0, column=0, rowspan=4, sticky="nsew")
        self.frm_sidebar.grid_rowconfigure(6, weight=1)

        # Logo label
        self.lbl_logo = customtkinter.CTkLabel(
            self.frm_sidebar,
            text="Audiotext",
            font=customtkinter.CTkFont(size=20, weight="bold"),
        )
        self.lbl_logo.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Audio language
        self.lbl_audio_language = customtkinter.CTkLabel(
            self.frm_sidebar, text=f'{u._("Audio language")}:', anchor="w"
        )
        self.lbl_audio_language.grid(row=1, column=0, padx=20, pady=(20, 0))

        self.cbx_audio_language = customtkinter.CTkComboBox(
            self.frm_sidebar, values=list(c.LANGUAGES.values())
        )
        self.cbx_audio_language.grid(row=2, column=0, padx=20, pady=10)
        self.cbx_audio_language.set(c.LANGUAGES[locale.getdefaultlocale()[0]])

        # Select file button
        self.btn_select_file = customtkinter.CTkButton(
            self.frm_sidebar, text=u._("Select audio file"), command=self.open_file
        )
        self.btn_select_file.grid(row=3, column=0, padx=20, pady=(30, 20))

        # Transcribe from microphone button
        self.btn_transcribe_from_mic = customtkinter.CTkButton(
            self.frm_sidebar,
            text=u._("Transcribe from microphone"),
            command=lambda: self.get_transcription(c.MIC),
        )
        self.btn_transcribe_from_mic.grid(row=4, column=0, padx=20, pady=(20, 30))

        # Generate text button
        self.btn_generate_text = customtkinter.CTkButton(
            self.frm_sidebar,
            fg_color="green",
            text=u._("Generate text"),
            command=lambda: self.get_transcription(c.FILE),
        )
        self.btn_generate_text.grid(row=5, column=0, padx=20, pady=10)
        self.btn_generate_text.grid_remove()  # hidden at start

        # App language
        self.lbl_app_language = customtkinter.CTkLabel(
            self.frm_sidebar, text=f'{u._("App language")}:', anchor="w"
        )
        self.lbl_app_language.grid(row=7, column=0, padx=20, pady=(20, 0))

        self.omn_app_language = customtkinter.CTkOptionMenu(
            self.frm_sidebar,
            values=[c.LANGUAGES["es"], c.LANGUAGES["en"]],
            command=self.change_app_language,
        )
        self.omn_app_language.grid(row=8, column=0, padx=20, pady=10)
        self.omn_app_language.set(c.LANGUAGES[locale.getdefaultlocale()[0]])

        # Appearance mode
        self.lbl_appearance_mode = customtkinter.CTkLabel(
            self.frm_sidebar, text=f'{u._("Appearance mode")}:', anchor="w"
        )
        self.lbl_appearance_mode.grid(row=9, column=0, padx=20, pady=(10, 0))

        self.omn_appearance_mode = customtkinter.CTkOptionMenu(
            self.frm_sidebar,
            values=[u._("System"), u._("Light"), u._("Dark")],
            command=self.change_appearance_mode_event,
        )
        self.omn_appearance_mode.grid(row=10, column=0, padx=20, pady=10)

    def change_app_language(self, language_name):
        language_code = [i for i in c.LANGUAGES if c.LANGUAGES[i] == language_name][0]
        u.load_translation(language_code)

        self.lbl_audio_language.configure(text=f'{u._("Audio language")}:')
        self.btn_select_file.configure(text=u._("Select audio file"))
        self.btn_transcribe_from_mic.configure(text=u._("Transcribe from microphone"))
        self.btn_generate_text.configure(text=u._("Generate text"))
        self.lbl_app_language.configure(text=f'{u._("App language")}:')
        self.lbl_appearance_mode.configure(text=f'{u._("Appearance mode")}:')
        self.omn_appearance_mode.configure(
            values=[u._("System"), u._("Light"), u._("Dark")]
        )
        self.omn_appearance_mode.set(u._("System"))
        self.btn_save.configure(text=u._("Save transcription"))
        customtkinter.set_appearance_mode(u._(self.omn_appearance_mode.get()))

    def create_main_content(self):
        # Selected file entry
        self.ent_selected_file = customtkinter.CTkEntry(self, state="disabled")
        self.ent_selected_file.grid(
            row=0, column=1, padx=20, pady=(20, 0), sticky="new"
        )
        self.ent_selected_file.grid_remove()  # hidden at start

        # Text audio textbox
        self.tbx_transcription = customtkinter.CTkTextbox(self, wrap="word")
        self.tbx_transcription.grid(row=1, column=1, padx=20, pady=20, sticky="nsew")

        # Save text button
        self.btn_save = customtkinter.CTkButton(
            self,
            fg_color="green",
            text=u._("Save transcription"),
            command=self.save_transcription,
        )
        self.btn_save.grid(row=2, column=1, padx=20, pady=(0, 20), sticky="sew")
        self.btn_save.grid_remove()  # hidden at start

    # EVENTS

    @staticmethod
    def change_appearance_mode_event(new_appearance_mode: str):
        appearance_mode_map = {
            u._("Dark"): "Dark",
            u._("Light"): "Light",
            u._("System"): "System",
        }
        appearance_mode = appearance_mode_map.get(new_appearance_mode, "System")
        customtkinter.set_appearance_mode(appearance_mode)

    def open_file(self):
        # Open the file dialog
        filepath = lgc.open_file()

        if filepath:
            self.filepath = filepath
            self.ent_selected_file.grid()
            self.ent_selected_file.configure(
                textvariable=customtkinter.StringVar(self, filepath)
            )
            self.btn_generate_text.grid()

    def get_transcription(self, source):
        selected_path = Path(self.filepath)
        is_file_extension_valid = False

        if selected_path.suffix in c.VIDEO_FILE_EXTENSIONS:
            is_file_extension_valid = True
        else:
            for extensions in c.AUDIO_FILE_EXTENSIONS.values():
                if selected_path.suffix in extensions:
                    is_file_extension_valid = True
                    break
        is_file_valid = selected_path.is_file() and is_file_extension_valid

        if source == c.FILE and not is_file_valid:
            self.display_text(
                u._(
                    "Error: No audio file selected, please select one before generating text."
                )
            )
        else:
            threading.Thread(
                target=lambda loop: loop.run_until_complete(
                    self.async_get_transcription(source)
                ),
                args=(asyncio.new_event_loop(),),
            ).start()

    async def async_get_transcription(self, source):
        try:
            # Get the selected language code
            language_code = [
                key
                for key, value in c.LANGUAGES.items()
                if value.lower() == self.cbx_audio_language.get().strip().lower()
            ][0]

            # Show progress bar
            self.progress_bar = customtkinter.CTkProgressBar(self)
            self.progress_bar.grid(row=1, column=1, padx=40, pady=0, sticky="ew")
            self.progress_bar.configure(mode="indeterminnate")
            self.progress_bar.start()

            # Disable action buttons to avoid multiple requests at the same time
            self.btn_generate_text.configure(state="disabled")
            self.btn_transcribe_from_mic.configure(state="disabled")

            # Get transcription
            if source == c.FILE:
                self.transcription = await lgc.generate_file_transcription(
                    self.filepath, language_code
                )
            elif source == c.MIC:
                self.transcription = await lgc.generate_mic_transcription(language_code)
            # Display transcription
            self.display_text(self.transcription)

            # Re-enable action buttons
            self.btn_generate_text.configure(state="enabled")
            self.btn_transcribe_from_mic.configure(state="enabled")

            # Hide generate button and remove progress bar
            self.progress_bar.grid_forget()
            self.btn_generate_text.grid_remove()

            # Show save button if transcription is not empty
            if self.transcription:
                self.btn_save.grid()
        except IndexError:
            self.display_text(u._("Error: The selected audio language is not valid."))

    def display_text(self, message):
        self.tbx_transcription.delete("1.0", "end")
        self.tbx_transcription.insert("0.0", message)

    def save_transcription(self):
        lgc.save_transcription(
            self.ent_selected_file.get(), self.tbx_transcription.get("1.0", "end-1c")
        )


if __name__ == "__main__":
    app = App()
    app.eval("tk::PlaceWindow . center")
    app.mainloop()
