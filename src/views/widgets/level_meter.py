from typing import Any

import customtkinter as ctk

from utils.audio_utils import MIN_LEVEL_DBFS
from views.style import theme


class LevelMeter(ctk.CTkCanvas):  # type: ignore[misc]
    """
    Segmented level meter of the microphone, from `MIN_LEVEL_DBFS` to 0 dBFS:
    green for normal levels, yellow when loud and red when close to clipping. A
    marker keeps the peak level for a moment.
    """

    SEGMENTS = 40
    GAP = 2
    YELLOW_DBFS = -18
    RED_DBFS = -6
    PEAK_HOLD_UPDATES = 12

    COLORS = {
        "green": ("#34C759", "#30D158"),
        "yellow": ("#FFCC00", "#FFD60A"),
        "red": ("#FF3B30", "#FF453A"),
        "off": ("#E0E0E5", "#3A3A3F"),
    }

    def __init__(self, master: Any, height: int = 14, **kwargs: Any) -> None:
        super().__init__(master, height=height, highlightthickness=0, bd=0, **kwargs)
        self._dbfs = float(MIN_LEVEL_DBFS)
        self._peak_dbfs = float(MIN_LEVEL_DBFS)
        self._peak_hold = 0
        self.bind("<Configure>", lambda _event: self._draw())
        ctk.AppearanceModeTracker.add(self._on_appearance_change, self)

    def destroy(self) -> None:
        ctk.AppearanceModeTracker.remove(self._on_appearance_change)
        super().destroy()

    def set_level(self, dbfs: float) -> None:
        self._dbfs = max(min(dbfs, 0.0), float(MIN_LEVEL_DBFS))

        if self._dbfs >= self._peak_dbfs or self._peak_hold <= 0:
            self._peak_dbfs = self._dbfs
            self._peak_hold = self.PEAK_HOLD_UPDATES
        else:
            self._peak_hold -= 1

        self._draw()

    def reset(self) -> None:
        self._dbfs = self._peak_dbfs = float(MIN_LEVEL_DBFS)
        self._peak_hold = 0
        self._draw()

    def _on_appearance_change(self, _mode: str) -> None:
        self._draw()

    def _color(self, name: str) -> str:
        light, dark = self.COLORS[name]
        return dark if ctk.get_appearance_mode() == "Dark" else light

    def _draw(self) -> None:
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        if width <= 1:
            return

        bg_light, bg_dark = theme.CARD_BG
        self.configure(bg=bg_dark if ctk.get_appearance_mode() == "Dark" else bg_light)

        segment_width = (width - self.GAP * (self.SEGMENTS - 1)) / self.SEGMENTS
        lit = round((1 - self._dbfs / MIN_LEVEL_DBFS) * self.SEGMENTS)
        peak = round((1 - self._peak_dbfs / MIN_LEVEL_DBFS) * self.SEGMENTS) - 1

        for idx in range(self.SEGMENTS):
            segment_dbfs = MIN_LEVEL_DBFS * (1 - (idx + 1) / self.SEGMENTS)
            if segment_dbfs >= self.RED_DBFS:
                color = "red"
            elif segment_dbfs >= self.YELLOW_DBFS:
                color = "yellow"
            else:
                color = "green"

            if idx >= lit and idx != peak:
                color = "off"

            x = idx * (segment_width + self.GAP)
            self.create_rectangle(
                x, 0, x + segment_width, height, fill=self._color(color), width=0
            )
