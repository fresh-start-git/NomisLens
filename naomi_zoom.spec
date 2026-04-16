# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for NomisLens.
# Build:  pyinstaller naomi_zoom.spec
# Output: dist\NomisLens.exe  (single-file, no console window)

a = Analysis(
    ['main.py'],
    pathex=['src'],          # src-layout: magnifier_bubble lives here
    binaries=[],
    datas=[],
    hiddenimports=[
        # win32gui is imported conditionally in shapes.py; PyInstaller
        # static analysis misses conditional imports.
        'win32gui',
        'win32api',
        'win32con',
        'pywintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim unused stdlib modules to keep the exe lean.
        'unittest', 'email', 'http', 'xml', 'pydoc',
        'doctest', 'difflib', 'multiprocessing',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='NomisLens',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX can trip AV scanners; leave off by default
    runtime_tmpdir=None,
    console=False,       # no console window — GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
)
