import sys

import customtkinter as ctk


def set_button_state(button: ctk.CTkButton, state: str) -> None:
    """
    Enables or disables a button without making it flicker.

    CustomTkinter changes the cursor of the frame of the button with its state.
    On macOS, configuring that frame hides its text and image for a moment. The
    cursor is changed in its canvas and labels instead, which cover the frame.
    """
    if button.cget("state") == state:
        return

    button._cursor_manipulation_enabled = False
    button.configure(state=state)

    # The same cursors as CustomTkinter
    hand_cursor = {"darwin": "pointinghand", "win32": "hand2"}.get(sys.platform)
    if hand_cursor and button.cget("command") is not None:
        cursor = "arrow" if state == ctk.DISABLED else hand_cursor
        for widget in (button._canvas, button._text_label, button._image_label):
            if widget is not None:
                widget.configure(cursor=cursor)
