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
import queue
import sys
import tkinter as tk
from ctypes import wintypes
from typing import Callable

from PIL import ImageTk

from magnifier_bubble import shapes, wndproc
from magnifier_bubble import winconst as wc
from magnifier_bubble.capture import CaptureWorker
from magnifier_bubble.controls import (
    ButtonRect,
    SHAPE_CYCLE,
    hit_button,
    layout_controls,
    resize_clamp,
    zoom_step,
)
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

# Magnification-API transform matrix (3×3 row-major float).
# Filled in _mag_set_transform: diagonal (zoom, zoom, 1), rest zero.
class _MAGTRANSFORM(ctypes.Structure):
    _fields_ = [("v", (ctypes.c_float * 3) * 3)]


# Color themes — right-click the top strip to cycle.
# Index 0 is the default (teal). Saved in theme.json next to config.json.
THEMES: list[dict] = [
    {"name": "teal",   "border": "#2ec4b6", "strip": "#1a1a1a", "bg": "#0a0a0a"},
    {"name": "blue",   "border": "#4a9eff", "strip": "#0d1117", "bg": "#060a0f"},
    {"name": "purple", "border": "#bf5fff", "strip": "#12091a", "bg": "#08040f"},
    {"name": "amber",  "border": "#ffb347", "strip": "#1a1200", "bg": "#0a0900"},
]


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
        u32.SetWindowDisplayAffinity.argtypes = [
            wintypes.HWND, wintypes.DWORD
        ]
        u32.SetWindowDisplayAffinity.restype = wintypes.BOOL
        u32.GetWindowDisplayAffinity.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
        ]
        u32.GetWindowDisplayAffinity.restype = wintypes.BOOL
        _WINDOW_SIGNATURES_APPLIED = True
    return u32


class BubbleWindow:
    """The Phase 2 visible artifact: a borderless, click-through bubble.

    Construction is synchronous and produces a visible window. Call
    self.root.mainloop() (from app.main) to drive the Tk event loop.
    """

    def __init__(
        self,
        state: AppState,
        *,
        click_injection_enabled: bool = True,
    ) -> None:
        self.state: AppState = state
        # Phase 4 Plan 03: cross-process click injection toggle. When True
        # (default), content-zone clicks on the bubble are forwarded to the
        # app below via PostMessageW. When False (set by app.py from the
        # --no-click-injection CLI flag), content-zone clicks are consumed
        # by the bubble — Phase 2 fallback behavior, documented in
        # 04-RESEARCH.md Open Question #1.
        self._click_injection_enabled: bool = click_injection_enabled
        self._wndproc_keepalive: wndproc.WndProcKeepalive | None = None
        self._canvas_wndproc_keepalive: wndproc.WndProcKeepalive | None = None
        self._frame_wndproc_keepalive: wndproc.WndProcKeepalive | None = None
        # Phase 5 (PERS-04): set by app.py via attach_config_writer; used
        # by destroy() to flush pending writes BEFORE Tk teardown so
        # root.after_cancel still has a live root.  None until attached.
        self._config_writer = None  # type: ignore[assignment]
        # Phase 6 (HOTK-05): set by app.py via attach_hotkey_manager; used
        # by destroy() to stop the worker thread BEFORE capture_worker.stop()
        # so a late WM_HOTKEY can't schedule root.after on a tearing-down root.
        # None until attached.  attach_hotkey_manager is a no-op-safe symmetric
        # helper so tests and --no-hotkey paths can skip wiring without branching.
        self._hotkey_manager = None  # type: ignore[assignment]
        # Thread-safe frame queue: the capture thread puts PIL Images here;
        # the main thread drains it via a recurring root.after() poll.
        # This eliminates ALL Tk/Tcl calls from the capture thread, removing
        # the Python 3.14 GIL/PyEval_RestoreThread crash that occurred when
        # root.after(0, ...) was called from the capture thread during any
        # message-pump-active window (modal Send-Message drag loop, WM_NCHITTEST, etc.)
        self._frame_queue: queue.SimpleQueue = queue.SimpleQueue()

        # Theme — loaded from theme.json; determines instance color vars used
        # by _draw_border and _apply_theme.  Defaults to theme 0 until loaded.
        self._theme_idx: int = 0
        self._border_color: str = BORDER_COLOR
        self._strip_color: str = STRIP_COLOR
        self._bg_color: str = BG_COLOR

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
        # Set to the #32768 menu HWND while a context menu is visible after a
        # right-click pass-through.  _on_canvas_press uses it to PostMessageW
        # directly to the known menu window, bypassing inject_click's Z-order
        # walk which can find PROGMAN/WorkerW (full-screen desktop) instead.
        self._active_menu_hwnd: int = 0
        self._active_menu_cls: str = ""   # class of the active menu window
        # True when SetWindowPos on the active menu HWND would dismiss it.
        # Set on first detection; used to skip Z-order fix on every poll tick.
        # Covers both WinUI3 PopupWindowSiteBridge and desktop shell #32768
        # menus (owned by Progman / WorkerW) — both are dismissed by SWP.
        self._active_menu_skip_zorder: bool = False
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

                # --- Step 8b (Phase 3): hall-of-mirrors Path A defense ---
                # SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE) tells
                # the OS to exclude this window from all screen-capture paths.
                # Works against BitBlt+CAPTUREBLT (mss 10.1.0), DXGI Desktop
                # Duplication, screenshot tools, and screen sharing. Windows 10
                # 2004+; on older Windows this silently fails and Path B
                # (CAPTUREBLT=0 in capture.py run()) takes over.
                # See .planning/phases/03-capture-loop/03-RESEARCH.md Pattern 3.
                if not u32.SetWindowDisplayAffinity(
                    self._hwnd, wc.WDA_EXCLUDEFROMCAPTURE
                ):
                    print(
                        "[bubble] SetWindowDisplayAffinity failed "
                        f"(err={ctypes.get_last_error()}); relying on "
                        "capture.py CAPTUREBLT=0 fallback",
                        flush=True,
                    )

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

        # --- Step 9b bis (Phase 3): single ImageTk.PhotoImage + canvas image item ---
        # CAPT-05: one PhotoImage, reused every frame via paste() (not
        # reassigned). Rebuilt only on bubble resize via _on_frame's
        # size-mismatch path (Phase 4 will drive that).
        # CPython issue 124364 defense: NEVER create ImageTk.PhotoImage
        # in the hot loop.
        content_w = snap.w
        content_h = snap.h - DRAG_STRIP_HEIGHT - CONTROL_STRIP_HEIGHT
        self._photo: ImageTk.PhotoImage = ImageTk.PhotoImage(
            "RGB", (content_w, content_h), master=self.root
        )
        self._photo_size: tuple[int, int] = (content_w, content_h)
        # Z-order: image item created LAST among the content-zone items
        # sits ABOVE the canvas background. tag_lower pushes it below the
        # strips and border items so the magnified pixels peek out
        # from the middle zone only.
        self._image_id: int = self._canvas.create_image(
            0, DRAG_STRIP_HEIGHT,
            image=self._photo,
            anchor="nw",
        )
        self._canvas.tag_lower(self._image_id)

        # --- Step 9c (Phase 4): button layout + glyphs + zoom text ---
        # All controls are Canvas items (rectangle + text pairs). Adding
        # a Tk Button-style widget here would create a 4th HWND in the
        # WndProc chain (Pitfall 11) — the structural lint in
        # tests/test_window_phase4.py enforces the no-widget rule.
        # Press routing happens in _on_canvas_press via controls.hit_button.
        self._buttons: list[ButtonRect] = layout_controls(snap.w, snap.h)

        # Grip glyph (CTRL-01) — centered between the close button (left 44 px)
        # and the shape button (right 44 px).
        grip_cx = snap.w // 2
        grip_cy = DRAG_STRIP_HEIGHT // 2
        self._grip_id: int = self._canvas.create_text(
            grip_cx, grip_cy,
            text="\u2261",  # ≡ U+2261 IDENTICAL TO (grip indicator)
            fill=BORDER_COLOR,
            font=("Segoe UI Symbol", 20, "bold"),
        )
        # Bottom grip glyph — mirrors the top grip in the bottom strip's
        # centre, between the zoom buttons (left) and resize grip (right).
        # Bottom strip has no grip glyph — the zoom text occupies the centre
        # and a second ≡ would overlap it.  Top strip ≡ is the drag affordance.
        self._bottom_grip_id: int = self._canvas.create_text(
            -100, -100,  # parked off-screen; kept so _relayout_canvas_items ref is valid
            text="",
        )

        # Close button — top-left 44x44, ✕ glyph (index 0).
        close_btn = self._buttons[0]
        self._close_btn_rect_id: int = self._canvas.create_rectangle(
            close_btn.x, close_btn.y,
            close_btn.x + close_btn.w, close_btn.y + close_btn.h,
            fill=STRIP_COLOR, outline=BORDER_COLOR, width=1,
        )
        self._close_btn_text_id: int = self._canvas.create_text(
            close_btn.x + close_btn.w // 2, close_btn.y + close_btn.h // 2,
            text="\u2715",  # ✕ U+2715 MULTIPLICATION X
            fill="#ff6b6b", font=("Segoe UI Symbol", 18, "bold"),
        )

        # Shape button (CTRL-02) — top-right 44x44, bullseye glyph.
        # layout_controls returns [close, shape, zoom_out, zoom_in, resize].
        shape_btn = self._buttons[1]
        self._shape_btn_rect_id: int = self._canvas.create_rectangle(
            shape_btn.x, shape_btn.y,
            shape_btn.x + shape_btn.w, shape_btn.y + shape_btn.h,
            fill=STRIP_COLOR, outline=BORDER_COLOR, width=1,
        )
        self._shape_btn_text_id: int = self._canvas.create_text(
            shape_btn.x + shape_btn.w // 2, shape_btn.y + shape_btn.h // 2,
            text="\u25ce",  # U+25CE BULLSEYE (shape-cycle indicator)
            fill=BORDER_COLOR, font=("Segoe UI Symbol", 22, "bold"),
        )

        # Zoom-out button [−] (CTRL-04) — bottom-left 44x44.
        zoom_out_btn = self._buttons[2]
        self._zoom_out_rect_id: int = self._canvas.create_rectangle(
            zoom_out_btn.x, zoom_out_btn.y,
            zoom_out_btn.x + zoom_out_btn.w, zoom_out_btn.y + zoom_out_btn.h,
            fill=STRIP_COLOR, outline=BORDER_COLOR, width=1,
        )
        self._zoom_out_text_id: int = self._canvas.create_text(
            zoom_out_btn.x + zoom_out_btn.w // 2,
            zoom_out_btn.y + zoom_out_btn.h // 2,
            text="\u2212",  # − U+2212 MINUS SIGN
            fill=BORDER_COLOR, font=("Segoe UI Symbol", 22, "bold"),
        )

        # Zoom-in button [+] (CTRL-04) — bottom 44x44 at x = w - 88.
        zoom_in_btn = self._buttons[3]
        self._zoom_in_rect_id: int = self._canvas.create_rectangle(
            zoom_in_btn.x, zoom_in_btn.y,
            zoom_in_btn.x + zoom_in_btn.w, zoom_in_btn.y + zoom_in_btn.h,
            fill=STRIP_COLOR, outline=BORDER_COLOR, width=1,
        )
        self._zoom_in_text_id: int = self._canvas.create_text(
            zoom_in_btn.x + zoom_in_btn.w // 2,
            zoom_in_btn.y + zoom_in_btn.h // 2,
            text="+",  # U+002B PLUS SIGN
            fill=BORDER_COLOR, font=("Segoe UI Symbol", 22, "bold"),
        )

        # Live zoom value text (CTRL-04) — centered between zoom buttons.
        zoom_text_cx = (zoom_out_btn.x + zoom_out_btn.w + zoom_in_btn.x) // 2
        zoom_text_cy = zoom_out_btn.y + zoom_out_btn.h // 2
        self._zoom_text_id: int = self._canvas.create_text(
            zoom_text_cx, zoom_text_cy,
            text=f"{snap.zoom:.1f}\u00d7",  # e.g. "2.0×" — 1 decimal, × symbol
            fill=BORDER_COLOR,
            font=("Segoe UI", 16, "bold"),
        )

        # Resize button [⤢] (CTRL-06/07) — bottom-right 44x44.
        resize_btn = self._buttons[4]
        self._resize_btn_rect_id: int = self._canvas.create_rectangle(
            resize_btn.x, resize_btn.y,
            resize_btn.x + resize_btn.w, resize_btn.y + resize_btn.h,
            fill=STRIP_COLOR, outline=BORDER_COLOR, width=1,
        )
        self._resize_btn_text_id: int = self._canvas.create_text(
            resize_btn.x + resize_btn.w // 2, resize_btn.y + resize_btn.h // 2,
            text="\u2922",  # ⤢ U+2922 NORTH EAST AND SOUTH WEST ARROW
            fill=BORDER_COLOR, font=("Segoe UI Symbol", 20, "bold"),
        )

        # Phase 4 resize-drag origin (separate state machine from _drag_origin).
        # Set by _on_canvas_press when event lands in resize button; consumed
        # by _on_canvas_drag (Task 2); cleared by _on_canvas_release.
        self._resize_origin: tuple[int, int, int, int] | None = None

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
        # Phase 4 bug fix: strip_top / strip_bottom arguments UNION the
        # shape region with the full-width drag + control strips, so the
        # shape button (top-right corner) and zoom/resize buttons (bottom
        # corners) remain visible AND clickable when the shape is circle
        # or rounded. Without this, cycling to "circle" clipped the
        # corners away and the user could not tap back out.
        if sys.platform == "win32" and self._hwnd:
            shapes.apply_shape(self._hwnd, snap.w, snap.h, snap.shape,
                               strip_top=DRAG_STRIP_HEIGHT,
                               strip_bottom=CONTROL_STRIP_HEIGHT)

        # --- Manual-geometry drag for the top strip ---
        # WS_EX_NOACTIVATE windows cannot use the OS-managed caption-drag
        # modal move loop (it triggers a re-entrant WndProc pump that
        # released the GIL inside Tk's message handler and crashed
        # Python 3.14 via PyEval_RestoreThread(NULL) — see STATE.md Phase 3
        # decisions). Instead, press records the screen origin, B1-Motion
        # moves the window via geometry(), release syncs AppState. Purely
        # Python — no modal loop, no re-entrant OS pump, no GIL hazard.
        # Phase 4 extends the same three bindings with a resize drag state
        # machine (self._resize_origin) — see _on_canvas_press /
        # _on_canvas_drag / _on_canvas_release below.
        self._drag_origin: tuple[int, int, int, int] | None = None
        self._canvas.bind("<Button-1>", self._on_canvas_press)
        self._canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self._canvas.bind("<Button-3>", self._on_canvas_rclick)

        # Apply saved theme (reconfigures canvas items created above).
        saved_idx = self._load_theme()
        if saved_idx != 0:
            self._apply_theme(saved_idx)

        # --- Graceful teardown on window close ---
        self.root.protocol("WM_DELETE_WINDOW", self.destroy)

        # --- Step 12: Show the window ---
        self.root.deiconify()

        # --- Step 13 (Phase 4): register state observer for shape/size/zoom ---
        # Stores a snapshot to diff against on every notification so the
        # observer knows which of (shape, w, h, zoom) changed. Tk button
        # handlers fire state.set_* from the main thread, so the observer
        # callback also runs on the main thread — safe to call Tk APIs.
        self._prev_snap = self.state.snapshot()
        self.state.on_change(self._on_state_change)

        # Phase 3: capture worker placeholder (started by app.py via start_capture)
        self._capture_worker: CaptureWorker | None = None

        # Magnification API state (alternative to mss capture; set in _mag_init).
        self._hwnd_mag: int = 0        # Magnifier child-window HWND
        self._mag_dll = None           # magnification.dll WinDLL handle
        self._mag_last_zoom: float = 0.0
        self._mag_last_wh: tuple[int, int] = (0, 0)

    # ---- Phase 5: Config writer attach point ----

    def attach_config_writer(self, writer) -> None:
        """Wire a Phase 5 ConfigWriter so destroy() can flush_pending.

        Called from app.py main() AFTER the writer has registered itself
        as an AppState.on_change observer.  Stored as a plain attribute
        (no type import to avoid creating a window.py -> config.py import
        edge that couples Phase 5 wiring into the Phase 2 hard dependency
        chain).  Multiple calls silently overwrite — the last wins.
        """
        self._config_writer = writer

    # ---- Phase 6: Hotkey manager attach point ----

    def attach_hotkey_manager(self, manager) -> None:
        """Wire a Phase 6 HotkeyManager so destroy() can stop it cleanly.

        Called from app.py main() AFTER manager.start() succeeded.  Stored
        as a plain attribute (duck-typed; no type import to avoid creating
        a window.py -> hotkey.py import edge — same discipline as
        attach_config_writer).  Multiple calls silently overwrite.
        """
        self._hotkey_manager = manager

    # ---- Phase 6 (HOTK-03): visibility wrappers ----
    # Called from the Tk main thread — either directly by user actions
    # or scheduled via root.after(0, ...) from the hotkey worker thread.
    # state.set_visible(...) triggers the AppState observer; the observer
    # does NOT re-enter these methods (Pitfall 8 in config.py).

    def show(self) -> None:
        """Reveal the bubble and mark state visible."""
        self.root.deiconify()
        self.state.set_visible(True)

    def hide(self) -> None:
        """Hide the bubble (preserve HWND + capture worker) and mark invisible."""
        self.root.withdraw()
        self.state.set_visible(False)

    def toggle(self) -> None:
        """Flip visibility; called from hotkey worker via root.after(0, ...)."""
        if self.state.snapshot().visible:
            self.hide()
        else:
            self.show()

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
                outline=self._border_color, width=BORDER_WIDTH, fill="",
            )
        return self._canvas.create_rectangle(
            inset, inset, w - inset, h - inset,
            outline=self._border_color, width=BORDER_WIDTH, fill="",
        )

    def _on_canvas_press(self, event) -> None:
        """Phase 4 dispatch: button hit-test first, then drag, then
        Plan 04-03 content-zone click injection.

        Order of checks (first match wins):
          1. controls.hit_button -> named button dispatch
          2. top-strip y < DRAG_STRIP_HEIGHT -> Phase 3 drag start
          3. middle band + click_injection_enabled -> inject_click to
             the app below via PostMessageW (Plan 04-03 / Pattern 6)
          4. otherwise -> no-op (bottom strip without a button hit)
        """
        btn = hit_button(event.x, event.y, self._buttons)
        if btn == "close":
            self.destroy()
            return
        if btn == "shape":
            cur_shape = self.state.snapshot().shape
            self.state.set_shape(SHAPE_CYCLE[cur_shape])
            return
        if btn == "zoom_in":
            self.state.set_zoom(zoom_step(self.state.snapshot().zoom, +1))
            return
        if btn == "zoom_out":
            self.state.set_zoom(zoom_step(self.state.snapshot().zoom, -1))
            return
        if btn == "resize":
            snap = self.state.snapshot()
            self._resize_origin = (
                event.x_root, event.y_root, snap.w, snap.h,
            )
            return
        # No button — drag-start for the top strip OR the bottom strip.
        # Bottom drag allows repositioning when the overlay is near the top
        # of the screen (cursor can't go above y=0 to drag from the top bar).
        _h = self.root.winfo_height()
        if event.y < DRAG_STRIP_HEIGHT or event.y >= _h - CONTROL_STRIP_HEIGHT:
            # If a context menu was active, clear it — the user dragging the
            # overlay signals they've abandoned the menu.  Don't hard-block drag
            # here: if _active_menu_hwnd gets stuck for any reason, the overlay
            # would become permanently immovable (perceived as a crash).
            if self._active_menu_hwnd:
                self._active_menu_hwnd = 0
                self._active_menu_cls = ""
                self._active_menu_skip_zorder = False
            self._drag_origin = (
                event.x_root, event.y_root,
                self.root.winfo_x(), self.root.winfo_y(),
            )
            return
        # Phase 4 Plan 03: content-zone click injection.
        # The middle band is everything between the drag strip and the
        # control strip. If a click lands here (no button hit), forward
        # it to whatever app is below us via PostMessageW. The self-HWND
        # guard inside inject_click (Pitfall I) prevents recursion into
        # our own layered bubble. Import is deferred so clickthru.py's
        # Windows-only ctypes surface stays out of window.py's module-
        # level import graph on non-Windows CI.
        if (
            self._click_injection_enabled
            and sys.platform == "win32"
            and self._hwnd
            and DRAG_STRIP_HEIGHT <= event.y < (self.root.winfo_height() - CONTROL_STRIP_HEIGHT)
        ):
            # Map canvas (event.x, event.y) back through the zoom transform to
            # find the source-content screen coordinate.  The capture worker
            # grabs a (w/zoom × h/zoom) region centered on the overlay, then
            # scales it up.  Inverting that:
            #   src_x = overlay_x + (w - w/zoom) / 2
            #   actual_screen_x = src_x + canvas_x / zoom
            snap = self.state.snapshot()
            zoom = snap.zoom
            src_x = snap.x + (snap.w - snap.w / zoom) / 2
            src_y = snap.y + (snap.h - snap.h / zoom) / 2
            actual_x = round(src_x + event.x / zoom)
            actual_y = round(src_y + (event.y - DRAG_STRIP_HEIGHT) / zoom)
            # Strategy 0: active context menu — hide overlay then SendInput.
            # WinUI3 PopupWindowSiteBridge ignores PostMessageW WM_LBUTTONDOWN;
            # it only processes real hardware pointer events (EnableMouseInPointer).
            # Our overlay has WS_EX_NOACTIVATE so SW_HIDE never steals focus or
            # dismisses the menu (the menu is a separate File Explorer window).
            # Pattern mirrors the existing DesktopChildSiteBridge two-phase path.
            if self._active_menu_hwnd:
                import ctypes as _ct
                from ctypes import wintypes as _wt
                from magnifier_bubble.clickthru import _dbg, send_hover_at, send_click_at
                _u32m = _ct.windll.user32  # type: ignore[attr-defined]
                _menu_h = self._active_menu_hwnd   # local copy — safe to read
                if not _u32m.IsWindowVisible(_menu_h):
                    self._active_menu_hwnd = 0
                    self._active_menu_cls = ""
                    self._active_menu_skip_zorder = False
                    # Menu gone — fall through to inject_click below.
                elif self._active_menu_skip_zorder:
                    # Desktop shell (#32768 owned by Progman/WorkerW) or
                    # WinUI3 PopupWindowSiteBridge — these menus sit ABOVE
                    # our overlay in Z-order (SetWindowPos on them causes an
                    # instant dismissal so we never push them below us).
                    # The Magnifier API shows them because DWM composes them
                    # above the overlay in the scene.
                    # The zoom-mapped (actual_x, actual_y) correctly maps the
                    # canvas click to the menu item's real screen position —
                    # the same math that placed the right-click.
                    # No WS_EX_TRANSPARENT needed: the menu is the topmost
                    # window at (actual_x, actual_y), so SendInput routes to
                    # it naturally without any transparency tricks.
                    from magnifier_bubble.clickthru import _dbg, send_click_at as _sca
                    _u32m.ReleaseCapture()
                    _dbg(f"menu lclick skip_zorder: actual=({actual_x},{actual_y})")
                    _sca(actual_x, actual_y)
                    return
                else:
                    # Determine the menu class — WinUI3 vs classic Win32/Chrome.
                    _cls_b = _ct.create_unicode_buffer(128)
                    _u32m.GetClassNameW(_menu_h, _cls_b, 128)
                    _mcls  = _cls_b.value
                    _dbg(f"menu lclick: cls={_mcls!r} actual=({actual_x},{actual_y})")

                    if "PopupWindowSiteBridge" in _mcls:
                        # WinUI3 popup: HTTRANSPARENT alone is insufficient —
                        # WindowFromPoint still reports our canvas so the
                        # deferred SendInput LEFTDOWN is re-delivered to us,
                        # causing an infinite _on_canvas_press loop.
                        # Fix: set WS_EX_TRANSPARENT immediately before
                        # send_click_at fires (inside the deferred callback)
                        # so the OS bypasses our window for that one click.
                        # WS_EX_TRANSPARENT is cleared 16 ms later — a short
                        # enough window that physical user right-clicks during
                        # the 150 ms hover delay still reach Tk normally.
                        _u32m.ReleaseCapture()
                        _dbg(
                            f"menu lclick WinUI3:"
                            f" actual=({actual_x},{actual_y})"
                        )
                        send_hover_at(actual_x, actual_y)
                        def _do_click_ui3(
                            _ax=actual_x, _ay=actual_y,
                            _hwnd=self._hwnd, _u=_u32m,
                            _root=self.root,
                        ):
                            # Set WS_EX_TRANSPARENT just before the click.
                            _cx = _u.GetWindowLongW(_hwnd, -20)
                            _u.SetWindowLongW(
                                _hwnd, -20,
                                _cx | wc.WS_EX_TRANSPARENT,
                            )
                            send_click_at(_ax, _ay)
                            # Restore after one frame — SendInput events are
                            # in the hardware queue and will be routed while
                            # WS_EX_TRANSPARENT is still set.  16 ms is enough.
                            _clean = _cx & ~wc.WS_EX_TRANSPARENT
                            _root.after(
                                16,
                                lambda __u=_u, __h=_hwnd, __ex=_clean:
                                    __u.SetWindowLongW(__h, -20, __ex),
                            )
                        self.root.after(150, _do_click_ui3)
                    else:
                        # Classic Win32 / Chrome / Firefox menus (pushed below
                        # our overlay by _poll_menu_restore).  PostMessageW
                        # directly to the known menu HWND — bypasses all
                        # WS_EX_TRANSPARENT / Canvas-interception problems.
                        # WS_EX_TRANSPARENT on self._hwnd does NOT propagate
                        # to the Canvas child, so SendInput still routes back
                        # to our canvas.  PostMessageW sidesteps hit-testing
                        # entirely by targeting the menu window identity.
                        # ScreenToClient converts (actual_x, actual_y) to
                        # client coordinates the menu expects in lParam.
                        import ctypes as _ct2
                        from ctypes import wintypes as _wt2
                        _pt2 = _wt2.POINT()
                        _pt2.x = actual_x
                        _pt2.y = actual_y
                        _u32m.ScreenToClient(_ct2.c_void_p(_menu_h), _ct2.byref(_pt2))
                        _cx2, _cy2 = _pt2.x, _pt2.y
                        _lp2 = (_cy2 << 16) | (_cx2 & 0xFFFF)
                        _u32m.ReleaseCapture()
                        _dbg(
                            f"menu lclick PostMsgW:"
                            f" hwnd={_menu_h}"
                            f" client=({_cx2},{_cy2})"
                            f" actual=({actual_x},{actual_y})"
                        )
                        _u32m.PostMessageW(_ct2.c_void_p(_menu_h), wc.WM_LBUTTONDOWN, 0, _lp2)
                        _u32m.PostMessageW(_ct2.c_void_p(_menu_h), wc.WM_LBUTTONUP, 0, _lp2)
                    return
            # Strategy 1: PostMessageW directly to the deepest child HWND below
            # our bubble (no hide/show needed — message goes straight to the
            # target's queue regardless of z-order).  inject_click walks the
            # Z-order past own_hwnd so it never returns our own HWND.
            from magnifier_bubble.clickthru import (
                inject_click, send_click_at, send_hover_at, inject_touch_at,
            )
            _result = inject_click(actual_x, actual_y, self._hwnd)
            if _result is not True:
                # Strategy 2 / 3: hide overlay, inject input, restore.
                # _result is False  → SW_HIDE + SendInput  (mouse events)
                # _result is None   → SW_HIDE + WinUI3 two-phase hover→click
                import ctypes as _ct
                from ctypes import wintypes as _wt
                _u32 = _ct.windll.user32  # type: ignore[attr-defined]
                _old_pt = _wt.POINT()
                _u32.GetCursorPos(_ct.byref(_old_pt))
                old_cx, old_cy = _old_pt.x, _old_pt.y
                _u32.ShowWindow(self._hwnd, 0)   # SW_HIDE
                # Defer input by 50 ms so DWM and WinUI3's DirectComposition
                # tree process SW_HIDE before synthetic input arrives.
                if _result is None:
                    # WinUI3 path (DesktopChildSiteBridge / breadcrumb bar).
                    # Strategy A: InjectTouchInput — goes through the OS pointer
                    # stack WinUI3 registers for.  Requires a touch digitizer
                    # driver; fails with 0x57 on non-touch hardware.
                    # Strategy B (fallback): two-phase SendInput.
                    #   Phase 1 — MOVE (hover): arms the BreadcrumbBar item by
                    #     triggering WinUI3 PointerEntered.
                    #   Phase 2 — DOWN + UP: fires 150 ms later so WinUI3 has
                    #     processed PointerEntered before PointerPressed arrives.
                    def _deferred_winui3(
                        _u32=_u32, _hwnd=self._hwnd,
                        _cx=old_cx, _cy=old_cy,
                        _ax=actual_x, _ay=actual_y,
                    ):
                        if inject_touch_at(_ax, _ay):
                            def _restore(__u32=_u32, __hwnd=_hwnd, __cx=_cx, __cy=_cy):
                                __u32.ShowWindow(__hwnd, 8)
                                __u32.SetCursorPos(__cx, __cy)
                            self.root.after(32, _restore)
                        else:
                            # Touch unavailable — two-phase mouse: hover then click.
                            send_hover_at(_ax, _ay)
                            def _phase2(
                                __u32=_u32, __hwnd=_hwnd,
                                __cx=_cx, __cy=_cy,
                                __ax=_ax, __ay=_ay,
                            ):
                                send_click_at(__ax, __ay)
                                def _restore(
                                    ___u32=__u32, ___hwnd=__hwnd,
                                    ___cx=__cx, ___cy=__cy,
                                ):
                                    ___u32.ShowWindow(___hwnd, 8)
                                    ___u32.SetCursorPos(___cx, ___cy)
                                self.root.after(32, _restore)
                            self.root.after(150, _phase2)
                    self.root.after(50, _deferred_winui3)
                else:
                    # Mouse path: SW_HIDE + SendInput for targets that ignore
                    # PostMessageW (e.g. ContentIslandWindow).
                    def _deferred(
                        _u32=_u32, _hwnd=self._hwnd,
                        _cx=old_cx, _cy=old_cy,
                        _ax=actual_x, _ay=actual_y,
                    ):
                        send_click_at(_ax, _ay)
                        def _restore(__u32=_u32, __hwnd=_hwnd, __cx=_cx, __cy=_cy):
                            __u32.ShowWindow(__hwnd, 8)   # SW_SHOWNA
                            __u32.SetCursorPos(__cx, __cy)
                        self.root.after(32, _restore)
                    self.root.after(50, _deferred)

    def _on_canvas_drag(self, event) -> None:
        """Phase 4 amended: resize drag takes precedence over move drag.

        The two state machines are mutually exclusive — press only sets
        _resize_origin XOR _drag_origin, so checking resize first is safe.
        """
        if self._resize_origin is not None:
            sx0, sy0, w0, h0 = self._resize_origin
            raw_w = w0 + (event.x_root - sx0)
            raw_h = h0 + (event.y_root - sy0)
            new_w, new_h = resize_clamp(raw_w, raw_h)
            # Top-left stays fixed; only the bottom-right corner moves.
            cur_x = self.root.winfo_x()
            cur_y = self.root.winfo_y()
            self.root.geometry(f"{new_w}x{new_h}+{cur_x}+{cur_y}")
            # AppState write — observer re-applies SetWindowRgn + re-layouts buttons.
            self.state.set_size(new_w, new_h)
            return
        # Existing Phase 3 drag motion (unchanged)
        if self._drag_origin is None:
            return
        sx0, sy0, wx0, wy0 = self._drag_origin
        new_x = wx0 + (event.x_root - sx0)
        new_y = wy0 + (event.y_root - sy0)
        self.root.geometry(f"+{new_x}+{new_y}")
        # Update AppState immediately so the capture thread grabs from
        # the new position on its next tick — live drag content update.
        self.state.set_position(new_x, new_y)

    def _on_canvas_release(self, event) -> None:
        """Phase 4 amended: clear resize origin OR finish move drag."""
        if self._resize_origin is not None:
            self._resize_origin = None
            return
        if self._drag_origin is None:
            return
        self._drag_origin = None
        self.state.set_position(self.root.winfo_x(), self.root.winfo_y())

    # ---- Phase 4: AppState observer + canvas relayout ----

    def _on_state_change(self) -> None:
        """AppState observer. Runs on the Tk main thread because every
        state.set_* caller is a Tk event binding. MUST NOT call state.set_*
        or the observer loops (Pitfall G — re-entrancy).

        Diffs against self._prev_snap to determine which of shape / size /
        zoom changed, then applies the corresponding visual update.
        """
        snap = self.state.snapshot()
        prev = self._prev_snap
        if snap.shape != prev.shape and sys.platform == "win32" and self._hwnd:
            # Strip-aware HRGN — union with top + bottom strip rects so
            # the shape / zoom / resize buttons in the corners remain
            # clickable even in circle / rounded modes (bug: cycling into
            # circle clipped the control corners away).
            shapes.apply_shape(
                self._hwnd, snap.w, snap.h, snap.shape,
                strip_top=DRAG_STRIP_HEIGHT,
                strip_bottom=CONTROL_STRIP_HEIGHT,
            )
            self._canvas.delete(self._border_id)
            self._border_id = self._draw_border(snap.w, snap.h, snap.shape)
        if (snap.w, snap.h) != (prev.w, prev.h):
            if sys.platform == "win32" and self._hwnd:
                shapes.apply_shape(
                    self._hwnd, snap.w, snap.h, snap.shape,
                    strip_top=DRAG_STRIP_HEIGHT,
                    strip_bottom=CONTROL_STRIP_HEIGHT,
                )
            self._buttons = layout_controls(snap.w, snap.h)
            self._relayout_canvas_items(snap.w, snap.h, snap.shape)
        if snap.zoom != prev.zoom:
            self._canvas.itemconfig(
                self._zoom_text_id, text=f"{snap.zoom:.1f}\u00d7"
            )
        self._prev_snap = snap

    def _relayout_canvas_items(self, w: int, h: int, shape: str) -> None:
        """Move every canvas item to match the new window size.

        Called from _on_state_change on size change. Uses canvas.coords()
        for items and canvas.configure() for the canvas widget itself.
        The image item's size is driven by the capture loop's _on_frame
        size-mismatch path — do NOT rebuild PhotoImage here.
        """
        self._canvas.configure(width=w, height=h)
        # Top + bottom strips
        self._canvas.coords(self._top_strip_id, 0, 0, w, DRAG_STRIP_HEIGHT)
        self._canvas.coords(
            self._bottom_strip_id,
            0, h - CONTROL_STRIP_HEIGHT, w, h,
        )
        # Border — delete and redraw for correct shape/coords
        self._canvas.delete(self._border_id)
        self._border_id = self._draw_border(w, h, shape)
        # Grip glyphs — re-center top (between close and shape) and bottom
        self._canvas.coords(self._grip_id, w // 2, DRAG_STRIP_HEIGHT // 2)
        self._canvas.coords(self._bottom_grip_id, w // 2, h - CONTROL_STRIP_HEIGHT // 2)
        # Close button (index 0) — fixed at top-left; x/y don't change with w/h
        cb = self._buttons[0]
        self._canvas.coords(
            self._close_btn_rect_id, cb.x, cb.y, cb.x + cb.w, cb.y + cb.h,
        )
        self._canvas.coords(
            self._close_btn_text_id, cb.x + cb.w // 2, cb.y + cb.h // 2,
        )
        # Shape button (index 1)
        sb = self._buttons[1]
        self._canvas.coords(
            self._shape_btn_rect_id, sb.x, sb.y, sb.x + sb.w, sb.y + sb.h,
        )
        self._canvas.coords(
            self._shape_btn_text_id, sb.x + sb.w // 2, sb.y + sb.h // 2,
        )
        # Zoom-out (index 2)
        zob = self._buttons[2]
        self._canvas.coords(
            self._zoom_out_rect_id, zob.x, zob.y, zob.x + zob.w, zob.y + zob.h,
        )
        self._canvas.coords(
            self._zoom_out_text_id, zob.x + zob.w // 2, zob.y + zob.h // 2,
        )
        # Zoom-in (index 3)
        zib = self._buttons[3]
        self._canvas.coords(
            self._zoom_in_rect_id, zib.x, zib.y, zib.x + zib.w, zib.y + zib.h,
        )
        self._canvas.coords(
            self._zoom_in_text_id, zib.x + zib.w // 2, zib.y + zib.h // 2,
        )
        # Zoom text — re-center between zoom_out and zoom_in
        zoom_text_cx = (zob.x + zob.w + zib.x) // 2
        zoom_text_cy = zob.y + zob.h // 2
        self._canvas.coords(self._zoom_text_id, zoom_text_cx, zoom_text_cy)
        # Resize button (index 4)
        rb = self._buttons[4]
        self._canvas.coords(
            self._resize_btn_rect_id, rb.x, rb.y, rb.x + rb.w, rb.y + rb.h,
        )
        self._canvas.coords(
            self._resize_btn_text_id, rb.x + rb.w // 2, rb.y + rb.h // 2,
        )

    # ---- Phase 3: capture consumer ----

    def _poll_frame_queue(self) -> None:
        """Main-thread timer callback: drain the frame queue and display the
        latest frame. Scheduled only from the main thread via root.after(),
        so it always runs inside the Tk event loop — never from the capture
        thread. This is the single place where frames cross the thread
        boundary safely: the capture thread puts, the main thread gets.

        Drains all pending frames each tick (drops stale frames, displays
        only the most recent) to avoid a growing backlog when Tk is busy.
        """
        img = None
        while True:
            try:
                img = self._frame_queue.get_nowait()
            except queue.Empty:
                break
        if img is not None:
            self._on_frame(img)
        self.root.after(16, self._poll_frame_queue)  # ~60 fps poll

    def _on_frame(self, img) -> None:
        """Runs on the Tk main thread, called only from _poll_frame_queue.
        Paste the pre-resized PIL.Image into the single reused PhotoImage.
        Rebuild the PhotoImage only if the bubble has been resized since
        the last frame (Phase 4 will drive this path via state.set_size).
        """
        if img.size != self._photo_size:
            self._photo = ImageTk.PhotoImage("RGB", img.size, master=self.root)
            self._photo_size = img.size
            self._canvas.itemconfig(self._image_id, image=self._photo)
        self._photo.paste(img)

    # ---- Magnification API (preferred renderer — captures popup menus) ----

    def _mag_init(self) -> bool:
        """Initialise the Windows Magnification API and create a Magnifier
        child window that covers the content zone of the bubble.

        The Magnifier class is a DWM-level compositor that captures the
        desktop *before* our overlay is composited, so popup menus and
        other always-on-top windows appear correctly magnified.  We call
        MagSetWindowFilterList to exclude self._hwnd from the magnified
        view (anti-hall-of-mirrors).

        Returns True on success; caller falls back to the mss path on False.
        """
        try:
            import ctypes as _ct
            from ctypes import wintypes as _wt

            _mag = _ct.WinDLL("magnification.dll")
            _mag.MagInitialize.restype = _ct.c_bool
            if not _mag.MagInitialize():
                print("[mag] MagInitialize returned False", flush=True)
                return False

            snap = self.state.snapshot()
            _cx = BORDER_WIDTH
            _cy = DRAG_STRIP_HEIGHT
            _cw = snap.w - 2 * BORDER_WIDTH
            _ch = snap.h - DRAG_STRIP_HEIGHT - CONTROL_STRIP_HEIGHT

            _WS_CHILD   = 0x40000000
            _WS_VISIBLE = 0x10000000
            _u32 = _ct.windll.user32
            hwnd_mag = _u32.CreateWindowExW(
                0, "Magnifier", "",
                _WS_CHILD | _WS_VISIBLE,
                _cx, _cy, _cw, _ch,
                self._hwnd,   # parent: outer wrapper above the Tk frame
                None, None, None,
            )
            if not hwnd_mag:
                _mag.MagUninitialize()
                print("[mag] CreateWindowExW(Magnifier) failed", flush=True)
                return False

            # Exclude our overlay from magnification to prevent hall-of-mirrors.
            # MW_FILTERMODE_EXCLUDE = 1
            _mag.MagSetWindowFilterList.argtypes = [
                _wt.HWND, _ct.c_uint32, _ct.c_int, _ct.POINTER(_wt.HWND)
            ]
            _hwnd_arr = (_wt.HWND * 1)(self._hwnd)
            _mag.MagSetWindowFilterList(hwnd_mag, 1, 1, _hwnd_arr)

            # Wire argtypes for hot-path calls (avoids repeated inference).
            _mag.MagSetWindowTransform.argtypes = [
                _wt.HWND, _ct.POINTER(_MAGTRANSFORM)
            ]
            _mag.MagSetWindowTransform.restype = _ct.c_bool
            _mag.MagSetWindowSource.argtypes = [_wt.HWND, _wt.RECT]
            _mag.MagSetWindowSource.restype = _ct.c_bool

            self._hwnd_mag = hwnd_mag
            self._mag_dll  = _mag
            print(f"[mag] Magnifier hwnd={hwnd_mag:#010x}", flush=True)
            return True

        except Exception as exc:
            print(f"[mag] init failed: {exc}", flush=True)
            return False

    def _mag_set_transform(self, zoom: float) -> None:
        """Push a new zoom transform to the Magnifier window."""
        t = _MAGTRANSFORM()
        t.v[0][0] = zoom
        t.v[1][1] = zoom
        t.v[2][2] = 1.0
        self._mag_dll.MagSetWindowTransform(self._hwnd_mag, ctypes.byref(t))

    def _mag_tick(self) -> None:
        """60-fps main-thread timer: sync Magnifier position/size/source from
        current AppState.  Replaces the mss CaptureWorker + _poll_frame_queue
        pipeline when the Magnification API is active.
        """
        if not self._hwnd_mag or self._mag_dll is None:
            return

        import ctypes as _ct
        from ctypes import wintypes as _wt

        snap = self.state.snapshot()
        zoom = snap.zoom

        # Resize Magnifier child if the bubble was resized.
        _cw = snap.w - 2 * BORDER_WIDTH
        _ch = snap.h - DRAG_STRIP_HEIGHT - CONTROL_STRIP_HEIGHT
        if (_cw, _ch) != self._mag_last_wh:
            _ct.windll.user32.MoveWindow(
                self._hwnd_mag, BORDER_WIDTH, DRAG_STRIP_HEIGHT, _cw, _ch, True
            )
            self._mag_last_wh = (_cw, _ch)

        # Update transform only when zoom changes.
        if zoom != self._mag_last_zoom:
            self._mag_set_transform(zoom)
            self._mag_last_zoom = zoom

        # Update source rectangle every tick (window may have moved).
        _src_x = snap.x + (snap.w - snap.w / zoom) / 2
        _src_y = snap.y + (snap.h - snap.h / zoom) / 2
        _rect = _wt.RECT(
            int(_src_x), int(_src_y),
            int(_src_x + snap.w / zoom), int(_src_y + snap.h / zoom),
        )
        self._mag_dll.MagSetWindowSource(self._hwnd_mag, _rect)

        self.root.after(16, self._mag_tick)

    def start_capture(self) -> None:
        """Start the rendering pipeline.  Tries the Windows Magnification API
        first — it captures at the DWM level so popup menus and other always-
        on-top windows are visible in the zoom view.  Falls back to the mss
        CaptureWorker if the Magnification API is unavailable.

        Safe to call more than once (no-op on repeated calls).
        """
        if self._capture_worker is not None or self._hwnd_mag:
            return
        if sys.platform == "win32" and self._mag_init():
            self._mag_tick()   # kick off 60-fps update loop
            return
        # mss fallback: the capture thread puts PIL Images into _frame_queue;
        # _poll_frame_queue drains them on the main thread via root.after.
        self._capture_worker = CaptureWorker(
            state=self.state,
            on_frame=self._frame_queue.put,  # thread-safe; no Tk calls
        )
        self._capture_worker.start()
        self._poll_frame_queue()  # start the main-thread display loop

    # ---- Theme support ----

    def _load_theme(self) -> int:
        """Read theme index from theme.json next to config.json. Never raises."""
        try:
            import json as _j
            from magnifier_bubble import config as _cfg
            p = _cfg.config_path().parent / "theme.json"
            if p.exists():
                idx = int(_j.loads(p.read_text(encoding="utf-8")).get("theme", 0))
                return max(0, min(len(THEMES) - 1, idx))
        except Exception:
            pass
        return 0

    def _save_theme(self) -> None:
        """Write current theme index to theme.json. Never raises."""
        try:
            import json as _j
            from magnifier_bubble import config as _cfg
            p = _cfg.config_path().parent / "theme.json"
            p.write_text(_j.dumps({"theme": self._theme_idx}), encoding="utf-8")
        except Exception:
            pass

    def _apply_theme(self, idx: int) -> None:
        """Switch to theme[idx], reconfigure all canvas items, update instance vars."""
        idx = idx % len(THEMES)
        t = THEMES[idx]
        self._theme_idx = idx
        self._border_color = t["border"]
        self._strip_color = t["strip"]
        self._bg_color = t["bg"]
        bc, sc = self._border_color, self._strip_color
        self._canvas.configure(bg=self._bg_color)
        self._canvas.itemconfig(self._top_strip_id, fill=sc)
        self._canvas.itemconfig(self._bottom_strip_id, fill=sc)
        self._canvas.delete(self._border_id)
        snap = self.state.snapshot()
        self._border_id = self._draw_border(snap.w, snap.h, snap.shape)
        self._canvas.itemconfig(self._grip_id, fill=bc)
        self._canvas.itemconfig(self._close_btn_rect_id, fill=sc, outline=bc)
        self._canvas.itemconfig(self._shape_btn_rect_id, fill=sc, outline=bc)
        self._canvas.itemconfig(self._shape_btn_text_id, fill=bc)
        self._canvas.itemconfig(self._zoom_out_rect_id, fill=sc, outline=bc)
        self._canvas.itemconfig(self._zoom_out_text_id, fill=bc)
        self._canvas.itemconfig(self._zoom_in_rect_id, fill=sc, outline=bc)
        self._canvas.itemconfig(self._zoom_in_text_id, fill=bc)
        self._canvas.itemconfig(self._zoom_text_id, fill=bc)
        self._canvas.itemconfig(self._resize_btn_rect_id, fill=sc, outline=bc)
        self._canvas.itemconfig(self._resize_btn_text_id, fill=bc)

    def _on_canvas_rclick(self, event) -> None:
        """Right-click dispatch:
          - Top strip  → cycle color theme.
          - Content zone → pass right-click through to app below.
          - Bottom strip → no-op (our control area).

        Content-zone strategy: temporarily add WS_EX_TRANSPARENT so the
        overlay stays fully visible (no flicker) but mouse input falls through
        to whatever is beneath.  send_rclick_at injects the right-click and
        atomically restores the cursor position in the same SendInput batch
        (sub-frame, imperceptible).  _poll_menu_restore races the overlay above
        the resulting popup so the Magnification API can show it zoomed.
        """
        if event.y < DRAG_STRIP_HEIGHT:
            self._apply_theme(self._theme_idx + 1)
            self._save_theme()
            return
        _h = self.root.winfo_height()
        if (
            self._click_injection_enabled
            and sys.platform == "win32"
            and self._hwnd
            and DRAG_STRIP_HEIGHT <= event.y < (_h - CONTROL_STRIP_HEIGHT)
        ):
            from magnifier_bubble.clickthru import inject_right_click
            import ctypes as _ct
            _u32 = _ct.windll.user32  # type: ignore[attr-defined]
            snap = self.state.snapshot()
            zoom = snap.zoom
            src_x = snap.x + (snap.w - snap.w / zoom) / 2
            src_y = snap.y + (snap.h - snap.h / zoom) / 2
            actual_x = round(src_x + event.x / zoom)
            actual_y = round(src_y + (event.y - DRAG_STRIP_HEIGHT) / zoom)
            # Clear any stale menu state from a previous right-click so a
            # fresh _poll_menu_restore chain starts without interference.
            self._active_menu_hwnd = 0
            self._active_menu_cls = ""
            self._active_menu_skip_zorder = False
            # Store screen coords so _poll_menu_restore can proximity-filter
            # newly appeared popup windows.
            self._rclick_screen_x = actual_x
            self._rclick_screen_y = actual_y
            # PostMessageW directly to the window below — identical pattern to
            # inject_click for left-clicks.  No WS_EX_TRANSPARENT toggling
            # needed: PostMessageW targets the window by HWND identity and
            # bypasses OS hit-testing entirely.  The previous send_rclick_at
            # (SendInput + WS_EX_TRANSPARENT) was broken because the Canvas
            # child HWND returns HTCLIENT, routing SendInput events back to
            # us instead of the target.
            inject_right_click(actual_x, actual_y, self._hwnd)
            # _poll_menu_restore detects the resulting context-menu popup,
            # manages Z-order so the Magnifier API can show it, and sets
            # _active_menu_hwnd so _on_canvas_press routes left-clicks to
            # the menu via PostMessageW (not inject_click's Z-order walk,
            # which could land on a full-screen desktop HWND instead).
            _raw = _u32.GetWindowLongW(self._hwnd, wc.GWL_EXSTYLE)
            _saved = _raw & ~wc.WS_EX_TRANSPARENT
            self.root.after(
                16,
                lambda: self._poll_menu_restore(_u32, self._hwnd, _saved),
            )

    def _poll_menu_restore(
        self,
        u32,
        hwnd,
        saved_exstyle: int,
        attempts: int = 0,
        seen: bool = False,
    ) -> None:
        """Poll for the context-menu popup and manage overlay Z-order.

        Detection is two-tier:
          1. FindWindowW on known classes (#32768, CoreWindow) — fast path.
          2. EnumWindows proximity search — class-agnostic fallback that
             catches WinUI3/Chrome menus which reuse pre-existing HWNDs.

        Z-order: overlay is re-asserted at HWND_TOPMOST.  Classic Win32 /
        Chrome / Firefox menus are pushed just below us so the Magnification
        API captures them in the source-rect view.  WinUI3 PopupWindowSiteBridge
        (File Explorer) and desktop shell menus (Progman/WorkerW owned) are
        dismissed by any SetWindowPos call on their HWND, so we skip the push
        for them — they appear unmagnified above or near the overlay instead.

        WS_EX_TRANSPARENT is removed as soon as the menu is first detected so
        that left-clicks are received by Tk and forwarded via inject_click with
        zoom-mapped coordinates (clicking the correct menu item).
        """
        _GRACE = 40    # 40 × 50 ms = 2 s grace period before first detection
        _MAX   = 600   # 600 × 50 ms = 30 s max — user may read menu slowly
        # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
        _SWP   = 0x0001 | 0x0002 | 0x0010

        # Fast path once the menu has been found: skip the expensive detection
        # (FindWindowW + EnumWindows) and just check if the known HWND is still
        # visible.  Cuts per-tick cost from ~2 ms to ~0.1 ms while menu is open.
        if seen and self._active_menu_hwnd:
            import ctypes as _ct
            _u32c = _ct.windll.user32
            _still_up = bool(_u32c.IsWindowVisible(self._active_menu_hwnd))
            if _still_up:
                u32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, _SWP)
                # For WinUI3 PopupWindowSiteBridge (desktop / File Explorer
                # context menus): do NOT push the menu below us — even a single
                # SetWindowPos call on those HWNDs triggers an immediate dismissal.
                # For classic Win32 / Chrome / Firefox menus: push below us every
                # tick so the Magnifier API can show them (DWM composes them into
                # the source rect only when they are below our overlay in Z-order).
                if not self._active_menu_skip_zorder:
                    u32.SetWindowPos(self._active_menu_hwnd, hwnd, 0, 0, 0, 0, _SWP)
                if attempts < _MAX:
                    self.root.after(
                        50,
                        lambda: self._poll_menu_restore(
                            u32, hwnd, saved_exstyle, attempts + 1, True
                        ),
                    )
                else:
                    self._active_menu_hwnd = 0
                    self._active_menu_cls = ""
                    self._active_menu_skip_zorder = False
            else:
                try:
                    from magnifier_bubble.clickthru import _dbg
                    _dbg(f"poll_menu: DISMISSED attempts={attempts}")
                except Exception:
                    pass
                u32.SetWindowLongW(hwnd, wc.GWL_EXSTYLE, saved_exstyle)
                self._active_menu_hwnd = 0
                self._active_menu_cls = ""
                self._active_menu_skip_zorder = False
            return

        menu_hwnd = 0
        try:
            import ctypes as _ct
            from ctypes import wintypes as _wt
            _u32c = _ct.windll.user32
            # #32768 is the Win32 popup-menu class used by all shell context
            # menus (File Explorer, desktop, etc.).  CoreWindow / other XAML
            # classes are intentionally excluded — they match persistent Windows
            # 11 system-UI windows (Start, Widgets, Notification Center) and
            # would leave WS_EX_TRANSPARENT stuck on forever.
            _h = _u32c.FindWindowW("#32768", None)
            # Accept the topmost #32768 window unconditionally — FindWindowW
            # returns the topmost Z-order match, which is our freshly created
            # menu after a right-click.  Any alien persistent window from
            # another app sits lower in Z-order and is skipped by the API.
            # known_hwnds filtering here was too aggressive: Windows shell
            # reuses a hidden #32768 window (already in the EnumWindows snapshot)
            # rather than creating a fresh HWND, so the filter incorrectly
            # rejected the desktop right-click menu.
            if _h:
                menu_hwnd = int(_h)
            # Fallback: proximity search — find the topmost visible WS_POPUP
            # within ~200 px of where the right-click landed.  We do NOT use a
            # known_hwnds diff because Chrome and WinUI3 reuse pre-existing
            # hidden popup HWNDs (same pattern as the shell's #32768 reuse):
            # those HWNDs would be in the diff snapshot and therefore skipped,
            # causing detection to fail for 1-2 seconds.
            if not menu_hwnd:
                _cx    = getattr(self, '_rclick_screen_x', 0)
                _cy    = getattr(self, '_rclick_screen_y', 0)
                _own   = int(hwnd)
                _MRG   = 200   # px slack — menus often appear offset from cursor
                _WS_POPUP  = 0x80000000
                _GWL_STYLE = -16
                _best  = [0]
                _CB2   = _ct.WINFUNCTYPE(_ct.c_bool, _wt.HWND, _wt.LPARAM)
                def _chk2(h, _lp):
                    _hi = int(h)
                    if _hi == _own or _best[0]:
                        return True
                    if _u32c.IsWindowVisible(h):
                        _sty = _u32c.GetWindowLongW(h, _GWL_STYLE)
                        if _sty & _WS_POPUP:
                            _r = _wt.RECT()
                            _u32c.GetWindowRect(h, _ct.byref(_r))
                            _w  = _r.right  - _r.left
                            _hh = _r.bottom - _r.top
                            if 20 < _w < 1200 and 20 < _hh < 1200:
                                if (
                                    _r.left - _MRG <= _cx <= _r.right  + _MRG
                                    and _r.top  - _MRG <= _cy <= _r.bottom + _MRG
                                ):
                                    _best[0] = _hi
                    return True
                _cb2_obj = _CB2(_chk2)
                _u32c.EnumWindows(_cb2_obj, 0)
                if _best[0]:
                    menu_hwnd = _best[0]
        except Exception:
            menu_hwnd = 0

        menu_up = bool(menu_hwnd)

        if menu_up:
            if not seen:
                # Capture the menu class NOW (outside logging try-block) so
                # we can store it for Z-order and _on_canvas_press decisions.
                try:
                    _cls_buf2 = _ct.create_unicode_buffer(128)
                    _u32c.GetClassNameW(_ct.c_void_p(menu_hwnd), _cls_buf2, 128)
                    _detected_cls = _cls_buf2.value
                except Exception:
                    _detected_cls = ""
                self._active_menu_cls = _detected_cls
                # Determine whether SetWindowPos on this menu HWND would
                # dismiss it immediately.  Two known dismiss-on-SWP cases:
                #   1. WinUI3 PopupWindowSiteBridge (File Explorer menus)
                #   2. Desktop shell #32768 menus owned by Progman / WorkerW
                # Classic Chrome / Firefox / Win32 app menus are safe to push.
                _skip_z = "PopupWindowSiteBridge" in _detected_cls
                if not _skip_z:
                    try:
                        _GW_OWNER = 4
                        _ow = _u32c.GetWindow(_ct.c_void_p(menu_hwnd), _GW_OWNER)
                        if _ow:
                            _ob = _ct.create_unicode_buffer(64)
                            _u32c.GetClassNameW(_ct.c_void_p(_ow), _ob, 64)
                            if _ob.value in ("Progman", "WorkerW", "SHELLDLL_DefView"):
                                _skip_z = True
                    except Exception:
                        pass
                self._active_menu_skip_zorder = _skip_z
                try:
                    from magnifier_bubble.clickthru import _dbg
                    _dbg(
                        f"poll_menu: DETECTED hwnd={menu_hwnd} cls={_detected_cls!r}"
                        f" skip_zorder={_skip_z} attempts={attempts}"
                    )
                except Exception:
                    pass
            # Assert our overlay at absolute top of topmost band.
            u32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, _SWP)
            # Selective Z-order fix: push classic Win32 / Chrome / Firefox menus
            # below us so the Magnifier API shows them in the source-rect view.
            # WinUI3 PopupWindowSiteBridge and desktop shell menus (Progman/
            # WorkerW owned) are dismissed by SetWindowPos — skip for them.
            if not self._active_menu_skip_zorder:
                u32.SetWindowPos(menu_hwnd, hwnd, 0, 0, 0, 0, _SWP)
            # Remove WS_EX_TRANSPARENT immediately so subsequent left-clicks
            # are received by Tk and dispatched through _on_canvas_press.
            u32.SetWindowLongW(hwnd, wc.GWL_EXSTYLE, saved_exstyle)
            self._active_menu_hwnd = menu_hwnd
            if attempts < _MAX:
                self.root.after(
                    50,
                    lambda: self._poll_menu_restore(
                        u32, hwnd, saved_exstyle, attempts + 1, True
                    ),
                )
            else:
                # Polling budget exhausted — menu still visible but give up.
                self._active_menu_hwnd = 0
                self._active_menu_cls = ""
                self._active_menu_skip_zorder = False
            return

        if not seen:
            if attempts < _GRACE:
                self.root.after(
                    50,
                    lambda: self._poll_menu_restore(
                        u32, hwnd, saved_exstyle, attempts + 1, False
                    ),
                )
                return
            u32.SetWindowLongW(hwnd, wc.GWL_EXSTYLE, saved_exstyle)
            self._active_menu_hwnd = 0
            self._active_menu_cls = ""
            self._active_menu_skip_zorder = False
            return

        # menu_up=False, seen=True: dismissed — restore.
        try:
            from magnifier_bubble.clickthru import _dbg
            _dbg(f"poll_menu: DISMISSED attempts={attempts}")
        except Exception:
            pass
        u32.SetWindowLongW(hwnd, wc.GWL_EXSTYLE, saved_exstyle)
        self._active_menu_hwnd = 0
        self._active_menu_cls = ""
        self._active_menu_skip_zorder = False

    # ---- Public teardown ----

    def destroy(self) -> None:
        """Called on WM_DELETE_WINDOW. Uninstall the WndProc subclass
        BEFORE destroying the root so the original proc is re-seated on
        a still-valid HWND.

        Phase 5 addition (PERS-04): flush any pending ConfigWriter debounce
        SYNCHRONOUSLY before capture/WndProc teardown, while root.after_cancel
        still has a live Tk root.  Pitfall 7 in 05-RESEARCH.md — do NOT use
        root.after(0, ...) here; the scheduled callback would never fire.
        """
        try:
            # Phase 5 PERS-04: flush debounced config write SYNC, before
            # anything else in the teardown chain.  Wrapped in its own
            # try so a writer bug cannot block capture/WndProc teardown.
            if self._config_writer is not None:
                try:
                    self._config_writer.flush_pending()
                except Exception as exc:
                    print(
                        f"[config] flush_pending failed during destroy err={exc}",
                        flush=True,
                    )
            # Phase 6 (HOTK-05): stop the hotkey worker BEFORE the capture
            # worker.  PostThreadMessageW(WM_QUIT) is fire-and-forget from
            # this thread; the worker's GetMessageW loop breaks and the
            # finally block calls UnregisterHotKey on the worker thread
            # (the only thread allowed to do so, per Pitfall 1).  Wrapped
            # in try so a stop() bug cannot block capture/WndProc teardown.
            if self._hotkey_manager is not None:
                try:
                    self._hotkey_manager.stop()
                except Exception as exc:
                    print(
                        f"[hotkey] stop failed during destroy err={exc}",
                        flush=True,
                    )
                self._hotkey_manager = None
            # Phase 3: stop the capture worker BEFORE tearing down
            # root / WndProc chain so the worker can't fire one last
            # frame onto a dead canvas.
            if self._capture_worker is not None:
                self._capture_worker.stop()
                self._capture_worker.join(timeout=1.0)
                self._capture_worker = None
            # Magnification API cleanup (if _mag_init succeeded).
            if self._mag_dll is not None:
                try:
                    self._mag_dll.MagUninitialize()
                except Exception:
                    pass
                self._mag_dll = None
                self._hwnd_mag = 0
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
