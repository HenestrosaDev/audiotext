#!/usr/bin/env bash
# Installs Audiotext for the current user, adding it to the applications menu.
# `packaging/linux.sh` includes it in the Linux archive as `install.sh`.
#
# The app included is the CPU build. If there's an NVIDIA GPU, it offers to download
# the GPU add-on from the GitHub release, which turns it into the GPU (CUDA) build.
#
# Usage: ./install.sh [--gpu | --cpu]   Install (asks about the GPU if not specified)
#        ./install.sh --uninstall       Uninstall (the settings are kept)

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
app_dir="$data_home/audiotext"
bin_link="$HOME/.local/bin/audiotext"
desktop_file="$data_home/applications/audiotext.desktop"

uninstall() {
	rm -rf "$app_dir"
	rm -f "$bin_link" "$desktop_file"
	echo "Audiotext has been uninstalled."
}

ask_gpu() {
	local answer default="n"
	if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
		default="y"
	fi
	# Without a terminal (e.g. a script), only what's detected is used
	if [[ ! -t 0 ]]; then
		[[ $default == "y" ]]
		return
	fi
	local size
	size=$(awk '{ total += $2 } END { printf "%.1f GB", total / 1e9 }' "$here/gpu-addon.txt")
	if [[ $default == "y" ]]; then
		read -r -p "Use the NVIDIA GPU (CUDA) to transcribe faster? It downloads $size. [Y/n] " answer
	else
		echo "No NVIDIA GPU was detected."
		read -r -p "Use an NVIDIA GPU (CUDA) to transcribe faster anyway? It downloads $size. [y/N] " answer
	fi
	answer="${answer:-$default}"
	[[ ${answer,,} == y* ]]
}

install_gpu_addon() {
	local tmp_dir sha size url name
	tmp_dir="$(mktemp -d)"
	trap 'rm -rf "$tmp_dir"' RETURN

	while read -r sha size url; do
		name="${url##*/}"
		echo "Downloading $name..."
		curl -fL --retry 3 --progress-bar -o "$tmp_dir/$name" "$url"
		echo "$sha  $tmp_dir/$name" | sha256sum --check --quiet -
		# tar detects the compression of the archive (xz)
		tar -xf "$tmp_dir/$name" -C "$app_dir"
		rm "$tmp_dir/$name"
	done <"$here/gpu-addon.txt"

	# Deletes the files of the CPU build that aren't in the GPU build
	while IFS= read -r path; do
		[[ -n $path ]] && rm -f -- "$app_dir/$path"
	done <"$app_dir/gpu-addon-remove.txt"
	rm -f "$app_dir/gpu-addon-remove.txt"
}

gpu="ask"
case "${1:-}" in
	--uninstall)
		uninstall
		exit 0
		;;
	--gpu) gpu="yes" ;;
	--cpu) gpu="no" ;;
	"") ;;
	*)
		sed -n '2,10s/^# \{0,1\}//p' "$0"
		exit 1
		;;
esac

if [[ $gpu == "ask" ]]; then
	if [[ -f "$here/gpu-addon.txt" ]] && ask_gpu; then gpu="yes"; else gpu="no"; fi
fi

echo "Installing Audiotext in $app_dir..."
rm -rf "$app_dir"
mkdir -p "$(dirname "$app_dir")"
cp -a "$here/Audiotext" "$app_dir"

if [[ $gpu == "yes" ]]; then
	install_gpu_addon
fi

mkdir -p "$(dirname "$bin_link")" "$(dirname "$desktop_file")"
ln -sf "$app_dir/Audiotext" "$bin_link"
cat >"$desktop_file" <<EOF
[Desktop Entry]
Type=Application
Name=Audiotext
Comment=Transcribe audio and video files, YouTube videos and microphone recordings
Exec="$app_dir/Audiotext"
Icon=$app_dir/_internal/res/img/icon-light.png
Terminal=false
Categories=AudioVideo;Audio;Utility;
EOF

echo "Audiotext has been installed. Open it from the applications menu or run 'audiotext'."
