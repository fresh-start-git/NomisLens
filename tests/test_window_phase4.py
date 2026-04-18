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
    """CTRL-01: the grip glyph (U+2261) sits in the top strip, centered.

    For a 400x400 bubble:
      grip_cx = 400 // 2 = 200
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
    expected_cx = 400 // 2
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
    # Format: N.Nx× (1 decimal place, U+00D7 multiplication sign)
    assert re.match(r"^\d+\.\d{1}\u00d7$", text), (
        f"zoom text {text!r} does not match ^\\d+\\.\\d{{1}}×$"
    )
    assert text == "2.0\u00d7", f"expected '2.0×', got {text!r}"
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


# =================== HRGN control-visibility bug (Task 3 regression) ===================
#
# Bug report (Task 3 human verification): "if you switch it to a circle you
# lose the buttons and can't revert it back to the rectangle." Root cause:
# apply_shape("circle", w, h) produced an ellipse inscribed in (0, 0, w, h).
# The four corners of the bounding rect fall OUTSIDE the ellipse, so the
# Canvas items drawn in those corners (shape button top-right, zoom-out /
# zoom-in / resize buttons in the bottom strip) get clipped away by
# Windows — the pixels are invisible AND mouse events in those corners
# are blocked by the HRGN. The user cannot tap back to any shape.
#
# Fix: window.py passes strip_top=DRAG_STRIP_HEIGHT and
# strip_bottom=CONTROL_STRIP_HEIGHT to shapes.apply_shape, which CombineRgn-
# unions the shape with two full-width strip rectangles. The strips remain
# hittable in their entirety regardless of shape.


def test_window_passes_strip_heights_to_apply_shape():
    """Structural regression guard: every shapes.apply_shape CALL in
    window.py MUST include strip_top and strip_bottom kwargs.

    Without them, apply_shape falls back to the Phase 2 pure-shape
    behavior which clips the corners of the control strips away and
    makes the shape / zoom / resize buttons unreachable in circle mode
    (Task 3 bug).

    Matches `shapes.apply_shape(` (with opening paren) so comment /
    docstring mentions of the bare function name don't inflate the count.
    """
    src = WINDOW_PATH.read_text(encoding="utf-8")
    apply_count = src.count("shapes.apply_shape(")
    assert apply_count >= 2, (
        f"Expected at least 2 shapes.apply_shape(...) call sites in "
        f"window.py (initial Step 11 + observer); found {apply_count}"
    )
    # Every call must reference strip_top= and strip_bottom=.
    strip_top_count = src.count("strip_top=DRAG_STRIP_HEIGHT")
    strip_bot_count = src.count("strip_bottom=CONTROL_STRIP_HEIGHT")
    assert strip_top_count == apply_count, (
        f"apply_shape calls: {apply_count}, but only {strip_top_count} "
        f"pass strip_top=DRAG_STRIP_HEIGHT — every call must include it "
        f"so controls remain clickable in circle / rounded shapes"
    )
    assert strip_bot_count == apply_count, (
        f"apply_shape calls: {apply_count}, but only {strip_bot_count} "
        f"pass strip_bottom=CONTROL_STRIP_HEIGHT — every call must "
        f"include it so bottom controls remain clickable"
    )


@win_only
def test_all_buttons_hittable_in_every_shape(phase4_bubble):
    """Task 3 regression: after cycling to each shape in turn, every
    button rect returned by layout_controls must lie entirely INSIDE
    the window's HRGN (i.e. mouse events land — Windows does not clip
    them). This verifies the strip_top / strip_bottom CombineRgn fix.

    For each shape ('rect', 'rounded', 'circle'), we read the HWND's
    current region via GetWindowRgn and check all 4 corners of every
    button rect via win32gui.PtInRegion. If PtInRegion returns False
    for any button corner, the HRGN is clipping that pixel away and
    the button is unreachable.
    """
    import win32gui  # type: ignore[import-not-found]
    from magnifier_bubble.controls import layout_controls

    bubble, state = phase4_bubble
    # Reset to a generous baseline so rounded-rect corner math is well-defined.
    state.set_size(400, 400)
    bubble.root.update_idletasks()
    w, h = 400, 400
    buttons = layout_controls(w, h)

    for shape in ("rect", "rounded", "circle"):
        state.set_shape(shape)
        bubble.root.update_idletasks()
        # Fresh region handle each iteration; GetWindowRgn requires a
        # pre-existing HRGN to copy into.
        rgn = win32gui.CreateRectRgnIndirect((0, 0, 1, 1))
        try:
            rc = win32gui.GetWindowRgn(bubble._hwnd, rgn)
            # GetWindowRgn returns region type; 0 = ERROR, 1 = NULLREGION.
            assert rc not in (0, 1), (
                f"GetWindowRgn returned {rc} for shape={shape!r} "
                f"(0=ERROR, 1=NULLREGION)"
            )
            for btn in buttons:
                # Sample the 4 corners of the button + its center (5 points).
                # If ANY fail, the control is partly/fully clipped.
                pts = [
                    (btn.x + 1,              btn.y + 1),
                    (btn.x + btn.w - 1,      btn.y + 1),
                    (btn.x + 1,              btn.y + btn.h - 1),
                    (btn.x + btn.w - 1,      btn.y + btn.h - 1),
                    (btn.x + btn.w // 2,     btn.y + btn.h // 2),
                ]
                for (px, py) in pts:
                    inside = win32gui.PtInRegion(rgn, px, py)
                    assert inside, (
                        f"shape={shape!r} button={btn.name!r} point="
                        f"({px},{py}) is OUTSIDE the window HRGN — "
                        f"Windows will clip the click. Task 3 regression."
                    )
        finally:
            win32gui.DeleteObject(rgn)


# =================== Plan 04-03: click injection wiring ===================
# Phase 7: test_bubble_window_accepts_click_injection_enabled_kwarg removed — click injection infrastructure deleted.
# Phase 7: test_content_zone_click_invokes_inject_click_when_enabled removed — click injection infrastructure deleted.
# Phase 7: test_content_zone_click_does_nothing_when_injection_disabled removed — click injection infrastructure deleted.


def test_bubble_window_constructor_no_click_injection_param():
    """Phase 7: BubbleWindow.__init__ must NOT accept click_injection_enabled."""
    import inspect
    from magnifier_bubble.window import BubbleWindow
    sig = inspect.signature(BubbleWindow.__init__, eval_str=True)
    params = list(sig.parameters)
    assert "click_injection_enabled" not in params, (
        "click_injection_enabled parameter must be removed in Phase 7"
    )


@win_only
def test_bubble_has_zone_poll_id_attribute(phase4_bubble):
    """Phase 7: BubbleWindow must have _zone_poll_id attribute (may be None on non-Win32)."""
    bubble, state = phase4_bubble
    assert hasattr(bubble, "_zone_poll_id"), (
        "BubbleWindow must have _zone_poll_id attribute for zone transparency poll cancellation"
    )


@win_only
def test_bubble_has_poll_frame_queue_id_attribute(phase4_bubble):
    """Phase 7: BubbleWindow must have _poll_frame_queue_id attribute for after-cancel in destroy()."""
    bubble, state = phase4_bubble
    assert hasattr(bubble, "_poll_frame_queue_id"), (
        "BubbleWindow must have _poll_frame_queue_id attribute to cancel _poll_frame_queue in destroy()"
    )


# ---------------------------------------------------------------------
# Phase 6 Wave 0 stub — visibility wrappers (HOTK-03)
# Plan 06-03 adds BubbleWindow.show() / hide() / toggle() + fills in this test.
# ---------------------------------------------------------------------


def _require_bubble_toggle():
    """Skip if Plan 06-03 hasn't added show/hide/toggle yet."""
    try:
        from magnifier_bubble.window import BubbleWindow
    except ImportError:
        pytest.skip("BubbleWindow import failed")
    if not all(hasattr(BubbleWindow, name) for name in ("show", "hide", "toggle")):
        pytest.skip(
            "BubbleWindow.show/hide/toggle not yet implemented "
            "(pending Plan 06-03)"
        )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
def test_bubble_show_hide_toggle(phase4_bubble):
    """HOTK-03: BubbleWindow show/hide/toggle wrappers update state AND
    call the underlying Tk visibility primitives.

    Uses the module-scoped phase4_bubble fixture (same pattern as the
    other Windows-only tests here) rather than building a fresh Tk().
    Python 3.14 + tk 8.6 cannot tolerate multiple tk.Tk() in the same
    process (STATE.md Phase 02/02 decisions).
    """
    _require_bubble_toggle()
    bubble, state = phase4_bubble

    # Put the bubble into a known-visible baseline regardless of what
    # previous tests in this module did.
    state.set_visible(True)
    bubble.root.deiconify()
    bubble.root.update_idletasks()
    assert state.snapshot().visible is True

    try:
        bubble.hide()
        bubble.root.update_idletasks()
        assert state.snapshot().visible is False, (
            "hide() must set state.visible to False"
        )

        bubble.show()
        bubble.root.update_idletasks()
        assert state.snapshot().visible is True, (
            "show() must set state.visible back to True"
        )

        # First toggle: True -> False
        bubble.toggle()
        bubble.root.update_idletasks()
        assert state.snapshot().visible is False

        # Second toggle: False -> True (returns to original)
        bubble.toggle()
        bubble.root.update_idletasks()
        assert state.snapshot().visible is True
    finally:
        # Restore the shared fixture to a visible state for any
        # downstream test in this module.
        state.set_visible(True)
        bubble.root.deiconify()
