"""
Creates the GPU add-on of a release from the CPU and the CUDA (GPU) builds of the app.

The installers include the CPU build, which is a fraction of the size of the GPU one.
When the user chooses GPU acceleration, they download the add-on and extract it over
the CPU build, which turns it into the GPU build. The add-on contains:

- The files that are new or different in the GPU build, split into archives that fit
  in a GitHub release asset (2 GiB at most).
- `gpu-addon-remove.txt`, in the first archive, with the files of the CPU build that
  aren't in the GPU build and must be deleted after extracting the archives.

It also writes:

- A manifest with a `<SHA-256> <size> <URL>` line per archive (`--manifest`), which
  the Linux installer reads.
- An Inno Setup include file (`--iss`), which the Windows installer uses.
"""

import argparse
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

MAX_ASSET_SIZE = 2 * 1024**3
# Compressed bytes per archive, as the sum of the compressed size of its files. 7z
# compresses each file on its own (not solid) and xz in independent blocks, so an
# archive is about as big as that sum. The margin covers the difference
MAX_PART_SIZE = int(MAX_ASSET_SIZE * 0.97)
# The files are compressed one by one to measure them, except the smaller ones, which
# are thousands. Their uncompressed size is used, which is bigger
MIN_MEASURED_SIZE = 1024**2
REMOVE_LIST_NAME = "gpu-addon-remove.txt"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def scan(root: Path) -> dict[str, Path]:
    """Returns the files and symbolic links of a build by their relative path."""
    entries = {}
    for dir_path, dir_names, file_names in os.walk(root):
        for name in dir_names + file_names:
            path = Path(dir_path, name)
            # Directories are created when their files are extracted
            if path.is_symlink() or path.is_file():
                entries[path.relative_to(root).as_posix()] = path
    return entries


def is_same(cpu_path: Path, gpu_path: Path) -> bool:
    if cpu_path.is_symlink() or gpu_path.is_symlink():
        return (
            cpu_path.is_symlink()
            and gpu_path.is_symlink()
            and os.readlink(cpu_path) == os.readlink(gpu_path)
        )
    if cpu_path.stat().st_size != gpu_path.stat().st_size:
        return False
    return sha256(cpu_path) == sha256(gpu_path)


def entry_size(path: Path) -> int:
    return 0 if path.is_symlink() else path.stat().st_size


def split_into_parts(sizes: dict[str, int], max_size: int) -> list[list[str]]:
    """Distributes the files into archives of `max_size` (first-fit decreasing)."""
    parts: list[list[str]] = []
    part_sizes: list[int] = []
    for rel_path in sorted(sizes, key=lambda p: sizes[p], reverse=True):
        size = sizes[rel_path]
        for i, part_size in enumerate(part_sizes):
            if part_size + size <= max_size:
                parts[i].append(rel_path)
                part_sizes[i] += size
                break
        else:
            parts.append([rel_path])
            part_sizes.append(size)
    return parts


def create_archive(root: Path, rel_paths: list[str], archive: Path, fmt: str) -> None:
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".txt", delete=False
    ) as list_file:
        list_file.write("\n".join(rel_paths) + "\n")

    try:
        if fmt == "7z":
            # Not solid, which Inno Setup recommends for a faster extraction
            command = ["7z", "a", "-t7z", "-mx=5", "-ms=off", "-mmt=on", "-scsUTF-8"]
            command += [str(archive.resolve()), f"@{list_file.name}"]
        else:
            # xz (LZMA2, like 7z) makes the CUDA libraries much smaller than gzip. -T0
            # compresses with all the cores
            command = ["tar", "-cf", str(archive.resolve()), "--no-recursion"]
            command += ["--use-compress-program=xz -6 -T0", "-T", list_file.name]
        subprocess.run(command, cwd=root, check=True)
    finally:
        os.unlink(list_file.name)


def compressed_sizes(root: Path, rel_paths: list[str], fmt: str) -> dict[str, int]:
    """Returns the size of each file once compressed in an archive of its own."""
    sizes = {}
    with tempfile.TemporaryDirectory() as tmp_dir:
        archive = Path(tmp_dir, f"file.{fmt}")
        for rel_path in rel_paths:
            size = entry_size(root / rel_path)
            if size >= MIN_MEASURED_SIZE:
                create_archive(root, [rel_path], archive, fmt)
                size = archive.stat().st_size
                archive.unlink()
            sizes[rel_path] = size
    return sizes


def format_size(size: int) -> str:
    return f"{size / 1000**3:.1f} GB"


def write_iss(path: Path, archives: list[tuple[Path, str, int, str]]) -> None:
    total_size = sum(size for _, _, size, _ in archives)
    lines = [
        "; Generated by .github/scripts/make_gpu_addon.py",
        f'#define GpuDownloadSize "{format_size(total_size)}"',
        "",
        "[Files]",
    ]
    lines += [
        f'Source: "{{tmp}}\\{archive.name}"; DestDir: "{{app}}"; '
        "Flags: external extractarchive recursesubdirs createallsubdirs "
        "ignoreversion; Tasks: gpu"
        for archive, _, _, _ in archives
    ]
    lines += [
        "",
        "[Code]",
        "procedure AddGpuDownloads(Page: TDownloadWizardPage);",
        "begin",
    ]
    lines += [
        f"  Page.Add('{url}', '{archive.name}', '{digest}');"
        for archive, digest, _, url in archives
    ]
    lines += ["end;", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cpu", type=Path, required=True, help="CPU build")
    parser.add_argument("--gpu", type=Path, required=True, help="GPU build")
    parser.add_argument("--out", type=Path, required=True, help="archives directory")
    parser.add_argument("--name", required=True, help="archives name, e.g. App-gpu")
    parser.add_argument("--format", choices=["7z", "tar.xz"], required=True)
    parser.add_argument("--url-base", required=True, help="URL of the release assets")
    parser.add_argument("--manifest", type=Path, help="manifest file to write")
    parser.add_argument("--iss", type=Path, help="Inno Setup include file to write")
    args = parser.parse_args()

    cpu_entries = scan(args.cpu)
    gpu_entries = scan(args.gpu)

    changed = {
        rel_path: path
        for rel_path, path in gpu_entries.items()
        if rel_path not in cpu_entries or not is_same(cpu_entries[rel_path], path)
    }
    removed = sorted(set(cpu_entries) - set(gpu_entries))
    print(f"{len(changed)} files to add or replace, {len(removed)} to remove")

    # The GPU build is only used to create the add-on, so the list can be written there
    remove_list = args.gpu / REMOVE_LIST_NAME
    remove_list.write_text("".join(f"{p}\n" for p in removed), encoding="utf-8")

    sizes = compressed_sizes(args.gpu, sorted(changed), args.format)
    print(f"{format_size(sum(sizes.values()))} once compressed")

    args.out.mkdir(parents=True, exist_ok=True)
    max_size = MAX_PART_SIZE
    for _ in range(3):
        parts = split_into_parts(sizes, max_size)
        parts[0].insert(0, REMOVE_LIST_NAME)
        archives = []
        for i, rel_paths in enumerate(parts, start=1):
            archive = args.out / f"{args.name}-{i}.{args.format}"
            create_archive(args.gpu, rel_paths, archive, args.format)
            size = archive.stat().st_size
            url = f"{args.url_base.rstrip('/')}/{archive.name}"
            archives.append((archive, sha256(archive), size, url))
            print(f"{archive.name}: {len(rel_paths)} files, {format_size(size)}")
        if all(size <= MAX_ASSET_SIZE for _, _, size, _ in archives):
            break
        # The archives are bigger than measured, so they're created again smaller
        for archive, _, _, _ in archives:
            archive.unlink()
        max_size = int(max_size * 0.95)
        print("An archive is bigger than a GitHub release asset, splitting again")
    else:
        raise SystemExit("The archives are still bigger than a GitHub release asset")

    if args.manifest:
        args.manifest.write_text(
            "".join(f"{digest} {size} {url}\n" for _, digest, size, url in archives),
            encoding="utf-8",
        )
    if args.iss:
        write_iss(args.iss, archives)


if __name__ == "__main__":
    main()
