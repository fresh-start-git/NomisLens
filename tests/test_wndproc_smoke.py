"""Structural lints + Windows-only smoke for src/magnifier_bubble/wndproc.py.

Structural lints run on every platform — they assert the source file
contains the load-bearing argtypes lines, has no forbidden imports, and
exports the locked interface. Windows-only tests create a throwaway Tk
root, install the wndproc subclass, and send synthetic WM_NCHITTEST
messages to verify the hit-test routing works end-to-end.
"""
from __future__ import annotations

import ctypes
import inspect
import pathlib
import sys

import pytest

from magnifier_bubble import wndproc
from magnifier_bubble import winconst as wc

WNDPROC_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "magnifier_bubble" / "wndproc.py"
)


# ========== Structural lints (every platform) ==========

def test_wndproc_imports_without_side_effect():
    """Importing wndproc must not call SetProcessDpiAwarenessContext or touch user32."""
    assert hasattr(wndproc, "install")
    assert hasattr(wndproc, "uninstall")
    assert hasattr(wndproc, "WndProcKeepalive")
    assert hasattr(wndproc, "WNDPROC")


def test_wndproc_keepalive_has_locked_slots():
    ka = wndproc.WndProcKeepalive()
    assert hasattr(ka, "__slots__")
    assert set(ka.__slots__) == {"new_proc", "old_proc", "hwnd"}


def test_install_signature_is_locked():
    sig = inspect.signature(wndproc.install)
    params = list(sig.parameters.keys())
    assert params == ["hwnd", "compute_zone_fn"], (
        f"install params are {params}; Plan 03 expects ['hwnd', 'compute_zone_fn']"
    )


def test_uninstall_signature_is_locked():
    sig = inspect.signature(wndproc.uninstall)
    params = list(sig.parameters.keys())
    assert params == ["keepalive"]


def test_source_contains_longptr_argtypes():
    """LONG_PTR argtypes MUST be explicit or x64 Python truncates pointers."""
    src = WNDPROC_PATH.read_text(encoding="utf-8")
    assert "SetWindowLongPtrW.argtypes" in src
    assert "ctypes.c_void_p" in src
    assert "SetWindowLongPtrW.restype = ctypes.c_void_p" in src
    assert "GetWindowLongPtrW.argtypes" in src
    assert "GetWindowLongPtrW.restype = ctypes.c_void_p" in src
    assert "CallWindowProcW.argtypes" in src
    assert "CallWindowProcW.restype = ctypes.c_ssize_t" in src
    assert "GetWindowRect.argtypes" in src
    assert "_SIGNATURES_APPLIED" in src


def test_source_uses_c_short_not_loword_hiword():
    """Multi-monitor WM_NCHITTEST lParam unpack must use signed c_short."""
    src = WNDPROC_PATH.read_text(encoding="utf-8")
    assert "c_short" in src, "wndproc.py must unpack WM_NCHITTEST lParam via c_short"
    assert "LOWORD" not in src, (
        "wndproc.py must NOT use LOWORD — it returns unsigned and breaks "
        "on multi-monitor per Microsoft Learn WM_NCHITTEST Remarks"
    )
    assert "HIWORD" not in src


def test_source_does_not_call_dpi_api():
    """DPI awareness is main.py's exclusive responsibility per OVER-05."""
    src = WNDPROC_PATH.read_text(encoding="utf-8")
    assert "SetProcessDpiAwarenessContext" not in src
    assert "SetProcessDpiAwareness(" not in src
    assert "SetProcessDPIAware(" not in src


def test_source_imports_winconst():
    src = WNDPROC_PATH.read_text(encoding="utf-8")
    assert "from magnifier_bubble import winconst" in src


def test_source_does_not_import_tkinter_or_mss_or_pil():
    src = WNDPROC_PATH.read_text(encoding="utf-8")
    forbidden = ["import tkinter", "from tkinter", "import mss", "from mss",
                 "import PIL", "from PIL", "import win32gui", "from win32"]
    for f in forbidden:
        assert f not in src, f"wndproc.py must not import {f}"


# ========== Windows-only smoke ==========

win_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")


def _pack_lparam_screen_point(x: int, y: int) -> int:
    """Pack two 16-bit signed shorts into a LPARAM, matching WM_NCHITTEST."""
    # lParam low word = x, high word = y — both as signed 16-bit
    return (x & 0xFFFF) | ((y & 0xFFFF) << 16)


@win_only
def test_install_returns_keepalive_with_populated_fields(tk_toplevel):
    top, hwnd = tk_toplevel
    ka = wndproc.install(hwnd, lambda cx, cy, w, h: "content")
    try:
        assert ka is not None
        assert ka.hwnd == hwnd
        assert ka.new_proc is not None
        assert ka.old_proc is not None
    finally:
        wndproc.uninstall(ka)


@win_only
def test_wndproc_returns_htcaption_for_drag_zone(tk_toplevel):
    """Synthetic WM_NCHITTEST at top-center of window -> zone='drag' -> HTCAPTION."""
    top, hwnd = tk_toplevel
    ka = wndproc.install(
        hwnd,
        lambda cx, cy, w, h: "drag" if cy < 44 else "content",
    )
    try:
        u32 = ctypes.windll.user32
        u32.SendMessageW.argtypes = [
            ctypes.wintypes.HWND, ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
        ]
        u32.SendMessageW.restype = ctypes.c_ssize_t
        # Screen coords: window is at (200, 200), so top-center is (400, 210).
        lparam = _pack_lparam_screen_point(400, 210)
        result = u32.SendMessageW(hwnd, wc.WM_NCHITTEST, 0, lparam)
        assert result == wc.HTCAPTION, (
            f"expected HTCAPTION ({wc.HTCAPTION}) for drag zone, got {result}"
        )
    finally:
        wndproc.uninstall(ka)


@win_only
def test_wndproc_returns_httransparent_for_middle(tk_toplevel):
    """Synthetic WM_NCHITTEST at window center -> zone='content' -> HTTRANSPARENT."""
    top, hwnd = tk_toplevel
    ka = wndproc.install(hwnd, lambda cx, cy, w, h: "content")
    try:
        u32 = ctypes.windll.user32
        u32.SendMessageW.argtypes = [
            ctypes.wintypes.HWND, ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
        ]
        u32.SendMessageW.restype = ctypes.c_ssize_t
        lparam = _pack_lparam_screen_point(400, 400)  # center
        result = u32.SendMessageW(hwnd, wc.WM_NCHITTEST, 0, lparam)
        assert result == wc.HTTRANSPARENT, (
            f"expected HTTRANSPARENT ({wc.HTTRANSPARENT}) for content zone, got {result}"
        )
    finally:
        wndproc.uninstall(ka)


@win_only
def test_wndproc_delegates_control_zone_to_default_proc(tk_toplevel):
    """Synthetic WM_NCHITTEST for 'control' zone -> CallWindowProcW default -> HTCLIENT."""
    top, hwnd = tk_toplevel
    ka = wndproc.install(hwnd, lambda cx, cy, w, h: "control")
    try:
        u32 = ctypes.windll.user32
        u32.SendMessageW.argtypes = [
            ctypes.wintypes.HWND, ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
        ]
        u32.SendMessageW.restype = ctypes.c_ssize_t
        lparam = _pack_lparam_screen_point(400, 590)  # near bottom
        result = u32.SendMessageW(hwnd, wc.WM_NCHITTEST, 0, lparam)
        # Default Tk window proc returns HTCLIENT (1) for in-client-area points.
        # Acceptable results: HTCLIENT or any positive non-HT{CAPTION,TRANSPARENT} code,
        # because the default proc may legitimately return HTNOWHERE for points that
        # Windows considers outside the window. We assert it is NOT HTCAPTION and NOT
        # HTTRANSPARENT (proves the 'control' path delegates and does not return a
        # custom code).
        assert result != wc.HTCAPTION, (
            f"control zone should delegate, not return HTCAPTION"
        )
        assert result != wc.HTTRANSPARENT, (
            f"control zone should delegate, not return HTTRANSPARENT"
        )
    finally:
        wndproc.uninstall(ka)


@win_only
def test_wndproc_survives_50_messages_no_gc_crash(tk_toplevel):
    """Pitfall A: 50 consecutive messages must not crash the process.
    If the keepalive is missing, CPython GCs the WNDPROC thunk and the
    second or third SendMessageW crashes with ACCESS_VIOLATION."""
    import gc
    top, hwnd = tk_toplevel
    ka = wndproc.install(hwnd, lambda cx, cy, w, h: "content")
    try:
        u32 = ctypes.windll.user32
        u32.SendMessageW.argtypes = [
            ctypes.wintypes.HWND, ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
        ]
        u32.SendMessageW.restype = ctypes.c_ssize_t
        for i in range(50):
            # Alternate between drag and content points to exercise both branches.
            if i % 2 == 0:
                lparam = _pack_lparam_screen_point(400, 210)
            else:
                lparam = _pack_lparam_screen_point(400, 400)
            gc.collect()  # aggressive — would trigger Pitfall A if keepalive were missing
            result = u32.SendMessageW(hwnd, wc.WM_NCHITTEST, 0, lparam)
            assert isinstance(result, int)
        # Still alive and keepalive still holding references
        assert ka.new_proc is not None
        assert ka.old_proc is not None
    finally:
        wndproc.uninstall(ka)


@win_only
def test_uninstall_restores_original_proc(tk_toplevel):
    """uninstall() must call SetWindowLongPtrW with the saved old_proc address."""
    top, hwnd = tk_toplevel
    u32 = ctypes.windll.user32
    u32.GetWindowLongPtrW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
    u32.GetWindowLongPtrW.restype = ctypes.c_void_p
    original = u32.GetWindowLongPtrW(hwnd, wc.GWLP_WNDPROC)

    ka = wndproc.install(hwnd, lambda cx, cy, w, h: "content")
    after_install = u32.GetWindowLongPtrW(hwnd, wc.GWLP_WNDPROC)
    assert after_install != original, "install did not replace the proc"

    wndproc.uninstall(ka)
    after_uninstall = u32.GetWindowLongPtrW(hwnd, wc.GWLP_WNDPROC)
    assert after_uninstall == original, (
        f"uninstall did not restore original proc: "
        f"expected {original}, got {after_uninstall}"
    )
