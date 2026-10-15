#!/usr/bin/env bash
# Builds the FFmpeg bundled with the macOS app. The one of Homebrew can't draw
# subtitles (it's built without libass), which burning them into videos needs.
#
# It's an LGPL build: without --enable-gpl, so without x264 and x265. The videos are
# encoded with VideoToolbox, the encoder of macOS, instead. The libraries it uses
# (libass, LAME and dav1d) are installed with Homebrew, and PyInstaller bundles them.
#
# To bundle it locally, build it and add it to PATH before building the app:
#
#   packaging/macos/build_ffmpeg.sh
#   export PATH="$PWD/build/ffmpeg/bin:$PATH"
#   pyinstaller audiotext.spec --noconfirm
#
# Usage: packaging/macos/build_ffmpeg.sh [prefix]
#   prefix  Where FFmpeg is installed (default: build/ffmpeg)

set -euo pipefail

version="9.0.2"
# Of the release, whose signature was verified with the FFmpeg release signing key
# (FCF986EA15E6E293A5644F10B4322F04D67658D8)
sha256="8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e"

prefix="$(mkdir -p "${1:-build/ffmpeg}" && cd "${1:-build/ffmpeg}" && pwd)"
source_dir="$(mktemp -d)"
trap 'rm -rf "$source_dir"' EXIT

# Without upgrading the installed ones, nor what depends on them
HOMEBREW_NO_INSTALL_UPGRADE=1 HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1 \
    brew install pkgconf libass lame dav1d
brew_prefix="$(brew --prefix)"

curl -fsSL "https://ffmpeg.org/releases/ffmpeg-$version.tar.xz" -o "$source_dir/ffmpeg.tar.xz"
echo "$sha256  $source_dir/ffmpeg.tar.xz" | shasum -a 256 --check --quiet
tar -xf "$source_dir/ffmpeg.tar.xz" -C "$source_dir" --strip-components 1

# Only the libraries given are used, not the ones found installed, so the build is
# the same on any Mac. LAME has no pkg-config file, so it's found in the folders of
# Homebrew. FFmpeg's own libraries are linked statically, so only the ones of
# Homebrew are bundled along with ffmpeg and ffprobe
cd "$source_dir"
./configure \
    --prefix="$prefix" \
    --extra-version=audiotext \
    --disable-debug \
    --disable-doc \
    --disable-ffplay \
    --disable-autodetect \
    --extra-cflags="-I$brew_prefix/include" \
    --extra-ldflags="-L$brew_prefix/lib" \
    --enable-libass \
    --enable-libmp3lame \
    --enable-libdav1d \
    --enable-videotoolbox \
    --enable-audiotoolbox \
    --enable-zlib \
    --enable-bzlib
make -j "$(sysctl -n hw.ncpu)"
make install

# What the app needs from this build, and what it must not have
configuration=$("$prefix/bin/ffmpeg" -hide_banner -buildconf)
if grep -qE -- "--enable-(gpl|nonfree)" <<< "$configuration"; then
    echo "The build isn't LGPL" >&2
    exit 1
fi
filters=$("$prefix/bin/ffmpeg" -hide_banner -filters)
encoders=$("$prefix/bin/ffmpeg" -hide_banner -encoders)
grep -qw subtitles <<< "$filters"
grep -qw h264_videotoolbox <<< "$encoders"
grep -qw libmp3lame <<< "$encoders"

echo "Built FFmpeg $version in $prefix"
