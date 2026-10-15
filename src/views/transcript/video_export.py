import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from models.config.config_system import ConfigSystem
from utils.cancellation import CancellationToken, TranscriptionCancelledError
from utils.i18n import _
from utils.subtitle_burner import BurnedVideo, SubtitleLook, burn_subtitles
from utils.subtitle_cues import Cue
from views.transcript.video_pane import SUBTITLE_OUTLINE, SUBTITLE_SIZES

logger = logging.getLogger(__name__)


def subtitle_look(config: ConfigSystem) -> SubtitleLook:
    """The look of the subtitles shown over the video, as the user configured it."""
    return SubtitleLook(
        relative_size=SUBTITLE_SIZES.get(
            config.subtitle_size, SUBTITLE_SIZES["medium"]
        ),
        is_top=config.subtitle_position == "top",
        is_outline=config.subtitle_style == SUBTITLE_OUTLINE,
    )


class VideoExport:
    """
    Exports a copy of a video with its subtitles drawn on it, in the background.
    Only one is exported at a time, and it goes on if another transcription is
    shown, so its state is shared by the views of the transcriptions.
    """

    _token: CancellationToken | None = None

    @classmethod
    def is_running(cls) -> bool:
        return cls._token is not None

    @classmethod
    def cancel(cls) -> None:
        if cls._token:
            cls._token.cancel()

    @classmethod
    def start(
        cls,
        video_path: Path,
        cues: list[Cue],
        output_path: Path,
        look: SubtitleLook,
        show_status: Callable[..., None],
        run_on_ui_thread: Callable[..., Any],
    ) -> None:
        """
        :param show_status: Shows a message, and whether it's an error, in the
                            window.
        :param run_on_ui_thread: Runs a callback in the thread of the interface.
        """
        if cls._token is not None:
            return
        token = cls._token = CancellationToken()
        last_percent: list[int | None] = [None]

        def on_progress(_message: str, fraction: float | None) -> None:
            percent = round(fraction * 100) if fraction is not None else None
            # The status is only updated when the shown percentage changes
            if percent != last_percent[0]:
                last_percent[0] = percent
                run_on_ui_thread(show_status, progress_message(percent))

        def finish(message: str, is_error: bool = False) -> None:
            cls._token = None
            show_status(message, is_error)

        def export() -> None:
            try:
                burned = burn_subtitles(
                    video_path, cues, output_path, look, on_progress, token
                )
            except TranscriptionCancelledError:
                run_on_ui_thread(
                    finish, _("Adding the subtitles to the video was cancelled.")
                )
            except (OSError, ValueError) as e:
                logger.error("Could not burn the subtitles", exc_info=e)
                run_on_ui_thread(
                    finish, _("Could not export: {error}").format(error=e), True
                )
            else:
                run_on_ui_thread(finish, *export_message(burned))

        show_status(progress_message(None))
        threading.Thread(target=export, daemon=True).start()


def export_message(burned: BurnedVideo) -> tuple[str, bool]:
    """The message shown when the video is exported, and whether it's an error."""
    if not burned.missing_characters:
        return _("Exported to {path}").format(path=burned.path), False
    # The video is exported, but some of the text is drawn as boxes
    return (
        _(
            "Exported to {path}, but no font has these characters, so they're "
            "shown as boxes: {characters}"
        ).format(path=burned.path, characters=burned.missing_characters),
        True,
    )


def progress_message(percent: int | None) -> str:
    if percent is None:
        return _("Adding the subtitles to the video…")
    return _("Adding the subtitles to the video… {percent}%").format(percent=percent)
