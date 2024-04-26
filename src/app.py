import customtkinter as ctk
import torch
import utils.config_manager as cm
import utils.constants as c
import utils.path_helper as ph
from controller.main_controller import MainController
from model.config.config_whisperx import ConfigWhisperX
from model.transcription import Transcription
from utils.enums import ComputeType
from view.main_window import MainWindow


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Modes: "System" (standard), "Dark", "Light"
        ctk.set_appearance_mode("System")
        # Themes: "blue" (standard), "green", "dark-blue"
        ctk.set_default_color_theme("blue")

        self.title(c.APP_NAME)
        self.wm_iconbitmap(ph.ROOT_PATH / ph.IMG_RELATIVE_PATH / "icon.ico")

        # Initial size of the window
        width = 1000
        height = 768
        self.geometry(f"{width}x{height}")

        # Min size of the window
        min_width = 500
        min_height = 250
        self.minsize(min_width, min_height)

        # Check GPU
        cm.ConfigManager.modify_value(
            section=ConfigWhisperX.Key.SECTION,
            key=ConfigWhisperX.Key.CAN_USE_GPU,
            new_value=str(torch.cuda.is_available()),
        )

        if not torch.cuda.is_available():
            cm.ConfigManager.modify_value(
                section=ConfigWhisperX.Key.SECTION,
                key=ConfigWhisperX.Key.COMPUTE_TYPE,
                new_value=ComputeType.INT8.value,
            )

        # Initialize configs
        config_whisperx = cm.ConfigManager.get_config_whisperx()
        config_google_api = cm.ConfigManager.get_config_google_api()
        config_subtitles = cm.ConfigManager.get_config_subtitles()

        # Create the view and place it on the root window
        view = MainWindow(self, config_whisperx, config_google_api, config_subtitles)
        view.pack(fill="both", expand=True)

        # Create the model for the controller
        transcription = Transcription()

        # Create the controller
        controller = MainController(transcription, view)

        # Set the controller to view
        view.set_controller(controller)


if __name__ == "__main__":
    app = App()
    app.eval("tk::PlaceWindow . center")
    app.mainloop()
