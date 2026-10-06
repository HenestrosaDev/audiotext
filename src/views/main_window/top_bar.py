from collections.abc import Callable
from functools import partial
from typing import Any

import customtkinter as ctk

from utils.enums import AudioSource
from utils.i18n import L_, _
from views.localization import localize
from views.style import icons, theme

STATUS_DURATION_MS = 6000
# Space between the status and the edges of its label
STATUS_PADDING = 10

# The sources of the top bar, in order. Both folder modes share the folder button
SOURCES = [
    (AudioSource.FILE, "file"),
    (AudioSource.YOUTUBE, "link"),
    (AudioSource.MIC, "mic"),
    (AudioSource.DIRECTORY, "folder"),
]


def source_button_label(source: AudioSource) -> str:
    return {
        AudioSource.FILE: _("File"),
        AudioSource.YOUTUBE: _("URL"),
        AudioSource.MIC: _("Microphone"),
        AudioSource.DIRECTORY: _("Folder"),
    }[source]


class TopBar(ctk.CTkFrame):  # type: ignore[misc]
    """
    Bar at the top of the window: the button that collapses the history, the
    buttons to start a transcription from each kind of source, the status of the
    app, the new version available, if any, and the preferences.
    """

    def __init__(
        self,
        master: Any,
        on_toggle_sidebar: Callable[[], None],
        on_source: Callable[[AudioSource], None],
        on_preferences: Callable[[], None],
    ) -> None:
        super().__init__(master, height=52, corner_radius=0, fg_color=theme.TOPBAR_BG)
        self.grid_propagate(False)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(3, weight=1)

        self.btn_sidebar = ctk.CTkButton(
            self,
            text="",
            width=34,
            height=32,
            image=icons.icon("sidebar", 20),
            command=on_toggle_sidebar,
            **theme.GHOST_BUTTON,
        )
        self.btn_sidebar.grid(row=0, column=0, padx=(10, 6))

        ctk.CTkFrame(self, width=1, height=24, fg_color=theme.DIVIDER).grid(
            row=0, column=1, padx=(4, 10)
        )

        frm_sources = ctk.CTkFrame(self, fg_color="transparent")
        frm_sources.grid(row=0, column=2, sticky=ctk.W)
        localize(
            ctk.CTkLabel(frm_sources, font=theme.font(12), text_color=theme.HINT_TEXT),
            text=L_("New transcription:"),
        ).grid(row=0, column=0, padx=(0, 8))

        self._source_buttons: dict[AudioSource, tuple[ctk.CTkButton, str]] = {}
        for idx, (source, icon_name) in enumerate(SOURCES):
            button = localize(
                ctk.CTkButton(
                    frm_sources,
                    image=icons.icon(icon_name, 17),
                    compound=ctk.LEFT,
                    width=0,
                    height=32,
                    corner_radius=8,
                    font=theme.font(13),
                    command=lambda source=source: on_source(source),
                    **theme.GHOST_BUTTON,
                ),
                text=partial(source_button_label, source),
            )
            button.grid(row=0, column=idx + 1, padx=2)
            self._source_buttons[source] = (button, icon_name)

        self._status_message = ""
        self._status_font = theme.font(12)
        self.lbl_status = ctk.CTkLabel(
            self,
            text="",
            font=self._status_font,
            text_color=theme.HINT_TEXT,
            anchor=ctk.E,
        )
        self.lbl_status.grid(row=0, column=3, padx=12, sticky=ctk.EW)
        # The bar only fits one line, so long messages are shortened
        self.lbl_status.bind("<Configure>", lambda _event: self._fit_status())
        self._status_after_id: str | None = None

        # Shown when a new version of the app is available
        self.btn_update = ctk.CTkButton(
            self,
            text="",
            image=icons.icon("import", 16, theme.ICON_ON_ACCENT),
            compound=ctk.LEFT,
            width=0,
            height=30,
            corner_radius=8,
            font=theme.font(12),
            **theme.PRIMARY_BUTTON,
        )
        self.btn_update.grid(row=0, column=4, padx=(0, 6))
        self.btn_update.grid_remove()

        ctk.CTkButton(
            self,
            text="",
            width=34,
            height=32,
            image=icons.icon("gear", 18),
            command=on_preferences,
            **theme.GHOST_BUTTON,
        ).grid(row=0, column=5, padx=(0, 10))

        ctk.CTkFrame(self, height=1, fg_color=theme.DIVIDER, corner_radius=0).place(
            relx=0, rely=1, relwidth=1, anchor=ctk.SW
        )

    def set_active_source(self, active: AudioSource | None) -> None:
        """Highlights the button of the source being set up, if any."""
        for source, (button, icon_name) in self._source_buttons.items():
            if source == active:
                button.configure(
                    fg_color=theme.ACCENT,
                    hover_color=theme.ACCENT_HOVER,
                    text_color=theme.ICON_ON_ACCENT,
                    image=icons.icon(icon_name, 17, theme.ICON_ON_ACCENT),
                )
            else:
                button.configure(
                    fg_color="transparent",
                    hover_color=theme.ROW_HOVER,
                    text_color=theme.TEXT,
                    image=icons.icon(icon_name, 17),
                )

    def show_update(self, version: str, on_click: Callable[[], Any]) -> None:
        """Shows the button that opens the page of a new version of the app."""
        self.btn_update.configure(command=on_click)
        localize(
            self.btn_update,
            text=lambda: _("Version {version} is available").format(version=version),
        )
        self.btn_update.grid()

    def show_status(
        self, message: str, is_error: bool = False, is_persistent: bool = False
    ) -> None:
        """Shows a message, which disappears after a while unless it's persistent."""
        if self._status_after_id:
            self.after_cancel(self._status_after_id)
            self._status_after_id = None

        self._status_message = message
        self.lbl_status.configure(
            text_color=theme.ERROR_TEXT if is_error else theme.HINT_TEXT
        )
        self._fit_status()
        if message and not is_persistent and not is_error:
            self._status_after_id = self.after(
                STATUS_DURATION_MS, lambda: self.show_status("", is_persistent=True)
            )

    def _fit_status(self) -> None:
        width = self.lbl_status.winfo_width() - STATUS_PADDING
        self.lbl_status.configure(
            text=theme.fit_text(self._status_message, self._status_font, width)
        )

    def destroy(self) -> None:
        if self._status_after_id:
            self.after_cancel(self._status_after_id)
        super().destroy()
