#!/usr/bin/env bash
# Builds the app with PyInstaller in a new virtual environment, which is deleted
# afterwards along with the cache of uv to free disk space (the CUDA build of PyTorch
# takes several GB).
#
# Usage: build_bundle.sh <name> <group>   The app is created in `build/<name>/`, with
#                                         the build of PyTorch of the dependency group
#                                         (`cpu` or `cuda`)

set -euo pipefail

name="$1"
group="$2"
export UV_PROJECT_ENVIRONMENT="build/venv-$name"

uv sync --locked --no-default-groups --group build --group "$group"
uv run --no-sync pyinstaller audiotext.spec --noconfirm \
	--distpath "build/$name" --workpath "build/work-$name"

rm -rf "$UV_PROJECT_ENVIRONMENT" "build/work-$name"
uv cache clean
