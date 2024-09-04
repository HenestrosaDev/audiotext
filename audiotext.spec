# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.compat import is_darwin, is_win
import shutil

import sys ; sys.setrecursionlimit(sys.getrecursionlimit() * 5)

def find_site_packages(venv_dir = "venv"):
    venv_path = Path(venv_dir)
    for site_packages in venv_path.rglob("site-packages"):
        if site_packages.is_dir():
            return site_packages

    return None

site_packages_path = find_site_packages()

datas = [
    (f"{site_packages_path}/customtkinter", "customtkinter"),
    (f"{site_packages_path}/transformers", "transformers"),
    (f"{site_packages_path}/lightning", "lightning"),
    (f"{site_packages_path}/lightning_fabric", "lightning_fabric"),
    (f"{site_packages_path}/speechbrain", "speechbrain"),
    (f"{site_packages_path}/pyannote", "pyannote"),
    (f"{site_packages_path}/asteroid_filterbanks", "asteroid_filterbanks"),
    (f"{site_packages_path}/whisperx", "whisperx"),
    (f"{site_packages_path}/librosa", "librosa"),
    ("res", "res"),
    ("config.ini", "."),
    (".env", "."),
]

hiddenimports = [
    "huggingface_hub.repository",
    "sklearn.utils._cython_blas",
    "sklearn.neighbors.quad_tree",
    "sklearn.tree",
    "sklearn.tree._utils",
]

block_cipher = None

is_debug = False
if is_debug:
    options = [("v", None, "OPTION")]
else:
    options = []

binaries = [
    (shutil.which("ffmpeg"), "."),
    (shutil.which("ffprobe"), "."),
]

if flac_path := shutil.which("flac"):
    binaries += [(flac_path, ".")]

a = Analysis(
    ["src/app.py"],
    pathex=[site_packages_path],
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
    version="2.3.0",
    info_plist={
        "NSPrincipalClass": "NSApplication",
        "NSAppleScriptEnabed": False,
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "Allow Audiotext to record audio from your microphone to generate transcriptions.",
    }
)
