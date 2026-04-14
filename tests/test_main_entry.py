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
    """python main.py must exit 0 and print the Phase 2 observable log lines.

    Phase 2 note: app.main now constructs a BubbleWindow and calls
    bubble.root.mainloop(). We pass ULTIMATE_ZOOM_SMOKE=1 so app.main
    schedules a 50 ms auto-destroy, letting the subprocess exit cleanly
    within the 10-second timeout.
    """
    import os as _os
    env = {**_os.environ, "ULTIMATE_ZOOM_SMOKE": "1"}
    result = subprocess.run(
        [sys.executable, str(MAIN_PY)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"main.py exited {result.returncode}; stderr:\n{result.stderr}"
    )
    out = result.stdout
    assert "[dpi] pmv2=" in out, f"missing [dpi] line in stdout:\n{out}"
    # Phase 2 observable: the bubble logs its hwnd + geometry before mainloop.
    assert "[bubble] hwnd=" in out, (
        f"missing Phase 2 [bubble] line in stdout:\n{out}"
    )
    # Phase 5: goodbye line now references "phase 5" because app.py
    # was rewritten to wire config.load + ConfigWriter into main().
    assert "[app] phase 5 mainloop exited" in out, (
        f"missing Phase 5 [app] exit line in stdout:\n{out}"
    )
    # Phase 5 PERS-01 proof: config.load runs and prints before the
    # bubble appears, so the stdout stream must contain a [config]
    # line from app.py's resolved-path print.
    assert "[config] loaded path=" in out, (
        f"missing Phase 5 [config] loaded line in stdout:\n{out}"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="DPI API is Windows-only")
def test_main_py_dpi_line_contains_physical_dimensions():
    """VALIDATION.md grep hook: stdout must contain physical=<w>x<h>."""
    import os as _os
    env = {**_os.environ, "ULTIMATE_ZOOM_SMOKE": "1"}
    result = subprocess.run(
        [sys.executable, str(MAIN_PY)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=10,
    )
    assert result.returncode == 0
    assert "physical=" in result.stdout
    m = re.search(r"physical=(\d+)x(\d+)", result.stdout)
    assert m is not None, f"physical=WxH not found in stdout:\n{result.stdout}"
    pw = int(m.group(1))
    ph = int(m.group(2))
    assert pw > 0 and ph > 0


# ---- Phase 5 structural lints (Plan 05-02 Task 1) ----


def test_app_loads_config_before_state():
    """PERS-03 structural guarantee: config.load(...) must appear
    earlier in app.main() than AppState(...), or restore-on-launch
    is silently defaulted away.

    Scans the source of magnifier_bubble.app for the first line of
    each call; asserts load's line < AppState's line.
    """
    import ast
    import inspect
    from magnifier_bubble import app

    src = inspect.getsource(app)
    tree = ast.parse(src)

    load_lines: list[int] = []
    appstate_lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # config.load(...)
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "load"
                and isinstance(func.value, ast.Name)
                and func.value.id == "config"
            ):
                load_lines.append(node.lineno)
            # AppState(...)
            if isinstance(func, ast.Name) and func.id == "AppState":
                appstate_lines.append(node.lineno)

    assert load_lines, (
        "app.py must call config.load(...) (PERS-03); none found"
    )
    assert appstate_lines, (
        "app.py must call AppState(...) somewhere; none found"
    )
    assert min(load_lines) < min(appstate_lines), (
        f"config.load must precede AppState construction in app.py; "
        f"got load at line {min(load_lines)} "
        f"and AppState at line {min(appstate_lines)}"
    )


def test_app_wires_config_writer():
    """PERS-02 + PERS-04 structural guarantee: app.main() must
    construct ConfigWriter AND hand it to the bubble via
    attach_config_writer.  If either is missing, debounced writes
    and shutdown flushes silently regress to no-ops.
    """
    import inspect
    from magnifier_bubble import app

    src = inspect.getsource(app)
    assert "config.ConfigWriter(" in src, (
        "app.py must construct config.ConfigWriter(state, bubble.root, path) "
        "for PERS-02 debounced persistence"
    )
    assert "attach_config_writer(" in src, (
        "app.py must call bubble.attach_config_writer(writer) for "
        "PERS-04 shutdown flush; without it destroy() cannot flush "
        "pending writes before Tk teardown"
    )
    assert "writer.register()" in src, (
        "app.py must call writer.register() to attach the "
        "AppState.on_change observer (PERS-02)"
    )


# ---- Phase 6 structural lints (Plan 06-03 Task 2) ----


def test_app_has_no_hotkey_flag():
    """HOTK-04: --no-hotkey must be an argparse flag in app.main()."""
    import inspect
    from magnifier_bubble import app
    src = inspect.getsource(app)
    assert '"--no-hotkey"' in src, (
        "app.py must declare --no-hotkey argparse flag (HOTK-04 escape hatch)"
    )
    assert 'args.no_hotkey' in src


def test_app_constructs_hotkey_manager_after_attach_config_writer():
    """HOTK-05 ordering: HotkeyManager() must be called AFTER
    bubble.attach_config_writer(...) so bubble.root is live."""
    import ast
    import inspect
    from magnifier_bubble import app

    src = inspect.getsource(app)
    tree = ast.parse(src)

    hm_lines: list[int] = []
    acw_lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "HotkeyManager":
                hm_lines.append(node.lineno)
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "attach_config_writer"
            ):
                acw_lines.append(node.lineno)

    assert hm_lines, "app.py must call HotkeyManager(...) somewhere"
    assert acw_lines, "app.py must call bubble.attach_config_writer(...)"
    assert min(acw_lines) < min(hm_lines), (
        f"attach_config_writer must precede HotkeyManager construction; "
        f"got attach_config_writer at line {min(acw_lines)} "
        f"and HotkeyManager at line {min(hm_lines)}"
    )


def test_app_attaches_hotkey_manager_after_construction():
    """HOTK-05: attach_hotkey_manager must follow HotkeyManager(...) so
    the ONLY manager attached is one whose start() returned True."""
    import ast
    import inspect
    from magnifier_bubble import app

    src = inspect.getsource(app)
    tree = ast.parse(src)

    hm_lines: list[int] = []
    ahm_lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "HotkeyManager":
                hm_lines.append(node.lineno)
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "attach_hotkey_manager"
            ):
                ahm_lines.append(node.lineno)

    assert hm_lines, "app.py must construct HotkeyManager"
    assert ahm_lines, (
        "app.py must call bubble.attach_hotkey_manager(hm) after "
        "HotkeyManager.start() returns True"
    )
    assert min(hm_lines) < min(ahm_lines), (
        f"HotkeyManager() must precede attach_hotkey_manager() call"
    )


def test_app_uses_parse_hotkey_on_raw_config():
    """HOTK-04: parse_hotkey must consume the raw dict, not the StateSnapshot."""
    import inspect
    from magnifier_bubble import app
    src = inspect.getsource(app)
    assert "parse_hotkey" in src, (
        "app.py must call config.parse_hotkey(...) (HOTK-04 config integration)"
    )
    # raw config dict read is required (not a StateSnapshot attribute lookup)
    assert "raw_cfg" in src or "raw.get(" in src or 'raw_cfg.get("hotkey")' in src, (
        "app.py must read the raw hotkey dict from json, not from StateSnapshot"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="DPI API is Windows-only")
def test_main_py_no_hotkey_flag_smoke():
    """--no-hotkey path: stdout contains the disabled message."""
    import os as _os
    env = {**_os.environ, "ULTIMATE_ZOOM_SMOKE": "1"}
    result = subprocess.run(
        [sys.executable, str(MAIN_PY), "--no-hotkey"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"main.py --no-hotkey exited {result.returncode}; "
        f"stderr:\n{result.stderr}"
    )
    assert "[hotkey] disabled by --no-hotkey flag" in result.stdout, (
        f"missing [hotkey] disabled line in stdout:\n{result.stdout}"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="DPI API is Windows-only")
def test_main_py_default_smoke_contains_hotkey_line():
    """Default path: stdout contains some [hotkey] line (registered,
    registration failed, or skipped — all acceptable)."""
    import os as _os
    env = {**_os.environ, "ULTIMATE_ZOOM_SMOKE": "1"}
    result = subprocess.run(
        [sys.executable, str(MAIN_PY)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"main.py exited {result.returncode}; stderr:\n{result.stderr}"
    )
    assert "[hotkey]" in result.stdout, (
        f"missing any [hotkey] line in stdout; got:\n{result.stdout}"
    )
