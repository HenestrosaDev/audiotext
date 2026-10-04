#!/usr/bin/env bash
# Builds the app with PyInstaller in a new virtual environment, which is deleted
# afterwards to free disk space (the CUDA build of PyTorch takes several GB).
#
# Usage: build_bundle.sh <name>   The app is created in `build/<name>/`

set -euo pipefail

name="$1"
venv="build/venv-$name"

python -m venv "$venv"
if [[ $RUNNER_OS == "Windows" ]]; then
	python="$venv/Scripts/python.exe"
else
	python="$venv/bin/python"
fi

"$python" -m pip install --upgrade pip
"$python" -m pip install -r requirements.txt pyinstaller
"$python" -m PyInstaller audiotext.spec --noconfirm \
	--distpath "build/$name" --workpath "build/work-$name"

rm -rf "$venv" "build/work-$name"
