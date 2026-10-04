import logging
from pathlib import Path

from interfaces.transcriber import Transcriber
from models.transcription import Transcription, TranscriptionResult
from utils import constants as c
from utils.folder_watcher import list_supported_files

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
    :return: Whether the file has a transcription for any of the output file types.
    """
    transcription_path = (output_dir or file_path.parent) / file_path.name

    return any(
        transcription_path.with_suffix(f".{get_file_extension(file_type)}").exists()
        for file_type in output_file_types
    )


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
            transcription.audio_source_path
            if transcription.audio_source
            and transcription.audio_source.has_several_files
            else None
        )

    def get_output_dir(self, file_path: Path) -> Path:
        return get_output_dir(
            file_path, self._transcription.output_dir, self._source_dir
        )

    def get_output_root(self) -> Path:
        """The folder where the transcriptions of a folder are saved."""
        return self._transcription.output_dir or self._transcription.audio_source_path

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
        have a transcription for any of the output file types are skipped.

        :return: A sorted list of the paths of the files to transcribe.
        """
        return [
            file_path
            for file_path in list_supported_files(dir_path)
            if not self.should_skip(file_path)
        ]

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
        save_path = output_dir / f"{file_path.stem}{self._get_extension()}"

        transcriber.save(result, self._transcription, save_path)

        return save_path.parent.resolve()

    def _get_extension(self) -> str:
        """
        Returns the extension of the output file, which is only known if there is a
        single output file type. Otherwise, each output file type adds its own.
        """
        output_file_types = self._transcription.output_file_types

        if len(output_file_types) != 1:
            return ""

        return f".{get_file_extension(output_file_types[0])}"
