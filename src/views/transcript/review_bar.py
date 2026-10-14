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
# The key that accepts a low confidence word, as the keyboard names it
ACCEPT_KEY_LABEL = "Return" if theme.IS_MACOS else "Enter"


class ReviewBar(ctk.CTkFrame):  # type: ignore[misc]
    """
    The review of the low confidence words of the transcript, above it: how many
    are left to review, the buttons to go through them, and its options. It shows
    each state of the review (see `ReviewState`), keeping its height so it doesn't
    jump while the threshold changes.
    """

    def __init__(
        self,
        master: Any,
        on_previous: Callable[[], None],
        on_next: Callable[[], None],
        on_enable: Callable[[], None],
        on_adjust_threshold: Callable[[Any], None],
        on_review_again: Callable[[], None],
        on_undo: Callable[[], Any],
        on_auto_play_change: Callable[[bool], None],
        on_only_flagged_change: Callable[[bool], None],
        is_auto_play: bool,
        previous_tooltip: Text,
        next_tooltip: Text,
    ) -> None:
        """
        :param on_enable: Turns the highlighting of the low confidence words on.
        :param on_adjust_threshold: Shows the thresholds below the widget given.
        :param on_review_again: Forgets which words were accepted.
        :param on_undo: Undoes the last review.
        :param on_auto_play_change: Called with whether going to a word plays it.
        :param on_only_flagged_change: Called with whether only the segments with
            words to review are shown.
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
        # Between the options on the left and the one on the right
        self.grid_columnconfigure(6, weight=1)

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

        self._on_only_flagged_change = on_only_flagged_change
        self._only_flagged_variable = ctk.BooleanVar(self, value=False)
        self.chk_only_flagged = localize(
            ctk.CTkCheckBox(
                self,
                variable=self._only_flagged_variable,
                command=lambda: on_only_flagged_change(
                    self._only_flagged_variable.get()
                ),
                checkbox_width=18,
                checkbox_height=18,
                border_width=2,
                font=theme.font(13),
            ),
            text=L_("Only flagged"),
        )
        self._auto_play_variable = ctk.BooleanVar(self, value=is_auto_play)
        self.chk_auto_play = localize(
            ctk.CTkCheckBox(
                self,
                variable=self._auto_play_variable,
                command=lambda: on_auto_play_change(self._auto_play_variable.get()),
                checkbox_width=18,
                checkbox_height=18,
                border_width=2,
                font=theme.font(13),
            ),
            text=L_("Auto-play"),
        )
        self.btn_undo = localize(
            ctk.CTkButton(
                self, width=0, height=28, command=on_undo, **theme.GHOST_BUTTON
            ),
            text=L_("Undo"),
        )
        self.lbl_accept_hint = localize(
            ctk.CTkLabel(self, font=theme.font(12), text_color=theme.HINT_TEXT),
            text=lambda: _("{key} — accept as is").format(key=ACCEPT_KEY_LABEL),
        )

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
            # Not all of them: the corrected words stay reviewed
            text=L_("Review accepted words again"),
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

    def show(self, review: Review, can_undo: bool = False) -> None:
        """
        :param can_undo: Whether the last review can be undone.
        """
        self._review = review
        state = review.state
        for widget in (
            self.lbl_icon,
            self.lbl_status,
            self.frm_arrows,
            self.chk_only_flagged,
            self.chk_auto_play,
            self.btn_undo,
            self.lbl_accept_hint,
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
        # Also once all are reviewed, to show all the segments again
        if state in (ReviewState.ACTIVE, ReviewState.ALL_REVIEWED):
            self.chk_only_flagged.grid(row=0, column=3, padx=(12, 0))
        if state == ReviewState.ACTIVE:
            self.chk_auto_play.grid(row=0, column=4, padx=(12, 0))
            self.lbl_accept_hint.grid(row=0, column=7, padx=(0, 12))
        # After accepting the last word too
        if can_undo and state in (ReviewState.ACTIVE, ReviewState.ALL_REVIEWED):
            self.btn_undo.grid(row=0, column=5, padx=(8, 0))
        if state == ReviewState.NOTHING_FLAGGED:
            self.btn_adjust.grid(row=0, column=7, padx=(0, 6))
        # The edited words stay reviewed, so only the accepted ones can be
        # reviewed again
        elif state == ReviewState.ALL_REVIEWED and review.accepted:
            self.btn_review_again.grid(row=0, column=7, padx=(0, 6))

    def set_only_flagged(self, is_on: bool) -> None:
        """Checks or unchecks "Only flagged", as if the user did."""
        self._only_flagged_variable.set(is_on)
        self._on_only_flagged_change(is_on)

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
