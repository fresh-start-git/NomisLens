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


@win_only
def test_grip_glyph_drawn_centered():
    """CTRL-01: the ≡ grip glyph sits in the top strip, centered left-of-center
    (the shape button occupies the rightmost 44 px).

    For a 400x400 bubble:
      grip_cx = (400 - 44) // 2 = 178
      grip_cy = DRAG_STRIP_HEIGHT // 2 = 22
    """
    from magnifier_bubble.state import AppState, StateSnapshot
    from magnifier_bubble.window import BubbleWindow, DRAG_STRIP_HEIGHT

    state = AppState(StateSnapshot(x=200, y=200, w=400, h=400))
    bubble = BubbleWindow(state)
    try:
        bubble.root.update_idletasks()
        grip_id = bubble._grip_id
        # canvas.coords returns [cx, cy] for a text item
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
        # And the text is the expected glyph
        text = bubble._canvas.itemcget(grip_id, "text")
        assert text == "\u2261", f"grip glyph: {text!r}"
    finally:
        bubble.destroy()


@win_only
def test_zoom_buttons_and_text_display():
    """CTRL-04: bottom strip has a live "N.NNx" zoom text item."""
    from magnifier_bubble.state import AppState, StateSnapshot
    from magnifier_bubble.window import BubbleWindow

    state = AppState(StateSnapshot(x=200, y=200, w=400, h=400, zoom=2.0))
    bubble = BubbleWindow(state)
    try:
        bubble.root.update_idletasks()
        text = bubble._canvas.itemcget(bubble._zoom_text_id, "text")
        assert re.match(r"^\d+\.\d{2}x$", text), (
            f"zoom text {text!r} does not match ^\\d+\\.\\d{{2}}x$"
        )
        assert text == "2.00x", f"expected 2.00x at init, got {text!r}"
        # And [-] / [+] glyphs exist
        zoom_out_text = bubble._canvas.itemcget(bubble._zoom_out_text_id, "text")
        zoom_in_text = bubble._canvas.itemcget(bubble._zoom_in_text_id, "text")
        assert zoom_out_text == "\u2212", f"zoom-out glyph: {zoom_out_text!r}"
        assert zoom_in_text == "+", f"zoom-in glyph: {zoom_in_text!r}"
    finally:
        bubble.destroy()


@win_only
def test_observer_does_not_recurse():
    """The internal _on_state_change observer must NOT call state.set_*;
    if it did, each set_zoom would recursively re-trigger the observer.
    """
    from magnifier_bubble.state import AppState, StateSnapshot
    from magnifier_bubble.window import BubbleWindow

    state = AppState(StateSnapshot(x=200, y=200, w=400, h=400, zoom=2.0))
    bubble = BubbleWindow(state)
    try:
        calls = []

        def counter():
            calls.append(state.snapshot().zoom)

        state.on_change(counter)
        state.set_zoom(3.0)
        # The internal observer fired once AND the counter observer fired
        # once. If _on_state_change recursed into set_zoom, counter would
        # fire >= 2 times.
        assert len(calls) == 1, (
            f"observer recursed — expected 1 counter call, got {len(calls)}"
        )
    finally:
        bubble.destroy()


# =================== Task 2 tests (still stubs — flipped in Task 2) ===================


def test_resize_button_drag():
    pytest.skip("Plan 04-02 Task 2 will implement this test")


def test_resize_clamp_on_drag_motion():
    pytest.skip("Plan 04-02 Task 2 will implement this test")


def test_no_sendmessagew_for_resize():
    pytest.skip("Plan 04-02 Task 2 will implement this test")
