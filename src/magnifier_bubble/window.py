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
    ) -> None:
        self.state: AppState = state
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

        # Phase 7: DXGICaptureWorker set by start_capture()
        self._capture_worker = None  # DXGICaptureWorker set by start_capture()

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

        # Phase 7 menu tracking: HWND of active #32768 context menu (0 = none).
        # Set/cleared by _zone_transparency_poll; read by _on_canvas_press.
        self._active_menu_hwnd: int = 0

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

        # Phase 7: zone transparency poll — sets WS_EX_TRANSPARENT when cursor
        # is in the content zone so physical mouse/touch falls through to the
        # underlying app. Cleared for drag and control strips.
        self._zone_poll_id: str | None = None
        self._poll_frame_queue_id: str | None = None
        if sys.platform == "win32" and self._hwnd:
            self._zone_poll_id = self.root.after(50, self._zone_transparency_poll)

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
        """Phase 4 dispatch: button hit-test first, then drag.

        Order of checks (first match wins):
          1. controls.hit_button -> named button dispatch
          2. top-strip y < DRAG_STRIP_HEIGHT -> drag start
          3. bottom-strip y >= h-CONTROL_STRIP_HEIGHT -> drag start
          4. otherwise -> no-op (content zone: WS_EX_TRANSPARENT handles pass-through)
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
            self._drag_origin = (
                event.x_root, event.y_root,
                self.root.winfo_x(), self.root.winfo_y(),
            )
            return
        # Content zone: WS_EX_TRANSPARENT set by _zone_transparency_poll
        # means physical clicks pass through to the underlying app.
        # Exception: when a context menu is active, inject a zoom-mapped click
        # so the menu item at the magnified cursor position is selected.
        if self._active_menu_hwnd and sys.platform == "win32":
            _menu_h = self._active_menu_hwnd
            _u32m = ctypes.windll.user32  # type: ignore[attr-defined]
            if not _u32m.IsWindowVisible(_menu_h):
                self._active_menu_hwnd = 0
            else:
                snap = self.state.snapshot()
                zoom = snap.zoom
                src_x = snap.x + (snap.w - snap.w / zoom) / 2
                src_y = snap.y + (snap.h - snap.h / zoom) / 2
                actual_x = round(src_x + event.x / zoom)
                actual_y = round(src_y + (event.y - DRAG_STRIP_HEIGHT) / zoom)
                _hwnd = self._hwnd
                cur_ex = _u32m.GetWindowLongW(_hwnd, wc.GWL_EXSTYLE)
                _u32m.SetWindowLongW(_hwnd, wc.GWL_EXSTYLE, cur_ex | wc.WS_EX_TRANSPARENT)
                _u32m.ReleaseCapture()
                from magnifier_bubble.clickthru import send_lclick_at
                send_lclick_at(actual_x, actual_y)
                self.root.after(16, lambda: _u32m.SetWindowLongW(_hwnd, wc.GWL_EXSTYLE, cur_ex & ~wc.WS_EX_TRANSPARENT))

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
        self._poll_frame_queue_id = self.root.after(16, self._poll_frame_queue)  # ~60 fps poll

    def _zone_transparency_poll(self) -> None:
        """50 ms timer: set WS_EX_TRANSPARENT when cursor is in content zone,
        clear it when cursor is in drag/control strip or outside overlay.

        When WS_EX_TRANSPARENT is set, WindowFromPoint skips the overlay entirely
        and all mouse/touch events go to the topmost window at the cursor position
        regardless of process. This replaces all click injection machinery.

        Context menu special case: when a #32768 menu is visible, TRANSPARENT
        is cleared (so the overlay receives left-clicks for menu item injection)
        and the Z-order is fixed (overlay above menu, menu just below overlay)
        so DXGI captures the menu through the excluded overlay layer.

        Runs on Tk main thread only — safe to call SetWindowLongW here.
        Cancellable: cancel self._zone_poll_id in destroy() before root.destroy().
        """
        if sys.platform != "win32" or not self._hwnd:
            return
        u32 = ctypes.windll.user32  # type: ignore[attr-defined]

        # --- Context menu detection and Z-order fix ---
        menu_hwnd = u32.FindWindowW("#32768", None)
        menu_visible = bool(menu_hwnd and u32.IsWindowVisible(menu_hwnd))
        if menu_visible:
            if self._active_menu_hwnd != menu_hwnd:
                self._active_menu_hwnd = menu_hwnd
                # Assert overlay at HWND_TOPMOST, then push menu just below.
                # DXGI Desktop Duplication captures through WDA_EXCLUDEFROMCAPTURE
                # and sees the menu when it is below the overlay in Z-order.
                _SWP = 0x0002 | 0x0001 | 0x0010  # NOMOVE | NOSIZE | NOACTIVATE
                u32.SetWindowPos(self._hwnd, -1, 0, 0, 0, 0, _SWP)   # HWND_TOPMOST
                u32.SetWindowPos(menu_hwnd, self._hwnd, 0, 0, 0, 0, _SWP)
        else:
            if self._active_menu_hwnd:
                self._active_menu_hwnd = 0

        pt = ctypes.wintypes.POINT()
        u32.GetCursorPos(ctypes.byref(pt))
        wx = self.root.winfo_x()
        wy = self.root.winfo_y()
        ww = self.root.winfo_width()
        wh = self.root.winfo_height()
        cx = pt.x - wx
        cy = pt.y - wy
        in_overlay = 0 <= cx < ww and 0 <= cy < wh
        # Never set TRANSPARENT while dragging or resizing: the cursor passes
        # through the content zone at high speed and TRANSPARENT would steal
        # the B1-Motion / ButtonRelease-1 events, freezing the drag.
        # Also never set TRANSPARENT while a context menu is active: we need
        # to receive left-click events to inject zoom-mapped menu item clicks.
        is_dragging = self._drag_origin is not None or self._resize_origin is not None
        in_content = (
            in_overlay
            and not is_dragging
            and not self._active_menu_hwnd
            and DRAG_STRIP_HEIGHT <= cy < (wh - CONTROL_STRIP_HEIGHT)
        )
        cur_ex = u32.GetWindowLongW(self._hwnd, wc.GWL_EXSTYLE)
        has_t = bool(cur_ex & wc.WS_EX_TRANSPARENT)
        if in_content and not has_t:
            u32.SetWindowLongW(self._hwnd, wc.GWL_EXSTYLE, cur_ex | wc.WS_EX_TRANSPARENT)
        elif not in_content and has_t:
            u32.SetWindowLongW(self._hwnd, wc.GWL_EXSTYLE, cur_ex & ~wc.WS_EX_TRANSPARENT)
        self._zone_poll_id = self.root.after(50, self._zone_transparency_poll)

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

    def start_capture(self) -> None:
        """Start the DXGI Desktop Duplication capture pipeline.

        Uses DXGICaptureWorker (dxcam) — the only capture path after Phase 7.
        The Magnification API path is removed. Safe to call more than once (no-op).
        """
        if self._capture_worker is not None:
            return
        from magnifier_bubble.capture_dxgi import DXGICaptureWorker
        self._capture_worker = DXGICaptureWorker(
            state=self.state,
            on_frame=self._frame_queue.put,
        )
        self._capture_worker.start()
        self._poll_frame_queue()

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
        """Right-click top strip to cycle color theme."""
        if event.y < DRAG_STRIP_HEIGHT:
            self._apply_theme(self._theme_idx + 1)
            self._save_theme()

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
            # Phase 7: cancel zone transparency poll BEFORE root.destroy()
            if self._zone_poll_id is not None:
                try:
                    self.root.after_cancel(self._zone_poll_id)
                except Exception:
                    pass
                self._zone_poll_id = None
            # Phase 7: cancel frame queue poll BEFORE root.destroy()
            if self._poll_frame_queue_id is not None:
                try:
                    self.root.after_cancel(self._poll_frame_queue_id)
                except Exception:
                    pass
                self._poll_frame_queue_id = None
            # Phase 7: clear WS_EX_TRANSPARENT so WM_DELETE_WINDOW is delivered
            if sys.platform == "win32" and self._hwnd:
                u32_d = ctypes.windll.user32  # type: ignore[attr-defined]
                cur_d = u32_d.GetWindowLongW(self._hwnd, wc.GWL_EXSTYLE)
                u32_d.SetWindowLongW(self._hwnd, wc.GWL_EXSTYLE, cur_d & ~wc.WS_EX_TRANSPARENT)
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
