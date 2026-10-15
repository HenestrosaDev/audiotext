"""
Starts the app built by PyInstaller: its window, or its command-line interface if
it's run with one of its commands (e.g. `Audiotext transcribe talk.mp3`), so the
installed app can be used from scripts too.

From the source code, `app.py` and `cli.py` are run instead.
"""

import multiprocessing
import sys

# The arguments that run the command-line interface instead of the window
CLI_ARGUMENTS = {"transcribe", "watch", "check-update", "--version", "-h", "--help"}


def is_cli(argv: list[str]) -> bool:
    """:param argv: The arguments, without the program name."""
    return bool(argv) and argv[0] in CLI_ARGUMENTS


def main() -> None:
    # The bundled app is also run for the helper processes of multiprocessing (e.g.
    # the resource tracker used by PyTorch), which would otherwise open another
    # window. It returns right away in the main process
    multiprocessing.freeze_support()

    # Imported here, since each one takes a while and needs different modules
    if is_cli(sys.argv[1:]):
        import cli

        cli.main()
    else:
        import app

        app.main()


if __name__ == "__main__":
    main()
