"""Windows-only end-to-end integration for BubbleWindow.

Covers Plan 03's requirements:
- OVER-01 no taskbar entry (WS_EX_TOOLWINDOW)
- OVER-02 no title bar (overrideredirect)
- OVER-03 layered (WS_EX_LAYERED)
- OVER-04 no focus theft (WS_EX_NOACTIVATE)
- LAYT-01 three zones (via compute_zone at canvas points)
- LAYT-04 WndProc subclass + keepalive (instance attribute check)
- LAYT-05 dark strips on canvas
- LAYT-06 teal border outline on canvas

Manual-only verifications (Notepad click-through, 5-minute hover, touch)
are tracked in the Plan 03 checkpoint task, not here.
"""
from __future__ import annotations

import ctypes
import inspect
import pathlib
import sys

import pytest

from magnifier_bubble import window as window_mod
from magnifier_bubble import winconst as wc
from magnifier_bubble import wndproc
from magnifier_bubble.state import AppState, StateSnapshot
from magnifier_bubble.window import (
    BORDER_COLOR,
    BORDER_WIDTH,
    BG_COLOR,
    STRIP_COLOR,
    BubbleWindow,
)

WINDOW_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "magnifier_bubble" / "window.py"
)


# ========== Structural lints (every platform) ==========

def test_bubblewindow_constructor_signature():
    """BubbleWindow.__init__'s first two positional params MUST stay
    (self, state) so every Phase 1-3 call site keeps working. Keyword-only
    additions with defaults are allowed (Phase 4-03 added
    click_injection_enabled: bool = True for the --no-click-injection
    CLI fallback).

    Mirrors the Phase 4-02 relaxation of test_apply_shape_signature_locked
    in tests/test_shapes_smoke.py: lock the first N positional params,
    allow extras iff they have defaults.
    """
    sig = inspect.signature(BubbleWindow.__init__)
    params = list(sig.parameters.values())
    names = [p.name for p in params]
    # Lock the first 2: self, state.
    assert names[:2] == ["self", "state"], (
        f"first 2 params must be ['self', 'state']; got {names[:2]}"
    )
    # Any extras must have defaults so pre-Phase-4 call sites keep working.
    for p in params[2:]:
        assert p.default is not inspect.Parameter.empty, (
            f"BubbleWindow.__init__ extra param {p.name!r} has no default "
            f"— Phase 1-3 call sites would break"
        )


def test_visual_constants_locked():
    assert BORDER_COLOR == "#2ec4b6"
    assert BORDER_WIDTH in (3, 4)
    assert STRIP_COLOR == "#1a1a1a"
    assert BG_COLOR == "#0a0a0a"


def test_source_contains_canonical_ordering():
    """Grep-level check that the constructor steps appear in the right order.

    Each marker is chosen to match the CALL SITE inside __init__, not the
    argtypes-binding references inside the _u32() helper. That lets us lint
    the canonical Pattern 1 construction order without false positives from
    ctypes signature setup that has to appear earlier in the module for
    function-scope name resolution to work.
    """
    src = WINDOW_PATH.read_text(encoding="utf-8")
    # Find the position of each marker - each marker is a call-site literal
    # that only occurs once in __init__, so src.find() (first occurrence)
    # always points at the constructor call, not the _u32() argtypes setup.
    markers = [
        "tk.Tk = tk.Tk(",
        "self.root.withdraw()",
        "self.root.overrideredirect(True)",
        'self.root.wm_attributes("-topmost", True)',
        "self.root.geometry(",
        "self.root.update_idletasks()",
        "u32.GetParent(self.root.winfo_id()",
        "u32.SetWindowLongW(self._hwnd",
        "u32.SetLayeredWindowAttributes(self._hwnd",
        "wndproc.install(",
        "shapes.apply_shape(self._hwnd",
        "self.root.deiconify()",
    ]
    positions = [src.find(m) for m in markers]
    for m, pos in zip(markers, positions):
        assert pos >= 0, f"window.py missing canonical step marker: {m!r}"
    # Every marker must appear after the previous marker
    for i in range(1, len(positions)):
        assert positions[i] > positions[i - 1], (
            f"window.py ordering violation: {markers[i]!r} at {positions[i]} "
            f"appears BEFORE {markers[i - 1]!r} at {positions[i - 1]}"
        )


def test_source_has_ext_style_or_expression():
    src = WINDOW_PATH.read_text(encoding="utf-8")
    assert "WS_EX_LAYERED" in src
    assert "WS_EX_TOOLWINDOW" in src
    assert "WS_EX_NOACTIVATE" in src
    assert "wc.WS_EX_LAYERED | wc.WS_EX_TOOLWINDOW | wc.WS_EX_NOACTIVATE" in src


def test_source_uses_lwa_alpha():
    src = WINDOW_PATH.read_text(encoding="utf-8")
    assert "LWA_ALPHA" in src


def test_source_does_not_use_ws_ex_transparent():
    """WS_EX_TRANSPARENT would kill the drag bar (Pitfall 1). It can appear
    in comments, but never in a bitwise-or expression."""
    src = WINDOW_PATH.read_text(encoding="utf-8")
    # Allow the string to appear in a comment, but not in `| WS_EX_TRANSPARENT`
    # or `wc.WS_EX_TRANSPARENT`.
    assert "| wc.WS_EX_TRANSPARENT" not in src
    assert "|wc.WS_EX_TRANSPARENT" not in src
    assert "| WS_EX_TRANSPARENT" not in src


def test_source_does_not_call_dpi_api():
    src = WINDOW_PATH.read_text(encoding="utf-8")
    assert "SetProcessDpiAwarenessContext" not in src
    assert "SetProcessDpiAwareness(" not in src
    assert "SetProcessDPIAware(" not in src


def test_source_stores_wndproc_keepalive_on_instance():
    """Pitfall A (GC crash): the WNDPROC thunk MUST be stored on self."""
    src = WINDOW_PATH.read_text(encoding="utf-8")
    assert "self._wndproc_keepalive" in src
    assert "self._wndproc_keepalive = wndproc.install" in src


def test_source_wm_delete_window_uninstalls_first():
    """destroy() must call wndproc.uninstall BEFORE root.destroy."""
    src = WINDOW_PATH.read_text(encoding="utf-8")
    assert "WM_DELETE_WINDOW" in src
    assert "wndproc.uninstall" in src
    uninstall_pos = src.find("wndproc.uninstall(self._wndproc_keepalive)")
    destroy_pos = src.find("self.root.destroy()")
    assert uninstall_pos >= 0
    assert destroy_pos >= 0
    assert uninstall_pos < destroy_pos, (
        "wndproc.uninstall must run before self.root.destroy()"
    )


def test_source_uses_getparent_for_toplevel_hwnd():
    """PITFALLS.md Integration Gotchas: winfo_id is child HWND; use GetParent."""
    src = WINDOW_PATH.read_text(encoding="utf-8")
    assert "GetParent(self.root.winfo_id())" in src


def test_source_has_pattern_2b_drag_workaround():
    """Pitfall E: WS_EX_NOACTIVATE dead-drag fix uses ReleaseCapture + WM_NCLBUTTONDOWN."""
    src = WINDOW_PATH.read_text(encoding="utf-8")
    assert "ReleaseCapture" in src
    assert "WM_NCLBUTTONDOWN" in src
    assert "HTCAPTION" in src


# ========== Windows-only integration ==========

win_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")


@pytest.fixture(scope="module")
def bubble():
    """One BubbleWindow per test module to avoid the Python 3.14 + tk 8.6
    'SourceLibFile panedwindow' TclError that fires when tk.Tk() is torn
    down and recreated inside the same pytest process. STATE.md Phase 02/02
    decisions section documents the underlying flakiness; scope=module
    keeps this fixture's tk.Tk() calls to exactly one per module, which
    eliminates the race for all read-only tests. The write-path smoke
    (test_destroy_cleans_up_wndproc_then_root) is ordered LAST in the
    module so it only runs a second tk.Tk() after every other test has
    finished consuming the shared bubble."""
    if sys.platform != "win32":
        pytest.skip("Windows-only")
    state = AppState(StateSnapshot(x=200, y=200, w=400, h=400, shape="circle"))
    bw = BubbleWindow(state)
    bw.root.update_idletasks()
    bw.root.update()
    yield bw
    try:
        bw.destroy()
    except Exception:
        pass


@win_only
def test_bubble_has_nonzero_hwnd(bubble):
    assert bubble._hwnd != 0, "BubbleWindow failed to obtain a toplevel HWND"


@win_only
def test_ext_styles_set(bubble):
    """OVER-01 (toolwindow) + OVER-03 (layered) + OVER-04 (noactivate)."""
    u32 = ctypes.windll.user32
    u32.GetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
    u32.GetWindowLongW.restype = ctypes.c_long
    ex = u32.GetWindowLongW(bubble._hwnd, wc.GWL_EXSTYLE)
    assert ex & wc.WS_EX_LAYERED, f"WS_EX_LAYERED not set; ex={hex(ex)}"
    assert ex & wc.WS_EX_TOOLWINDOW, f"WS_EX_TOOLWINDOW not set; ex={hex(ex)}"
    assert ex & wc.WS_EX_NOACTIVATE, f"WS_EX_NOACTIVATE not set; ex={hex(ex)}"


@win_only
def test_layered_style_set(bubble):
    """OVER-03 alias."""
    u32 = ctypes.windll.user32
    u32.GetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
    u32.GetWindowLongW.restype = ctypes.c_long
    ex = u32.GetWindowLongW(bubble._hwnd, wc.GWL_EXSTYLE)
    assert ex & wc.WS_EX_LAYERED


@win_only
def test_noactivate_style_set(bubble):
    """OVER-04 alias."""
    u32 = ctypes.windll.user32
    u32.GetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
    u32.GetWindowLongW.restype = ctypes.c_long
    ex = u32.GetWindowLongW(bubble._hwnd, wc.GWL_EXSTYLE)
    assert ex & wc.WS_EX_NOACTIVATE


@win_only
def test_overrideredirect_set(bubble):
    """OVER-02 no title bar."""
    assert bool(bubble.root.overrideredirect()), (
        "overrideredirect must be True (OVER-02)"
    )


@win_only
def test_wndproc_keepalive_attribute(bubble):
    """LAYT-04 keepalive is held on instance."""
    assert bubble._wndproc_keepalive is not None
    assert isinstance(bubble._wndproc_keepalive, wndproc.WndProcKeepalive)
    assert bubble._wndproc_keepalive.new_proc is not None
    assert bubble._wndproc_keepalive.old_proc is not None
    assert bubble._wndproc_keepalive.hwnd == bubble._hwnd


@win_only
def test_strip_rectangles_drawn(bubble):
    """LAYT-05 dark strips are present with the expected fill."""
    top_fill = bubble._canvas.itemcget(bubble._top_strip_id, "fill")
    bottom_fill = bubble._canvas.itemcget(bubble._bottom_strip_id, "fill")
    assert top_fill == STRIP_COLOR, f"top strip fill: {top_fill!r}"
    assert bottom_fill == STRIP_COLOR, f"bottom strip fill: {bottom_fill!r}"


@win_only
def test_border_drawn(bubble):
    """LAYT-06 teal border outline is present with the locked color and width 3-4."""
    outline = bubble._canvas.itemcget(bubble._border_id, "outline")
    width_str = bubble._canvas.itemcget(bubble._border_id, "width")
    width_int = int(float(width_str))
    assert outline.lower() == BORDER_COLOR.lower(), f"border outline: {outline!r}"
    assert width_int in (3, 4), f"border width {width_int} not in (3, 4)"


@win_only
def test_canvas_compute_zone_center_is_content(bubble):
    """LAYT-01 + LAYT-02 sanity check via BubbleWindow._zone_fn."""
    snap = bubble.state.snapshot()
    # Center of the canvas
    zone = bubble._zone_fn(snap.w // 2, snap.h // 2, snap.w, snap.h)
    assert zone == "content"
    # Top of the canvas
    zone = bubble._zone_fn(snap.w // 2, 10, snap.w, snap.h)
    assert zone == "drag"
    # Bottom of the canvas
    zone = bubble._zone_fn(snap.w // 2, snap.h - 10, snap.w, snap.h)
    assert zone == "control"


@win_only
def test_wndproc_hit_test_returns_httransparent_at_center(bubble):
    """End-to-end: send WM_NCHITTEST at window center, expect HTTRANSPARENT."""
    u32 = ctypes.windll.user32
    u32.SendMessageW.argtypes = [
        ctypes.wintypes.HWND, ctypes.wintypes.UINT,
        ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
    ]
    u32.SendMessageW.restype = ctypes.c_ssize_t
    snap = bubble.state.snapshot()
    # Center in screen coords
    sx = snap.x + snap.w // 2
    sy = snap.y + snap.h // 2
    lparam = (sx & 0xFFFF) | ((sy & 0xFFFF) << 16)
    result = u32.SendMessageW(bubble._hwnd, wc.WM_NCHITTEST, 0, lparam)
    assert result == wc.HTTRANSPARENT, (
        f"expected HTTRANSPARENT ({wc.HTTRANSPARENT}) at window center, got {result}"
    )


# --- Phase 3 additions (bubble-consuming tests BEFORE destroy) ---

@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_set_window_display_affinity(bubble):
    """CAPT-06 Path A: SetWindowDisplayAffinity was called."""
    from ctypes import wintypes, byref
    u32 = ctypes.windll.user32  # type: ignore[attr-defined]
    u32.GetWindowDisplayAffinity.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
    ]
    u32.GetWindowDisplayAffinity.restype = wintypes.BOOL
    affinity = wintypes.DWORD()
    assert u32.GetWindowDisplayAffinity(
        wintypes.HWND(bubble._hwnd), byref(affinity)
    )
    # 0x11 = WDA_EXCLUDEFROMCAPTURE (Win10 2004+), 0x01 = WDA_MONITOR
    # fallback on older Windows. 0x00 = WDA_NONE = call failed.
    assert affinity.value in (0x01, 0x11), (
        f"unexpected display affinity: {affinity.value:#x}"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_photo_attribute_exists(bubble):
    """CAPT-05: BubbleWindow has a single ImageTk.PhotoImage."""
    from PIL import ImageTk
    assert isinstance(bubble._photo, ImageTk.PhotoImage)
    assert bubble._photo_size == (
        bubble._photo.width(), bubble._photo.height()
    )
    # Content zone = bubble - top strip - bottom strip
    from magnifier_bubble.window import (
        DRAG_STRIP_HEIGHT, CONTROL_STRIP_HEIGHT,
    )
    snap = bubble.state.snapshot()
    assert bubble._photo.width() == snap.w
    assert bubble._photo.height() == (
        snap.h - DRAG_STRIP_HEIGHT - CONTROL_STRIP_HEIGHT
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_image_id_is_valid_canvas_item(bubble):
    """CAPT-04 wiring: _image_id is a live Canvas item id."""
    assert bubble._image_id in bubble._canvas.find_all()
    # Item type is "image" (not rectangle, oval, etc.)
    assert bubble._canvas.type(bubble._image_id) == "image"


# --- Shared-bubble destructive test (MUST be LAST bubble consumer) ---

@win_only
def test_destroy_cleans_up_wndproc_then_root(bubble):
    """destroy must uninstall the WndProc subclass BEFORE destroying the root.

    NOTE: this test MUST be declared LAST among the shared-bubble tests
    because it destroys the module-scoped `bubble` fixture. Running any
    bubble-consuming test after this one would hit an already-destroyed
    Tk root. pytest runs tests in declaration order by default, so this
    ordering is preserved as long as nothing is re-ordered by markers / plugins.

    The Phase 3 lifecycle test below uses a DEDICATED `bubble_lifecycle`
    fixture and is safe to run after this one.
    """
    assert bubble._wndproc_keepalive is not None
    bubble.destroy()
    # After destroy, the keepalive should be cleared and calling destroy
    # again should be a no-op (no exception).
    assert bubble._wndproc_keepalive is None
    bubble.destroy()


# --- Phase 3 structural lints (no bubble fixture needed) ---

def test_photoimage_constructed_exactly_twice_in_window():
    """CAPT-05 Pitfall 12 lint: only two ImageTk.PhotoImage(
    call sites in window.py (initial build + resize rebuild)."""
    src = pathlib.Path(window_mod.__file__).read_text(encoding="utf-8")
    count = src.count("ImageTk.PhotoImage(")
    assert count == 2, (
        f"ImageTk.PhotoImage( appears {count} times in window.py; "
        f"expected exactly 2 (initial build in __init__ + resize "
        f"rebuild in _on_frame). More than 2 means CPython 124364 "
        f"leak defense is broken."
    )


def test_on_frame_uses_paste_not_reassign():
    """CAPT-05 lint: _on_frame must use self._photo.paste(img)."""
    src = pathlib.Path(window_mod.__file__).read_text(encoding="utf-8")
    assert "self._photo.paste(" in src, (
        "_on_frame must call self._photo.paste(img) per CAPT-05"
    )


@pytest.fixture
def bubble_lifecycle():
    """Per-test bubble for the lifecycle test, which calls destroy()
    inside the test body. CANNOT share the module-level `bubble`
    fixture because that fixture calls destroy() in its teardown —
    calling destroy() twice raises TclError and Tk "can't invoke
    "destroy" command" errors. This fixture intentionally does NOT
    call destroy() in teardown — the test body is responsible."""
    from magnifier_bubble.state import AppState, StateSnapshot
    from magnifier_bubble.window import BubbleWindow
    state = AppState(StateSnapshot())
    b = BubbleWindow(state)
    yield b
    # Safety net: if the test aborted before destroy(), clean up now
    try:
        if getattr(b, "_capture_worker", None) is not None:
            b._capture_worker.stop()
            b._capture_worker.join(timeout=1.0)
        b.root.destroy()
    except Exception:
        pass  # already torn down by the test body


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_capture_worker_lifecycle(bubble_lifecycle):
    """CAPT-01: start_capture creates a live worker; destroy stops it.
    Uses bubble_lifecycle (isolated per-test fixture) — NOT the shared
    `bubble` fixture — because this test calls bubble.destroy() in its
    body, and double-destroy raises TclError in the shared fixture's
    teardown."""
    import time
    bubble = bubble_lifecycle
    assert bubble._capture_worker is None
    bubble.start_capture()
    assert bubble._capture_worker is not None
    assert bubble._capture_worker.is_alive()
    # Calling start twice is a no-op
    first = bubble._capture_worker
    bubble.start_capture()
    assert bubble._capture_worker is first
    # Let one frame try to arrive
    bubble.root.update()
    time.sleep(0.05)
    bubble.root.update()
    # destroy() must stop the worker
    bubble.destroy()
    assert bubble._capture_worker is None
