from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from models.review import Review, ReviewState
from utils.i18n import L_, _
from views.localization import Text, localize
from views.style import icons, theme
from views.transcript.transcript_text import LOW_CONFIDENCE_COLOR
from views.widgets.button import icon_button, set_button_state

BAR_HEIGHT = 40


class ReviewBar(ctk.CTkFrame):  # type: ignore[misc]
    """
    The review of the low confidence words of the transcript, above it: how many
    are left to review, and the buttons to go through them. It shows each state of
    the review (see `ReviewState`), keeping its height so it doesn't jump while
    the threshold changes.
    """

    def __init__(
        self,
        master: Any,
        on_previous: Callable[[], None],
        on_next: Callable[[], None],
        on_enable: Callable[[], None],
        on_adjust_threshold: Callable[[Any], None],
        on_review_again: Callable[[], None],
        previous_tooltip: Text,
        next_tooltip: Text,
    ) -> None:
        """
        :param on_enable: Turns the highlighting of the low confidence words on.
        :param on_adjust_threshold: Shows the thresholds below the widget given.
        :param on_review_again: Forgets which words were reviewed.
        """
        super().__init__(
            master,
            fg_color=theme.SUBTLE_BG,
            border_color=theme.CARD_BORDER,
            border_width=1,
            corner_radius=10,
            height=BAR_HEIGHT,
        )
        self._review = Review(ReviewState.NO_DATA)
        self._on_adjust_threshold = on_adjust_threshold
        self.grid_columnconfigure(3, weight=1)

        self.lbl_icon = ctk.CTkLabel(self, text="", width=18)
        self.lbl_status = localize(
            ctk.CTkLabel(self, anchor=ctk.W, height=BAR_HEIGHT - 8),
            text=self._status_text,
        )
        self.frm_arrows = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_previous = icon_button(
            self.frm_arrows, "chevron_up", on_previous, previous_tooltip
        )
        self.btn_previous.grid(row=0, column=0)
        self.btn_next = icon_button(
            self.frm_arrows, "chevron_down", on_next, next_tooltip
        )
        self.btn_next.grid(row=0, column=1, padx=(2, 0))

        self.btn_adjust = localize(
            ctk.CTkButton(
                self,
                width=0,
                height=28,
                command=self._adjust_threshold,
                **(theme.GHOST_BUTTON | {"text_color": theme.ACCENT_TEXT}),
            ),
            text=L_("Adjust threshold"),
        )
        self.btn_review_again = localize(
            ctk.CTkButton(
                self,
                width=0,
                height=28,
                command=on_review_again,
                **theme.SECONDARY_BUTTON,
            ),
            text=L_("Review again"),
        )
        # The only content while the words aren't highlighted
        self.btn_enable = localize(
            ctk.CTkButton(
                self,
                image=icons.icon("warning", 14, theme.ACCENT_TEXT),
                compound=ctk.LEFT,
                width=0,
                height=28,
                command=on_enable,
                **(theme.GHOST_BUTTON | {"text_color": theme.ACCENT_TEXT}),
            ),
            text=L_("Review low-confidence words"),
        )

    @property
    def review(self) -> Review:
        return self._review

    def show(self, review: Review) -> None:
        self._review = review
        state = review.state
        for widget in (
            self.lbl_icon,
            self.lbl_status,
            self.frm_arrows,
            self.btn_adjust,
            self.btn_review_again,
            self.btn_enable,
        ):
            widget.grid_forget()

        # Collapsed to a link that turns the highlighting on
        if state == ReviewState.OFF:
            self.configure(fg_color="transparent", border_width=0)
            self.btn_enable.grid(row=0, column=0, pady=6, sticky=ctk.W)
            return

        self.configure(fg_color=theme.SUBTLE_BG, border_width=1)
        icon, color = {
            ReviewState.ACTIVE: ("warning", LOW_CONFIDENCE_COLOR),
            ReviewState.ALL_REVIEWED: ("check_circle", theme.STATUS_DONE),
        }.get(state, ("alert_circle", theme.ICON_MUTED))
        self.lbl_icon.configure(image=icons.icon(icon, 16, color))
        self.lbl_icon.grid(row=0, column=0, padx=(12, 8), pady=4)

        is_muted = state in (ReviewState.NO_DATA, ReviewState.NOTHING_FLAGGED)
        self.lbl_status.configure(
            text=self._status_text(),
            text_color=theme.HINT_TEXT if is_muted else theme.TEXT,
            font=theme.font(13, "normal" if is_muted else "bold"),
        )
        self.lbl_status.grid(row=0, column=1, sticky=ctk.W)

        if state in (ReviewState.ACTIVE, ReviewState.NOTHING_FLAGGED):
            arrow_state = ctk.NORMAL if state == ReviewState.ACTIVE else ctk.DISABLED
            set_button_state(self.btn_previous, arrow_state)
            set_button_state(self.btn_next, arrow_state)
            self.frm_arrows.grid(row=0, column=2, padx=(12, 0))
        if state == ReviewState.NOTHING_FLAGGED:
            self.btn_adjust.grid(row=0, column=4, padx=(0, 6))
        # The edited words stay reviewed, so only the accepted ones can be
        # reviewed again
        elif state == ReviewState.ALL_REVIEWED and review.accepted:
            self.btn_review_again.grid(row=0, column=4, padx=(0, 6))

    def _adjust_threshold(self) -> None:
        self._on_adjust_threshold(self.btn_adjust)

    def _status_text(self) -> str:
        review = self._review
        if review.state == ReviewState.ACTIVE:
            return _("{remaining} of {total} to review").format(
                remaining=review.remaining, total=review.total
            )
        if review.state == ReviewState.ALL_REVIEWED:
            return _("All reviewed · {total} of {total}").format(total=review.total)
        if review.state == ReviewState.NOTHING_FLAGGED:
            return _("No low-confidence words at this threshold")
        if review.state == ReviewState.NO_DATA:
            return _("Confidence data isn’t available for this transcript")
        return ""
