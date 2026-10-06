"""
Command-line interface of Audiotext, to transcribe from scripts.

Examples:
    python src/cli.py transcribe interview.mp3 --language es --output-types txt,srt
    python src/cli.py transcribe recordings/ --diarize --output-dir transcriptions/
    python src/cli.py transcribe "https://www.youtube.com/watch?v=…" -m whisper-api
    python src/cli.py transcribe meeting.m4a -m whisper-api \
        --openai-model gpt-transcribe --keywords "Audiotext, WhisperX"
    python src/cli.py watch inbox/ --output-types srt
    python src/cli.py check-update

The options that are not given take the values configured in the app.
"""

import argparse
import dataclasses
import logging
import signal
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

import utils.config_manager as cm
import utils.constants as c
from controllers.main_controller import MainController
from handlers.openai_api_handler import API_MODELS
from handlers.whisperx_handler import WhisperXHandler
from interfaces.transcription_view import IgnoreHistoryEvents
from models.config.config_whisperx import ConfigWhisperX
from models.transcription import Transcription, split_keywords
from utils.enums import (
    AudioSource,
    ComputeType,
    ModelSize,
    TranscriptionMethod,
    WhisperXFileTypes,
)
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


class ConsoleView(IgnoreHistoryEvents):
    """
    Implements the interface of the main window that the controller uses, writing
    the progress and the messages to stderr and the transcription to stdout, so
    the output can be redirected to a file.
    """

    def __init__(self, stdout: TextIO, stderr: TextIO, quiet: bool) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self._quiet = quiet
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
    valid_types = [file_type.value for file_type in WhisperXFileTypes]

    for output_type in output_types:
        if output_type not in valid_types:
            raise argparse.ArgumentTypeError(
                f"invalid output type '{output_type}' "
                f"(choose from {', '.join(valid_types)})"
            )

    return output_types


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
        help="translate the audio into English (not supported by Google)",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="only print errors to stderr"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="print the logs to debug errors"
    )

    whisperx_group = parser.add_argument_group("WhisperX options")
    whisperx_group.add_argument(
        "-t",
        "--output-types",
        type=parse_output_types,
        help="comma-separated list of output file types (e.g. 'txt,srt')",
    )
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
        "output_file_types": args.output_types,
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

    return transcription


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

    view = ConsoleView(stdout, stderr, quiet=args.quiet)

    config_whisperx = None
    whisperx_handler = None
    if get_method(args) == TranscriptionMethod.WHISPERX:
        config_whisperx = whisperx_config = get_whisperx_config(args)
        whisperx_handler = WhisperXHandler(config_provider=lambda: whisperx_config)

    transcription = build_transcription(args, config_whisperx)
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


if __name__ == "__main__":
    logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
    # Services are stopped with SIGTERM, which stops the process like Ctrl+C
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
    sys.exit(run())
