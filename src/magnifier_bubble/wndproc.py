"""WndProc subclass installer for the bubble window.

Implements research Pattern 2 + Pitfall A fix:
- Subclass hwnd's WindowProc via SetWindowLongPtrW(hwnd, GWLP_WNDPROC, new_proc)
- Store the new WNDPROC callable on a WndProcKeepalive container so CPython
  does NOT garbage-collect the thunk while Windows still holds the raw pointer
- Handle WM_NCHITTEST by unpacking lParam's signed low/high shorts via
  ctypes.c_short (signed 16-bit cast required for multi-monitor safety
  per Microsoft Learn WM_NCHITTEST "Remarks" — the unsigned macro forms
  break on negative screen coordinates) and dispatching through a
  caller-provided compute_zone_fn(client_x, client_y, w, h)
- Delegate every other message to the original proc via CallWindowProcW

This module has ZERO tkinter / pywin32 / mss / PIL imports. It uses only
ctypes + ctypes.wintypes + typing. It does NOT change process DPI awareness
(DPI is main.py's exclusive responsibility per OVER-05).

LONG_PTR safety: on 64-bit Python, the SetWindowLongPtrW / GetWindowLongPtrW /
CallWindowProcW return and argument types must be declared as c_void_p (not
the default c_int). Without explicit argtypes, ctypes uses the int ABI and
truncates pointer values to 32 bits, which corrupts the WndProc address and
crashes the process. This mirrors the Phase 1 P03 x64-HANDLE-truncation fix
in dpi.py (same pattern, different functions).
"""
from __future__ import annotations

import ctypes
from ctypes import WINFUNCTYPE, wintypes
from typing import Callable

from magnifier_bubble import winconst as wc

# WindowProc signature: LRESULT (= Py_ssize_t on x64) WindowProc(HWND, UINT, WPARAM, LPARAM)
WNDPROC = WINFUNCTYPE(
    ctypes.c_ssize_t,
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
)

_SIGNATURES_APPLIED = False


def _u32():
    """Lazy access to user32 — avoids any import-time side effect on non-Windows.

    On first use, applies argtypes/restype to the six functions wndproc.py
    calls. Without these, x64 Python truncates LONG_PTR values to 32 bits
    and the WndProc subclass either no-ops or jumps to a corrupted pointer.
    """
    global _SIGNATURES_APPLIED
    u32 = ctypes.windll.user32  # type: ignore[attr-defined]
    if not _SIGNATURES_APPLIED:
        u32.SetWindowLongPtrW.argtypes = [
            wintypes.HWND, ctypes.c_int, ctypes.c_void_p
        ]
        u32.SetWindowLongPtrW.restype = ctypes.c_void_p
        u32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        u32.GetWindowLongPtrW.restype = ctypes.c_void_p
        u32.CallWindowProcW.argtypes = [
            ctypes.c_void_p,
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        u32.CallWindowProcW.restype = ctypes.c_ssize_t
        u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u32.GetWindowRect.restype = wintypes.BOOL
        u32.SendMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        ]
        u32.SendMessageW.restype = ctypes.c_ssize_t
        _SIGNATURES_APPLIED = True
    return u32


class WndProcKeepalive:
    """Container for references that MUST outlive the HWND.

    Losing a reference to `new_proc` crashes the process on the next
    message dispatched to the HWND (Pitfall A from PITFALLS.md / Pitfall 2).
    Plan 03's BubbleWindow stores this on self._wndproc_keepalive — the
    attribute name is intentionally grep-able for post-mortem debugging.
    """
    __slots__ = ("new_proc", "old_proc", "hwnd")

    def __init__(self) -> None:
        self.new_proc = None
        self.old_proc = None
        self.hwnd = None


def install(
    hwnd: int,
    compute_zone_fn: Callable[[int, int, int, int], str],
) -> WndProcKeepalive:
    """Subclass hwnd's WndProc to route WM_NCHITTEST via compute_zone_fn.

    Args:
        hwnd: The toplevel HWND (NOT winfo_id() — that's the child widget HWND;
              callers must wrap with GetParent(winfo_id()) — see research
              Pattern 1 and PITFALLS.md Integration Gotchas table).
        compute_zone_fn: A callable taking (client_x, client_y, w, h) and
                         returning one of "drag", "content", "control".

    Returns:
        A WndProcKeepalive holding strong refs to the new WNDPROC thunk,
        the old proc address, and the hwnd. The CALLER MUST store this on
        an instance attribute that outlives the window — otherwise CPython
        garbage-collects the thunk and the next message crashes the process.
    """
    u32 = _u32()
    old_proc = u32.GetWindowLongPtrW(hwnd, wc.GWLP_WNDPROC)

    def py_wndproc(h, msg, wparam, lparam):
        if msg == wc.WM_MOUSEACTIVATE:
            # Prevent the parent window from stealing focus on any click.
            # WM_MOUSEACTIVATE fires before WM_NCHITTEST, so this must be
            # handled here — returning MA_NOACTIVATE keeps the foreground
            # window (e.g. Notepad) unchanged regardless of which zone was hit.
            return wc.MA_NOACTIVATE
        if msg == wc.WM_NCHITTEST:
            # lParam packs SCREEN-space coordinates as two 16-bit shorts.
            # Use signed c_short cast — the unsigned word-extraction macros
            # return unsigned shorts and break on multi-monitor negative
            # coordinates per Microsoft Learn WM_NCHITTEST "Remarks".
            sx = ctypes.c_short(lparam & 0xFFFF).value
            sy = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            rect = wintypes.RECT()
            u32.GetWindowRect(h, ctypes.byref(rect))
            cx = sx - rect.left
            cy = sy - rect.top
            w = rect.right - rect.left
            wh = rect.bottom - rect.top
            try:
                zone = compute_zone_fn(cx, cy, w, wh)
            except Exception:
                # Never let a Python exception escape into Windows'
                # dispatcher — fall through to default handling.
                zone = "content"
            if zone == "drag":
                return wc.HTCAPTION
            if zone == "content":
                return wc.HTTRANSPARENT
            # zone == "control" falls through to default WndProc, which
            # returns HTCLIENT for in-client-area points.
        return u32.CallWindowProcW(old_proc, h, msg, wparam, lparam)

    new_proc = WNDPROC(py_wndproc)  # GC-fragile — MUST be stored on keepalive

    ka = WndProcKeepalive()
    ka.new_proc = new_proc
    ka.old_proc = old_proc
    ka.hwnd = hwnd

    u32.SetWindowLongPtrW(
        hwnd, wc.GWLP_WNDPROC,
        ctypes.cast(new_proc, ctypes.c_void_p).value,
    )
    return ka


def install_child(
    child_hwnd: int,
    compute_zone_fn: Callable[[int, int, int, int], str],
) -> WndProcKeepalive:
    """Subclass the canvas child HWND to fix click-through and focus theft.

    The parent WndProc installed by install() never receives WM_NCHITTEST
    when the cursor is over the canvas child, because Windows delivers
    WM_NCHITTEST to the topmost HWND at the cursor — which is the child.
    Tkinter's default canvas WndProc returns HTCLIENT for everything, so
    HTTRANSPARENT never fires and clicks never reach apps below.

    This child WndProc:
    - WM_MOUSEACTIVATE → MA_NOACTIVATE: belt-and-suspenders against focus
      steal (the parent WndProc also handles this via propagation, but
      intercepting it here prevents Tk's canvas WndProc from processing it
      first and potentially activating the window).
    - WM_NCHITTEST content zone → HTTRANSPARENT: click passes to parent
      WndProc, which also returns HTTRANSPARENT, so the click reaches the
      app below (e.g. Notepad).
    - WM_NCHITTEST drag/control zone → delegates to original Tk canvas
      WndProc (returns HTCLIENT), so Tkinter fires <Button-1> and Pattern
      2b (ReleaseCapture + SendMessage WM_NCLBUTTONDOWN) initiates the move.
    """
    u32 = _u32()
    old_proc = u32.GetWindowLongPtrW(child_hwnd, wc.GWLP_WNDPROC)

    def py_child_wndproc(h, msg, wparam, lparam):
        if msg == wc.WM_MOUSEACTIVATE:
            return wc.MA_NOACTIVATE
        if msg == wc.WM_NCHITTEST:
            sx = ctypes.c_short(lparam & 0xFFFF).value
            sy = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            rect = wintypes.RECT()
            u32.GetWindowRect(h, ctypes.byref(rect))
            cx = sx - rect.left
            cy = sy - rect.top
            w = rect.right - rect.left
            wh = rect.bottom - rect.top
            try:
                zone = compute_zone_fn(cx, cy, w, wh)
            except Exception:
                zone = "content"
            if zone == "content":
                return wc.HTTRANSPARENT
            # drag/control: let Tk's original canvas WndProc handle it
            # (returns HTCLIENT → Tk fires <Button-1> → Pattern 2b drag).
        return u32.CallWindowProcW(old_proc, h, msg, wparam, lparam)

    new_proc = WNDPROC(py_child_wndproc)

    ka = WndProcKeepalive()
    ka.new_proc = new_proc
    ka.old_proc = old_proc
    ka.hwnd = child_hwnd

    u32.SetWindowLongPtrW(
        child_hwnd, wc.GWLP_WNDPROC,
        ctypes.cast(new_proc, ctypes.c_void_p).value,
    )
    return ka


def uninstall(keepalive: WndProcKeepalive) -> None:
    """Restore the original WndProc. Plan 03's BubbleWindow calls this on
    WM_DELETE_WINDOW before root.destroy() so the original proc address is
    re-seated before the HWND is freed. After this call the caller may
    drop the keepalive reference — Windows no longer points at new_proc.
    """
    if keepalive is None or keepalive.hwnd is None or keepalive.old_proc is None:
        return
    u32 = _u32()
    u32.SetWindowLongPtrW(
        keepalive.hwnd, wc.GWLP_WNDPROC, keepalive.old_proc
    )
