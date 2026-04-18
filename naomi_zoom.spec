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
        # win32gui imported conditionally in shapes.py
        'win32gui',
        'win32api',
        'win32con',
        'pywintypes',
        # dxcam (Phase 7 DXGI capture) — dynamic imports need explicit listing
        'dxcam',
        'dxcam.dxcam',
        'dxcam._libs',
        'dxcam._libs.d3d11',
        'dxcam._libs.dxgi',
        'dxcam._libs.user32',
        'dxcam.core',
        'dxcam.core.backend',
        'dxcam.core.capture_loop',
        'dxcam.core.capture_runtime',
        'dxcam.core.device',
        'dxcam.core.display_recovery',
        'dxcam.core.duplicator',
        'dxcam.core.dxgi_duplicator',
        'dxcam.core.dxgi_errors',
        'dxcam.core.output',
        'dxcam.core.output_recovery',
        'dxcam.core.stagesurf',
        'dxcam.processor',
        'dxcam.processor.base',
        'dxcam.processor.numpy_processor',
        'dxcam.processor.cv2_processor',
        'dxcam.types',
        'dxcam.util',
        'dxcam.util.io',
        'dxcam.util.timer',
        # comtypes (dxcam dependency)
        'comtypes',
        'comtypes.client',
        # pystray (Phase 8 system tray) — _win32 is a dynamic platform import
        # not detected by PyInstaller analysis (Pitfall T-5 in 08-RESEARCH.md)
        'pystray._win32',
        # Phase 9 BULD-02 additions:
        'PIL._tkinter_finder',  # Pillow/Tk bridge — prevents ImageTk crash in one-file EXE
        'win32timezone',         # pywin32 internal — prevents startup ImportError on some Windows
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],  # pkg_resources runtime hook needs xml/email/etc — don't exclude stdlib
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
