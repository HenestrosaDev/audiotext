from typing import Any

import customtkinter as ctk

from utils.i18n import _
from views.style import theme
from views.widgets.window import place_dialog


class ConfirmDialog(ctk.CTkToplevel):  # type: ignore[misc]
    """
    Modal dialog to confirm an action, with an option that changes what it does
    (e.g. whether to also delete some files), which is off by default.
    """

    def __init__(
        self,
        master: Any,
        title: str,
        message: str,
        confirm_text: str,
        option_text: str,
        option_hint: str = "",
    ) -> None:
        """
        :param option_text: The label of the checkbox of the option.
        :param option_hint: Shown below the option (e.g. where the files are).
        """
        super().__init__(master)
        # Shown by `place_dialog` once it's built, already in its place
        self.withdraw()
        self._result: bool | None = None

        self.title(title)
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text=message, font=theme.font(13), wraplength=400, justify=ctk.LEFT
        ).grid(row=0, column=0, padx=20, pady=(18, 12), sticky=ctk.W)

        self.chk_option = ctk.CTkCheckBox(self, text=option_text, font=theme.font(13))
        self.chk_option.grid(row=1, column=0, padx=20, sticky=ctk.W)
        if option_hint:
            ctk.CTkLabel(
                self,
                text=option_hint,
                font=theme.font(12),
                text_color=theme.HINT_TEXT,
                wraplength=370,
                justify=ctk.LEFT,
            ).grid(row=2, column=0, padx=(50, 20), pady=(2, 0), sticky=ctk.W)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=3, column=0, padx=20, pady=18, sticky=ctk.E)
        ctk.CTkButton(
            buttons,
            text=_("Cancel"),
            width=90,
            command=self._cancel,
            **theme.SECONDARY_BUTTON,
        ).grid(row=0, column=0, padx=(0, 8))
        self.btn_confirm = ctk.CTkButton(
            buttons,
            text=confirm_text,
            width=90,
            command=self._confirm,
            **theme.DANGER_BUTTON,
        )
        self.btn_confirm.grid(row=0, column=1)

        self.bind("<Escape>", lambda _event: self._cancel())
        self.after(50, self._focus)

    def _focus(self) -> None:
        if not self.winfo_exists():
            return
        self.lift()
        self.grab_set()
        self.btn_confirm.focus_set()

    def _confirm(self) -> None:
        self._result = bool(self.chk_option.get())
        self.grab_release()
        self.destroy()

    def _cancel(self) -> None:
        self.grab_release()
        self.destroy()

    def get_result(self) -> bool | None:
        """
        Waits until the dialog is closed.

        :return: Whether the option was checked, or None if it was cancelled.
        """
        place_dialog(self, self.master)
        self.master.wait_window(self)
        return self._result
