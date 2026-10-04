"""
Checks that the translations of the interface are up to date with the code. If a
test fails, run `python .github/scripts/update_translations.py` and translate the
texts that it lists.
"""

import importlib.util
from pathlib import Path

import pytest
from babel.messages.catalog import Catalog
from babel.messages.mofile import read_mo
from babel.messages.pofile import read_po

from utils.i18n import DEFAULT_LANGUAGE, UI_LANGUAGES

ROOT_PATH = Path(__file__).parents[1]
SCRIPT_PATH = ROOT_PATH / ".github" / "scripts" / "update_translations.py"

spec = importlib.util.spec_from_file_location("update_translations", SCRIPT_PATH)
assert spec and spec.loader
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)
# The module that compiles the catalogs and checks their placeholders
compile_translations = script.compile_translations

TRANSLATED_LANGUAGES = sorted(set(UI_LANGUAGES) - {DEFAULT_LANGUAGE})


def read_catalog(path: Path) -> Catalog:
    with path.open("rb") as file:
        return read_po(file)


def catalog_path(language: str) -> Path:
    return script.LOCALES_PATH / language / "LC_MESSAGES" / f"{script.DOMAIN}.po"


def message_ids(catalog: Catalog) -> set[str]:
    return {script.message_id(message) for message in catalog if message.id}


def test_the_template_has_the_texts_of_the_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The script runs pybabel from the root, and the directory is restored after
    monkeypatch.chdir(ROOT_PATH)
    extracted_path = tmp_path / "audiotext.pot"
    script.extract(extracted_path)

    extracted = message_ids(read_catalog(extracted_path))
    template = message_ids(read_catalog(script.TEMPLATE_PATH))

    assert extracted - template == set(), "Texts missing from the template"
    assert template - extracted == set(), "Texts no longer in the code"


def test_every_interface_language_has_a_catalog() -> None:
    languages = {path.parents[1].name for path in script.catalog_paths()}

    assert languages == set(TRANSLATED_LANGUAGES)


@pytest.mark.parametrize("language", TRANSLATED_LANGUAGES)
def test_the_catalog_has_the_texts_of_the_template(language: str) -> None:
    template = message_ids(read_catalog(script.TEMPLATE_PATH))
    catalog = message_ids(read_catalog(catalog_path(language)))

    assert template - catalog == set(), "Texts missing from the catalog"
    assert catalog - template == set(), "Texts no longer in the template"


@pytest.mark.parametrize("language", TRANSLATED_LANGUAGES)
def test_every_text_is_translated_and_reviewed(language: str) -> None:
    assert script.pending_translations(catalog_path(language)) == []


@pytest.mark.parametrize("language", TRANSLATED_LANGUAGES)
def test_the_translations_keep_the_placeholders(language: str) -> None:
    path = catalog_path(language)

    assert compile_translations.check_placeholders(path, read_catalog(path)) == []


@pytest.mark.parametrize("language", TRANSLATED_LANGUAGES)
def test_the_compiled_catalog_is_up_to_date(language: str) -> None:
    path = catalog_path(language)
    with path.with_suffix(".mo").open("rb") as file:
        compiled = compile_translations.get_messages(read_mo(file))

    assert compiled == compile_translations.get_messages(read_catalog(path))
