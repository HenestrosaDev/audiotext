"""
API keys and tokens of the services used by the app.

The keys are stored in the credential store of the operating system (the Keychain
on macOS, the Credential Manager on Windows and the Secret Service on Linux), so
they're encrypted and never written to a plain-text file. If the system has no
credential store (e.g. a Linux server without a desktop), they're stored in a
`.env` file of the user's configuration folder that only the user can read.

The variables of the environment take precedence, so the keys can also be given
to the command-line interface without storing them.
"""

import contextlib
import logging
import os
import sys
from enum import Enum
from pathlib import Path

import keyring
from dotenv import dotenv_values, set_key, unset_key
from keyring.errors import PasswordDeleteError

import utils.path_helper as ph

# The API keys are stored in the user's configuration folder, outside the project
# and the app bundle, so they are never committed or distributed by mistake
ENV_FILE_PATH = ph.get_user_config_dir() / ".env"
# Location used by previous versions, still read to keep the keys of the users
LEGACY_ENV_FILE_PATH = ph.ROOT_PATH / ".env"
# Name of the app in the credential store of the system
KEYRING_SERVICE = "Audiotext"

logger = logging.getLogger(__name__)

# Reading the credential store is slow, and the settings check the keys each time
# they change, so the values read are kept
_keyring_cache: dict[str, str | None] = {}


def clear_cache() -> None:
    _keyring_cache.clear()


def _read_keyring(name: str) -> str | None:
    if name in _keyring_cache:
        return _keyring_cache[name]

    # The backends of the credential stores can fail in many ways (e.g. a locked
    # keychain or a missing D-Bus session), which must not prevent using the app
    try:
        value = keyring.get_password(KEYRING_SERVICE, name)
    except Exception:
        logger.warning("Could not read %s from the credential store", name)
        value = None

    _keyring_cache[name] = value
    return value


def _write_keyring(name: str, value: str) -> bool:
    """:return: Whether the value was stored (or removed, if empty)."""
    try:
        if value:
            keyring.set_password(KEYRING_SERVICE, name, value)
        else:
            with contextlib.suppress(PasswordDeleteError):
                keyring.delete_password(KEYRING_SERVICE, name)
    except Exception:
        logger.warning("Could not store %s in the credential store", name)
        return False

    _keyring_cache[name] = value or None
    return True


def _read_env_files(env_file_path: Path) -> dict[str, str]:
    """The keys of the `.env` files. The ones of the user's file take precedence."""
    values: dict[str, str] = {}

    for path in (LEGACY_ENV_FILE_PATH, env_file_path):
        if path.is_file():
            values.update(
                {key: value for key, value in dotenv_values(path).items() if value}
            )

    return values


def _write_env_file(name: str, value: str, env_file_path: Path) -> None:
    try:
        if value:
            env_file_path.parent.mkdir(parents=True, exist_ok=True)
            env_file_path.touch(exist_ok=True)
            if sys.platform != "win32":
                # Only the user can read the keys
                env_file_path.chmod(0o600)
            set_key(env_file_path, name, value)
        elif env_file_path.is_file() and name in dotenv_values(env_file_path):
            unset_key(env_file_path, name)
    except OSError:
        logger.warning("Could not persist %s in %s", name, env_file_path)


class EnvKeys(Enum):
    GOOGLE_API_KEY = "GOOGLE_API_KEY"
    # Needed to download the speaker diarization model
    HF_TOKEN = "HF_TOKEN"
    OPENAI_API_KEY = "OPENAI_API_KEY"
    # Providers of language models that summarize and translate
    ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
    DEEPSEEK_API_KEY = "DEEPSEEK_API_KEY"
    GEMINI_API_KEY = "GEMINI_API_KEY"
    MISTRAL_API_KEY = "MISTRAL_API_KEY"
    XAI_API_KEY = "XAI_API_KEY"
    # Provider of translations
    DEEPL_API_KEY = "DEEPL_API_KEY"

    def get_value(
        self, default: str | None = None, env_file_path: Path | None = None
    ) -> str:
        """
        Gets the value of the key: from the environment, the credential store of
        the system or the `.env` file, in that order.

        :param default: Value returned if the key is not set.
        :param env_file_path: The `.env` file where the key may be stored. Defaults
                              to `ENV_FILE_PATH`.
        :raises OSError: If the key is not set and no default is provided.
        :return: The value of the key.
        """
        value = (
            os.environ.get(self.value)
            or _read_keyring(self.value)
            or _read_env_files(env_file_path or ENV_FILE_PATH).get(self.value)
            or default
        )

        if value is None:
            raise OSError(
                f"Environment variable {self.value} not set and no default value "
                "provided."
            )

        return value

    def set_value(self, value: str, env_file_path: Path | None = None) -> None:
        """
        Sets the key for the current session and stores it, so that it's still
        available the next time the app starts. An empty value removes it.

        :param value: The new value of the key.
        :param env_file_path: The `.env` file where the key is stored if the system
                              has no credential store. Defaults to `ENV_FILE_PATH`.
        """
        env_file_path = env_file_path or ENV_FILE_PATH

        if value:
            os.environ[self.value] = value
        else:
            os.environ.pop(self.value, None)

        if _write_keyring(self.value, value):
            # A copy in the file would be readable by other programs
            _write_env_file(self.value, "", env_file_path)
        else:
            _write_env_file(self.value, value, env_file_path)


def migrate_env_file(env_file_path: Path | None = None) -> None:
    """
    Moves the keys that previous versions stored in the `.env` file of the user to
    the credential store of the system. The keys that can't be moved are kept in
    the file.
    """
    env_file_path = env_file_path or ENV_FILE_PATH
    if not env_file_path.is_file():
        return

    known_names = {env_key.value for env_key in EnvKeys}

    for name, value in dotenv_values(env_file_path).items():
        if name in known_names and value and _write_keyring(name, value):
            _write_env_file(name, "", env_file_path)
            logger.info("Moved %s to the credential store", name)
