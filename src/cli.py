"""
Command-line interface of Audiotext, to transcribe from scripts.

Examples:
    python src/cli.py transcribe interview.mp3 --language es --output-types txt,srt
    python src/cli.py transcribe recordings/ --diarize --output-dir transcriptions/
    python src/cli.py transcribe "https://www.youtube.com/watch?v=…" -m whisper-api
    python src/cli.py transcribe meeting.m4a -m whisper-api \
        --openai-model gpt-transcribe --keywords "Audiotext, WhisperX"
    python src/cli.py transcribe talk.mp4 -t srt,md --summarize --translate-to es
    python src/cli.py watch inbox/ --output-types srt
    python src/cli.py check-update

The installed app runs it too when it's given a command (see `launcher.py`).

The options that are not given take the values configured in the app.
"""

import argparse
import dataclasses
import logging
import signal
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, TextIO

import utils.config_manager as cm
import utils.constants as c
from controllers.main_controller import MainController
from controllers.transcription_saver import get_file_extension, get_output_dir
from handlers import translation_handler
from handlers.ai_providers import AiProvider, get_provider, has_api_key
from handlers.openai_api_handler import API_MODELS
from handlers.summary_handler import SummaryHandler
from handlers.translation_handler import TranslationHandler, translation_providers
from handlers.whisperx_handler import WhisperXHandler
from interfaces.transcription_view import IgnoreHistoryEvents
from models.config.config_whisperx import ConfigWhisperX
from models.transcript_segment import TranscriptSegment
from models.transcription import Transcription, split_keywords
from utils.enums import (
    AudioSource,
    ComputeType,
    ModelSize,
    TranscriptionMethod,
    WhisperXFileTypes,
)
from utils.exporters import EXPORTERS, ExportDocument, export, export_summary
from utils.update_checker import UpdateCheckError, get_available_update

EXIT_SUCCESS = 0
EXIT_ERROR = 1
# Conventional exit code of a process interrupted with Ctrl+C
EXIT_CANCELLED = 130

METHODS = {
    "whisperx": TranscriptionMethod.WHISPERX,
    "google": TranscriptionMethod.GOOGLE_API,
    "whisper-api": TranscriptionMethod.WHISPER_API,
}
YOUTUBE_URL_PREFIXES = ("http://", "https://")
# The files that WhisperX saves itself. The other ones are exported from its result
WHISPERX_FILE_TYPES = [file_type.value for file_type in WhisperXFileTypes]
OUTPUT_FILE_TYPES = list(dict.fromkeys([*WHISPERX_FILE_TYPES, *EXPORTERS]))


@dataclass
class FollowUps:
    """
    What's done with each transcription after it's transcribed: exporting it to
    the file types that its method doesn't save, summarizing it and translating
    it. Their files are saved next to the ones of the transcription.
    """

    # Exported with `utils.exporters`
    output_types: list[str] = field(default_factory=list)
    should_summarize: bool = False
    summary_provider: AiProvider | None = None
    summary_model: str | None = None
    # The code of the language to translate into (e.g. "es")
    translation_language: str | None = None
    translation_provider: str | None = None
    translation_model: str | None = None
    # The file types of the translation
    translation_types: list[str] = field(default_factory=list)
    output_dir: Path | None = None
    # The transcribed folder, whose subfolders are recreated in `output_dir`
    source_dir: Path | None = None
    should_overwrite: bool = False

    def run(
        self, file_path: Path, text: str, segments: list[TranscriptSegment]
    ) -> tuple[list[Path], list[str]]:
        """
        :return: The saved files, and the errors of the ones that failed.
        """
        folder = get_output_dir(file_path, self.output_dir, self.source_dir)
        stem, title = file_path.stem, file_path.stem
        document = ExportDocument(title, text, segments)
        saved: list[Path] = []
        errors: list[str] = []

        def save(path: Path, write: Callable[[], Path]) -> None:
            if path.exists() and not self.should_overwrite:
                return
            try:
                folder.mkdir(parents=True, exist_ok=True)
                saved.append(write())
            except (OSError, ValueError) as e:
                errors.append(f"Could not save {path.name}: {e}")

        for file_type in self.output_types:
            path = folder / f"{stem}.{file_type}"
            save(path, partial(export, path, file_type, document))

        if self.should_summarize:
            path = folder / f"{stem}.summary.md"
            try:
                summary = SummaryHandler().summarize(
                    text, segments, self.summary_provider, self.summary_model
                )
            except (OSError, ValueError) as e:
                errors.append(f"Could not summarize {file_path.name}: {e}")
            else:
                save(path, partial(export_summary, path, "md", title, summary))

        if self.translation_language:
            language = self.translation_language
            try:
                translation = TranslationHandler().translate(
                    text,
                    segments,
                    is_text_edited=False,
                    language=language,
                    provider=self.translation_provider,
                    model=self.translation_model,
                )
            except (OSError, ValueError) as e:
                errors.append(f"Could not translate {file_path.name}: {e}")
            else:
                translated = ExportDocument(
                    f"{title} ({language})",
                    translation.text,
                    list(translation.segments),
                )
                for file_type in self.translation_types:
                    path = folder / f"{stem}.{language}.{file_type}"
                    save(path, partial(export, path, file_type, translated))

        return saved, errors


class ConsoleView(IgnoreHistoryEvents):
    """
    Implements the interface of the main window that the controller uses, writing
    the progress and the messages to stderr and the transcription to stdout, so
    the output can be redirected to a file.
    """

    def __init__(
        self,
        stdout: TextIO,
        stderr: TextIO,
        quiet: bool,
        follow_ups: FollowUps | None = None,
    ) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self._quiet = quiet
        self._follow_ups = follow_ups or FollowUps()
        self._lock = threading.Lock()
        self._is_progress_line_open = False
        self._last_progress_line = ""
        self._printed_report_lines: set[str] = set()
        self._text = ""

        self.finished = threading.Event()
        self.has_error = False
        self.should_print_text = True

    def run_on_ui_thread(self, callback: Callable[..., Any], *args: Any) -> None:
        with self._lock:
            callback(*args)

    def display_text(self, text: str) -> None:
        self._text = text

        if not self.should_print_text:
            # The report of a folder is rendered again on each change, so only the
            # lines that changed are printed
            for line in text.splitlines():
                if line and line not in self._printed_report_lines:
                    self._printed_report_lines.add(line)
                    self._print_message(line)

    def on_transcription_progress(self, message: str, fraction: float | None) -> None:
        if self._quiet:
            return

        progress = f" {fraction:.0%}" if fraction is not None else ""
        line = f"{message}{progress}"

        # The watcher reports the same message while waiting for files
        if line == self._last_progress_line or line in self._printed_report_lines:
            return
        self._last_progress_line = line

        if self._stderr.isatty():
            # Overwrites the previous progress line
            self._stderr.write(f"\r\033[K{line}")
            self._stderr.flush()
            self._is_progress_line_open = True
        else:
            self._print_message(line)

    def on_processed_transcription(self, status: str | None = None) -> None:
        if self.should_print_text and self._text:
            self._close_progress_line()
            print(self._text, file=self._stdout, flush=True)

        if status:
            self._print_message(status)

        self.finished.set()

    def on_transcription_saved(self, folder: Path) -> None:
        self._print_message(f"Saved in {folder}.")

    def on_file_transcribed(
        self,
        file_path: Path,
        text: str,
        segments: list[TranscriptSegment],
        _language: str | None,
    ) -> None:
        # It runs in the thread of the transcription, which waits for it
        saved, errors = self._follow_ups.run(file_path, text, segments)
        for path in saved:
            self._print_message(f"Saved {path}.")
        for error in errors:
            self.show_error(error)

    def show_error(self, message: str) -> None:
        self.has_error = True
        self._print_message(f"Error: {message}", force=True)

    def show_status(self, message: str) -> None:
        self._print_message(message)

    # The microphone is not available from the command line
    def on_recording_progress(self, elapsed_seconds: float, level: float) -> None:
        pass

    def on_stop_recording_from_mic(self) -> None:
        pass

    def _print_message(self, message: str, force: bool = False) -> None:
        if self._quiet and not force:
            return

        self._close_progress_line()
        print(message, file=self._stderr, flush=True)

    def _close_progress_line(self) -> None:
        if self._is_progress_line_open:
            self._stderr.write("\n")
            self._is_progress_line_open = False


def parse_output_types(value: str) -> list[str]:
    output_types = [item.strip().lstrip(".") for item in value.split(",") if item]

    for output_type in output_types:
        if output_type not in OUTPUT_FILE_TYPES:
            raise argparse.ArgumentTypeError(
                f"invalid output type '{output_type}' "
                f"(choose from {', '.join(OUTPUT_FILE_TYPES)})"
            )

    return list(dict.fromkeys(output_types))


def parse_target_language(value: str) -> str:
    if value not in c.AUDIO_LANGUAGES:
        raise argparse.ArgumentTypeError(
            f"unknown language '{value}'. Use an ISO 639-1 code (e.g. 'en', 'es')"
        )

    return value


def parse_language(value: str) -> str:
    if value != c.AUTO_DETECT_LANGUAGE and value not in c.AUDIO_LANGUAGES:
        raise argparse.ArgumentTypeError(
            f"unknown language '{value}'. Use an ISO 639-1 code (e.g. 'en', 'es') "
            f"or '{c.AUTO_DETECT_LANGUAGE}'"
        )

    return value


def parse_non_negative_int(value: str) -> int:
    if not value.isdigit():
        raise argparse.ArgumentTypeError(f"'{value}' is not a non-negative integer")

    return int(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audiotext",
        description="Transcribe audio and video files, folders and YouTube videos. "
        "The options that are not given take the values configured in the app.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {c.APP_VERSION}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    transcribe_parser = subparsers.add_parser(
        "transcribe",
        help="transcribe a file, the files of a folder or a YouTube video",
        description="Transcribe a file, the files of a folder (and its subfolders) "
        "or a YouTube video. The transcription of a single file is also printed "
        "to stdout.",
    )
    transcribe_parser.add_argument(
        "source", help="path of a file or folder, or URL of a YouTube video"
    )

    watch_parser = subparsers.add_parser(
        "watch",
        help="transcribe the files added to a folder until stopped with Ctrl+C",
        description="Watch a folder (and its subfolders) and transcribe each audio "
        "or video file added to it. The files it already contains are ignored. "
        "Press Ctrl+C to stop.",
    )
    watch_parser.add_argument("source", help="path of the folder to watch")

    for subparser in (transcribe_parser, watch_parser):
        add_common_arguments(subparser)

    subparsers.add_parser(
        "check-update",
        help="check whether a new version is available",
        description="Check whether a new version of Audiotext has been released "
        "on GitHub, and print the link to download it if so.",
    )

    return parser


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-m",
        "--method",
        choices=METHODS,
        help="transcription method",
    )
    parser.add_argument(
        "-l",
        "--language",
        type=parse_language,
        help=f"language of the audio as an ISO 639-1 code, or "
        f"'{c.AUTO_DETECT_LANGUAGE}' to detect it (not supported by Google)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        help="folder where the transcriptions are saved (default: next to each "
        "transcribed file)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=None,
        help="overwrite existing transcriptions",
    )
    parser.add_argument(
        "-p",
        "--prompt",
        help="what the audio is about, such as its topic or setting (not "
        "supported by Google)",
    )
    parser.add_argument(
        "-k",
        "--keywords",
        help="comma-separated names, terms or acronyms said in the audio, so "
        "they're spelled right (not supported by Google)",
    )
    parser.add_argument(
        "--translate",
        action="store_true",
        help="translate the audio into English while transcribing it (not "
        "supported by Google). See --translate-to for other languages",
    )
    parser.add_argument(
        "-t",
        "--output-types",
        type=parse_output_types,
        help="comma-separated list of output file types (e.g. 'txt,srt,md'), from "
        f"{', '.join(OUTPUT_FILE_TYPES)}. The ones that the method doesn't save "
        "are exported from its result",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="only print errors to stderr"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="print the logs to debug errors"
    )

    ai_group = parser.add_argument_group("summary and translation options")
    ai_group.add_argument(
        "--summarize",
        action="store_true",
        help="summarize each transcription, with its key points and chapters, "
        "into a '.summary.md' file",
    )
    ai_group.add_argument(
        "--summary-provider",
        choices=[provider.value for provider in AiProvider],
        help="provider of the language model that summarizes",
    )
    ai_group.add_argument("--summary-model", help="language model that summarizes")
    ai_group.add_argument(
        "--translate-to",
        type=parse_target_language,
        metavar="LANGUAGE",
        help="translate each transcription into a language (an ISO 639-1 code), "
        "saved in its output file types (e.g. 'talk.es.srt')",
    )
    ai_group.add_argument(
        "--translation-provider",
        choices=list(translation_providers()),
        help="provider of the translations",
    )
    ai_group.add_argument(
        "--translation-model",
        help="language model that translates, for the providers of language models",
    )

    whisperx_group = parser.add_argument_group("WhisperX options")
    whisperx_group.add_argument(
        "--diarize",
        action="store_true",
        default=None,
        help="identify the speakers (requires the HF_TOKEN environment variable "
        "or the token set in the app)",
    )
    whisperx_group.add_argument(
        "--speakers",
        type=parse_non_negative_int,
        help="number of speakers when identifying them (0 to detect it)",
    )
    whisperx_group.add_argument(
        "--model-size", choices=[size.value for size in ModelSize]
    )
    whisperx_group.add_argument(
        "--compute-type", choices=[compute.value for compute in ComputeType]
    )
    whisperx_group.add_argument(
        "--batch-size", type=parse_non_negative_int, help="batch size"
    )
    whisperx_group.add_argument(
        "--cpu", action="store_true", default=None, help="run on the CPU"
    )

    api_group = parser.add_argument_group("Whisper API options")
    api_group.add_argument(
        "--openai-model",
        choices=list(API_MODELS),
        help="transcription model of the OpenAI API",
    )


def get_whisperx_config(args: argparse.Namespace) -> ConfigWhisperX:
    """
    Returns the configured WhisperX options, replaced by the ones given in the
    command line. Without a CUDA GPU, it always runs on the CPU.
    """
    config = cm.ConfigManager.get_config_whisperx()
    overrides = {
        "model_size": args.model_size,
        "compute_type": args.compute_type,
        "batch_size": args.batch_size or None,
        "use_cpu": args.cpu,
        "diarize": args.diarize,
        "num_speakers": args.speakers,
    }
    config = dataclasses.replace(
        config, **{key: value for key, value in overrides.items() if value is not None}
    )

    # Imported here because it takes several seconds
    import torch

    if not torch.cuda.is_available():
        config.use_cpu = True
        # The CPU doesn't support float16
        if config.compute_type == ComputeType.FLOAT16.value:
            config.compute_type = ComputeType.INT8.value

    return config


def get_method(args: argparse.Namespace) -> TranscriptionMethod:
    if args.method:
        return METHODS[args.method]

    return TranscriptionMethod(cm.ConfigManager.get_config_transcription().method)


def build_transcription(
    args: argparse.Namespace, config_whisperx: ConfigWhisperX | None
) -> Transcription:
    """
    Builds the transcription from the command-line arguments and the configured
    options.

    :param config_whisperx: The WhisperX options, if WhisperX is the method.
    """
    config_transcription = cm.ConfigManager.get_config_transcription()
    method = get_method(args)
    language = args.language or config_transcription.language

    if args.command == "watch":
        audio_source = AudioSource.WATCH
    elif args.source.startswith(YOUTUBE_URL_PREFIXES):
        audio_source = AudioSource.YOUTUBE
    elif Path(args.source).is_dir():
        audio_source = AudioSource.DIRECTORY
    else:
        audio_source = AudioSource.FILE

    transcription = Transcription(
        language_code=None if language == c.AUTO_DETECT_LANGUAGE else language,
        audio_source=audio_source,
        method=method,
        should_autosave=True,
        should_overwrite=(
            args.overwrite
            if args.overwrite is not None
            else config_transcription.overwrite_files
        ),
        output_dir=args.output_dir,
    )

    if audio_source == AudioSource.YOUTUBE:
        transcription.url = args.source
    else:
        transcription.audio_source_path = Path(args.source).expanduser()

    if method != TranscriptionMethod.GOOGLE_API:
        transcription.should_translate = args.translate
        transcription.prompt = (
            args.prompt if args.prompt is not None else config_transcription.prompt
        ).strip()
        transcription.keywords = split_keywords(
            args.keywords
            if args.keywords is not None
            else config_transcription.keywords
        )

    if method == TranscriptionMethod.WHISPERX and config_whisperx:
        transcription.output_file_types = list(config_whisperx.output_file_types)
        transcription.should_diarize = config_whisperx.diarize
        transcription.num_speakers = config_whisperx.num_speakers or None
    elif method == TranscriptionMethod.WHISPER_API:
        config_whisper_api = cm.ConfigManager.get_config_whisper_api()
        transcription.api_model = args.openai_model or config_whisper_api.model
        transcription.api_response_format = config_whisper_api.response_format
        transcription.output_file_types = [config_whisper_api.response_format]
    else:
        transcription.output_file_types = ["txt"]

    if args.output_types:
        set_output_types(transcription, args.output_types)

    return transcription


def set_output_types(transcription: Transcription, output_types: list[str]) -> None:
    """
    Sets the output file types chosen in the command line, which replace the
    configured ones. WhisperX saves its file types itself, and the others are
    exported from the result (see `get_exported_types`). If it doesn't save any,
    the transcriptions are only exported.
    """
    is_whisperx = transcription.method == TranscriptionMethod.WHISPERX
    saved_types = [
        output_type
        for output_type in output_types
        if is_whisperx and output_type in WHISPERX_FILE_TYPES
    ]
    # The skipped files of a folder are the ones with any of them
    transcription.output_file_types = saved_types or list(output_types)
    transcription.should_autosave = bool(saved_types)


def get_exported_types(
    transcription: Transcription, output_types: list[str] | None
) -> list[str]:
    """The output file types exported from the result, instead of saved by it."""
    if not output_types:
        return []
    if not transcription.should_autosave:
        return output_types
    return [t for t in output_types if t not in transcription.output_file_types]


def build_follow_ups(
    args: argparse.Namespace, transcription: Transcription
) -> FollowUps:
    """
    :raises ValueError: If the provider of the summaries or the translations has
                        no API key.
    """
    config_ai = cm.ConfigManager.get_config_ai()
    summary_provider = get_provider(args.summary_provider or config_ai.summary_provider)
    translation_provider = args.translation_provider or config_ai.translation_provider

    if args.summarize and not has_api_key(summary_provider):
        raise ValueError(
            f"The API key of {summary_provider.value} is not set, so it can't "
            "summarize. Set it in the app or in its environment variable."
        )
    if args.translate_to and not translation_handler.has_api_key(translation_provider):
        raise ValueError(
            f"The API key of {translation_provider} is not set, so it can't "
            "translate. Set it in the app or in its environment variable."
        )

    output_types = args.output_types or [
        get_file_extension(file_type) for file_type in transcription.output_file_types
    ]
    translation_types = [t for t in output_types if t in EXPORTERS] or ["txt"]

    return FollowUps(
        output_types=get_exported_types(transcription, args.output_types),
        should_summarize=args.summarize,
        summary_provider=summary_provider,
        summary_model=args.summary_model
        or (config_ai.summary_model if not args.summary_provider else None),
        translation_language=args.translate_to,
        translation_provider=translation_provider,
        translation_model=args.translation_model
        or (config_ai.translation_model if not args.translation_provider else None),
        translation_types=translation_types,
        output_dir=transcription.output_dir,
        source_dir=(
            transcription.audio_source_path
            if transcription.audio_source.has_several_files
            else None
        ),
        should_overwrite=transcription.should_overwrite,
    )


def check_update(stdout: TextIO, stderr: TextIO) -> int:
    """
    Prints whether a new version is available.

    :return: The exit code, which is an error if the check fails.
    """
    try:
        release = get_available_update()
    except UpdateCheckError as e:
        print(f"Could not check for updates: {e}", file=stderr)
        return EXIT_ERROR

    if release:
        print(
            f"{c.APP_NAME} {release.version} is available (installed: "
            f"{c.APP_VERSION}). Download it from {release.url}",
            file=stdout,
        )
    else:
        print(f"{c.APP_NAME} {c.APP_VERSION} is the latest version.", file=stdout)
    return EXIT_SUCCESS


def _raise_keyboard_interrupt(_signum: int, _frame: Any) -> None:
    raise KeyboardInterrupt


def run(
    argv: list[str] | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """
    Runs the command-line interface.

    :param argv: The command-line arguments, without the program name.
    :return: The exit code.
    """
    args = build_parser().parse_args(argv)

    if args.command == "check-update":
        return check_update(stdout, stderr)

    # The errors are already printed, so the logs are only shown to debug them
    logging.getLogger().setLevel(logging.INFO if args.verbose else logging.CRITICAL)

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    config_whisperx = None
    whisperx_handler = None
    if get_method(args) == TranscriptionMethod.WHISPERX:
        config_whisperx = whisperx_config = get_whisperx_config(args)
        whisperx_handler = WhisperXHandler(config_provider=lambda: whisperx_config)

    transcription = build_transcription(args, config_whisperx)
    try:
        # Before transcribing, so a missing key doesn't waste the transcription
        follow_ups = build_follow_ups(args, transcription)
    except ValueError as e:
        print(f"Error: {e}", file=stderr)
        return EXIT_ERROR

    view = ConsoleView(stdout, stderr, quiet=args.quiet, follow_ups=follow_ups)
    view.should_print_text = transcription.audio_source not in (
        AudioSource.DIRECTORY,
        AudioSource.WATCH,
    )

    controller = MainController(view, view, whisperx_handler)
    controller.prepare_for_transcription(transcription)

    is_cancelled = False
    while True:
        try:
            # Waiting with a timeout lets Python handle Ctrl+C
            if view.finished.wait(0.2):
                break
        except KeyboardInterrupt:
            if is_cancelled:  # Pressed twice: exit right away
                return EXIT_CANCELLED

            is_cancelled = True
            view.show_status("Stopping… (press Ctrl+C again to exit now)")
            controller.cancel_transcription()

    if view.has_error:
        return EXIT_ERROR

    # Stopping the watcher is the normal way to finish it
    if is_cancelled and args.command != "watch":
        return EXIT_CANCELLED

    return EXIT_SUCCESS


def main() -> None:
    logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
    # Services are stopped with SIGTERM, which stops the process like Ctrl+C
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
    sys.exit(run())


if __name__ == "__main__":
    main()
