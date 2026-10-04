# -*- mode: python ; coding: utf-8 -*-
import platform
import re
import shutil
import sysconfig
from pathlib import Path

from PyInstaller.compat import is_darwin, is_win
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

import sys ; sys.setrecursionlimit(sys.getrecursionlimit() * 5)

sys.path.insert(0, "packaging")
from third_party_licenses import write_third_party_licenses

# The version of the app, which is set in `pyproject.toml`
version = re.search(
    r'^version = "(.+)"', Path("pyproject.toml").read_text(encoding="utf-8"), re.M
).group(1)

# The packages of the environment that runs PyInstaller (e.g. `venv` or `.venv`)
site_packages_path = Path(sysconfig.get_paths()["purelib"])

datas = [
    ("LICENSE", "."),
    (f"{site_packages_path}/babel", "babel"),
    (f"{site_packages_path}/customtkinter", "customtkinter"),
    # The native tkdnd libraries that tkinterdnd2 loads to drop files on the window
    (f"{site_packages_path}/tkinterdnd2", "tkinterdnd2"),
    (f"{site_packages_path}/transformers", "transformers"),
    (f"{site_packages_path}/lightning", "lightning"),
    (f"{site_packages_path}/lightning_fabric", "lightning_fabric"),
    (f"{site_packages_path}/pyannote", "pyannote"),
    (f"{site_packages_path}/asteroid_filterbanks", "asteroid_filterbanks"),
    (f"{site_packages_path}/whisperx", "whisperx"),
    ("res", "res"),
    ("config.ini", "."),
    # The template of the Word documents
    *collect_data_files("docx"),
    # keyring finds the credential store of the system through its metadata
    *copy_metadata("keyring"),
]

hiddenimports = [
    "huggingface_hub.repository",
    "sklearn.utils._cython_blas",
    "sklearn.neighbors.quad_tree",
    "sklearn.tree",
    "sklearn.tree._utils",
    # Imported by PIL.ImageTk on Linux when Tk doesn't find its image command
    "PIL._tkinter_finder",
    # The credential stores of each system, which keyring imports dynamically
    *collect_submodules("keyring.backends"),
]

block_cipher = None

is_debug = False
if is_debug:
    options = [("v", None, "OPTION")]
else:
    options = []


def find_executable(name, required=True):
    """Returns the path of an executable in PATH to bundle it."""
    path = shutil.which(name)
    if path is None:
        if required:
            raise SystemExit(f"{name} isn't installed")
        return None
    # Chocolatey adds shims to PATH (in `C:\ProgramData\chocolatey\bin`), which run the
    # executables from where the package is installed and so only work on this computer
    if Path(path).parent.parent.name.lower() == "chocolatey":
        raise SystemExit(
            f"{path} is a shim of Chocolatey. Add the directory of the actual executable "
            "to PATH (e.g. `C:\\ProgramData\\chocolatey\\lib\\ffmpeg\\tools\\ffmpeg\\bin`)"
        )
    return path


binaries = [
    (find_executable("ffmpeg"), "."),
    (find_executable("ffprobe"), "."),
]

if flac_path := find_executable("flac", required=False):
    binaries += [(flac_path, ".")]

a = Analysis(
    ["src/app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# The licenses of the bundled software, which most of them require to include. It's
# written after the analysis, since it lists the native libraries that are bundled
third_party_licenses_path = Path(workpath, "THIRD_PARTY_LICENSES.txt")
write_third_party_licenses(
    third_party_licenses_path, binary_paths=[source for _, source, _ in a.binaries]
)
a.datas += [("THIRD_PARTY_LICENSES.txt", str(third_party_licenses_path), "DATA")]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

macos_icon = "res/macos/icon.icns"
windows_icon = "res/windows/icon.ico"

exe = EXE(
    pyz,
    a.scripts,
    options,
    exclude_binaries=True,
    name="Audiotext",
    debug=is_debug,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=is_debug,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file="res/macos/entitlements.plist" if is_darwin else None,
    icon=windows_icon if is_win else macos_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Audiotext",
)

app = BUNDLE(
    coll,
    name="Audiotext.app",
    icon=macos_icon,
    bundle_identifier="com.henestrosadev.audiotext",
    version=version,
    info_plist={
        # The bundled binaries (e.g. FFmpeg) only run on the macOS version that built
        # them or later
        "LSMinimumSystemVersion": ".".join(platform.mac_ver()[0].split(".")[:2]) if is_darwin else "",
        "NSPrincipalClass": "NSApplication",
        "NSAppleScriptEnabed": False,
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "Allow Audiotext to record audio from your microphone to generate transcriptions.",
    }
)
