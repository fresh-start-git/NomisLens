"""Table-driven boundary tests for src/magnifier_bubble/hit_test.py.

Covers LAYT-01 (three zones), LAYT-02 (middle is "content" -> WndProc will
map to HTTRANSPARENT), LAYT-03 (drag + control bands -> WndProc will map
to HTCAPTION / HTCLIENT). The win32 -> string mapping itself is Plan 02's
wndproc.py concern; this file covers only the pure zone math.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from magnifier_bubble import hit_test
from magnifier_bubble.hit_test import (
    CONTROL_BAR_HEIGHT,
    DRAG_BAR_HEIGHT,
    compute_zone,
)

HIT_TEST_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "magnifier_bubble" / "hit_test.py"
)


# ---- Module-level constants are locked ----

def test_drag_bar_height_is_44():
    assert DRAG_BAR_HEIGHT == 44, (
        "DRAG_BAR_HEIGHT is the CTRL-09 finger touch target; must stay 44"
    )


def test_control_bar_height_is_44():
    assert CONTROL_BAR_HEIGHT == 44


# ---- Boundary table (LAYT-01, LAYT-02, LAYT-03) ----
# Covers standard 400x400 bubble, minimum 150x150 bubble, and degenerate 60x60.

@pytest.mark.parametrize(
    ("cx", "cy", "w", "h", "expected"),
    [
        # 400x400 standard — drag band [0..44), content [44..356), control [356..400)
        (200, 0,   400, 400, "drag"),     # top-left of drag bar
        (200, 43,  400, 400, "drag"),     # last pixel of drag bar
        (200, 44,  400, 400, "content"),  # first pixel of content
        (200, 200, 400, 400, "content"),  # dead center
        (200, 355, 400, 400, "content"),  # last pixel of content
        (200, 356, 400, 400, "control"),  # first pixel of control strip
        (200, 399, 400, 400, "control"),  # last pixel of control strip
        # Out of bounds — content (WndProc will return HTTRANSPARENT; SetWindowRgn handles the real corner clip)
        (-10, 200, 400, 400, "content"),
        (410, 200, 400, 400, "content"),
        (200, -5,  400, 400, "content"),
        (200, 500, 400, 400, "content"),
        # 150x150 minimum — drag [0..44), content [44..106), control [106..150)
        (75, 0,   150, 150, "drag"),
        (75, 43,  150, 150, "drag"),
        (75, 44,  150, 150, "content"),
        (75, 105, 150, 150, "content"),
        (75, 106, 150, 150, "control"),
        (75, 149, 150, 150, "control"),
        # 60x60 degenerate — drag [0..44), control [16..60). Overlap [16..44) resolves to "drag" (first test wins).
        (30, 0,  60, 60, "drag"),
        (30, 15, 60, 60, "drag"),
        (30, 16, 60, 60, "drag"),        # overlap region — drag wins
        (30, 43, 60, 60, "drag"),        # last pixel of drag band
        (30, 44, 60, 60, "control"),     # first pixel above [16, 60)? No: 44 is in [16, 60) -> "control"
        (30, 59, 60, 60, "control"),
    ],
)
def test_compute_zone_boundary(cx, cy, w, h, expected):
    assert compute_zone(cx, cy, w, h) == expected, (
        f"compute_zone({cx}, {cy}, {w}, {h}) should be {expected!r}"
    )


def test_middle_returns_content():
    """LAYT-02 contract at the center of a standard 400x400 bubble."""
    assert compute_zone(200, 200, 400, 400) == "content"


def test_drag_bar_returns_drag():
    """LAYT-03 top-strip contract."""
    assert compute_zone(200, 10, 400, 400) == "drag"


def test_control_strip_returns_control():
    """LAYT-03 bottom-strip contract."""
    assert compute_zone(200, 390, 400, 400) == "control"


# ---- Signature lock (Plan 02 wndproc.py depends on this exact signature) ----

def test_compute_zone_signature():
    sig = inspect.signature(compute_zone)
    params = list(sig.parameters.keys())
    assert params == ["client_x", "client_y", "w", "h"], (
        f"compute_zone params are {params}; Plan 02's wndproc.py expects "
        f"['client_x', 'client_y', 'w', 'h']"
    )
    assert sig.return_annotation is str


# ---- Module purity lint (no win32 / Tk imports) ----

def test_hit_test_has_no_third_party_imports():
    source = HIT_TEST_PATH.read_text(encoding="utf-8")
    forbidden = [
        "import ctypes",
        "from ctypes",
        "import tkinter",
        "from tkinter",
        "import win32",
        "from win32",
        "import mss",
        "from mss",
        "import PIL",
        "from PIL",
        # hit_test is also intentionally decoupled from winconst — Plan 02 bridges them.
        "from magnifier_bubble import winconst",
        "from magnifier_bubble.winconst",
    ]
    for f in forbidden:
        assert f not in source, f"hit_test.py must be pure — found: {f}"


def test_hit_test_module_contract_via_ast():
    """One function (compute_zone) + two module-level Assigns + docstring + future import."""
    tree = ast.parse(HIT_TEST_PATH.read_text(encoding="utf-8"))
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    assigns = [n for n in tree.body if isinstance(n, ast.Assign) or isinstance(n, ast.AnnAssign)]
    func_names = [f.name for f in funcs]
    assert "compute_zone" in func_names, (
        f"hit_test.py must define compute_zone; top-level functions are {func_names}"
    )
    # Must define DRAG_BAR_HEIGHT and CONTROL_BAR_HEIGHT at module level.
    assigned_names: list[str] = []
    for a in assigns:
        if isinstance(a, ast.AnnAssign) and isinstance(a.target, ast.Name):
            assigned_names.append(a.target.id)
        elif isinstance(a, ast.Assign):
            for tgt in a.targets:
                if isinstance(tgt, ast.Name):
                    assigned_names.append(tgt.id)
    assert "DRAG_BAR_HEIGHT" in assigned_names
    assert "CONTROL_BAR_HEIGHT" in assigned_names
