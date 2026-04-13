"""Phase 4 Plan 01 unit tests for src/magnifier_bubble/controls.py.

Pure Python — zero tkinter/ctypes/pywin32 imports. Runs on any platform.
RED phase: all assertions fail on ImportError/AttributeError until Task 2
implements controls.py.
"""
from __future__ import annotations

import pytest

from magnifier_bubble.controls import (
    SHAPE_CYCLE,
    ButtonRect,
    hit_button,
    layout_controls,
    resize_clamp,
    zoom_step,
)


# ---- CTRL-02: shape cycle state machine ----

def test_shape_cycle_dict():
    assert SHAPE_CYCLE == {"circle": "rounded", "rounded": "rect", "rect": "circle"}


def test_shape_cycle_covers_all_valid_shapes():
    assert set(SHAPE_CYCLE.keys()) == set(SHAPE_CYCLE.values()) == {"circle", "rounded", "rect"}


# ---- CTRL-05: zoom step helper (snap to 0.25 grid, clamp to [1.5, 6.0]) ----

def test_zoom_step_up_from_2_returns_2_25():
    assert zoom_step(2.0, +1) == 2.25


def test_zoom_step_down_from_2_returns_1_75():
    assert zoom_step(2.0, -1) == 1.75


def test_zoom_step_clamps_at_max():
    assert zoom_step(6.0, +1) == 6.0


def test_zoom_step_clamps_at_min():
    assert zoom_step(1.5, -1) == 1.5


def test_zoom_step_snaps_to_0_25_grid():
    # snap 2.13 -> 2.25, then + 0.25 would be 2.50; spec says snap-then-step
    # returns 2.25 after +1 because 2.13 snaps to 2.25 and the "round to next
    # 0.25 upward" direction keeps us at the snapped value.
    # Per the plan behavior table: zoom_step(2.13, +1) == 2.25
    assert zoom_step(2.13, +1) == 2.25


# ---- CTRL-08: resize clamp ----

def test_resize_clamp_below_min():
    assert resize_clamp(100, 100) == (150, 150)


def test_resize_clamp_above_max():
    assert resize_clamp(800, 800) == (700, 700)


def test_resize_clamp_independent_axes():
    assert resize_clamp(100, 800) == (150, 700)


def test_resize_clamp_in_range_passthrough():
    assert resize_clamp(400, 400) == (400, 400)


# ---- CTRL-09: button layout + 44x44 touch targets ----

def test_button_rects_all_44x44_min_at_150():
    for b in layout_controls(150, 150):
        assert b.w >= 44 and b.h >= 44, f"{b.name} is {b.w}x{b.h}"


def test_button_rects_all_44x44_min_at_700():
    for b in layout_controls(700, 700):
        assert b.w >= 44 and b.h >= 44, f"{b.name} is {b.w}x{b.h}"


def test_button_rects_all_inside_window_at_150():
    w, h = 150, 150
    for b in layout_controls(w, h):
        assert b.x >= 0 and b.y >= 0 and b.x + b.w <= w and b.y + b.h <= h, (
            f"{b.name} {(b.x, b.y, b.w, b.h)} out of [0, {w})x[0, {h})"
        )


def test_button_rects_all_inside_window_at_700():
    w, h = 700, 700
    for b in layout_controls(w, h):
        assert b.x >= 0 and b.y >= 0 and b.x + b.w <= w and b.y + b.h <= h, (
            f"{b.name} {(b.x, b.y, b.w, b.h)} out of [0, {w})x[0, {h})"
        )


def test_button_rects_names_unique():
    assert {b.name for b in layout_controls(400, 400)} == {"shape", "zoom_out", "zoom_in", "resize"}


def test_button_rects_shape_in_top_strip():
    (shape,) = [b for b in layout_controls(400, 400) if b.name == "shape"]
    assert shape.y == 0 and shape.y + shape.h <= 44


def test_button_rects_zoom_and_resize_in_bottom_strip():
    h = 400
    rects = {b.name: b for b in layout_controls(400, h)}
    for name in ("zoom_out", "zoom_in", "resize"):
        b = rects[name]
        assert b.y + b.h == h, f"{name} y+h={b.y + b.h}; expected {h}"


# ---- hit_button linear-scan helper ----

def test_hit_button_returns_name_on_hit():
    assert hit_button(20, 20, [ButtonRect("foo", 10, 10, 44, 44)]) == "foo"


def test_hit_button_returns_none_on_miss():
    assert hit_button(0, 0, [ButtonRect("foo", 10, 10, 44, 44)]) is None


def test_hit_button_right_edge_exclusive():
    # x = 10 + 44 = 54 is exclusive; expect miss.
    assert hit_button(54, 20, [ButtonRect("foo", 10, 10, 44, 44)]) is None


def test_hit_button_bottom_edge_exclusive():
    assert hit_button(20, 54, [ButtonRect("foo", 10, 10, 44, 44)]) is None


# ---- Integration smoke (pure Python; AppState mock) ----

def test_zoom_button_dispatch_calls_set_zoom():
    class FakeState:
        def __init__(self):
            self.calls = []
            self._zoom = 2.0
        def set_zoom(self, z):
            self.calls.append(z)
    fs = FakeState()
    fs.set_zoom(zoom_step(fs._zoom, +1))
    assert fs.calls == [2.25]
