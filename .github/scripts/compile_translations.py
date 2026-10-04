"""
Compiles the `.po` files of `res/locales` into the `.mo` files that the app loads,
and checks that the translations keep the placeholders (e.g. `{count}`) of the
original text, since a missing one makes `str.format` raise an error.

Only the `.mo` files whose messages differ from their `.po` are rewritten, so the
files compiled with another tool (e.g. `msgfmt`) aren't changed for nothing. Exits
with an error if a `.mo` was rewritten or a placeholder doesn't match, so it can be
run as a pre-commit hook and in the workflows.
"""

import io
import re
import sys
from pathlib import Path

from babel.messages.catalog import Catalog
from babel.messages.mofile import read_mo, write_mo
from babel.messages.pofile import read_po

ROOT_PATH = Path(__file__).parents[2]
LOCALES_PATH = ROOT_PATH / "res" / "locales"
PLACEHOLDER = re.compile(r"\{[^{}]*\}")

# The singular and plural forms of the original text, and its context
MessageKey = tuple[tuple[str, ...], str | None]


def as_tuple(value: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Babel uses a string for the messages without plural forms."""
    return (value,) if isinstance(value, str) else tuple(value)


def get_messages(catalog: Catalog) -> dict[MessageKey, tuple[str, ...]]:
    """
    :return: The translated messages of the catalog, without the header.
    """
    return {
        (as_tuple(message.id), message.context): as_tuple(message.string)
        for message in catalog
        if message.id and message.string and not message.fuzzy
    }


def check_placeholders(po_path: Path, catalog: Catalog) -> list[str]:
    """
    :return: The errors of the messages whose translation has other placeholders.
    """
    errors = []
    for (original, _), translations in get_messages(catalog).items():
        expected = set(PLACEHOLDER.findall(original[0]))
        for translation in translations:
            if set(PLACEHOLDER.findall(translation)) != expected:
                errors.append(
                    f"{po_path.relative_to(ROOT_PATH)}: the translation of "
                    f"{original[0]!r} should contain {sorted(expected)}: "
                    f"{translation!r}"
                )
    return errors


def compile_catalog(po_path: Path, catalog: Catalog) -> bool:
    """
    Writes the `.mo` file of the catalog if it's missing or out of date.

    :return: Whether the `.mo` file was written.
    """
    mo_path = po_path.with_suffix(".mo")
    compiled = io.BytesIO()
    write_mo(compiled, catalog)

    if mo_path.is_file():
        with mo_path.open("rb") as file:
            current = get_messages(read_mo(file))
        compiled.seek(0)
        if current == get_messages(read_mo(compiled)):
            return False

    mo_path.write_bytes(compiled.getvalue())
    return True


def main() -> int:
    errors: list[str] = []
    compiled_paths: list[Path] = []

    for po_path in sorted(LOCALES_PATH.glob("*/LC_MESSAGES/*.po")):
        with po_path.open("rb") as file:
            catalog = read_po(file)
        errors += check_placeholders(po_path, catalog)
        if compile_catalog(po_path, catalog):
            compiled_paths.append(po_path.with_suffix(".mo"))

    for path in compiled_paths:
        print(f"Compiled {path.relative_to(ROOT_PATH)}")
    for error in errors:
        print(error, file=sys.stderr)

    return 1 if errors or compiled_paths else 0


if __name__ == "__main__":
    sys.exit(main())
