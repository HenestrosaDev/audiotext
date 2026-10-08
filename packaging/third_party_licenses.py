"""
Writes the licenses of the third-party software bundled with the app, which most of
them require to distribute along with it:

- The Python packages of `pyproject.toml` and their dependencies.
- Python and Tcl/Tk.
- FFmpeg and FFprobe, and FLAC if it's installed (see `audiotext.spec`).
- The native libraries bundled from the system (e.g. those of FFmpeg), with the package
  and version they come from.

Some of them are GPL or LGPL (e.g. FFmpeg, also the one included in PyAV), so the
notice starts with an offer of their source code and ends with the full text of those
licenses.

`packaging/licenses/` contains the texts of the licenses that aren't always installed
along with the software.

`audiotext.spec` calls it when building the app. To check the result:

    python packaging/third_party_licenses.py [output file]
"""

import re
import shutil
import subprocess
import sys
import sysconfig
from collections.abc import Iterable
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent
LICENSE_TEXTS_DIR = Path(__file__).resolve().parent / "licenses"

# The files of a package that contain its license, or the licenses of the code it
# includes (e.g. `LICENSE`, `LICENSE-MIT.txt`, `COPYING.LESSER` or `NOTICE`)
LICENSE_FILE_PATTERN = re.compile(r"^(licen[cs]e|copying|notice|copyright)", re.I)
NON_LICENSE_SUFFIXES = {".py", ".pyc", ".pyi", ".so", ".pyd", ".dll", ".dylib", ".h"}

# The licenses whose full text is included, since some of the bundled software (or the
# libraries it's built with) is distributed under each of them
GPL_LICENSE_IDS = ["GPL-2.0", "GPL-3.0", "LGPL-2.1", "LGPL-3.0"]

SOURCE_CODE_EMAIL = "info@getaudiotext.com"

SEPARATOR = "=" * 80


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _section(title: str, *parts: str) -> str:
    return "\n\n".join([SEPARATOR, title, SEPARATOR, *parts])


def _required_distributions() -> list[metadata.Distribution]:
    """Returns the installed packages of `pyproject.toml` and their dependencies."""
    with (ROOT / "pyproject.toml").open("rb") as file:
        dependencies: list[str] = tomllib.load(file)["project"]["dependencies"]
    pending = [Requirement(dependency) for dependency in dependencies]

    distributions: dict[str, metadata.Distribution] = {}
    # The extras of each package already processed, to process it again if another
    # package requires an extra that adds more dependencies
    processed_extras: dict[str, set[str]] = {}

    while pending:
        requirement = pending.pop()
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue

        name = canonicalize_name(requirement.name)
        extras = {""} | set(requirement.extras)
        if extras <= processed_extras.get(name, set()):
            continue
        processed_extras.setdefault(name, set()).update(extras)

        try:
            distribution = metadata.distribution(requirement.name)
        except metadata.PackageNotFoundError:
            continue
        distributions[name] = distribution

        for dependency in map(Requirement, distribution.requires or []):
            if not dependency.marker or any(
                dependency.marker.evaluate({"extra": extra}) for extra in extras
            ):
                # Without the marker, since it's already been evaluated
                dependency.marker = None
                pending.append(dependency)

    return sorted(distributions.values(), key=lambda d: d.metadata["Name"].lower())


def _license_name(distribution: metadata.Distribution) -> str:
    package_metadata = distribution.metadata
    if expression := package_metadata.get("License-Expression"):
        return expression
    # Some packages put the whole text of the license in this field
    license_field = (package_metadata.get("License") or "").strip()
    if license_field and "\n" not in license_field and len(license_field) < 100:
        return license_field
    classifiers = [
        classifier.split("::")[-1].strip()
        for classifier in package_metadata.get_all("Classifier") or []
        if classifier.startswith("License ::")
    ]
    return ", ".join(classifiers) or "See the license below"


def _package_section(distribution: metadata.Distribution) -> str:
    package_metadata = distribution.metadata
    header = [f"License: {_license_name(distribution)}"]
    if url := package_metadata.get("Home-page") or next(
        (
            url.split(",", 1)[-1].strip()
            for url in package_metadata.get_all("Project-URL") or []
        ),
        None,
    ):
        header.append(f"Website: {url}")

    license_paths = sorted(
        {
            Path(str(distribution.locate_file(file)))
            for file in distribution.files or []
            if LICENSE_FILE_PATTERN.match(file.name)
            and file.suffix.lower() not in NON_LICENSE_SUFFIXES
        }
    )
    texts = [
        f"--- {path.name} ---\n\n{_read(path)}"
        for path in license_paths
        if path.is_file()
    ]

    return _section(
        f"{package_metadata['Name']} {package_metadata['Version']}",
        "\n".join(header),
        *texts,
    )


def _python_section() -> str:
    candidates = [
        Path(sysconfig.get_path("stdlib"), "LICENSE.txt"),
        Path(sys.base_prefix, "LICENSE.txt"),
    ]
    texts = [_read(path) for path in candidates if path.is_file()][:1]
    return _section(
        f"Python {sys.version.split()[0]}",
        "License: PSF-2.0\nWebsite: https://docs.python.org/3/license.html",
        *texts,
    )


def _tcl_tk_section() -> str:
    # Some builds of Python don't include the license of Tcl/Tk, which is the same for
    # both
    import tkinter

    return _section(
        f"Tcl/Tk {tkinter.TclVersion}",
        "License: TCL\nWebsite: https://www.tcl-lang.org/software/tcltk/license.html",
        _read(LICENSE_TEXTS_DIR / "TCL.txt"),
    )


def _source_code_offer_section() -> str:
    return _section(
        "Source code offer",
        "Some of the software included with Audiotext is distributed under the GNU "
        "General Public License (GPL) or the GNU Lesser General Public License (LGPL), "
        "such as FFmpeg and the libraries it's built with (including the ones bundled "
        "in the PyAV package) and FLAC. The source code of most of them can be "
        "downloaded from the links of their sections.",
        "For at least three years after the release of this version of Audiotext, José "
        "Carlos López Henestrosa will give anyone who asks for it a copy of the "
        "complete corresponding source code of that software, either by download at no "
        "charge or on a physical medium customarily used for software interchange for "
        "no more than the cost of performing the distribution. To ask for it, write to "
        f"{SOURCE_CODE_EMAIL} with the version of Audiotext and the system it's for.",
        "The versions of that software are listed in their sections and in "
        '"Native libraries".',
    )


def _ffmpeg_section() -> str | None:
    if not (ffmpeg_path := shutil.which("ffmpeg")):
        return None
    output = subprocess.run(
        [ffmpeg_path, "-version"], capture_output=True, text=True, check=True
    ).stdout
    version_match = re.search(r"^ffmpeg version (\S+)", output, re.M)
    version = version_match.group(1) if version_match else "unknown"
    configuration_match = re.search(r"^configuration: (.*)$", output, re.M)
    configuration = configuration_match.group(1) if configuration_match else ""

    if "--enable-nonfree" in configuration:
        raise RuntimeError(
            "The FFmpeg build is configured with --enable-nonfree, so it can't be "
            "distributed. Install a build without it."
        )
    is_gpl = "--enable-gpl" in configuration
    is_version_3 = "--enable-version3" in configuration
    license_id = {
        (True, True): "GPL-3.0",
        (True, False): "GPL-2.0",
        (False, True): "LGPL-3.0",
        (False, False): "LGPL-2.1",
    }[(is_gpl, is_version_3)]

    # Release builds start with the version (e.g. `7.1.1-full_build-www.gyan.dev` or
    # `6.1.1-3ubuntu5`), while development builds don't (e.g. `N-118000-g1234567`)
    if release := re.match(r"\d+(\.\d+)*", version):
        source = f"https://ffmpeg.org/releases/ffmpeg-{release.group(0)}.tar.xz"
    else:
        source = "https://ffmpeg.org/download.html#get-sources"

    return _section(
        f"FFmpeg {version} (ffmpeg and ffprobe)",
        f"License: {license_id}-or-later (the full text is at the end of this file), "
        'including the libraries it\'s built with (see "Native libraries")\n'
        "Website: https://ffmpeg.org\n"
        f"Source code: {source}\n"
        f"Build configuration: {configuration or 'unknown'}",
    )


def _flac_section() -> str | None:
    if not (flac_path := shutil.which("flac")):
        return None
    output = subprocess.run(
        [flac_path, "--version"], capture_output=True, text=True, check=True
    ).stdout
    version = output.split()[-1]
    return _section(
        f"FLAC {version} (flac)",
        "License: GPL-2.0-or-later (the full text is at the end of this file)\n"
        "Website: https://xiph.org/flac/\n"
        f"Source code: https://ftp.osuosl.org/pub/xiph/releases/flac/flac-{version}.tar.xz",
    )


def _library_origin(path: Path) -> str:
    """Returns the package and version that a native library comes from."""
    resolved_path = path.resolve()
    # e.g. `/opt/homebrew/Cellar/x264/r3222/lib/libx264.164.dylib`
    if match := re.search(r"/Cellar/([^/]+)/([^/]+)/", resolved_path.as_posix()):
        return f"Homebrew package {match.group(1)} {match.group(2)}"

    if shutil.which("dpkg-query"):
        # dpkg knows the files by the path they're installed at, which may be a
        # symbolic link or omit `/usr` (e.g. `/lib/x86_64-linux-gnu/libx264.so.164`)
        candidates = {str(path), str(resolved_path)}
        if resolved_path.as_posix().startswith("/usr/"):
            candidates.add(resolved_path.as_posix().removeprefix("/usr"))
        for candidate in sorted(candidates):
            result = subprocess.run(
                ["dpkg", "-S", candidate], capture_output=True, text=True
            )
            if result.returncode == 0:
                package = result.stdout.split(":", 1)[0]
                package_version = subprocess.run(
                    ["dpkg-query", "-W", "-f=${Version}", package],
                    capture_output=True,
                    text=True,
                ).stdout
                return f"Debian package {package} {package_version}"

    return str(path)


def _native_libraries_section(binary_paths: Iterable[str]) -> str | None:
    """
    Lists the native libraries that come from the system and not from Python or its
    packages (e.g. FFmpeg and the libraries it's built with).
    """
    python_paths = {
        Path(path).resolve()
        for path in [
            sys.prefix,
            sys.base_prefix,
            sysconfig.get_paths()["purelib"],
            sysconfig.get_paths()["platlib"],
        ]
    }
    system_paths = sorted(
        {
            Path(path)
            for path in binary_paths
            if not any(Path(path).resolve().is_relative_to(p) for p in python_paths)
        },
        key=lambda path: path.name.lower(),
    )
    if not system_paths:
        return None
    return _section(
        "Native libraries",
        "The native libraries bundled from the system that built this version of "
        "Audiotext, and the package they come from. The ones that come from the Python "
        "packages are covered by the sections of those packages.",
        "\n".join(f"{path.name}: {_library_origin(path)}" for path in system_paths),
    )


def write_third_party_licenses(
    output_path: Path, binary_paths: Iterable[str] = ()
) -> None:
    """
    Writes the notice to `output_path`. `binary_paths` are the native libraries and
    executables bundled with the app, as PyInstaller finds them.
    """
    sections = [
        "This file contains the licenses of the third-party software included with "
        "Audiotext.",
        _source_code_offer_section(),
        _python_section(),
        _tcl_tk_section(),
    ]
    sections += filter(
        None,
        [
            _ffmpeg_section(),
            _flac_section(),
            _native_libraries_section(binary_paths),
        ],
    )
    sections += [_package_section(d) for d in _required_distributions()]
    sections += [
        _section(license_id, _read(LICENSE_TEXTS_DIR / f"{license_id}.txt"))
        for license_id in GPL_LICENSE_IDS
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n\n\n".join(sections) + "\n", encoding="utf-8")


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "build/THIRD_PARTY_LICENSES.txt")
    write_third_party_licenses(path)
    print(f"Created {path}")
