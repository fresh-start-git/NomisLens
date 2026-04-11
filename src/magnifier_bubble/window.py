"""BubbleWindow - the Phase 2 visible artifact.

Wires Plans 01 + 02 together into a borderless, always-on-top, click-
through, non-activating Tk Toplevel that paints a teal-bordered bubble
with two semi-transparent dark strips.

Construction ordering is LOAD-BEARING (PITFALLS.md Pitfall 15) - see the
__init__ body for the literal sequence. The high-level recipe is: create
Tk root hidden, strip chrome, set topmost, size+position, realize HWND,
look up toplevel HWND via GetParent, OR in the extended style bits, set
layered alpha, build canvas widgets, install the WndProc subclass, apply
the shape mask, and finally show the window.

Any reordering of these steps produces a specific bug:
- hiding AFTER mapping -> taskbar flash (Pitfall D)
- chrome-strip AFTER topmost -> lost topmost (Pitfall 15)
- ext styles BEFORE mapping -> Tk resets them (Pitfall 15)
- wndproc install BEFORE a visible HWND -> crash on first paint (Pitfall A adjacent)

Note: this docstring intentionally avoids the literal canonical-step
substrings (Tk creation, chrome stripping, topmost, layered alpha, etc.
as source tokens) because the structural lint in test_window_integration
grep-checks the ORDER in which those substrings appear, using src.find()
which returns the FIRST occurrence in the file. Mentioning them here in
narrative order would shift their find() positions into the docstring
and break the lint.

_wndproc_keepalive attribute name is INTENTIONAL - grep for it when
debugging a random ACCESS_VIOLATION (Pitfall A).
"""
from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from ctypes import wintypes
from typing import Callable

from magnifier_bubble import shapes, wndproc
from magnifier_bubble import winconst as wc
from magnifier_bubble.hit_test import compute_zone
from magnifier_bubble.state import AppState

# Visual constants (02-RESEARCH.md User Constraints > Claude's Discretion).
# Locked here so the integration test and Phase 4 both grep-reference them.
BORDER_COLOR: str = "#2ec4b6"   # teal - AAA contrast on #ffffff, AA on #101010
BORDER_WIDTH: int = 4           # pixels - LAYT-06 range is 3-4, 4 is safer on high DPI
STRIP_COLOR: str = "#1a1a1a"    # dark gray - LAYT-05 (flat dark; no per-pixel alpha)
BG_COLOR: str = "#0a0a0a"       # canvas background - visible inside content zone until Phase 3
DRAG_STRIP_HEIGHT: int = 44     # matches hit_test.DRAG_BAR_HEIGHT
CONTROL_STRIP_HEIGHT: int = 44  # matches hit_test.CONTROL_BAR_HEIGHT


_WINDOW_SIGNATURES_APPLIED = False


def _u32():
    """Lazy bind of user32 functions used by BubbleWindow construction.

    Mirrors the pattern in dpi.py and wndproc.py - defensive argtypes so
    x64 Python passes HWND and LONG_PTR values at full pointer width.
    """
    global _WINDOW_SIGNATURES_APPLIED
    u32 = ctypes.windll.user32  # type: ignore[attr-defined]
    if not _WINDOW_SIGNATURES_APPLIED:
        u32.GetParent.argtypes = [wintypes.HWND]
        u32.GetParent.restype = wintypes.HWND
        u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u32.GetWindowLongW.restype = ctypes.c_long
        u32.SetWindowLongW.argtypes = [
            wintypes.HWND, ctypes.c_int, ctypes.c_long
        ]
        u32.SetWindowLongW.restype = ctypes.c_long
        u32.SetLayeredWindowAttributes.argtypes = [
            wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD
        ]
        u32.SetLayeredWindowAttributes.restype = wintypes.BOOL
        u32.ReleaseCapture.argtypes = []
        u32.ReleaseCapture.restype = wintypes.BOOL
        u32.SendMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        ]
        u32.SendMessageW.restype = ctypes.c_ssize_t
        _WINDOW_SIGNATURES_APPLIED = True
    return u32


class BubbleWindow:
    """The Phase 2 visible artifact: a borderless, click-through bubble.

    Construction is synchronous and produces a visible window. Call
    self.root.mainloop() (from app.main) to drive the Tk event loop.
    """

    def __init__(self, state: AppState) -> None:
        self.state: AppState = state
        self._wndproc_keepalive: wndproc.WndProcKeepalive | None = None
        self._canvas_wndproc_keepalive: wndproc.WndProcKeepalive | None = None
        self._frame_wndproc_keepalive: wndproc.WndProcKeepalive | None = None

        snap = state.snapshot()

        # --- Step 1: Create Tk root, hidden ---
        self.root: tk.Tk = tk.Tk()
        self.root.withdraw()

        # --- Step 2: Strip chrome BEFORE topmost ---
        self.root.overrideredirect(True)

        # --- Step 3: Topmost AFTER chrome strip ---
        self.root.wm_attributes("-topmost", True)

        # --- Step 4: Geometry while hidden ---
        self.root.geometry(f"{snap.w}x{snap.h}+{snap.x}+{snap.y}")

        # --- Step 5: Realize the HWND so GetParent has something to grab ---
        self.root.update_idletasks()

        # --- Step 6-8: Windows-only ext styles + layered window ---
        self._hwnd: int = 0
        if sys.platform == "win32":
            u32 = _u32()
            self._hwnd = int(u32.GetParent(self.root.winfo_id()) or 0)
            if self._hwnd:
                cur = u32.GetWindowLongW(self._hwnd, wc.GWL_EXSTYLE)
                new = cur | wc.WS_EX_LAYERED | wc.WS_EX_TOOLWINDOW | wc.WS_EX_NOACTIVATE
                u32.SetWindowLongW(self._hwnd, wc.GWL_EXSTYLE, new)
                # Full-window alpha = 255 (opaque). Individual Tk widgets
                # paint their own dark fills for the LAYT-05 effect.
                u32.SetLayeredWindowAttributes(self._hwnd, 0, 255, wc.LWA_ALPHA)

        # --- Step 9: Build canvas + LAYT-05 strips + LAYT-06 border ---
        self._canvas: tk.Canvas = tk.Canvas(
            self.root,
            width=snap.w,
            height=snap.h,
            highlightthickness=0,
            bd=0,
            bg=BG_COLOR,
        )
        self._canvas.pack(fill="both", expand=True)

        # LAYT-05: top strip (dark gray, full width)
        self._top_strip_id: int = self._canvas.create_rectangle(
            0, 0, snap.w, DRAG_STRIP_HEIGHT,
            fill=STRIP_COLOR, outline="",
        )
        # LAYT-05: bottom strip (dark gray, full width)
        self._bottom_strip_id: int = self._canvas.create_rectangle(
            0, snap.h - CONTROL_STRIP_HEIGHT, snap.w, snap.h,
            fill=STRIP_COLOR, outline="",
        )
        # LAYT-06: teal border outline (drawn LAST so it sits on top).
        # For Phase 2 we draw the initial shape's border. Phase 4 will
        # swap the outline when the shape cycles; shapes.apply_shape
        # handles the SetWindowRgn clip separately.
        self._border_id: int = self._draw_border(snap.w, snap.h, snap.shape)

        # --- Step 9b: Realize canvas HWND before WndProc installation ---
        # The canvas is created in Step 9 but winfo_id() may return 0 until
        # Tk processes pending geometry events. update_idletasks() flushes
        # those so self._canvas.winfo_id() is valid below.
        self.root.update_idletasks()

        # --- Step 10: Install WndProc subclasses ---
        # Windows delivers WM_NCHITTEST to the topmost HWND at the cursor.
        # Tk creates three Win32 windows that stack as follows (outermost first):
        #   self._hwnd  (Win32 toplevel)
        #     self.root.winfo_id()  (Tk frame child)
        #       self._canvas.winfo_id()  (canvas widget, topmost at cursor)
        #
        # For content-zone click-through, every window in the chain must return
        # HTTRANSPARENT — otherwise the first one that returns HTCLIENT captures
        # the click and Notepad never sees it.  For drag, only the canvas matters:
        # it falls through to Tk's original proc (HTCLIENT → <Button-1> → Pattern 2b).
        # For focus theft, WM_MOUSEACTIVATE is intercepted at the canvas level
        # (MA_NOACTIVATE) before Tk's WndProc can activate the window.
        if sys.platform == "win32" and self._hwnd:
            self._wndproc_keepalive = wndproc.install(
                self._hwnd, self._zone_fn
            )
            # Tk frame: intermediate HWND — must also return HTTRANSPARENT for
            # content zone so the chain reaches self._hwnd's cross-process pass.
            self._frame_wndproc_keepalive = wndproc.install_child(
                self.root.winfo_id(), self._zone_fn
            )
            # Canvas: actual topmost HWND at cursor — intercept WM_NCHITTEST
            # first; drag zone falls through to Tk's WndProc (HTCLIENT → <Button-1>).
            self._canvas_wndproc_keepalive = wndproc.install_child(
                self._canvas.winfo_id(), self._zone_fn
            )

        # --- Step 11: Apply shape mask (SetWindowRgn clips corners) ---
        if sys.platform == "win32" and self._hwnd:
            shapes.apply_shape(self._hwnd, snap.w, snap.h, snap.shape)

        # --- Pattern 2b: live-feedback drag via WM_LBUTTONDOWN on top strip ---
        # With WS_EX_NOACTIVATE set, HTCAPTION-only drag has a documented
        # "dead-drag" regression (Pitfall E). The workaround is to bind a
        # Tk <Button-1> on the top-strip canvas item's y-band and fire
        # ReleaseCapture + SendMessage(WM_NCLBUTTONDOWN, HTCAPTION, 0).
        # We bind on the whole canvas and gate by y-coordinate so the
        # middle and bottom strips are not affected.
        self._canvas.bind("<Button-1>", self._on_canvas_press)

        # --- Graceful teardown on window close ---
        self.root.protocol("WM_DELETE_WINDOW", self.destroy)

        # --- Step 12: Show the window ---
        self.root.deiconify()

    # ---- Internal helpers ----

    def _zone_fn(self, client_x: int, client_y: int, w: int, h: int) -> str:
        """Adapter: wndproc gives us current w/h via GetWindowRect, we
        forward to the pure hit_test.compute_zone."""
        return compute_zone(client_x, client_y, w, h)

    def _draw_border(self, w: int, h: int, shape: str) -> int:
        """Draw the LAYT-06 teal outline for the given shape.
        For Phase 2 "rounded" we fall through to a rectangle outline -
        Phase 4 will implement a proper rounded-rect polygon. The
        SetWindowRgn call in shapes.apply_shape handles the actual clip.
        """
        inset = BORDER_WIDTH // 2
        if shape == "circle":
            return self._canvas.create_oval(
                inset, inset, w - inset, h - inset,
                outline=BORDER_COLOR, width=BORDER_WIDTH, fill="",
            )
        # "rounded" and "rect" both get a rectangular outline in Phase 2.
        return self._canvas.create_rectangle(
            inset, inset, w - inset, h - inset,
            outline=BORDER_COLOR, width=BORDER_WIDTH, fill="",
        )

    def _on_canvas_press(self, event) -> None:
        """Pattern 2b: live-feedback drag workaround for WS_EX_NOACTIVATE.

        If the press lands on the top strip, release Tk's capture and
        ask Windows to start its native move loop. This is what produces
        smooth mid-drag feedback on WS_EX_NOACTIVATE windows.
        """
        if event.y >= DRAG_STRIP_HEIGHT:
            return  # let WndProc + native hit-test handle non-drag zones
        if sys.platform != "win32" or not self._hwnd:
            return
        u32 = _u32()
        u32.ReleaseCapture()
        u32.SendMessageW(self._hwnd, wc.WM_NCLBUTTONDOWN, wc.HTCAPTION, 0)

    # ---- Public teardown ----

    def destroy(self) -> None:
        """Called on WM_DELETE_WINDOW. Uninstall the WndProc subclass
        BEFORE destroying the root so the original proc is re-seated on
        a still-valid HWND.
        """
        try:
            # Uninstall innermost WndProcs first (canvas → frame → parent)
            # so each HWND's chain is restored while all HWNDs are still valid.
            if self._canvas_wndproc_keepalive is not None:
                wndproc.uninstall(self._canvas_wndproc_keepalive)
                self._canvas_wndproc_keepalive = None
            if self._frame_wndproc_keepalive is not None:
                wndproc.uninstall(self._frame_wndproc_keepalive)
                self._frame_wndproc_keepalive = None
            if self._wndproc_keepalive is not None:
                wndproc.uninstall(self._wndproc_keepalive)
                self._wndproc_keepalive = None
        finally:
            try:
                self.root.destroy()
            except tk.TclError:
                # Window already torn down - swallow the secondary error.
                pass
