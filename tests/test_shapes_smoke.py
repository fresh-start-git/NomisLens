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
    sig = inspect.signature(shapes.apply_shape)
    params = list(sig.parameters.keys())
    assert params == ["hwnd", "w", "h", "shape"], (
        f"apply_shape params are {params}; Plan 03 and Phase 4 both expect "
        f"['hwnd', 'w', 'h', 'shape']"
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
    """The code must NOT call DeleteObject outside the failure branch.
    The critical Pitfall 6 fix is that a successful SetWindowRgn transfers
    ownership to the OS. A second DeleteObject would double-free."""
    src = SHAPES_PATH.read_text(encoding="utf-8")
    # Exactly one DeleteObject call, inside the failure branch
    assert src.count("DeleteObject(") == 1, (
        f"shapes.py should have exactly one DeleteObject call (failure branch); "
        f"found {src.count('DeleteObject(')}"
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
