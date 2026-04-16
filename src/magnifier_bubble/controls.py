"""Pure-Python control layout + hit-testing + shape cycle + zoom/resize
math for Phase 4. Zero tkinter / ctypes / pywin32 imports — the math is
fully unit-testable on any platform. The Tk wiring lives in window.py
(Plan 04-02), which imports ButtonRect + layout_controls + hit_button +
SHAPE_CYCLE + zoom_step + resize_clamp from here.

Constants mirror hit_test.DRAG_BAR_HEIGHT / CONTROL_BAR_HEIGHT (44) and
state.py _ZOOM_MIN / _ZOOM_MAX / _ZOOM_STEP but are redeclared here
instead of imported, so tests can run without importing any sibling
module that might have Windows-only runtime bindings.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Mirror hit_test.py — CTRL-09 44x44 touch target. Redeclared (not imported)
# so tests can import controls in isolation without side-effect risk.
DRAG_BAR_HEIGHT: int = 44
CONTROL_BAR_HEIGHT: int = 44

# Mirror state.py _ZOOM_MIN / _ZOOM_MAX / _ZOOM_STEP — CTRL-05.
ZOOM_MIN: float = 1.5
ZOOM_MAX: float = 6.0
ZOOM_STEP: float = 0.25

# CTRL-08 resize range.
MIN_SIZE: int = 150
MAX_SIZE: int = 700   # max height
MAX_WIDTH: int = 1200  # max width — wider horizontal expansion allowed

# CTRL-02 shape cycle state machine: circle -> rounded -> rect -> circle.
SHAPE_CYCLE: dict[str, str] = {
    "circle": "rounded",
    "rounded": "rect",
    "rect": "circle",
}


@dataclass(frozen=True)
class ButtonRect:
    name: str
    x: int
    y: int
    w: int
    h: int


def layout_controls(w: int, h: int) -> list[ButtonRect]:
    close = ButtonRect("close", 0, 0, 44, DRAG_BAR_HEIGHT)
    shape = ButtonRect("shape", w - 44, 0, 44, DRAG_BAR_HEIGHT)
    zoom_out = ButtonRect("zoom_out", 0, h - CONTROL_BAR_HEIGHT, 44, CONTROL_BAR_HEIGHT)
    zoom_in = ButtonRect("zoom_in", w - 88, h - CONTROL_BAR_HEIGHT, 44, CONTROL_BAR_HEIGHT)
    resize = ButtonRect("resize", w - 44, h - CONTROL_BAR_HEIGHT, 44, CONTROL_BAR_HEIGHT)
    return [close, shape, zoom_out, zoom_in, resize]


def hit_button(canvas_x: int, canvas_y: int, buttons: list[ButtonRect]) -> str | None:
    for b in buttons:
        if b.x <= canvas_x < b.x + b.w and b.y <= canvas_y < b.y + b.h:
            return b.name
    return None


def zoom_step(z: float, direction: int) -> float:
    # Snap to 0.25 grid and take one step in `direction`.
    #
    # Semantics (CTRL-05 user-visible):
    #   +1 -> next grid point strictly greater than z (ceil to grid, unless z
    #         is already ON grid, in which case add exactly one step)
    #   -1 -> next grid point strictly less than z
    # So zoom_step(2.00, +1) == 2.25, zoom_step(2.13, +1) == 2.25 (round up
    # to the next visible step), and zoom_step(2.25, +1) == 2.50.
    # This avoids the surprising two-step jump that "snap-then-always-add"
    # would produce when the caller passes an off-grid value.
    steps = z / ZOOM_STEP
    if direction > 0:
        # Next grid point strictly greater than z.
        n = math.floor(steps) + 1
        candidate = n * ZOOM_STEP
        # If z was already on grid, floor(steps) + 1 == steps + 1 already,
        # so this still lands exactly one step above.
    else:
        # Next grid point strictly less than z.
        n = math.ceil(steps) - 1
        candidate = n * ZOOM_STEP
    return max(ZOOM_MIN, min(ZOOM_MAX, candidate))


def resize_clamp(w: int, h: int) -> tuple[int, int]:
    return (
        max(MIN_SIZE, min(MAX_WIDTH, w)),
        max(MIN_SIZE, min(MAX_SIZE, h)),
    )
