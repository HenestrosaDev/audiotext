import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import customtkinter as ctk
from PIL import Image, ImageTk

from models.config.config_system import ConfigSystem, SubtitleTrack
from utils.config_manager import ConfigManager
from utils.i18n import _
from utils.media import VideoFrameSource
from utils.subtitle_cues import CueTrack

# Height of the subtitles shown over the video, relative to its shorter side
SUBTITLE_SIZES = {"small": 0.045, "medium": 0.06, "large": 0.08}
SUBTITLE_MIN_FONT_SIZE = 11
SUBTITLE_BACKGROUND = "background"
SUBTITLE_OUTLINE = "outline"
SUBTITLE_BACKGROUND_OPACITY = 0.6


class VideoPane(ctk.CTkFrame):  # type: ignore[misc]
    """
    Shows the frames of a video, fitted to its size, with the subtitles drawn over
    them as the user configures them (size, position and style). The subtitles
    show the transcription, or its translation if the user chooses it.
    """

    def __init__(
        self,
        master: Any,
        config_system: ConfigSystem,
        cue_track: CueTrack,
        on_click: Callable[[], None],
        on_subtitles_change: Callable[[], None],
    ) -> None:
        """
        :param cue_track: The subtitles of the transcription.
        :param config_system: The settings of the subtitles, which are changed in
                              place when the user changes them.
        :param on_subtitles_change: Called when the subtitles are shown or hidden.
        """
        # Its size is set by the layout of its parent, so it requests little
        super().__init__(
            master, width=10, height=10, fg_color="#000000", corner_radius=12
        )
        self._config = config_system
        self._cue_track = cue_track
        # The subtitles of the translation, if any, and the name of its language
        self._translation_track: CueTrack | None = None
        self._translation_language = ""
        self._on_subtitles_change = on_subtitles_change
        self._source: VideoFrameSource | None = None
        self._frame_number = -1
        self._photo: ImageTk.PhotoImage | None = None
        self._photo_size: tuple[int, int] = (0, 0)
        self._position = 0.0
        self._subtitle_text = ""
        # Area of the video darkened behind the subtitles
        self._subtitle_box: tuple[int, int, int, int] | None = None
        # The variables of the open options menu, which Tkinter needs to be kept
        self._menu_variables: list[tk.Variable] = []

        # A canvas, so the subtitles can be drawn over the frames
        self.cnv_video = tk.Canvas(
            self,
            width=1,
            height=1,
            bg="#000000",
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self.cnv_video.place(relx=0.5, rely=0.5, anchor=ctk.CENTER)
        self._video_item = self.cnv_video.create_image(0, 0, anchor=tk.NW)
        # The outline of the subtitles is drawn as copies of the text around it
        self._outline_items = [
            self.cnv_video.create_text(0, 0, fill="#000000", state=tk.HIDDEN)
            for _idx in range(8)
        ]
        self._subtitle_item = self.cnv_video.create_text(
            0, 0, fill="#FFFFFF", state=tk.HIDDEN
        )
        self._subtitle_font = tkfont.Font(
            family=ctk.CTkFont().cget("family"), size=-16, weight="bold"
        )
        self.cnv_video.bind("<Button-1>", lambda _event: on_click())
        self.bind("<Button-1>", lambda _event: on_click())
        self.bind("<Configure>", lambda _event: self.draw_frame(force=True))

    def destroy(self) -> None:
        self.close()
        super().destroy()

    # PUBLIC METHODS

    def open(self, media_path: Path) -> None:
        """
        Opens the video, whose first frame is shown when it's decoded.

        :raises OSError: If the video can't be opened.
        """
        self._source = VideoFrameSource(media_path)
        self._source.request(0)

    def close(self) -> None:
        if self._source:
            self._source.close()
            self._source = None

    @property
    def has_subtitles(self) -> bool:
        return bool(self._cue_track.cues) or self.has_translation_subtitles

    @property
    def has_translation_subtitles(self) -> bool:
        return bool(self._translation_track and self._translation_track.cues)

    @property
    def is_showing_subtitles(self) -> bool:
        return self._config.show_subtitles

    @property
    def is_showing_translation(self) -> bool:
        """Whether the subtitles show the translation, if they're shown."""
        return (
            self.has_translation_subtitles
            and self._config.subtitle_track == SubtitleTrack.TRANSLATION.value
        )

    def set_cue_track(self, cue_track: CueTrack) -> None:
        self._cue_track = cue_track
        self._update_subtitle(force=True)

    def set_translation_track(self, cue_track: CueTrack | None, language: str) -> None:
        """
        :param cue_track: The subtitles of the translation, or None if there is
                          none.
        :param language: The name of the language of the translation.
        """
        self._translation_track = cue_track
        self._translation_language = language
        self._update_subtitle(force=True)

    def show_translation(self, is_translation: bool) -> None:
        """Shows the subtitles of the translation, or the ones of the original."""
        track = SubtitleTrack.TRANSLATION if is_translation else SubtitleTrack.ORIGINAL
        self._set_option(ConfigSystem.Key.SUBTITLE_TRACK, "subtitle_track", track.value)
        # Choosing the text of the subtitles shows them
        if not self._config.show_subtitles:
            self.toggle_subtitles()

    def show_position(self, position: float) -> None:
        """Shows the frame and the subtitle at the position of the playback."""
        self._position = position
        if self._source is None:
            return
        self._source.request(position)
        self._update_subtitle()
        self.draw_frame()

    def draw_frame(self, force: bool = False) -> None:
        """Draws the last decoded frame, if it changed or `force` is True."""
        if self._source is None:
            return
        frame_number = self._source.frame_number
        if frame_number == self._frame_number and not force:
            return
        source = self._source.latest_frame
        if source is None:
            return
        self._frame_number = frame_number

        box_width = max(self.winfo_width() - 8, 2)
        box_height = max(self.winfo_height() - 8, 2)
        scale = min(box_width / source.width, box_height / source.height)
        size = (max(int(source.width * scale), 1), max(int(source.height * scale), 1))
        image = (
            source.resize(size, Image.Resampling.BILINEAR)
            if size != source.size
            else source
        )

        if self._photo_size != size:
            self._photo_size = size
            self.cnv_video.configure(width=size[0], height=size[1])
            self._layout_subtitle()

        if self._subtitle_box:
            if image is source:
                image = image.copy()
            region = image.crop(self._subtitle_box)
            shade = Image.new(region.mode, region.size)
            image.paste(
                Image.blend(region, shade, SUBTITLE_BACKGROUND_OPACITY),
                self._subtitle_box[:2],
            )

        if self._photo is None or (self._photo.width(), self._photo.height()) != size:
            self._photo = ImageTk.PhotoImage(image)
            self.cnv_video.itemconfigure(self._video_item, image=self._photo)
        else:
            self._photo.paste(image)

    # SUBTITLES

    def toggle_subtitles(self) -> None:
        self._set_option(
            ConfigSystem.Key.SHOW_SUBTITLES,
            "show_subtitles",
            not self._config.show_subtitles,
        )

    def show_subtitle_menu(self, anchor: Any) -> None:
        """Shows the options of the subtitles below the given widget."""
        config = self._config
        menu = tk.Menu(self, tearoff=False)
        variables: list[tk.Variable] = []

        is_shown = tk.BooleanVar(menu, config.show_subtitles)
        variables.append(is_shown)
        menu.add_checkbutton(
            label=_("Show subtitles on the video"),
            variable=is_shown,
            command=self.toggle_subtitles,
        )
        menu.add_separator()

        if self.has_translation_subtitles:
            track = tk.StringVar(
                menu,
                SubtitleTrack.TRANSLATION.value
                if self.is_showing_translation
                else SubtitleTrack.ORIGINAL.value,
            )
            variables.append(track)
            menu.add_radiobutton(
                label=_("Transcription"),
                value=SubtitleTrack.ORIGINAL.value,
                variable=track,
                command=lambda: self.show_translation(False),
            )
            menu.add_radiobutton(
                label=_("Translation into {language}").format(
                    language=self._translation_language
                ),
                value=SubtitleTrack.TRANSLATION.value,
                variable=track,
                command=lambda: self.show_translation(True),
            )
            menu.add_separator()

        choices = [
            (
                _("Size"),
                ConfigSystem.Key.SUBTITLE_SIZE,
                "subtitle_size",
                [
                    ("small", _("Small")),
                    ("medium", _("Medium")),
                    ("large", _("Large")),
                ],
            ),
            (
                _("Position"),
                ConfigSystem.Key.SUBTITLE_POSITION,
                "subtitle_position",
                [("bottom", _("Bottom")), ("top", _("Top"))],
            ),
            (
                _("Style"),
                ConfigSystem.Key.SUBTITLE_STYLE,
                "subtitle_style",
                [
                    (SUBTITLE_BACKGROUND, _("Dark background")),
                    (SUBTITLE_OUTLINE, _("Outline")),
                ],
            ),
        ]
        for title, key, name, options in choices:
            submenu = tk.Menu(menu, tearoff=False)
            variable = tk.StringVar(menu, getattr(config, name))
            variables.append(variable)
            for value, label in options:
                submenu.add_radiobutton(
                    label=label,
                    value=value,
                    variable=variable,
                    command=partial(self._set_option, key, name, value),
                )
            menu.add_cascade(label=title, menu=submenu)

        self._menu_variables = variables
        try:
            menu.tk_popup(
                anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height() + 2
            )
        finally:
            menu.grab_release()

    def _set_option(self, key: ConfigSystem.Key, name: str, value: Any) -> None:
        setattr(self._config, name, value)
        ConfigManager.modify_value(ConfigSystem.Key.SECTION, key, str(value))
        self._on_subtitles_change()
        self._update_subtitle(force=True)

    def _update_subtitle(self, force: bool = False) -> None:
        track = (
            self._translation_track
            if self._translation_track and self.is_showing_translation
            else self._cue_track
        )
        cue = track.at(self._position)
        text = cue.text if cue and self._config.show_subtitles else ""
        if text != self._subtitle_text or force:
            self._subtitle_text = text
            self._layout_subtitle()
            self.draw_frame(force=True)

    def _layout_subtitle(self) -> None:
        """Places the subtitle over the video, as the user configured it."""
        canvas = self.cnv_video
        width, height = self._photo_size
        items = [self._subtitle_item, *self._outline_items]
        self._subtitle_box = None
        if not self._subtitle_text or width < 2:
            for item in items:
                canvas.itemconfigure(item, state=tk.HIDDEN)
            return

        config = self._config
        relative_size = SUBTITLE_SIZES.get(
            config.subtitle_size, SUBTITLE_SIZES["medium"]
        )
        font_size = max(
            round(min(width, height) * relative_size), SUBTITLE_MIN_FONT_SIZE
        )
        self._subtitle_font.configure(size=-font_size)

        is_top = config.subtitle_position == "top"
        margin = max(round(height * 0.05), 6)
        x = width / 2
        y = margin if is_top else height - margin
        options: dict[str, Any] = {
            "text": self._subtitle_text,
            "font": self._subtitle_font,
            "width": round(width * 0.86),
            "anchor": tk.N if is_top else tk.S,
            "justify": tk.CENTER,
        }

        is_outline = config.subtitle_style == SUBTITLE_OUTLINE
        offset = max(round(font_size / 16), 1)
        offsets = [
            (dx * offset, dy * offset)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            if dx or dy
        ]
        for item, (dx, dy) in zip(self._outline_items, offsets, strict=True):
            canvas.coords(item, x + dx, y + dy)
            canvas.itemconfigure(
                item, state=tk.NORMAL if is_outline else tk.HIDDEN, **options
            )
        canvas.coords(self._subtitle_item, x, y)
        canvas.itemconfigure(self._subtitle_item, state=tk.NORMAL, **options)
        canvas.tag_raise(self._subtitle_item)

        if not is_outline:
            left, top, right, bottom = canvas.bbox(self._subtitle_item)
            padding_x, padding_y = round(font_size * 0.4), round(font_size * 0.15)
            self._subtitle_box = (
                max(left - padding_x, 0),
                max(top - padding_y, 0),
                min(right + padding_x, width),
                min(bottom + padding_y, height),
            )
