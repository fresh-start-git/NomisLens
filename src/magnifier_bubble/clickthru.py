"""Cross-process click-through injection.

Closes the Phase 2 LAYT-02 documented gap: HTTRANSPARENT works in-process
but cross-process Tk-frame propagation is blocked. This module posts a
synthetic WM_LBUTTONDOWN + WM_LBUTTONUP to the HWND below our layered
bubble so a click in the content zone reaches Notepad / Cornerstone.

CRITICAL rules (from 04-RESEARCH.md Pattern 6 and Pitfalls I/K):

1. CWP_SKIPTRANSPARENT is LOAD-BEARING. Without it,
   ChildWindowFromPointEx returns our own WS_EX_LAYERED bubble's HWND
   and PostMessageW recurses into our canvas.
2. Self-HWND guard is belt-and-suspenders. Even with CWP_SKIPTRANSPARENT,
   explicitly reject `target == own_hwnd` before posting.
3. lParam must be CLIENT-relative, not screen-relative. Always call
   ScreenToClient FIRST, then pack.
4. Use ctypes.windll (NOT the GIL-holding variant). Call sites are Tk
   main-thread button handlers, not inside a WndProc callback. The
   GIL-holding-DLL rule is scoped to hot-path WndProc calls only
   (see wndproc.py).
5. PostMessageW only - never the synchronous Send variant. PostMessage
   is asynchronous and safe cross-process; the synchronous sibling blocks
   on the target message pump and also triggers the Python 3.14
   re-entrant-WndProc crash mode (see STATE.md Phase 3 decisions).
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from magnifier_bubble import winconst as wc

_SIGNATURES_APPLIED = False


def _u32():
    """Lazy bind user32 functions used by inject_click.

    Mirrors the pattern in wndproc.py._u32 and dpi.py._u32. On first use,
    applies argtypes/restype so x64 Python passes HWND values at full
    pointer width. After the first call the global sentinel short-
    circuits further re-binds.
    """
    global _SIGNATURES_APPLIED
    u32 = ctypes.windll.user32  # type: ignore[attr-defined]
    if not _SIGNATURES_APPLIED:
        u32.GetDesktopWindow.argtypes = []
        u32.GetDesktopWindow.restype = wintypes.HWND
        u32.ChildWindowFromPointEx.argtypes = [
            wintypes.HWND, wintypes.POINT, wintypes.UINT,
        ]
        u32.ChildWindowFromPointEx.restype = wintypes.HWND
        u32.WindowFromPoint.argtypes = [wintypes.POINT]
        u32.WindowFromPoint.restype = wintypes.HWND
        u32.ScreenToClient.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.POINT),
        ]
        u32.ScreenToClient.restype = wintypes.BOOL
        u32.PostMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        u32.PostMessageW.restype = wintypes.BOOL
        _SIGNATURES_APPLIED = True
    return u32


def inject_click(screen_x: int, screen_y: int, own_hwnd: int) -> bool:
    """Post WM_LBUTTONDOWN + WM_LBUTTONUP to the window beneath
    (screen_x, screen_y), skipping our own layered bubble.

    Args:
        screen_x: screen-relative X (event.x_root from Tk)
        screen_y: screen-relative Y (event.y_root from Tk)
        own_hwnd: our bubble's toplevel HWND (from BubbleWindow._hwnd)

    Returns:
        True if a target was found and both messages were posted.
        False if no target (over desktop / occluded by non-skippable
        window) OR the target matched own_hwnd (self-guard).

    Never raises - on any ctypes error the click is silently dropped
    and the caller falls back to Phase 2 behavior (click consumed by bubble).
    """
    try:
        u32 = _u32()
        pt = wintypes.POINT(screen_x, screen_y)
        # Walk from desktop down, skipping transparent (our WS_EX_LAYERED
        # bubble), invisible, and disabled children. This returns the
        # topmost NON-transparent HWND at the point - i.e. the app
        # below our bubble.
        flags = (
            wc.CWP_SKIPTRANSPARENT
            | wc.CWP_SKIPINVISIBLE
            | wc.CWP_SKIPDISABLED
        )
        target = u32.ChildWindowFromPointEx(
            u32.GetDesktopWindow(), pt, flags,
        )
        if not target or target == own_hwnd:
            return False
        # Translate screen -> client coords for the target's WM_LBUTTONDOWN.
        client_pt = wintypes.POINT(screen_x, screen_y)
        if not u32.ScreenToClient(target, ctypes.byref(client_pt)):
            return False
        # Pack lParam: (y << 16) | (x & 0xFFFF). Matches the encoding
        # wndproc.py uses to UNpack WM_NCHITTEST lParam, but in CLIENT
        # space not screen space.
        lparam = ((client_pt.y & 0xFFFF) << 16) | (client_pt.x & 0xFFFF)
        # WM_LBUTTONDOWN with MK_LBUTTON, then WM_LBUTTONUP with 0.
        u32.PostMessageW(target, wc.WM_LBUTTONDOWN, wc.MK_LBUTTON, lparam)
        u32.PostMessageW(target, wc.WM_LBUTTONUP, 0, lparam)
        return True
    except Exception:
        # Never let a ctypes error escape into the Tk main loop.
        # Phase 2 behavior is the fallback - click stays on our bubble.
        return False
