"""Structural lints + Windows-only 50-cycle HRGN stress for shapes.apply_shape.

Pitfall F (PITFALLS.md Pitfall 6): if DeleteObject is called on an HRGN
after a successful SetWindowRgn call, the process double-frees on the
next repaint or next SetWindowRgn call. The 50-cycle stress loop is
calibrated to catch this within the first few iterations.
"""
from __future__ import annotations

import ctypes
import inspect
import pathlib
import sys

import pytest

from magnifier_bubble import shapes

SHAPES_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "magnifier_bubble" / "shapes.py"
)


# ========== Structural lints (every platform) ==========

def test_valid_shapes_locked():
    assert shapes.VALID_SHAPES == ("circle", "rounded", "rect")


def test_rounded_radius_is_40():
    assert shapes.ROUNDED_RADIUS == 40


def test_apply_shape_signature_locked():
    """The first 4 params are locked for Plan 03 + Phase 4 call-site
    stability. Phase 4 Plan 02 adds two OPTIONAL strip-aware kwargs
    (strip_top, strip_bottom) so the shape HRGN can be unioned with the
    top + bottom control strips — without this, circle/rounded clip the
    control-button corners and make the shape button unreachable
    (Task 3 bug). The new kwargs default to 0 so Phase 2/3 callers
    that pass only the first 4 args continue to work unchanged.
    """
    sig = inspect.signature(shapes.apply_shape)
    params = list(sig.parameters.keys())
    assert params[:4] == ["hwnd", "w", "h", "shape"], (
        f"apply_shape first 4 params are {params[:4]}; "
        f"Plan 03 and Phase 4 both expect ['hwnd', 'w', 'h', 'shape']"
    )
    # Any additional params must be keyword-able with defaults so
    # existing callers work unchanged.
    for extra_name in params[4:]:
        extra = sig.parameters[extra_name]
        assert extra.default is not inspect.Parameter.empty, (
            f"apply_shape extra param {extra_name!r} has no default — "
            f"this would break existing Phase 2/3 call sites"
        )


def test_apply_shape_raises_valueerror_for_unknown_shape():
    """Guard must happen BEFORE any win32 call — so this works even on non-Windows."""
    with pytest.raises(ValueError):
        shapes.apply_shape(0, 100, 100, "triangle")
    with pytest.raises(ValueError):
        shapes.apply_shape(0, 100, 100, "")
    with pytest.raises(ValueError):
        shapes.apply_shape(0, 100, 100, "CIRCLE")  # case-sensitive


def test_source_contains_setwindowrgn_and_three_create_variants():
    src = SHAPES_PATH.read_text(encoding="utf-8")
    assert "win32gui.SetWindowRgn" in src
    assert "CreateEllipticRgn" in src
    assert "CreateRoundRectRgn" in src
    assert "CreateRectRgn" in src


def test_source_has_failure_branch_with_deleteobject():
    """On SetWindowRgn failure, we still own the HRGN and must DeleteObject it."""
    src = SHAPES_PATH.read_text(encoding="utf-8")
    assert "if result == 0:" in src
    assert "DeleteObject(rgn)" in src
    assert 'raise OSError' in src


def test_source_does_not_deleteobject_on_success():
    """The code must NOT call DeleteObject on the FINAL HRGN passed to
    SetWindowRgn after success. The critical Pitfall 6 fix is that a
    successful SetWindowRgn transfers ownership to the OS. A second
    DeleteObject on that handle would double-free.

    The Phase 4 bug fix introduced CombineRgn to union the shape with
    the top + bottom strip rectangles (see shapes.apply_shape strip_top /
    strip_bottom kwargs). Intermediate HRGNs (top strip rect, bottom strip
    rect, the original shape region after it has been copied into the
    combined dest) ARE owned by us and MUST be DeleteObject'd — those
    calls are legitimate and must NOT count toward this invariant.

    Invariant enforced here: the one DeleteObject call that references
    the FINAL `rgn` variable lives inside the `if result == 0:` failure
    branch. There is exactly one `DeleteObject(rgn)` pattern in the file.
    Intermediate cleanup uses different variable names (top_rgn, bot_rgn,
    shape_rgn) so it cannot accidentally be conflated with the final-
    region release.
    """
    src = SHAPES_PATH.read_text(encoding="utf-8")
    # Exactly one DeleteObject of the FINAL region variable `rgn`.
    # (Intermediate regions use different names and are allowed to be
    # deleted any number of times without violating Pitfall 6.)
    assert src.count("DeleteObject(rgn)") == 1, (
        f"shapes.py should have exactly one DeleteObject(rgn) call (the "
        f"failure-branch release of the final SetWindowRgn candidate); "
        f"found {src.count('DeleteObject(rgn)')}"
    )
    # The one DeleteObject(rgn) call must sit inside the `if result == 0:`
    # failure branch — structural check to guarantee it is not on the
    # success path.
    idx_fail = src.find("if result == 0:")
    idx_final_delete = src.find("DeleteObject(rgn)")
    assert idx_fail != -1, "missing `if result == 0:` failure branch"
    assert idx_final_delete != -1, "missing `DeleteObject(rgn)` call"
    assert idx_final_delete > idx_fail, (
        "DeleteObject(rgn) must appear AFTER the `if result == 0:` line "
        "so it only runs when SetWindowRgn failed"
    )


def test_source_does_not_call_dpi_api():
    src = SHAPES_PATH.read_text(encoding="utf-8")
    assert "SetProcessDpiAwarenessContext" not in src
    assert "SetProcessDpiAwareness(" not in src
    assert "SetProcessDPIAware(" not in src


def test_source_defers_win32gui_import_to_call_time():
    """Structural tests on non-Windows must be able to import shapes without pywin32.
    That requires `import win32gui` to be inside apply_shape, not at module top level."""
    src = SHAPES_PATH.read_text(encoding="utf-8")
    # Find the module-level imports (lines starting with `import ` or `from `
    # that are NOT inside a function body — a simple heuristic: look for
    # `import win32gui` at column 0).
    for line in src.splitlines():
        assert line != "import win32gui", (
            "win32gui must be imported inside apply_shape, not at module top-level, "
            "so structural tests run on non-Windows"
        )
        assert line != "from win32gui import *"


# ========== Windows-only smoke ==========

win_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")


@win_only
def test_apply_shape_circle_does_not_raise(tk_toplevel):
    top, hwnd = tk_toplevel
    shapes.apply_shape(hwnd, 400, 400, "circle")


@win_only
def test_apply_shape_rounded_does_not_raise(tk_toplevel):
    top, hwnd = tk_toplevel
    shapes.apply_shape(hwnd, 400, 400, "rounded")


@win_only
def test_apply_shape_rect_does_not_raise(tk_toplevel):
    top, hwnd = tk_toplevel
    shapes.apply_shape(hwnd, 400, 400, "rect")


@win_only
def test_apply_shape_50_cycle_no_double_free(tk_toplevel):
    """Pitfall F stress test: cycling 50 times must NOT crash the process.
    If apply_shape incorrectly DeleteObject'd a successful HRGN, the second
    or third call would double-free and ACCESS_VIOLATION the interpreter."""
    top, hwnd = tk_toplevel
    cycle = ("circle", "rounded", "rect")
    for i in range(50):
        shape = cycle[i % 3]
        shapes.apply_shape(hwnd, 400, 400, shape)
    # After 50 iterations, the hwnd must still be valid.
    u32 = ctypes.windll.user32
    u32.GetWindowRect.argtypes = [
        ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)
    ]
    u32.GetWindowRect.restype = ctypes.wintypes.BOOL
    rect = ctypes.wintypes.RECT()
    ok = u32.GetWindowRect(hwnd, ctypes.byref(rect))
    assert ok, "hwnd is no longer valid after 50 apply_shape cycles"


@win_only
def test_apply_shape_varies_dimensions_no_crash(tk_toplevel):
    """Phase 4 will call apply_shape on every resize — the smoke test
    uses 10 different (w, h) pairs to simulate that path."""
    top, hwnd = tk_toplevel
    sizes = [(150, 150), (200, 300), (300, 200), (400, 400), (500, 500),
             (600, 400), (400, 600), (700, 700), (250, 400), (400, 250)]
    for w, h in sizes:
        shapes.apply_shape(hwnd, w, h, "circle")
        shapes.apply_shape(hwnd, w, h, "rounded")
        shapes.apply_shape(hwnd, w, h, "rect")


@win_only
def test_apply_shape_100_cycle_interleaved_resize_no_crash(tk_toplevel):
    """Phase 4 Pitfall F regression guard — extended 100-iteration stress.

    Interleaves shape cycling with 5 different (w, h) sizes to mimic the
    real Phase 4 user flow where the user cycles the shape button WHILE
    the resize button is dragging. If any iteration accidentally called
    DeleteObject() on an HRGN owned by the OS, the process would
    ACCESS_VIOLATION within a few iterations. 100 iterations is well
    inside the slack PITFALLS.md recommends, and the 5-size rotation
    exercises every shape helper (CreateEllipticRgn, CreateRoundRectRgn,
    CreateRectRgn) at every window dimension."""
    top, hwnd = tk_toplevel
    cycle = ["circle", "rounded", "rect"]
    sizes = [(200, 200), (300, 250), (400, 400), (250, 350), (500, 500)]
    for i in range(100):
        shape = cycle[i % 3]
        w, h = sizes[i % 5]
        shapes.apply_shape(hwnd, w, h, shape)
    # After 100 iterations, the hwnd must still be valid.
    u32 = ctypes.windll.user32
    u32.GetWindowRect.argtypes = [
        ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)
    ]
    u32.GetWindowRect.restype = ctypes.wintypes.BOOL
    rect = ctypes.wintypes.RECT()
    result = u32.GetWindowRect(hwnd, ctypes.byref(rect))
    assert result != 0, "hwnd invalidated after 100-cycle stress (Pitfall F regression)"
