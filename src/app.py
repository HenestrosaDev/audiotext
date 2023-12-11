import customtkinter as ctk
import utils.constants as c
import utils.path_helper as ph
from controller.main_controller import MainController
from model.transcription import Transcription
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
        height = 800
        self.geometry(f"{width}x{height}")

        # Min size of the window
        min_width = 500
        min_height = 250
        self.minsize(min_width, min_height)

        # Create the view and place it on the root window
        view = MainWindow(self)
        view.pack(fill="both", expand=True)

        # Create the model
        transcription = Transcription()

        # Create the controller
        controller = MainController(transcription, view)

        # Set the controller to view
        view.set_controller(controller)


if __name__ == "__main__":
    app = App()
    app.eval("tk::PlaceWindow . center")
    app.mainloop()
