import dataclasses
import glob
import logging
from pathlib import Path

from interfaces.transcriber import Transcriber
from models.transcription import Transcription, TranscriptionResult
from utils import constants as c
from utils.folder_watcher import FileFilter, list_supported_files

logger = logging.getLogger(__name__)


def get_output_dir(
    file_path: Path, output_dir: Path | None, source_dir: Path | None = None
) -> Path:
    """
    Returns the folder where the transcription of a file is saved automatically.

    :param file_path: The path of the transcribed file.
    :param output_dir: The folder chosen to save the transcriptions. If None, they
                       are saved next to the transcribed file.
    :param source_dir: The transcribed folder, if the file belongs to one. Its
                       subfolders are recreated inside `output_dir`, so files with
                       the same name in different subfolders don't collide.
    :return: The folder of the transcription.
    """
    if output_dir is None:
        return file_path.parent

    if source_dir is not None and file_path.is_relative_to(source_dir):
        return output_dir / file_path.parent.relative_to(source_dir)

    return output_dir


def has_transcription(
    file_path: Path, output_file_types: list[str], output_dir: Path | None = None
) -> bool:
    """
    :param file_path: The path of an audio or video file.
    :param output_file_types: The output file types of the transcriptions.
    :param output_dir: The folder of the transcriptions. Defaults to the folder of
                       the file.
    :return: Whether the file has a transcription for each of the output file
             types, so it's transcribed again if one of them is added.
    """
    return bool(output_file_types) and all(
        path.exists()
        for path in transcription_paths(file_path, output_file_types, output_dir)
    )


def transcription_paths(
    file_path: Path, output_file_types: list[str], output_dir: Path | None = None
) -> list[Path]:
    """
    The paths of the transcriptions of a file, one for each output file type. See
    `has_transcription`.
    """
    name = transcription_name(file_path)
    folder = output_dir or file_path.parent

    return [
        folder / f"{name}.{get_file_extension(file_type)}"
        for file_type in output_file_types
    ]


def transcription_name(file_path: Path) -> str:
    """
    The name of the transcriptions of a file, without their extension: the name
    of the file without its extension (e.g. "talk" for "talk.mp3"), or with it
    (e.g. "talk.mp3") if another audio or video file of its folder has the same
    one, so their transcriptions don't replace each other.
    """
    try:
        others = [
            other
            for other in file_path.parent.glob(f"{glob.escape(file_path.stem)}.*")
            if other.stem == file_path.stem
            and other.name != file_path.name
            and other.suffix.lower() in c.SUPPORTED_FILE_EXTENSIONS
        ]
    except OSError:
        others = []
    return file_path.name if others else file_path.stem


def get_file_extension(file_type: str) -> str:
    """Returns the extension of an output file type or API response format."""
    return c.FORMATS_TO_FILE_TYPES.get(file_type, file_type)


class TranscriptionSaver:
    """
    Saves the transcriptions automatically, next to each transcribed file or in the
    output folder of the transcription.
    """

    def __init__(self, transcription: Transcription) -> None:
        self._transcription = transcription
        # The subfolders of a transcribed folder are recreated in the output folder
        self._source_dir = (
            transcription.path if transcription.audio_source.has_several_files else None
        )

    def get_output_dir(self, file_path: Path) -> Path:
        return get_output_dir(
            file_path, self._transcription.output_dir, self._source_dir
        )

    def get_output_root(self) -> Path:
        """The folder where the transcriptions of a folder are saved."""
        return self._transcription.output_dir or self._transcription.path

    def has_transcription(self, file_path: Path) -> bool:
        return has_transcription(
            file_path,
            self._transcription.output_file_types,
            self.get_output_dir(file_path),
        )

    def get_files_to_transcribe(self, dir_path: Path) -> list[Path]:
        """
        Retrieves the supported files of a directory (and its subdirectories).
        Unless the transcription overwrites the existing files, files that already
        have a transcription for each of the output file types are skipped.

        :return: A sorted list of the paths of the files to transcribe.
        """
        return [
            file_path
            for file_path in self.list_files(dir_path)
            if not self.should_skip(file_path)
        ]

    @property
    def file_filter(self) -> FileFilter:
        """Which files of the folder are transcribed."""
        return FileFilter(
            include_subfolders=self._transcription.should_include_subfolders,
            exclude_patterns=tuple(self._transcription.exclude_patterns),
        )

    def list_files(self, dir_path: Path) -> list[Path]:
        """The files of a folder that are transcribed, with a transcription or not."""
        return list_supported_files(dir_path, self.file_filter)

    def should_skip(self, file_path: Path) -> bool:
        """Whether the file is skipped because it already has a transcription."""
        if self._transcription.should_overwrite or not self.has_transcription(
            file_path
        ):
            return False

        logger.info("%s already has transcription(s). Skipping.", file_path)
        return True

    def save(
        self, transcriber: Transcriber, result: TranscriptionResult, file_path: Path
    ) -> Path:
        """
        Saves the result of a file in each of the output file types.

        :param file_path: The path of the transcribed file, used to name the output.
        :return: The folder where the files have been saved.
        """
        output_dir = self.get_output_dir(file_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        # With the extension of the first file type, which the transcribers
        # replace by the one of each type, since the name can have dots (e.g.
        # "talk.mp3", if there is also a "talk.mp4")
        file_types = self._transcription.output_file_types or ["txt"]
        extension = get_file_extension(file_types[0])
        save_path = output_dir / f"{transcription_name(file_path)}.{extension}"

        # Pointing to the file, not to its folder, e.g. to know if it's a vertical
        # video, which narrows its subtitles
        transcriber.save(
            result,
            dataclasses.replace(self._transcription, audio_source_path=file_path),
            save_path,
        )

        return save_path.parent.resolve()
