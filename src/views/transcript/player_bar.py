import logging
import threading
from collections.abc import Callable
from typing import Any

import customtkinter as ctk
import numpy as np

from utils.audio_player import AudioPlayer, PlaybackUnavailableError
from utils.i18n import L_, _
from utils.time_format import format_timestamp
from views.localization import Text, localize
from views.style import icons, theme
from views.widgets.option_menu import CTkOptionMenu

logger = logging.getLogger(__name__)

AUDIO_REFRESH_INTERVAL_MS = 100
VIDEO_REFRESH_INTERVAL_MS = 33
SEEK_STEP_SECONDS = 5
SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]

# Called on each refresh with the position of the playback and whether it's playing
TickCallback = Callable[[float, bool], None]


def format_speed(speed: float) -> str:
    return f"{speed:g}×"


class PlayerBar(ctk.CTkFrame):  # type: ignore[misc]
    """
    The controls of the audio of a transcription: play/pause, the position, the
    speed and, for videos, the subtitles. While playing, it reports the position
    to the owner to follow it in the text and the video.
    """

    def __init__(
        self,
        master: Any,
        on_tick: TickCallback,
        on_toggle_subtitles: Callable[[], None],
        on_subtitle_menu: Callable[[Any], None],
    ) -> None:
        """
        :param on_subtitle_menu: Called with the button below which the options of
                                 the subtitles are shown.
        """
        super().__init__(master, fg_color="transparent")
        self._on_tick = on_tick
        self._player: AudioPlayer | None = None
        self._is_video = False
        self._is_dragging_slider = False
        # Whether the audio was playing when the slider was pressed, to resume it
        # once it's released
        self._was_playing_before_drag = False
        self._refresh_after_id: str | None = None
        self._speed_change_thread: threading.Thread | None = None
        self._speed_change_error: Exception | None = None

        self.grid_columnconfigure(0, weight=1)
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=0, column=0, padx=28, pady=(12, 4), sticky=ctk.EW)
        controls.grid_columnconfigure(2, weight=1)

        self.btn_play = ctk.CTkButton(
            controls,
            text="",
            width=40,
            height=40,
            corner_radius=20,
            image=icons.icon("play", 16, theme.ICON_ON_ACCENT),
            command=self.toggle_playback,
        )
        self.btn_play.grid(row=0, column=0)
        self.lbl_time = ctk.CTkLabel(
            controls,
            text="--:-- / --:--",
            font=theme.font(13, family=theme.MONOSPACE_FAMILY),
        )
        self.lbl_time.grid(row=0, column=1, padx=12)
        self.sld_position = ctk.CTkSlider(
            controls, from_=0, to=1, command=self._on_slider_drag
        )
        self.sld_position.set(0)
        self.sld_position.grid(row=0, column=2, sticky=ctk.EW)
        self.sld_position.bind("<Button-1>", self._on_slider_press, add="+")
        self.sld_position.bind("<ButtonRelease-1>", self._on_slider_release, add="+")
        self.omn_speed = CTkOptionMenu(
            controls,
            values=[format_speed(speed) for speed in SPEEDS],
            width=74,
            command=self._on_speed_change,
        )
        self.omn_speed.set(format_speed(1.0))
        self.omn_speed.grid(row=0, column=5, padx=(12, 0))

        # Subtitles over the video, shown once a video is loaded
        self.btn_subtitles = localize(
            ctk.CTkButton(
                controls,
                image=icons.icon("subtitles", 15),
                compound=ctk.LEFT,
                width=0,
                height=28,
                command=on_toggle_subtitles,
                **theme.SECONDARY_BUTTON,
            ),
            text=L_("Subtitles"),
        )
        self.btn_subtitle_options = ctk.CTkButton(
            controls,
            text="",
            image=icons.icon("chevron_down", 11),
            width=24,
            height=28,
            **theme.GHOST_BUTTON,
        )
        self.btn_subtitle_options.configure(
            command=lambda: on_subtitle_menu(self.btn_subtitle_options)
        )

        self.lbl_hint = localize(
            ctk.CTkLabel(
                self, font=theme.font(12), text_color=theme.HINT_TEXT, anchor=ctk.W
            ),
            text=L_("Loading the audio…"),
        )
        self.lbl_hint.grid(row=1, column=0, padx=30, pady=(0, 14), sticky=ctk.EW)
        self._set_enabled(False)

    def destroy(self) -> None:
        if self._refresh_after_id:
            self.after_cancel(self._refresh_after_id)
            self._refresh_after_id = None
        if self._player:
            self._player.close()
        super().destroy()

    # PUBLIC METHODS

    @property
    def position(self) -> float:
        return self._player.position if self._player else 0.0

    def load(self, samples: np.ndarray, sample_rate: int, is_video: bool) -> None:
        """Prepares the audio to be played."""
        self._player = AudioPlayer(samples, sample_rate)
        self._is_video = is_video
        self.sld_position.configure(to=max(self._player.duration, 0.01))
        self._set_enabled(True)
        self.lbl_hint.configure(text_color=theme.HINT_TEXT)
        localize(
            self.lbl_hint,
            text=lambda: _("Space: play/pause · ←/→: {seconds} s back/forward").format(
                seconds=SEEK_STEP_SECONDS
            ),
        )
        self.refresh()

    def show_error(self, message: Text) -> None:
        self.lbl_hint.configure(text_color=theme.ERROR_TEXT)
        localize(self.lbl_hint, text=message)

    def show_subtitle_buttons(self, is_on: bool) -> None:
        self.btn_subtitles.grid(row=0, column=3, padx=(12, 0))
        self.btn_subtitle_options.grid(row=0, column=4, padx=(2, 0))
        self.set_subtitles_on(is_on)

    def set_subtitles_on(self, is_on: bool) -> None:
        self.btn_subtitles.configure(
            fg_color=theme.ROW_SELECTED if is_on else "transparent",
            image=icons.icon(
                "subtitles", 15, theme.ACCENT_TEXT if is_on else theme.ICON
            ),
        )

    def toggle_playback(self) -> None:
        if self._player is None:
            return
        try:
            self._player.toggle()
        except PlaybackUnavailableError as e:
            self._disable(e)
        self.refresh()

    def seek_relative(self, seconds: float) -> None:
        if self._player is None:
            return
        self._player.seek(self._player.position + seconds)
        self.refresh()

    def play_from(self, seconds: float) -> None:
        if self._player is None:
            return
        self._player.seek(seconds)
        try:
            self._player.play()
        except PlaybackUnavailableError as e:
            self._disable(e)
        self.refresh()

    def handle_key(self, key: str) -> bool:
        """Handles the playback shortcuts. :return: Whether the key was handled."""
        if key == "space":
            self.toggle_playback()
        elif key == "Left":
            self.seek_relative(-SEEK_STEP_SECONDS)
        elif key == "Right":
            self.seek_relative(SEEK_STEP_SECONDS)
        else:
            return False
        return True

    def refresh(self) -> None:
        """Shows the position and reports it, and does it again after a while."""
        if self._refresh_after_id:
            self.after_cancel(self._refresh_after_id)
            self._refresh_after_id = None
        if self._player is None:
            return

        self._check_speed_change()
        position = self._player.position
        is_playing = self._player.is_playing

        self.btn_play.configure(
            image=icons.icon(
                "pause" if is_playing else "play", 16, theme.ICON_ON_ACCENT
            )
        )
        self.lbl_time.configure(
            text=f"{format_timestamp(position)} / "
            f"{format_timestamp(self._player.duration)}"
        )
        if not self._is_dragging_slider:
            self.sld_position.set(position)

        self._on_tick(position, is_playing)

        interval = (
            VIDEO_REFRESH_INTERVAL_MS if self._is_video else AUDIO_REFRESH_INTERVAL_MS
        )
        self._refresh_after_id = self.after(interval, self.refresh)

    # HELPERS

    def _set_enabled(self, is_enabled: bool) -> None:
        state = ctk.NORMAL if is_enabled else ctk.DISABLED
        for widget in (self.btn_play, self.sld_position, self.omn_speed):
            widget.configure(state=state)

    def _disable(self, error: Exception) -> None:
        logger.error("Could not play the audio", exc_info=error)
        self._set_enabled(False)
        self.show_error(
            lambda: _("The audio can't be played: {error}").format(error=error)
        )

    def _check_speed_change(self) -> None:
        thread = self._speed_change_thread
        if thread is None or thread.is_alive() or self._player is None:
            return
        self._speed_change_thread = None
        self.omn_speed.set(format_speed(self._player.speed))
        if self._speed_change_error:
            if isinstance(self._speed_change_error, PlaybackUnavailableError):
                self._disable(self._speed_change_error)
                return
            logger.error(
                "Could not change the speed", exc_info=self._speed_change_error
            )
            self._speed_change_error = None
        self.omn_speed.configure(state=ctk.NORMAL)

    # EVENT HANDLERS

    def _on_slider_press(self, _event: Any) -> None:
        if self._player is None or self._is_dragging_slider:
            return
        self._is_dragging_slider = True
        # Paused while dragging, so the position and the frame follow the slider
        # without playing the audio
        self._was_playing_before_drag = self._player.is_playing
        self._player.pause()
        self.refresh()

    def _on_slider_drag(self, value: float) -> None:
        if self._player is None:
            return
        self._player.seek(value)
        self.refresh()

    def _on_slider_release(self, _event: Any) -> None:
        if self._player is None or not self._is_dragging_slider:
            return
        self._is_dragging_slider = False
        self._player.seek(self.sld_position.get())
        if self._was_playing_before_drag:
            try:
                self._player.play()
            except PlaybackUnavailableError as e:
                self._disable(e)
        self.refresh()

    def _on_speed_change(self, label: str) -> None:
        if self._player is None:
            return
        speed = SPEEDS[[format_speed(s) for s in SPEEDS].index(label)]
        if speed == self._player.speed or self._speed_change_thread is not None:
            return
        self.omn_speed.configure(state=ctk.DISABLED)
        player = self._player

        # Changing the speed resamples the audio, which takes a while
        def change_speed() -> None:
            try:
                player.set_speed(speed)
            except Exception as e:
                self._speed_change_error = e

        self._speed_change_thread = threading.Thread(target=change_speed, daemon=True)
        self._speed_change_thread.start()
