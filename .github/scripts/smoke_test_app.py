"""
Opens the app built by PyInstaller and checks that it's still running after a while.
A module or a data file missing from `audiotext.spec` makes the app close as soon as
it's opened, which the build alone doesn't catch.

Usage: python smoke_test_app.py <path of the executable>
"""

import subprocess
import sys

# The time that the app needs to import its modules and open the window
STARTUP_SECONDS = 60


def main() -> int:
    executable = sys.argv[1]
    process = subprocess.Popen(
        [executable],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )

    try:
        output, _ = process.communicate(timeout=STARTUP_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        print(f"The app was still running after {STARTUP_SECONDS} s")
        return 0

    print(output)
    print(f"The app closed with exit code {process.returncode}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
