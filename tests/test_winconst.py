"""Regression lint for src/magnifier_bubble/winconst.py.

Every value is checked against the documented Microsoft Learn constant.
This file runs on every platform because it never touches user32 — it is
a pure Python assert over the module's name bindings.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from magnifier_bubble import winconst

WINCONST_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "magnifier_bubble" / "winconst.py"
)


# ---- Value lint (each constant asserted against Microsoft Learn) ----

@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("WS_EX_LAYERED",     0x00080000),
        ("WS_EX_TOOLWINDOW",  0x00000080),
        ("WS_EX_NOACTIVATE",  0x08000000),
        ("WS_EX_TRANSPARENT", 0x00000020),
        ("GWL_EXSTYLE",       -20),
        ("GWLP_WNDPROC",      -4),
        ("LWA_ALPHA",         0x00000002),
        ("LWA_COLORKEY",      0x00000001),
        ("HTCLIENT",          1),
        ("HTCAPTION",         2),
        ("HTTRANSPARENT",     -1),
        ("HTBOTTOMRIGHT",     17),
        ("WM_NCHITTEST",      0x0084),
        ("WM_NCLBUTTONDOWN",  0x00A1),
        ("WM_MOUSEMOVE",      0x0200),
        ("WM_LBUTTONDOWN",    0x0201),
        ("WM_DESTROY",        0x0002),
        # ---- Phase 4 additions ----
        ("CWP_SKIPINVISIBLE",   0x0001),
        ("CWP_SKIPDISABLED",    0x0002),
        ("CWP_SKIPTRANSPARENT", 0x0004),
        ("MK_LBUTTON",          0x0001),
        ("WM_LBUTTONUP",        0x0202),
        # ---- Phase 6 additions ----
        ("MOD_ALT",      0x0001),
        ("MOD_CONTROL",  0x0002),
        ("MOD_SHIFT",    0x0004),
        ("MOD_WIN",      0x0008),
        ("MOD_NOREPEAT", 0x4000),
        ("VK_Z",         0x5A),
        ("WM_HOTKEY",    0x0312),
        ("WM_QUIT",      0x0012),
        ("ERROR_HOTKEY_ALREADY_REGISTERED", 1409),
    ],
)
def test_winconst_value(name, expected):
    actual = getattr(winconst, name)
    assert actual == expected, (
        f"winconst.{name} = {actual!r} ({hex(actual) if isinstance(actual, int) else actual}), "
        f"expected {expected!r} ({hex(expected) if isinstance(expected, int) else expected}) "
        f"per Microsoft Learn"
    )


# ---- Structural lint: no function/class defs, no runtime imports ----

def test_winconst_has_no_runtime_third_party_imports():
    source = WINCONST_PATH.read_text(encoding="utf-8")
    # Allowed: `from __future__ import annotations` only.
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
        "import pywin32",
    ]
    for f in forbidden:
        assert f not in source, (
            f"winconst.py must be pure constants — found forbidden import: {f}"
        )


def test_winconst_body_is_only_constants_and_future_import():
    """ast.parse yields only: ImportFrom(__future__), Assign(name = Constant/UnaryOp)."""
    tree = ast.parse(WINCONST_PATH.read_text(encoding="utf-8"))
    allowed_node_types = (ast.ImportFrom, ast.Assign)
    for i, node in enumerate(tree.body):
        # The module docstring is an ast.Expr(Constant(str)); allow it.
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            continue
        assert isinstance(node, allowed_node_types), (
            f"winconst.py body[{i}] is {type(node).__name__}; "
            f"winconst.py must contain only imports and top-level Assign nodes. "
            f"No FunctionDef, ClassDef, If, Try, For, or expression statements."
        )


def test_winconst_has_no_function_or_class_definitions():
    tree = ast.parse(WINCONST_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        assert not isinstance(node, ast.FunctionDef), (
            f"winconst.py must not define functions; found: {node.name}"
        )
        assert not isinstance(node, ast.AsyncFunctionDef)
        assert not isinstance(node, ast.ClassDef), (
            f"winconst.py must not define classes; found: {node.name}"
        )


def test_winconst_first_import_is_future_annotations():
    tree = ast.parse(WINCONST_PATH.read_text(encoding="utf-8"))
    # Module docstring is tree.body[0] if present; first non-docstring statement must be the future import.
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    assert body, "winconst.py has no statements after the docstring"
    first = body[0]
    assert isinstance(first, ast.ImportFrom), (
        f"First non-docstring statement in winconst.py should be the future import; got {type(first).__name__}"
    )
    assert first.module == "__future__"
    assert any(alias.name == "annotations" for alias in first.names)
