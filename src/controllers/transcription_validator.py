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
        _validate_api_response_format(transcription)

    _validate_audio_source(transcription)


def _validate_api_response_format(transcription: Transcription) -> None:
    """
    :raises ValueError: If the model of the OpenAI API can't generate the files of
                        the response format.
    """
    config = cm.ConfigManager.get_config_whisper_api()
    response_format = transcription.api_response_format or config.response_format
    model = get_api_model(
        # Whisper translates, whichever model is chosen
        None
        if transcription.should_translate
        else transcription.api_model or config.model
    )

    if response_format not in model.response_formats:
        raise ValueError(
            _(
                "The {model} model doesn't return timestamps, so it can't save "
                "{format} files. Choose another format or the whisper-1 model."
            ).format(model=model.name, format=response_format)
        )


def _validate_audio_source(transcription: Transcription) -> None:
    """
    :raises ValueError: If the file, the folder or the URL to transcribe is not
                        valid.
    """
    source = transcription.audio_source

    if source == AudioSource.FILE:
        file_path = transcription.audio_source_path
        is_file_supported = file_path.suffix.lower() in c.SUPPORTED_FILE_EXTENSIONS

        if not (file_path.is_file() and is_file_supported):
            raise ValueError(_("Please select a valid audio or video file."))

    elif source and source.has_several_files:
        if not transcription.audio_source_path.is_dir():
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
