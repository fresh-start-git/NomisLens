import sys
# sys.stdout / sys.stderr are None in a windowed (no-console) exe.
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
if sys.stderr is not None:
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

import ctypes
ctypes.windll.user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)  # PMv2
except (AttributeError, OSError):
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor V1 (Win 8.1+)
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()  # System-aware (legacy)

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from magnifier_bubble.app import main

import datetime
import traceback


def _crash_log_path() -> str:
    """Return path for the crash log file next to NomisLens.exe (or main.py)."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(base, f"nomislens_crash_{ts}.txt")


def _show_crash_dialog(msg: str) -> None:
    """Show a Win32 MessageBox with the crash summary. Never raises."""
    try:
        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            0,
            f"NomisLens crashed. A log was written next to NomisLens.exe.\n\n{msg[:400]}",
            "NomisLens — Unexpected Error",
            0x10,  # MB_ICONERROR
        )
    except Exception:
        pass


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    tb = traceback.format_exc()
    log_path = _crash_log_path()
    try:
        with open(log_path, "w", encoding="utf-8") as _f:
            _f.write(f"NomisLens crash report — {datetime.datetime.now()}\n\n")
            _f.write(tb)
    except Exception:
        pass
    _show_crash_dialog(tb.splitlines()[-1] if tb.strip() else "Unknown error")
    raise SystemExit(1)
