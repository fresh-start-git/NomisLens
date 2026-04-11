"""Integration tests for main.py - the OVER-05 entry point.

These tests pin down the single most important invariant of Phase 1:
    main.py line 1 is `import ctypes`, and the DPI awareness call
    happens before ANY other import (including magnifier_bubble).

Two layers:
  1. Static AST lint - parses main.py without executing it, asserts
     body[0] is `import ctypes` and the DPI try/except appears before
     any non-ctypes/non-stdlib import. Platform-independent; runs everywhere.
  2. Subprocess smoke - runs `python main.py` as a child process and
     checks the exit code + stdout log lines. Windows-only (the DPI
     call is a no-op / raises AttributeError on other OSes).

Note on structure: main.py body[1] is an Assign that sets argtypes on
SetProcessDpiAwarenessContext (so x64 Python passes the -4 sentinel as
a pointer-sized HANDLE instead of a truncated c_int). body[2] is the
try/except DPI ladder. The scan-based tests below accept this layout
while still enforcing that the DPI ladder appears before ANY import of
magnifier_bubble, tkinter, mss, PIL, or pywin32.
"""
from __future__ import annotations

import ast
import pathlib
import re
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MAIN_PY = REPO_ROOT / "main.py"


# ---- Helpers ----


def _parse_main() -> ast.Module:
    return ast.parse(MAIN_PY.read_text(encoding="utf-8"))


def _find_dpi_try(tree: ast.Module) -> tuple[int, ast.Try]:
    """Return (index, try-node) of the DPI try/except in tree.body.

    The DPI ladder is the first ast.Try whose inner body contains a call
    to SetProcessDpiAwarenessContext. This lets main.py put argtypes
    setup between `import ctypes` and the try without breaking the test.
    """
    for i, stmt in enumerate(tree.body):
        if not isinstance(stmt, ast.Try):
            continue
        for inner in stmt.body:
            if isinstance(inner, ast.Expr) and isinstance(inner.value, ast.Call):
                call = inner.value
                if (
                    isinstance(call.func, ast.Attribute)
                    and call.func.attr == "SetProcessDpiAwarenessContext"
                ):
                    return i, stmt
    raise AssertionError("main.py has no try/except calling SetProcessDpiAwarenessContext")


# ---- Static lint layer (platform-independent) ----


def test_main_py_exists():
    assert MAIN_PY.is_file(), f"main.py not found at {MAIN_PY}"


def test_main_py_first_line_is_import_ctypes():
    with MAIN_PY.open("rb") as f:
        first_line = f.readline().decode("utf-8").rstrip("\r\n")
    assert first_line == "import ctypes", (
        f"main.py line 1 must be 'import ctypes' (OVER-05); got: {first_line!r}"
    )


def test_main_py_has_no_module_docstring():
    """OVER-05 is unambiguous iff there is no docstring above `import ctypes`."""
    source = MAIN_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert len(tree.body) >= 1
    first = tree.body[0]
    assert isinstance(first, ast.Import), (
        f"main.py body[0] should be `import ctypes`; got {type(first).__name__}"
    )
    assert first.names[0].name == "ctypes"


def test_main_py_dpi_call_is_present_and_targets_pmv2():
    """The DPI try/except must appear, and call SetProcessDpiAwarenessContext(-4)."""
    tree = _parse_main()
    _, try_node = _find_dpi_try(tree)
    # The first statement inside the try must be the DPI call expression.
    inner = try_node.body[0]
    assert isinstance(inner, ast.Expr), (
        f"first statement inside DPI try must be the call; got {type(inner).__name__}"
    )
    call = inner.value
    assert isinstance(call, ast.Call)
    assert isinstance(call.func, ast.Attribute)
    assert call.func.attr == "SetProcessDpiAwarenessContext"
    assert len(call.args) == 1
    arg = call.args[0]
    assert isinstance(arg, ast.UnaryOp)
    assert isinstance(arg.op, ast.USub)
    assert isinstance(arg.operand, ast.Constant)
    assert arg.operand.value == 4


def test_main_py_dpi_runs_before_any_third_party_import():
    """OVER-05 invariant: DPI try/except appears before any import that
    could lock the DPI context — specifically magnifier_bubble, tkinter,
    mss, PIL, or pywin32. `import ctypes`, `import os`, `import sys` are
    allowed to flank the DPI call because stdlib modules do not touch DPI.
    """
    tree = _parse_main()
    dpi_index, _ = _find_dpi_try(tree)
    forbidden_modules = {"magnifier_bubble", "tkinter", "mss", "PIL", "win32api", "win32con", "win32gui"}
    for i, stmt in enumerate(tree.body[:dpi_index]):
        names: list[str] = []
        if isinstance(stmt, ast.Import):
            names = [a.name.split(".")[0] for a in stmt.names]
        elif isinstance(stmt, ast.ImportFrom):
            if stmt.module is not None:
                names = [stmt.module.split(".")[0]]
        for n in names:
            assert n not in forbidden_modules, (
                f"main.py body[{i}] imports {n!r} BEFORE the DPI try/except "
                f"(index {dpi_index}); this violates OVER-05"
            )


def test_main_py_does_not_import_mss_or_tkinter_at_top_level():
    """Those imports would violate DPI-first ordering at any position."""
    source = MAIN_PY.read_text(encoding="utf-8")
    assert "import mss" not in source
    assert "import tkinter" not in source
    assert "from tkinter" not in source
    assert "import PIL" not in source
    assert "from PIL" not in source
    assert "import win32" not in source
    assert "from win32" not in source


def test_main_py_has_specific_except_clauses():
    """Bare except: hides genuine bugs. We catch (AttributeError, OSError) only."""
    source = MAIN_PY.read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        assert stripped != "except:", "main.py must not contain a bare `except:`"
        assert stripped != "except Exception:", (
            "main.py must catch (AttributeError, OSError), not bare Exception"
        )
    assert "except (AttributeError, OSError):" in source


def test_main_py_delegates_to_magnifier_bubble_app_main():
    source = MAIN_PY.read_text(encoding="utf-8")
    assert "from magnifier_bubble.app import main" in source
    assert "raise SystemExit(main())" in source


# ---- Subprocess smoke layer (requires Windows for real DPI call) ----


@pytest.mark.skipif(sys.platform != "win32", reason="DPI API is Windows-only")
def test_main_py_runs_and_exits_zero():
    """python main.py must exit 0 and print the three expected log lines."""
    result = subprocess.run(
        [sys.executable, str(MAIN_PY)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=10,
    )
    assert result.returncode == 0, (
        f"main.py exited {result.returncode}; stderr:\n{result.stderr}"
    )
    out = result.stdout
    assert "[dpi] pmv2=" in out, f"missing [dpi] line in stdout:\n{out}"
    assert "[state] snapshot after set_position(300,400)" in out, (
        f"missing [state] line in stdout:\n{out}"
    )
    assert "[app] phase 1 scaffold OK" in out, (
        f"missing [app] scaffold line in stdout:\n{out}"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="DPI API is Windows-only")
def test_main_py_dpi_line_contains_physical_dimensions():
    """VALIDATION.md grep hook: stdout must contain physical=<w>x<h>."""
    result = subprocess.run(
        [sys.executable, str(MAIN_PY)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=10,
    )
    assert result.returncode == 0
    assert "physical=" in result.stdout
    m = re.search(r"physical=(\d+)x(\d+)", result.stdout)
    assert m is not None, f"physical=WxH not found in stdout:\n{result.stdout}"
    pw = int(m.group(1))
    ph = int(m.group(2))
    assert pw > 0 and ph > 0
