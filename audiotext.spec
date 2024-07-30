# -*- mode: python ; coding: utf-8 -*-
from os.path import join
from platform import system
from PyInstaller.utils.hooks import copy_metadata
from PyInstaller.utils.hooks import collect_data_files
from shutil import copyfile

datas = [
    (r'venv/Lib/site-packages/customtkinter', 'customtkinter'),
    (r'venv/Lib/site-packages/transformers', 'transformers'),
    (r'venv/Lib/site-packages/lightning', 'lightning'),
    (r'venv/Lib/site-packages/lightning_fabric', 'lightning_fabric'),
    (r'venv/Lib/site-packages/speechbrain', 'speechbrain'),
    (r'venv/Lib/site-packages/pyannote', 'pyannote'),
    (r'venv/Lib/site-packages/asteroid_filterbanks', 'asteroid_filterbanks'),
    (r'venv/Lib/site-packages/whisperx', 'whisperx'),
    ('res', 'res'),
    ('config.ini', '.'),
    ('.env', '.'),
]

datas += copy_metadata('torch')
datas += copy_metadata('tqdm', recursive=True)
datas += copy_metadata('regex')
datas += copy_metadata('requests')
datas += copy_metadata('packaging')
datas += copy_metadata('filelock')
datas += copy_metadata('numpy')
datas += copy_metadata('tokenizers')
datas += copy_metadata('pillow')
datas += copy_metadata('huggingface_hub')
datas += copy_metadata('safetensors')
datas += copy_metadata('pyyaml')
datas += collect_data_files('librosa')

block_cipher = None

a = Analysis(
    ['src/app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['huggingface_hub.repository', 'pytorch', 'sklearn.utils._cython_blas', 'sklearn.neighbors.typedefs', 'sklearn.neighbors.quad_tree', 'sklearn.tree', 'sklearn.tree._utils'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Filter out unused and/or duplicate shared libs
torch_lib_paths = {
    join('torch', 'lib', 'libtorch_cuda.so'),
    join('torch', 'lib', 'libtorch_cpu.so'),
}
a.datas = [entry for entry in a.datas if not entry[0] in torch_lib_paths]

os_path_separator = '\\' if system() == 'Windows' else '/'
a.datas = [entry for entry in a.datas if not f'torch{os_path_separator}_C.cp' in entry[0]]
a.datas = [entry for entry in a.datas if not f'torch{os_path_separator}_dl.cp' in entry[0]]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if system() == 'Darwin':  # macOS
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='Audiotext',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch='x86_64',
        codesign_identity=None,
        entitlements_file=None,
        icon=['res/img/icon.icns'],
    )

    # BUNDLE statement is used to create a macOS application bundle (.app) for the program
    app = BUNDLE(
        exe,
        name='Audiotext.app',
        icon=['res/img/icon.icns'],
        bundle_identifier=None,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='Audiotext',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch='x86_64',
        codesign_identity=None,
        entitlements_file=None,
        icon=['res/img/icon.ico'],
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='audiotext',
    )
