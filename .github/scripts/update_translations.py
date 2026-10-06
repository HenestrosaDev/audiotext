"""
Updates the translations of the interface after the texts of the code change:

1. Extracts the texts marked with `_()`, `N_()` and `L_()` into
   `res/locales/audiotext.pot`.
2. Merges the template into the catalog of each language (`audiotext.po`). New
   texts are left empty, and changed ones are marked as fuzzy with a guess.
3. Compiles each catalog into `audiotext.mo`, which the app reads, and checks that
   the translations keep the placeholders (with `compile_translations.py`). Fuzzy
   and empty translations are not compiled, so the app shows them in English.

Run it from the root of the project:

    python .github/scripts/update_translations.py

Then translate the empty and fuzzy entries that it lists, remove their `fuzzy`
flag, and run it again to compile them. `tests/test_translations.py` fails while
any catalog is out of date.
"""

import os
import sys
from pathlib import Path

from babel.messages.catalog import Message
from babel.messages.frontend import CommandLineInterface
from babel.messages.pofile import read_po

ROOT_PATH = Path(__file__).parents[2]
SRC_PATH = ROOT_PATH / "src"
LOCALES_PATH = ROOT_PATH / "res" / "locales"
TEMPLATE_PATH = LOCALES_PATH / "audiotext.pot"
DOMAIN = "audiotext"

sys.path.insert(0, str(SRC_PATH))
sys.path.insert(0, str(Path(__file__).parent))
import compile_translations  # noqa: E402

from utils.constants import APP_NAME, APP_VERSION  # noqa: E402

# Keywords that mark the texts to translate (see `utils/i18n.py`)
KEYWORDS = ["_", "N_", "L_"]


def extract(output_path: Path = TEMPLATE_PATH) -> None:
    """Extracts the texts of the code into a template."""
    pybabel(
        "extract",
        *[f"--keyword={keyword}" for keyword in KEYWORDS],
        "--no-default-keywords",
        f"--project={APP_NAME}",
        f"--version={APP_VERSION}",
        "--copyright-holder=HenestrosaDev",
        "--msgid-bugs-address=https://github.com/HenestrosaDev/audiotext/issues",
        f"--output-file={output_path}",
        # Relative, so the references of the texts don't include the local path
        str(SRC_PATH.relative_to(ROOT_PATH)),
    )


def update() -> None:
    """Merges the template into the catalog of each language."""
    pybabel(
        "update",
        f"--input-file={TEMPLATE_PATH}",
        f"--output-dir={LOCALES_PATH}",
        f"--domain={DOMAIN}",
        "--ignore-obsolete",
        "--update-header-comment",
    )


def compile_catalogs() -> list[str]:
    """
    Compiles the catalogs that changed, leaving out the fuzzy translations.

    :return: The errors of the translations whose placeholders don't match.
    """
    errors = []
    for catalog_path in catalog_paths():
        with catalog_path.open("rb") as file:
            catalog = read_po(file)
        errors += compile_translations.check_placeholders(catalog_path, catalog)
        compile_translations.compile_catalog(catalog_path, catalog)
    return errors


def end_with_one_newline(path: Path) -> None:
    """
    Removes the blank lines that pybabel leaves at the end of the files, which the
    `end-of-file-fixer` hook would remove anyway.
    """
    text = path.read_text(encoding="utf-8")
    path.write_text(text.rstrip("\n") + "\n", encoding="utf-8")


def pybabel(*args: str) -> None:
    os.chdir(ROOT_PATH)
    # Babel has no type hints
    CommandLineInterface().run(["pybabel", "--quiet", *args])  # type: ignore[no-untyped-call]


def catalog_paths() -> list[Path]:
    return sorted(LOCALES_PATH.glob(f"*/LC_MESSAGES/{DOMAIN}.po"))


def pending_translations(catalog_path: Path) -> list[str]:
    """The texts of a catalog that are not translated or need a review."""
    with catalog_path.open("rb") as file:
        catalog = read_po(file)

    return [
        message_id(message)
        for message in catalog
        if message.id and (message.fuzzy or not all(translations(message)))
    ]


def message_id(message: Message) -> str:
    """The text of a message (the singular one, if it has a plural)."""
    return message.id if isinstance(message.id, str) else message.id[0]


def translations(message: Message) -> list[str]:
    """The translations of a message (more than one if it has a plural)."""
    string = message.string
    if isinstance(string, (tuple, list)):
        return list(string)
    return [string or ""]


def main() -> None:
    extract()
    update()
    for path in [TEMPLATE_PATH, *catalog_paths()]:
        end_with_one_newline(path)
    errors = compile_catalogs()

    has_pending = False
    for catalog_path in catalog_paths():
        if pending := pending_translations(catalog_path):
            has_pending = True
            language = catalog_path.parents[1].name
            print(f"\n{language}: {len(pending)} text(s) to translate or review")
            for text in pending:
                print(f"  - {text!r}")

    for error in errors:
        print(error, file=sys.stderr)

    if has_pending or errors:
        sys.exit(1)
    print("All the catalogs are up to date.")


if __name__ == "__main__":
    main()
