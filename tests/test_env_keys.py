import sys
from pathlib import Path

import keyring
import pytest
from dotenv import dotenv_values

import utils.env_keys as env_keys
from tests.conftest import MemoryKeyring
from utils.env_keys import KEYRING_SERVICE, EnvKeys, migrate_env_file


class BrokenKeyring(MemoryKeyring):
    """A credential store that can't be used, like a Linux server without one."""

    def get_password(self, service: str, username: str) -> str | None:
        raise RuntimeError("No credential store")

    def set_password(self, service: str, username: str, password: str) -> None:
        raise RuntimeError("No credential store")

    def delete_password(self, service: str, username: str) -> None:
        raise RuntimeError("No credential store")


@pytest.fixture
def broken_keyring() -> None:
    keyring.set_keyring(BrokenKeyring())
    env_keys.clear_cache()


def test_get_value_returns_the_environment_variable(
    monkeypatch: pytest.MonkeyPatch, memory_keyring: MemoryKeyring
) -> None:
    memory_keyring.set_password(KEYRING_SERVICE, "OPENAI_API_KEY", "sk-stored")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    # The environment takes precedence, e.g. to use another key from a script
    assert EnvKeys.OPENAI_API_KEY.get_value() == "sk-test"


def test_get_value_reads_the_credential_store(memory_keyring: MemoryKeyring) -> None:
    memory_keyring.set_password(KEYRING_SERVICE, "OPENAI_API_KEY", "sk-stored")

    assert EnvKeys.OPENAI_API_KEY.get_value() == "sk-stored"


def test_get_value_reads_the_env_file_of_previous_versions() -> None:
    env_keys.ENV_FILE_PATH.parent.mkdir(parents=True)
    env_keys.ENV_FILE_PATH.write_text("HF_TOKEN=hf_file\n")
    env_keys.LEGACY_ENV_FILE_PATH.write_text("HF_TOKEN=hf_legacy\nGOOGLE_API_KEY=g\n")

    assert EnvKeys.HF_TOKEN.get_value() == "hf_file"
    assert EnvKeys.GOOGLE_API_KEY.get_value() == "g"


def test_get_value_returns_default_if_not_set() -> None:
    assert EnvKeys.GOOGLE_API_KEY.get_value(default="") == ""


def test_get_value_raises_if_not_set_without_default() -> None:
    with pytest.raises(OSError, match="GOOGLE_API_KEY"):
        EnvKeys.GOOGLE_API_KEY.get_value()


def test_set_value_stores_the_key_in_the_credential_store(
    tmp_path: Path, memory_keyring: MemoryKeyring
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_API_KEY=google\nOPENAI_API_KEY=sk-old\n")

    EnvKeys.OPENAI_API_KEY.set_value("sk-new", env_file_path=env_file)

    assert EnvKeys.OPENAI_API_KEY.get_value() == "sk-new"
    assert memory_keyring.passwords[(KEYRING_SERVICE, "OPENAI_API_KEY")] == "sk-new"
    # The plain-text copy is removed, and the other keys are kept
    assert dotenv_values(env_file) == {"GOOGLE_API_KEY": "google"}


def test_set_value_with_an_empty_value_removes_the_key(
    memory_keyring: MemoryKeyring,
) -> None:
    EnvKeys.HF_TOKEN.set_value("hf_token")

    EnvKeys.HF_TOKEN.set_value("")

    assert EnvKeys.HF_TOKEN.get_value(default="") == ""
    assert (KEYRING_SERVICE, "HF_TOKEN") not in memory_keyring.passwords


@pytest.mark.usefixtures("broken_keyring")
def test_set_value_falls_back_to_the_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / "config" / ".env"

    EnvKeys.HF_TOKEN.set_value("hf_token", env_file_path=env_file)

    assert dotenv_values(env_file) == {"HF_TOKEN": "hf_token"}
    if sys.platform != "win32":
        assert env_file.stat().st_mode & 0o777 == 0o600


@pytest.mark.usefixtures("broken_keyring")
def test_get_value_works_without_a_credential_store() -> None:
    env_keys.ENV_FILE_PATH.parent.mkdir(parents=True)
    env_keys.ENV_FILE_PATH.write_text("OPENAI_API_KEY=sk-file\n")

    assert EnvKeys.OPENAI_API_KEY.get_value() == "sk-file"


def test_migrate_env_file_moves_the_keys_to_the_credential_store(
    tmp_path: Path, memory_keyring: MemoryKeyring
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-old\nHF_TOKEN=\nOTHER=value\n")

    migrate_env_file(env_file)

    assert memory_keyring.passwords == {(KEYRING_SERVICE, "OPENAI_API_KEY"): "sk-old"}
    # Unknown variables are not the app's, so they're left untouched
    assert dotenv_values(env_file) == {"HF_TOKEN": "", "OTHER": "value"}


@pytest.mark.usefixtures("broken_keyring")
def test_migrate_env_file_keeps_the_keys_without_a_credential_store(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-old\n")

    migrate_env_file(env_file)

    assert dotenv_values(env_file) == {"OPENAI_API_KEY": "sk-old"}
