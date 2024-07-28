from typing import Optional, Tuple, Union

import customtkinter as ctk
from utils.enums import Color


class CTkInputDialog(ctk.CTkToplevel):  # type: ignore
    """
    Dialog with extra window, message, entry widget, cancel and ok button.
    For detailed information check out the documentation.
    """

    def __init__(
        self,
        fg_color: Optional[Union[str, Tuple[str, str]]] = None,
        text_color: Optional[Union[str, Tuple[str, str]]] = None,
        button_fg_color: Optional[Union[str, Tuple[str, str]]] = None,
        button_hover_color: Optional[Union[str, Tuple[str, str]]] = None,
        button_text_color: Optional[Union[str, Tuple[str, str]]] = None,
        entry_fg_color: Optional[Union[str, Tuple[str, str]]] = None,
        entry_border_color: Optional[Union[str, Tuple[str, str]]] = None,
        entry_text_color: Optional[Union[str, Tuple[str, str]]] = None,
        title: str = "CTkDialog",
        font: Optional[Union[Tuple[int, str], ctk.CTkFont]] = None,
        label_text: str = "CTkDialog",
        entry_text: Optional[str] = None,
    ):
        super().__init__(fg_color=fg_color)

        self._fg_color = (
            ctk.ThemeManager.theme["CTkToplevel"]["fg_color"]
            if fg_color is None
            else self._check_color_type(fg_color)
        )
        self._text_color = (
            ctk.ThemeManager.theme["CTkLabel"]["text_color"]
            if text_color is None
            else self._check_color_type(button_hover_color)
        )
        self._button_fg_color = (
            ctk.ThemeManager.theme["CTkButton"]["fg_color"]
            if button_fg_color is None
            else self._check_color_type(button_fg_color)
        )
        self._button_hover_color = (
            ctk.ThemeManager.theme["CTkButton"]["hover_color"]
            if button_hover_color is None
            else self._check_color_type(button_hover_color)
        )
        self._button_text_color = (
            ctk.ThemeManager.theme["CTkButton"]["text_color"]
            if button_text_color is None
            else self._check_color_type(button_text_color)
        )
        self._entry_fg_color = (
            ctk.ThemeManager.theme["CTkEntry"]["fg_color"]
            if entry_fg_color is None
            else self._check_color_type(entry_fg_color)
        )
        self._entry_border_color = (
            ctk.ThemeManager.theme["CTkEntry"]["border_color"]
            if entry_border_color is None
            else self._check_color_type(entry_border_color)
        )
        self._entry_text_color = (
            ctk.ThemeManager.theme["CTkEntry"]["text_color"]
            if entry_text_color is None
            else self._check_color_type(entry_text_color)
        )

        self._user_input: Union[str, None] = None
        self._running: bool = False
        self._title = title
        self._label_text = label_text
        self._entry_text = entry_text
        self._font = font

        self.title(self._title)
        self.lift()  # lift window on top
        self.attributes("-topmost", True)  # stay on top
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.after(
            10, self._create_widgets
        )  # create widgets with slight delay, to avoid white flickering of background
        self.resizable(False, False)
        self.grab_set()  # make other windows not clickable

    def _create_widgets(self):
        self.grid_columnconfigure((0, 1), weight=1)
        self.rowconfigure(0, weight=1)

        self._label = ctk.CTkLabel(
            master=self,
            width=300,
            wraplength=300,
            fg_color="transparent",
            text_color=self._text_color,
            text=self._label_text,
            font=self._font,
        )
        self._label.grid(row=0, column=0, columnspan=2, padx=20, pady=20, sticky="ew")

        self._entry = ctk.CTkEntry(
            master=self,
            width=230,
            fg_color=self._entry_fg_color,
            border_color=self._entry_border_color,
            text_color=self._entry_text_color,
            font=self._font,
            textvariable=ctk.StringVar(self, self._entry_text),
        )
        self._entry.grid(
            row=1, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew"
        )

        self._ok_button = ctk.CTkButton(
            master=self,
            width=100,
            border_width=0,
            fg_color=self._button_fg_color,
            hover_color=self._button_hover_color,
            text_color=self._button_text_color,
            text="Ok",
            font=self._font,
            command=self._ok_event,
        )
        self._ok_button.grid(
            row=2, column=0, columnspan=1, padx=(20, 10), pady=(0, 20), sticky="ew"
        )

        self._cancel_button = ctk.CTkButton(
            master=self,
            width=100,
            border_width=0,
            fg_color=(Color.LIGHT_RED.value, Color.DARK_RED.value),
            hover_color=(
                Color.HOVER_LIGHT_RED.value,
                Color.HOVER_DARK_RED.value,
            ),
            text_color=self._button_text_color,
            text="Cancel",
            font=self._font,
            command=self._cancel_event,
        )
        self._cancel_button.grid(
            row=2, column=1, columnspan=1, padx=(10, 20), pady=(0, 20), sticky="ew"
        )

        # set focus to entry with slight delay, otherwise it won't work
        self.after(150, lambda: self._entry.focus())
        self._entry.bind("<Return>", self._ok_event)

    def _ok_event(self):
        self._user_input = self._entry.get()
        self.grab_release()
        self.destroy()

    def _on_closing(self):
        self.grab_release()
        self.destroy()

    def _cancel_event(self):
        self.grab_release()
        self.destroy()

    def get_input(self):
        self.master.wait_window(self)
        return self._user_input
