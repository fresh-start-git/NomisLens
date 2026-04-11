"""Shared pytest fixtures and platform markers for Ultimate Zoom tests.

Phase 1 adds the win32-only skip marker used by tests/test_dpi.py.
Phase 2 adds a session-scoped shared Tk root because repeatedly creating
and destroying Tk roots in the same process triggers a flaky "SourceLibFile
panedwindow" TclError on Python 3.14 + tk8.6 on Windows. By sharing ONE
root across the entire test session, the Tcl library-loading path runs
exactly once and each test uses a fresh Toplevel instead of a fresh root.

Later phases will add mocks for AppState, fake mss grabs, and HWND stubs.
"""
from __future__ import annotations

import ctypes
import sys

import pytest

# Platform skip marker: DPI APIs only exist on Windows.
# Usage in a test module:
#     pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
# or on a single test:
#     @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
win_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")


@pytest.fixture(scope="session")
def tk_session_root():
    """One Tk root per pytest session, shared by every Windows smoke test.

    Creates a hidden root on first use and destroys it at session end.
    Tests should create a Toplevel off this root rather than another Tk().
    """
    if sys.platform != "win32":
        pytest.skip("Windows-only fixture")
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.update_idletasks()
    try:
        yield root
    finally:
        try:
            root.destroy()
        except Exception:
            pass


@pytest.fixture
def tk_toplevel(tk_session_root):
    """A fresh hidden Toplevel per test, plus its platform HWND.

    Yields (toplevel, hwnd) where hwnd is the Win32 HWND retrieved via
    GetParent(winfo_id()) — the toplevel's own HWND is the parent of the
    child widget HWND tkinter hands out.
    """
    import tkinter as tk
    top = tk.Toplevel(tk_session_root)
    top.withdraw()
    top.geometry("400x400+200+200")
    top.update_idletasks()
    u32 = ctypes.windll.user32  # type: ignore[attr-defined]
    u32.GetParent.argtypes = [ctypes.wintypes.HWND]
    u32.GetParent.restype = ctypes.wintypes.HWND
    hwnd = u32.GetParent(top.winfo_id())
    try:
        yield top, hwnd
    finally:
        try:
            top.destroy()
        except Exception:
            pass
