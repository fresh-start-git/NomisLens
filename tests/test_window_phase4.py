"""Phase 4 Plan 02 integration tests.

Wave 0 stubs (created by Plan 04-01) have been replaced here with real
bodies. Task 1 (Plan 04-02) flips the 9 tests covering grip glyph + shape
cycle + zoom buttons + observer + structural lints. Task 2 (Plan 04-02)
flips the 3 resize-related tests.

Windows-only tests use the session-scoped `tk_toplevel` fixture pattern
but construct a BubbleWindow (which owns its own tk.Tk root) — see
tests/test_window_integration.py for the same approach.
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest


WINDOW_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "magnifier_bubble" / "window.py"
)


# =================== Structural lints (any platform) ===================


def test_phase4_controls_imported_from_controls_module():
    """window.py must pull ButtonRect / SHAPE_CYCLE / hit_button /
    layout_controls / resize_clamp / zoom_step from controls.py exactly once.
    """
    src = WINDOW_PATH.read_text(encoding="utf-8")
    assert src.count("from magnifier_bubble.controls import") == 1, (
        f"Expected exactly one `from magnifier_bubble.controls import` in "
        f"window.py; found {src.count('from magnifier_bubble.controls import')}"
    )
    # Check the key names are in the import (one of the lines after the
    # `from magnifier_bubble.controls import (` must mention each name)
    for name in ("ButtonRect", "SHAPE_CYCLE", "hit_button", "layout_controls", "zoom_step"):
        assert name in src, f"{name} must be imported into window.py"


def test_no_new_wndproc_install_in_phase4_diff():
    """Phase 2 installed exactly 3 WndProc subclasses (parent + frame +
    canvas). Phase 4 must NOT add new ones — Tk <Button-1> routes through
    the existing canvas keepalive.
    """
    src = WINDOW_PATH.read_text(encoding="utf-8")
    # Match wndproc.install( OR wndproc.install_child( — the two callers.
    count = len(re.findall(r"wndproc\.install(?:_child)?\(", src))
    assert count == 3, (
        f"Expected exactly 3 wndproc.install*(...) call-sites "
        f"(parent + frame + canvas); found {count}"
    )


def test_no_tk_button_widget_added():
    """CTRL-01..08 uses Canvas items, NOT tk.Button widgets.
    A tk.Button creates a new HWND and would add a 4th link in the
    WndProc chain — scope creep and potential WM_MOUSEACTIVATE regression.
    """
    src = WINDOW_PATH.read_text(encoding="utf-8")
    assert "tk.Button" not in src, (
        "tk.Button must not appear in window.py — use Canvas items only"
    )


def test_shape_button_cycles():
    """Structural lint: the shape button handler must compute the next
    shape via SHAPE_CYCLE[cur] (the controls.py dict) and feed it into
    state.set_shape.
    """
    src = WINDOW_PATH.read_text(encoding="utf-8")
    assert "SHAPE_CYCLE[" in src, (
        "window.py must reference SHAPE_CYCLE[...] for the shape-cycle handler"
    )
    assert "self.state.set_shape(SHAPE_CYCLE[" in src, (
        "expected `self.state.set_shape(SHAPE_CYCLE[...` pattern in window.py"
    )


def test_shape_cycle_calls_apply_shape_no_deleteobject():
    """window.py must call shapes.apply_shape on shape change (the
    observer does this) and MUST NOT call DeleteObject directly — the
    HRGN ownership rule is enforced inside shapes.apply_shape.
    """
    src = WINDOW_PATH.read_text(encoding="utf-8")
    assert "shapes.apply_shape" in src, (
        "window.py must call shapes.apply_shape (Phase 2 helper)"
    )
    assert src.count("DeleteObject") == 0, (
        f"window.py must not call DeleteObject; shapes.apply_shape owns HRGN "
        f"(found {src.count('DeleteObject')} references)"
    )


def test_observer_registered_on_init():
    """BubbleWindow.__init__ must register an _on_state_change observer
    on the AppState.
    """
    src = WINDOW_PATH.read_text(encoding="utf-8")
    assert (
        "self.state.on_change(self._on_state_change)" in src
        or "state.on_change(self._on_state_change)" in src
    ), "window.py must register self._on_state_change via state.on_change"
    assert "def _on_state_change(self)" in src


# =================== Windows-only integration ===================


win_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")


@pytest.fixture(scope="module")
def phase4_bubble():
    """One BubbleWindow per module. Python 3.14 + tk 8.6 raises
    "init.tcl: couldn't read file" when tk.Tk() is constructed more
    than once in the same process (STATE.md Phase 02/02 decisions).
    All Windows-only Phase 4 tests share this fixture and reset the
    shared AppState via state.set_* between tests.
    """
    if sys.platform != "win32":
        pytest.skip("Windows-only fixture")
    from magnifier_bubble.state import AppState, StateSnapshot
    from magnifier_bubble.window import BubbleWindow
    state = AppState(StateSnapshot(x=100, y=100, w=400, h=400, zoom=2.0))
    bw = BubbleWindow(state)
    bw.root.update_idletasks()
    yield bw, state
    try:
        bw.destroy()
    except Exception:
        pass


@win_only
def test_grip_glyph_drawn_centered(phase4_bubble):
    """CTRL-01: the grip glyph (U+2261) sits in the top strip, centered
    left-of-center (the shape button occupies the rightmost 44 px).

    For a 400x400 bubble:
      grip_cx = (400 - 44) // 2 = 178
      grip_cy = DRAG_STRIP_HEIGHT // 2 = 22
    """
    from magnifier_bubble.window import DRAG_STRIP_HEIGHT
    bubble, state = phase4_bubble
    # Reset to 400x400 shared baseline
    state.set_size(400, 400)
    bubble.root.update_idletasks()
    grip_id = bubble._grip_id
    coords = bubble._canvas.coords(grip_id)
    assert len(coords) == 2, f"grip coords len: {len(coords)}"
    grip_cx, grip_cy = coords
    expected_cx = (400 - 44) // 2
    expected_cy = DRAG_STRIP_HEIGHT // 2
    assert abs(grip_cx - expected_cx) <= 1, (
        f"grip x: got {grip_cx}, expected {expected_cx}±1"
    )
    assert abs(grip_cy - expected_cy) <= 1, (
        f"grip y: got {grip_cy}, expected {expected_cy}±1"
    )
    text = bubble._canvas.itemcget(grip_id, "text")
    assert text == "\u2261", f"grip glyph: {text!r}"


@win_only
def test_zoom_buttons_and_text_display(phase4_bubble):
    """CTRL-04: bottom strip has a live "N.NNx" zoom text item."""
    bubble, state = phase4_bubble
    state.set_size(400, 400)
    state.set_zoom(2.0)
    bubble.root.update_idletasks()
    text = bubble._canvas.itemcget(bubble._zoom_text_id, "text")
    assert re.match(r"^\d+\.\d{2}x$", text), (
        f"zoom text {text!r} does not match ^\\d+\\.\\d{{2}}x$"
    )
    assert text == "2.00x", f"expected 2.00x, got {text!r}"
    zoom_out_text = bubble._canvas.itemcget(bubble._zoom_out_text_id, "text")
    zoom_in_text = bubble._canvas.itemcget(bubble._zoom_in_text_id, "text")
    assert zoom_out_text == "\u2212", f"zoom-out glyph: {zoom_out_text!r}"
    assert zoom_in_text == "+", f"zoom-in glyph: {zoom_in_text!r}"


@win_only
def test_observer_does_not_recurse(phase4_bubble):
    """The internal _on_state_change observer must NOT call state.set_*;
    if it did, each set_zoom would recursively re-trigger the observer.
    The added counter observer here fires exactly ONCE per set_zoom call.
    """
    bubble, state = phase4_bubble
    state.set_zoom(2.0)  # baseline
    calls = []

    def counter():
        calls.append(state.snapshot().zoom)

    state.on_change(counter)
    try:
        state.set_zoom(3.0)
        assert len(calls) == 1, (
            f"observer recursed — expected 1 counter call, got {len(calls)}"
        )
    finally:
        # Remove the counter observer so subsequent tests don't see it.
        state._observers.remove(counter)


# =================== Task 2: resize drag (press + motion + release) ===================


def test_no_sendmessagew_for_resize():
    """Phase 3 eliminated SendMessageW(WM_NCLBUTTONDOWN, HTCAPTION) for
    drag (it crashed Python 3.14 via re-entrant WndProc + GIL release).
    Phase 4 resize MUST use the same <B1-Motion> + root.geometry pattern.
    SendMessageW must never appear in window.py; neither may HTBOTTOMRIGHT
    nor WM_NCLBUTTONDOWN.
    """
    src = WINDOW_PATH.read_text(encoding="utf-8")
    assert "SendMessageW" not in src, (
        "SendMessageW found in window.py — Phase 4 must use "
        "<B1-Motion> + root.geometry() for resize, never "
        "SendMessageW(WM_NCLBUTTONDOWN, HTBOTTOMRIGHT, ...)"
    )
    assert "HTBOTTOMRIGHT" not in src, (
        "HTBOTTOMRIGHT found in window.py — OS-managed resize via "
        "SendMessageW(WM_NCLBUTTONDOWN, HTBOTTOMRIGHT) is banned (Pitfall B)"
    )
    assert "WM_NCLBUTTONDOWN" not in src, (
        "WM_NCLBUTTONDOWN found in window.py — Phase 3 removed the "
        "SendMessageW modal drag; Phase 4 must not reintroduce it"
    )


@win_only
def test_resize_button_drag(phase4_bubble):
    """CTRL-06: press + motion + release on the resize button moves the
    bottom-right corner; top-left stays fixed; state.set_size is called
    with the clamped new size.

    Uses the shared phase4_bubble fixture (module-scoped) because
    tk.Tk() churn triggers the Python 3.14 + tk 8.6 "init.tcl couldn't
    read file" flake (STATE.md Phase 02/02 decisions).
    """
    bubble, state = phase4_bubble
    state.set_size(400, 400)
    bubble.root.update_idletasks()
    # Snapshot the current window origin AFTER the reset so event coords line up.
    snap = state.snapshot()

    class FakeEvent:
        pass

    # Press at center of resize button (bottom-right 22x22 offset in 400x400)
    press = FakeEvent()
    press.x = 400 - 22
    press.y = 400 - 22
    press.x_root = snap.x + 400 - 22
    press.y_root = snap.y + 400 - 22
    bubble._on_canvas_press(press)
    assert bubble._resize_origin is not None, (
        "press on resize button must set _resize_origin"
    )
    assert bubble._drag_origin is None, (
        "press on resize button must NOT set _drag_origin"
    )

    # Motion: +100 in x, +50 in y -> expected new size 500x450
    motion = FakeEvent()
    motion.x_root = press.x_root + 100
    motion.y_root = press.y_root + 50
    bubble._on_canvas_drag(motion)
    new_snap = state.snapshot()
    assert new_snap.w == 500, f"expected w=500, got {new_snap.w}"
    assert new_snap.h == 450, f"expected h=450, got {new_snap.h}"

    # Release clears the resize origin
    release = FakeEvent()
    bubble._on_canvas_release(release)
    assert bubble._resize_origin is None


@win_only
def test_resize_clamp_on_drag_motion(phase4_bubble):
    """CTRL-08: resize clamps to [150, 700] on both axes under extreme
    drag deltas.
    """
    bubble, state = phase4_bubble
    state.set_size(200, 200)
    bubble.root.update_idletasks()
    snap = state.snapshot()

    class FakeEvent:
        pass

    # Press at center of resize button in 200x200 bubble
    press = FakeEvent()
    press.x = 200 - 22
    press.y = 200 - 22
    press.x_root = snap.x + 200 - 22
    press.y_root = snap.y + 200 - 22
    bubble._on_canvas_press(press)

    # Huge positive delta -> clamp to MAX (700, 700)
    motion = FakeEvent()
    motion.x_root = press.x_root + 1000
    motion.y_root = press.y_root + 1000
    bubble._on_canvas_drag(motion)
    max_snap = state.snapshot()
    assert max_snap.w == 700, f"expected w clamped to 700, got {max_snap.w}"
    assert max_snap.h == 700, f"expected h clamped to 700, got {max_snap.h}"

    rel = FakeEvent()
    bubble._on_canvas_release(rel)

    # New press at the now-700x700 bubble's resize-button center
    press2 = FakeEvent()
    press2.x = 700 - 22
    press2.y = 700 - 22
    press2.x_root = snap.x + 700 - 22
    press2.y_root = snap.y + 700 - 22
    bubble._on_canvas_press(press2)

    # Huge negative delta -> clamp to MIN (150, 150)
    motion2 = FakeEvent()
    motion2.x_root = press2.x_root - 1000
    motion2.y_root = press2.y_root - 1000
    bubble._on_canvas_drag(motion2)
    min_snap = state.snapshot()
    assert min_snap.w == 150, f"expected w clamped to 150, got {min_snap.w}"
    assert min_snap.h == 150, f"expected h clamped to 150, got {min_snap.h}"

    bubble._on_canvas_release(rel)
