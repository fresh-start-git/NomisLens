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
    sig = inspect.signature(BubbleWindow.__init__)
    params = list(sig.parameters.keys())
    assert params == ["self", "state"], f"expected ['self', 'state'], got {params}"


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


@win_only
def test_destroy_cleans_up_wndproc_then_root(bubble):
    """destroy must uninstall the WndProc subclass BEFORE destroying the root.

    NOTE: this test MUST be declared LAST in the module because it destroys
    the shared module-scoped `bubble` fixture. Running any bubble-consuming
    test after this one would hit an already-destroyed Tk root. pytest runs
    tests in declaration order by default, so this ordering is preserved as
    long as nothing is re-ordered by markers / plugins.
    """
    assert bubble._wndproc_keepalive is not None
    bubble.destroy()
    # After destroy, the keepalive should be cleared and calling destroy
    # again should be a no-op (no exception).
    assert bubble._wndproc_keepalive is None
    bubble.destroy()
