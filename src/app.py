import customtkinter as ctk
import utils.config_manager as cm
import utils.constants as c
import utils.path_helper as ph
from controllers.main_controller import MainController
from models.config.config_whisperx import ConfigWhisperX
from models.transcription import Transcription
from utils.enums import ComputeType
from views.main_window import MainWindow


class App(ctk.CTk):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()

        # Get config_system to set the initial appearance mode
        config_system = cm.ConfigManager.get_config_system()

        # Modes: "System", "Dark", "Light"
        ctk.set_appearance_mode(config_system.appearance_mode)
        # Themes: "blue" (standard), "green", "dark-blue"
        ctk.set_default_color_theme("blue")

        self.title(c.APP_NAME)
        self.wm_iconbitmap(ph.ROOT_PATH / "res/windows/icon.ico")

        # Initial size of the window
        width = 1000
        height = 755
        self.geometry(f"{width}x{height}")

        # Min size of the window
        min_width = 500
        min_height = 250
        self.minsize(min_width, min_height)

        # Place the torch import here to avoid the "No ffmpeg exe could be found" error
        import torch

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

            cm.ConfigManager.modify_value(
                section=ConfigWhisperX.Key.SECTION,
                key=ConfigWhisperX.Key.USE_CPU,
                new_value="True",
            )

        # Initialize configs
        config_subtitles = cm.ConfigManager.get_config_subtitles()
        config_transcription = cm.ConfigManager.get_config_transcription()
        config_whisper_api = cm.ConfigManager.get_config_whisper_api()
        config_whisperx = cm.ConfigManager.get_config_whisperx()

        # Create the view and place it on the root window
        view = MainWindow(
            self,
            config_subtitles,
            config_system,
            config_transcription,
            config_whisper_api,
            config_whisperx,
        )
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
