#!/usr/bin/env bash
# Creates the Linux archive of Audiotext, which contains the app and its installer
# (`linux-install.sh`, renamed to `install.sh`).
#
# To create it locally, build the app and run this script from the root of the project:
#
#   pyinstaller audiotext.spec --noconfirm
#   packaging/linux.sh
#
# Usage: packaging/linux.sh [app] [output directory] [GPU add-on manifest]
#   app                 The app built by PyInstaller (default: dist/Audiotext)
#   output directory    Where the archive is created (default: dist)
#   GPU add-on manifest Created by `.github/scripts/make_gpu_addon.py`. Without it, the
#                       installer doesn't offer GPU acceleration (default: none)

set -euo pipefail

app="${1:-dist/Audiotext}"
out_dir="${2:-dist}"
gpu_manifest="${3:-}"

version=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -n 1)
name="Audiotext-$version-linux-$(uname -m)"

staging_dir="$(mktemp -d)"
trap 'rm -rf "$staging_dir"' EXIT
mkdir "$staging_dir/$name"
cp -a "$app" "$staging_dir/$name/Audiotext"
cp packaging/linux-install.sh "$staging_dir/$name/install.sh"
if [[ -n $gpu_manifest ]]; then
	cp "$gpu_manifest" "$staging_dir/$name/gpu-addon.txt"
fi

mkdir -p "$out_dir"
tar -czf "$out_dir/$name.tar.gz" -C "$staging_dir" "$name"
echo "Created $out_dir/$name.tar.gz"
