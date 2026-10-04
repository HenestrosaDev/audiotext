from typing import Any

import customtkinter as ctk

from models.config.config_system import ConfigSystem
from utils.config_manager import ConfigManager
from views.widgets.splitter import Splitter

# Sizes, in pixels, kept for the video and the text when resizing them
VIDEO_MIN_SIZE = 120
LANDSCAPE_TEXT_MIN_HEIGHT = 200
PORTRAIT_TEXT_MIN_WIDTH = 340
SPLITTER_THICKNESS = 16


class MediaLayout:
    """
    Places the video and the text in their frame, with a handle between them to
    resize them: the video above the text if it's landscape, or on its left if
    it's portrait (e.g. phone recordings). The size chosen for the video is kept
    in the configuration.
    """

    def __init__(
        self, body: Any, video: Any, text_pane: Any, config: ConfigSystem
    ) -> None:
        """
        :param body: The frame that contains the video and the text.
        :param config: The sizes of the video, changed in place when resized.
        """
        self._body = body
        self._video = video
        self._text_pane = text_pane
        self._config = config
        self._splitter: Splitter | None = None
        self.has_video = False
        self.is_portrait = False
        body.bind("<Configure>", lambda _event: self.apply_size())

    def show_video(self, is_portrait: bool) -> None:
        self.has_video = True
        self.is_portrait = is_portrait
        self.layout()

    def layout(self) -> None:
        """
        Places the video above the text if it's landscape, or on its left if it's
        portrait (e.g. phone recordings).
        """
        for idx in range(3):
            self._body.grid_columnconfigure(idx, weight=0, minsize=0)
            self._body.grid_rowconfigure(idx, weight=0, minsize=0)
        self._video.grid_forget()
        self._text_pane.grid_forget()
        if self._splitter is not None:
            self._splitter.destroy()
            self._splitter = None

        if not self.has_video:
            self._body.grid_columnconfigure(0, weight=1)
            self._body.grid_rowconfigure(0, weight=1)
            self._text_pane.grid(row=0, column=0, sticky=ctk.NSEW)
            return

        self._splitter = Splitter(
            self._body,
            is_vertical=self.is_portrait,
            on_drag=self._on_splitter_drag,
            on_release=self._save_video_ratio,
            on_reset=self._reset_video_ratio,
            thickness=SPLITTER_THICKNESS,
        )
        self._video.grid(row=0, column=0, sticky=ctk.NSEW)
        if self.is_portrait:
            self._body.grid_rowconfigure(0, weight=1)
            self._body.grid_columnconfigure(2, weight=1)
            self._splitter.grid(row=0, column=1, sticky=ctk.NS)
            self._text_pane.grid(row=0, column=2, sticky=ctk.NSEW)
        else:
            self._body.grid_columnconfigure(0, weight=1)
            self._body.grid_rowconfigure(2, weight=1)
            self._splitter.grid(row=1, column=0, sticky=ctk.EW)
            self._text_pane.grid(row=2, column=0, sticky=ctk.NSEW)
        self.apply_size()

    @property
    def _video_ratio(self) -> float:
        config = self._config
        if self.is_portrait:
            return config.portrait_video_ratio
        return config.landscape_video_ratio

    @_video_ratio.setter
    def _video_ratio(self, ratio: float) -> None:
        ratio = min(max(ratio, 0.05), 0.95)
        if self.is_portrait:
            self._config.portrait_video_ratio = ratio
        else:
            self._config.landscape_video_ratio = ratio

    def _video_space(self) -> tuple[int, int]:
        """:return: The space of the body to share, and the part kept for the text."""
        if self.is_portrait:
            total, text_min = self._body.winfo_width(), PORTRAIT_TEXT_MIN_WIDTH
        else:
            total, text_min = self._body.winfo_height(), LANDSCAPE_TEXT_MIN_HEIGHT
        return max(total - SPLITTER_THICKNESS, 0), text_min

    def apply_size(self) -> None:
        """Sizes the video according to the ratio chosen by the user."""
        if not self.has_video:
            return
        available, text_min = self._video_space()
        if available <= 1:
            return
        size = round(available * self._video_ratio)
        size = max(min(size, available - text_min), VIDEO_MIN_SIZE)
        if self.is_portrait:
            self._body.grid_columnconfigure(0, minsize=size)
        else:
            self._body.grid_rowconfigure(0, minsize=size)

    def _on_splitter_drag(self, pointer: int) -> None:
        available, _text_min = self._video_space()
        if available <= 1:
            return
        if self.is_portrait:
            offset = pointer - self._body.winfo_rootx()
        else:
            offset = pointer - self._body.winfo_rooty()
        self._video_ratio = (offset - SPLITTER_THICKNESS / 2) / available
        self.apply_size()

    def _save_video_ratio(self) -> None:
        key = (
            ConfigSystem.Key.PORTRAIT_VIDEO_RATIO
            if self.is_portrait
            else ConfigSystem.Key.LANDSCAPE_VIDEO_RATIO
        )
        ConfigManager.modify_value(
            ConfigSystem.Key.SECTION, key, f"{self._video_ratio:.3f}"
        )

    def _reset_video_ratio(self) -> None:
        defaults = ConfigSystem(appearance_mode="")
        self._video_ratio = (
            defaults.portrait_video_ratio
            if self.is_portrait
            else defaults.landscape_video_ratio
        )
        self.apply_size()
        self._save_video_ratio()
