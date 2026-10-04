#!/usr/bin/env bash
# Creates the macOS disk image of Audiotext, where the app can be dragged into the
# Applications folder.
#
# To create it locally, build the app and run this script from the root of the project:
#
#   pyinstaller audiotext.spec --noconfirm
#   packaging/macos.sh
#
# Usage: packaging/macos.sh [app] [output directory]
#   app               The app built by PyInstaller (default: dist/Audiotext.app)
#   output directory  Where the disk image is created (default: dist)

set -euo pipefail

app="${1:-dist/Audiotext.app}"
out_dir="${2:-dist}"

version=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -n 1)
name="Audiotext-$version-macos-$(uname -m)"

# Fails if PyInstaller didn't sign the app properly, which macOS reports as "damaged"
codesign --verify --deep --strict "$app"

staging_dir="$(mktemp -d)"
trap 'rm -rf "$staging_dir"' EXIT
ditto "$app" "$staging_dir/Audiotext.app"
ln -s /Applications "$staging_dir/Applications"

mkdir -p "$out_dir"
hdiutil create -volname Audiotext -srcfolder "$staging_dir" -format UDZO -ov "$out_dir/$name.dmg"
echo "Created $out_dir/$name.dmg"
