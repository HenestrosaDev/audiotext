import utils.config_manager as cm
from handlers.openai_api_handler import get_api_model
from models.transcription import Transcription
from utils import constants as c
from utils.enums import AudioSource, TranscriptionMethod
from utils.i18n import _
from utils.validators import is_valid_url


def validate_transcription(transcription: Transcription) -> None:
    """
    :raises ValueError: If the transcription can't be generated with the given
                        settings.
    """
    if not transcription.output_file_types:
        raise ValueError(
            _("No output file types selected. Please select at least one.")
        )

    if (
        transcription.method == TranscriptionMethod.GOOGLE_API
        and not transcription.language_code
    ):
        raise ValueError(
            _(
                "The Google API can't detect the language. Please select the "
                "language of the audio."
            )
        )

    if (
        transcription.method == TranscriptionMethod.WHISPER_API
        and transcription.should_autosave
    ):
        _validate_api_file_types(transcription)

    _validate_audio_source(transcription)


def _validate_api_file_types(transcription: Transcription) -> None:
    """
    :raises ValueError: If the model of the OpenAI API can't generate the files of
                        any of the output file types.
    """
    config = cm.ConfigManager.get_config_whisper_api()
    model = get_api_model(
        # Whisper translates, whichever model is chosen
        None
        if transcription.should_translate
        else transcription.api_model or config.model
    )
    unsupported = [t for t in transcription.output_file_types if not model.can_save(t)]

    if unsupported:
        raise ValueError(
            _(
                "The {model} model doesn't return timestamps, so it can't save "
                "{format} files. Choose another format or the whisper-1 model."
            ).format(model=model.name, format=", ".join(unsupported))
        )


def _validate_audio_source(transcription: Transcription) -> None:
    """
    :raises ValueError: If the file, the folder or the URL to transcribe is not
                        valid.
    """
    source = transcription.audio_source
    path = transcription.audio_source_path

    if source == AudioSource.FILE:
        if not (
            path
            and path.is_file()
            and path.suffix.lower() in c.SUPPORTED_FILE_EXTENSIONS
        ):
            raise ValueError(_("Please select a valid audio or video file."))

    elif source.has_several_files:
        if not (path and path.is_dir()):
            raise ValueError(_("Please select a valid folder."))

    elif source == AudioSource.YOUTUBE and not (
        transcription.url and is_valid_url(transcription.url)
    ):
        raise ValueError(
            _(
                "Please enter a valid URL (e.g. the link of a YouTube video or of an "
                "audio or video file)."
            )
        )
