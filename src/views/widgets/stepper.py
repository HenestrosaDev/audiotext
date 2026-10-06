from enum import Enum
from typing import Any

import customtkinter as ctk

from views.localization import Text, localize
from views.style import icons, theme


class StepState(Enum):
    DONE = "done"
    CURRENT = "current"
    UPCOMING = "upcoming"
    ERROR = "error"


class Stepper(ctk.CTkFrame):  # type: ignore[misc]
    """
    Shows the steps of a process as numbered circles joined by lines, marking the
    completed steps with a check and highlighting the current one.
    """

    CIRCLE_SIZE = 26

    def __init__(self, master: Any, steps: list[Text], **kwargs: Any) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self._circles: list[ctk.CTkLabel] = []
        self._labels: list[ctk.CTkLabel] = []
        self._connectors: list[ctk.CTkFrame] = []

        for idx, step in enumerate(steps):
            column = idx * 2
            if idx > 0:
                connector = ctk.CTkFrame(self, height=2, fg_color=theme.DIVIDER)
                connector.grid(row=0, column=column - 1, sticky=ctk.EW, padx=8)
                self.grid_columnconfigure(column - 1, weight=1, minsize=24)
                self._connectors.append(connector)

            step_frame = ctk.CTkFrame(self, fg_color="transparent")
            step_frame.grid(row=0, column=column)

            circle = ctk.CTkLabel(
                step_frame,
                text=str(idx + 1),
                width=self.CIRCLE_SIZE,
                height=self.CIRCLE_SIZE,
                corner_radius=self.CIRCLE_SIZE // 2,
                font=theme.font(12, "bold"),
            )
            circle.grid(row=0, column=0)
            label = localize(ctk.CTkLabel(step_frame, font=theme.font(13)), text=step)
            label.grid(row=0, column=1, padx=(8, 0))

            self._circles.append(circle)
            self._labels.append(label)

        self.set_current(0)

    def set_steps(self, steps: list[Text]) -> None:
        """Renames the steps, which must be as many as before."""
        for label, step in zip(self._labels, steps, strict=True):
            localize(label, text=step)

    def set_current(self, current: int, is_error: bool = False) -> None:
        """
        Marks the steps before `current` as done.

        :param current: The index of the current step. If it's the number of
                        steps, all of them are done.
        :param is_error: Whether the current step has failed.
        """
        for idx in range(len(self._circles)):
            if idx < current:
                state = StepState.DONE
            elif idx == current:
                state = StepState.ERROR if is_error else StepState.CURRENT
            else:
                state = StepState.UPCOMING
            self._set_state(idx, state)

        for idx, connector in enumerate(self._connectors):
            connector.configure(
                fg_color=theme.ACCENT if idx < current else theme.DIVIDER
            )

    def _set_state(self, idx: int, state: StepState) -> None:
        circle, label = self._circles[idx], self._labels[idx]

        if state == StepState.DONE:
            circle.configure(
                text="",
                image=icons.icon("check", 14, theme.ICON_ON_ACCENT),
                fg_color=theme.ACCENT,
            )
            label.configure(text_color=theme.TEXT, font=theme.font(13))
            return

        # CTkLabel ignores `image=None`, so the check of a previous run would stay
        # next to the number unless the inner Tk label is cleared.
        circle._label.configure(image="")  # noqa: SLF001

        if state in (StepState.CURRENT, StepState.ERROR):
            color = theme.DANGER if state == StepState.ERROR else theme.ACCENT
            circle.configure(
                text=str(idx + 1),
                image=None,
                fg_color=color,
                text_color=theme.ICON_ON_ACCENT,
            )
            label.configure(text_color=theme.TEXT, font=theme.font(13, "bold"))
        else:
            circle.configure(
                text=str(idx + 1),
                image=None,
                fg_color=theme.SUBTLE_BG,
                text_color=theme.HINT_TEXT,
            )
            label.configure(text_color=theme.HINT_TEXT, font=theme.font(13))
