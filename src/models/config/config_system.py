from dataclasses import dataclass
from enum import Enum


@dataclass
class ConfigSystem:
    appearance_mode: str
    # Added in later versions, so they have a default for older `config.ini` files
    ui_language: str = "system"
    is_sidebar_collapsed: bool = False
    sidebar_width: int = 290
    # Part of the transcription view taken by the video: its height when the
    # video is landscape (shown above the text), its width when it's portrait
    landscape_video_ratio: float = 0.45
    portrait_video_ratio: float = 0.4
    # Subtitles shown over the video of a transcription
    show_subtitles: bool = False
    subtitle_size: str = "medium"
    subtitle_position: str = "bottom"
    subtitle_style: str = "background"
    # Size and position of the window when it was closed, as a Tk geometry
    # (e.g. "1280x820+100+50"), and whether it was maximized. The window is
    # maximized the first time the app is opened
    window_geometry: str = ""
    is_window_maximized: bool = True
    # Whether to show a notification of the system when a transcription is ready
    notify_when_done: bool = True
    # Whether to check if a new version is available when the app opens
    check_for_updates: bool = True

    class Key(Enum):
        """
        Enum class for keys associated with the system configuration.
        """

        SECTION = "system"
        APPEARANCE_MODE = "appearance_mode"
        UI_LANGUAGE = "ui_language"
        IS_SIDEBAR_COLLAPSED = "is_sidebar_collapsed"
        SIDEBAR_WIDTH = "sidebar_width"
        LANDSCAPE_VIDEO_RATIO = "landscape_video_ratio"
        PORTRAIT_VIDEO_RATIO = "portrait_video_ratio"
        SHOW_SUBTITLES = "show_subtitles"
        SUBTITLE_SIZE = "subtitle_size"
        SUBTITLE_POSITION = "subtitle_position"
        SUBTITLE_STYLE = "subtitle_style"
        WINDOW_GEOMETRY = "window_geometry"
        IS_WINDOW_MAXIMIZED = "is_window_maximized"
        NOTIFY_WHEN_DONE = "notify_when_done"
        CHECK_FOR_UPDATES = "check_for_updates"
