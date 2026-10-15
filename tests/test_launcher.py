import pytest

import launcher


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], False),
        (["transcribe", "a.mp3"], True),
        (["watch", "inbox"], True),
        (["check-update"], True),
        (["--version"], True),
        # macOS passes the serial number of the process to apps opened by Finder
        (["-psn_0_12345"], False),
    ],
)
def test_the_launcher_runs_the_cli_for_its_commands(
    argv: list[str], expected: bool
) -> None:
    assert launcher.is_cli(argv) is expected
