---
phase: 01-foundation-dpi
plan: 03
type: execute
wave: 3
depends_on: ["01-foundation-dpi/01", "01-foundation-dpi/02"]
files_modified:
  - main.py
  - src/magnifier_bubble/app.py
  - tests/test_main_entry.py
autonomous: true
requirements: [OVER-05]
must_haves:
  truths:
    - "python main.py exits cleanly with code 0 on Windows 11"
    - "main.py line 1 is 'import ctypes' (no docstring, no blank line, no shebang before it)"
    - "main.py line 2 starts the DPI awareness chain via ctypes.windll.user32.SetProcessDpiAwarenessContext(-4) inside a try/except ladder"
    - "The DPI call occurs BEFORE any import of mss, tkinter, PIL, pywin32, or magnifier_bubble submodules"
    - "Running python main.py prints a [dpi] pmv2=... line to stdout proving dpi.debug_print was reached"
    - "Running python main.py prints a [state] line proving AppState round-tripped a set_position and snapshot"
    - "Full phase suite: pytest tests/ -v passes (state + dpi + main-entry tests all green)"
  artifacts:
    - path: main.py
      provides: "Root entry point; OVER-05 first-line DPI call; 12-line shim that delegates to magnifier_bubble.app.main"
      contains: "SetProcessDpiAwarenessContext(-4)"
      min_lines: 10
    - path: src/magnifier_bubble/app.py
      provides: "Phase 1 app.main() - calls dpi.debug_print(), constructs AppState, smoke-tests setter+snapshot, exits 0"
      contains: "def main"
      min_lines: 20
    - path: tests/test_main_entry.py
      provides: "Static lint + subprocess smoke test for main.py DPI-first ordering"
      contains: "SetProcessDpiAwarenessContext"
      min_lines: 40
  key_links:
    - from: main.py
      to: ctypes.windll.user32
      via: "first executable statement calls SetProcessDpiAwarenessContext(-4) before any magnifier_bubble import"
      pattern: "SetProcessDpiAwarenessContext\\(-4\\)"
    - from: main.py
      to: src/magnifier_bubble/app.py
      via: "from magnifier_bubble.app import main; main()"
      pattern: "from magnifier_bubble\\.app import main"
    - from: src/magnifier_bubble/app.py
      to: src/magnifier_bubble/dpi.py
      via: "from magnifier_bubble import dpi; dpi.debug_print()"
      pattern: "dpi\\.debug_print"
    - from: src/magnifier_bubble/app.py
      to: src/magnifier_bubble/state.py
      via: "from magnifier_bubble.state import AppState, StateSnapshot; AppState(StateSnapshot())"
      pattern: "AppState\\(StateSnapshot"
---

<objective>
Wire the Phase 1 foundation together: the root main.py shim (with DPI-first ordering), the magnifier_bubble.app.main() Phase 1 entry that exercises both dpi.report and AppState, and a static+subprocess test that guarantees SetProcessDpiAwarenessContext(-4) really is the first executable statement of main.py.

Purpose: This is the plan that actually satisfies OVER-05 as a testable runtime property. Plans 01 and 02 built the scaffolding and the modules; plan 03 is the integration that makes python main.py exit 0 with correct output on Windows 11.

Output: A repository where python main.py runs end-to-end, the debug print proves PMv2 is active, and the full pytest suite (pytest tests/ -v) is green across all three plans of Phase 1.
</objective>

<execution_context>
@C:/Users/Jsupport/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/Jsupport/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/01-foundation-dpi/01-RESEARCH.md
@.planning/phases/01-foundation-dpi/01-VALIDATION.md

<interfaces>
Plan 02 produced:

src/magnifier_bubble/state.py exports:
    class StateSnapshot (dataclass: x, y, w, h, zoom, shape, visible, always_on_top)
    class AppState:
      __init__(initial: StateSnapshot | None)
      on_change(cb), snapshot(), capture_region()
      set_position(x, y), set_size(w, h), set_zoom(z), set_shape(s), set_visible(b)
      toggle_visible(), toggle_aot()

src/magnifier_bubble/dpi.py exports:
    DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
    is_pmv2_active() -> bool
    report() -> DpiReport (TypedDict)
    debug_print() -> None  # prints "[dpi] pmv2=B dpi=N scale=N% logical=WxH physical=WxH"

Plan 01 produced:
    pyproject.toml with pythonpath = ["src"]
    src/magnifier_bubble/__init__.py (EMPTY - DO NOT add imports)
    src/magnifier_bubble/__main__.py (imports magnifier_bubble.app.main - functional after this plan)

CRITICAL ordering constraint (OVER-05):
- main.py line 1: `import ctypes` (literally first line, no docstring, no shebang)
- main.py line 2..N: try/except ladder calling SetProcessDpiAwarenessContext(-4)
- Only AFTER the DPI call can sys, os, sys.path manipulation, and the magnifier_bubble imports happen.
- Research Pitfall 1: if `from magnifier_bubble.app import main` runs before the ctypes call, and app.py transitively imports anything that constructs mss.mss(), we lose V2 permanently.
- app.py for Phase 1 only imports from magnifier_bubble.dpi and .state, both stdlib-only and safe; but the ordering discipline must be maintained so Phase 3 (when capture.py lands and imports mss) does not break main.py retroactively.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create magnifier_bubble.app.main() Phase 1 entry</name>
  <files>src/magnifier_bubble/app.py</files>
  <read_first>
.planning/phases/01-foundation-dpi/01-RESEARCH.md (sections: Code Examples > app.py; Architecture Patterns > Recommended Project Structure)
src/magnifier_bubble/state.py (from plan 02)
src/magnifier_bubble/dpi.py (from plan 02)
src/magnifier_bubble/__init__.py (confirm still empty/0 bytes)
  </read_first>
  <action>
Create src/magnifier_bubble/app.py with EXACTLY this content (everything between the fenced code block below, verbatim):

~~~python
"""Ultimate Zoom — Phase 1 entry point.

This is the first phase — there is no Tk mainloop yet. The Phase 1 job is
to prove that the DPI-first main.py shim successfully:
  1. Set Per-Monitor-V2 DPI awareness (verified by dpi.debug_print).
  2. Constructed an AppState (verified by a round-trip set+snapshot).
  3. Exited cleanly with code 0.

Later phases replace this body: Phase 2 creates the bubble window here,
Phase 3 kicks off the capture thread, Phase 6 registers the hotkey, etc.
"""
from __future__ import annotations

from magnifier_bubble import dpi
from magnifier_bubble.state import AppState, StateSnapshot


def main() -> int:
    # Phase 1 Criterion 5: observable proof that DPI awareness worked.
    dpi.debug_print()

    # Phase 1 Criterion 4: AppState is the single source of truth.
    state = AppState(StateSnapshot())

    # Smoke: mutate then snapshot to prove the container round-trips.
    state.set_position(300, 400)
    snap = state.snapshot()
    print(
        f"[state] snapshot after set_position(300,400): "
        f"x={snap.x} y={snap.y} w={snap.w} h={snap.h} "
        f"zoom={snap.zoom} shape={snap.shape} "
        f"visible={snap.visible} always_on_top={snap.always_on_top}"
    )

    # Phase 1 has no mainloop — scaffold only. Exit cleanly.
    print("[app] phase 1 scaffold OK; exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
~~~

Do NOT:
- Import tkinter, mss, PIL, or pywin32 - those come in later phases and would silently fail DPI if pulled in here (research Pitfall 1).
- Add a Tk mainloop (Phase 2 concern).
- Parse command-line args (YAGNI; Phase 1 has no flags).
- Add logging config (plain print is explicitly the VALIDATION.md contract).
- Import from magnifier_bubble.capture, .window, .hotkey, .tray, .config - none exist yet.
- Set DPI awareness inside app.py - that is main.py's exclusive job per OVER-05.
  </action>
  <verify>
    <automated>python -c "import sys; sys.path.insert(0,'src'); from magnifier_bubble.app import main; import inspect; assert callable(main); sig = inspect.signature(main); assert sig.return_annotation is int, f'expected -> int, got {sig.return_annotation}'"</automated>
  </verify>
  <acceptance_criteria>
src/magnifier_bubble/app.py exists
file contains literal "def main() -> int:"
file contains literal "from magnifier_bubble import dpi"
file contains literal "from magnifier_bubble.state import AppState, StateSnapshot"
file contains literal "dpi.debug_print()"
file contains literal "AppState(StateSnapshot())"
file contains literal "state.set_position(300, 400)"
file contains literal "[state]" (the log tag)
file contains literal "[app] phase 1 scaffold OK"
file does NOT contain "import tkinter"
file does NOT contain "import mss"
file does NOT contain "import PIL"
file does NOT contain "import win32"
file does NOT contain "pywin32"
file does NOT contain "SetProcessDpiAwarenessContext" (DPI init belongs in main.py, not app.py)
python -c "import sys; sys.path.insert(0,'src'); from magnifier_bubble.app import main; import inspect; print(inspect.signature(main))" prints "() -> int"
  </acceptance_criteria>
  <done>
magnifier_bubble.app.main() is importable, returns int, and calls both dpi.debug_print() and AppState.set_position + snapshot when invoked. The module has zero third-party imports.
  </done>
</task>

<task type="auto">
  <name>Task 2: Create root main.py shim with DPI-first ordering</name>
  <files>main.py</files>
  <read_first>
.planning/phases/01-foundation-dpi/01-RESEARCH.md (sections: Architecture Patterns > Pattern 1 DPI-First main.py Header; Code Examples > main.py ENTIRE FILE; Common Pitfalls > Pitfall 1 Late DPI Awareness; Pitfall 5 main.py import path confusion; Open Questions > Q4 "first executable line")
.planning/REQUIREMENTS.md (OVER-05)
src/magnifier_bubble/app.py (from Task 1)
  </read_first>
  <action>
Create main.py at the repository root with EXACTLY this content. No shebang, no module docstring, no blank line before `import ctypes`. Line 1 MUST be `import ctypes`. Everything between the fenced block below is the whole file contents, verbatim:

~~~python
import ctypes
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)  # PMv2
except (AttributeError, OSError):
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor V1 (Win 8.1+)
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()  # System-aware (legacy)

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from magnifier_bubble.app import main

raise SystemExit(main())
~~~

Byte-for-byte requirements (OVER-05 is verified by static analysis - one character out of place fails the lint):
- Line 1: `import ctypes` (no leading whitespace, no comment before).
- Line 2: `try:`
- Line 3: `    ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)  # PMv2`
- Line 4: `except (AttributeError, OSError):`
- Lines 5-8: inner fallback ladder
- Line 9: blank (separator)
- Line 10: `import os`
- Line 11: `import sys`
- Line 12: `sys.path.insert(...)` with `"src"` suffix
- Line 13: blank
- Line 14: `from magnifier_bubble.app import main`
- Line 15: blank
- Line 16: `raise SystemExit(main())`

DO NOT:
- Add a module docstring (research Open Question 4: zero ambiguity wins).
- Add a shebang `#!/usr/bin/env python` (not needed on Windows, and would push `import ctypes` to line 2).
- Use a bare `except:` - catch `(AttributeError, OSError)` specifically so genuine programmer errors surface.
- Call DPI API twice at the same level - Microsoft explicitly says the second call fails with ERROR_ACCESS_DENIED.
- Move `sys.path.insert` BEFORE the DPI call (it must come after; `sys` is allowed to be imported after ctypes because `sys` itself does not touch DPI).
- Use `if __name__ == "__main__":` guard - this file IS the entry, not a library.
- Print "hello world" or any debug before main(); the debug print lives in app.py.

After creating the file, run `python main.py` (on Windows) and confirm:
1. Exit code is 0.
2. stdout contains a `[dpi] pmv2=True ...` line (True on Windows 10 1703+; may be False on older Windows where the ladder fell back to V1 or legacy - that is still a pass for OVER-05's fallback spec).
3. stdout contains a `[state] snapshot after set_position(300,400): x=300 y=400 ...` line.
4. stdout contains `[app] phase 1 scaffold OK; exiting`.
  </action>
  <verify>
    <automated>python -c "import ast; tree = ast.parse(open('main.py').read()); first = tree.body[0]; assert isinstance(first, ast.Import) and first.names[0].name == 'ctypes', 'main.py body[0] is not import ctypes'" &amp;&amp; python main.py</automated>
  </verify>
  <acceptance_criteria>
main.py exists at repository root
The very first 13 bytes of main.py are exactly "import ctypes" (head -c 13 main.py returns "import ctypes")
ast.parse(open('main.py').read()).body[0] is an ast.Import whose first alias name is "ctypes" (proves line 1 is `import ctypes`, with no docstring)
main.py contains literal "SetProcessDpiAwarenessContext(-4)"
main.py contains literal "SetProcessDpiAwareness(2)" (V1 fallback)
main.py contains literal "SetProcessDPIAware()" (legacy fallback)
main.py contains literal "except (AttributeError, OSError):" (specific exception catch, not bare except)
main.py does NOT contain "except Exception" (pattern grep returns 0)
main.py does NOT contain a bare "except:" line (stripped line equal to "except:" appears zero times)
main.py contains literal: sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
main.py contains literal "from magnifier_bubble.app import main"
main.py contains literal "raise SystemExit(main())"
main.py does NOT start with a triple-quote docstring (first non-empty line does not match pattern starting with triple quote)
main.py does NOT start with "#!" (no shebang)
main.py line count: wc -l main.py reports between 14 and 18 lines
Running `python main.py` in a venv with requirements.txt installed exits with code 0
python main.py stdout contains the substring "[dpi] pmv2="
python main.py stdout contains the substring "[state] snapshot after set_position(300,400)"
python main.py stdout contains the substring "[app] phase 1 scaffold OK"
On Windows 10 1703+ specifically, python main.py stdout contains "pmv2=True" (under the try branch, V2 succeeds). On non-Windows or older Windows where the ladder falls back, pmv2=False is acceptable - OVER-05 is about ordering, not about guaranteeing V2 on every OS.
  </acceptance_criteria>
  <done>
python main.py runs end-to-end, exits 0, and prints three observable log lines. ast.parse(main.py).body[0] is the ctypes import, static-confirming OVER-05. The repo now satisfies all five Phase 1 ROADMAP success criteria: (1) clean launch+exit, (2) DPI call first, (3) requirements.txt installs (plan 01), (4) AppState round-trips (plan 02 + this task), (5) debug print emits logical/physical dimensions (this task).
  </done>
</task>

<task type="auto">
  <name>Task 3: Create static lint + subprocess smoke test for main.py OVER-05</name>
  <files>tests/test_main_entry.py</files>
  <read_first>
.planning/phases/01-foundation-dpi/01-VALIDATION.md (Per-Task Verification Map rows 1-01-05, 1-01-06)
.planning/phases/01-foundation-dpi/01-RESEARCH.md (Validation Architecture > Phase Requirements Test Map; Open Questions > Q4)
main.py (from Task 2)
tests/conftest.py (provides win_only marker from plan 01)
  </read_first>
  <action>
Create tests/test_main_entry.py with EXACTLY this content:

~~~python
"""Integration tests for main.py - the OVER-05 entry point.

These tests pin down the single most important invariant of Phase 1:
    main.py line 1 is `import ctypes`, and the DPI awareness call
    happens before ANY other import (including magnifier_bubble).

Two layers:
  1. Static AST lint - parses main.py without executing it, asserts
     body[0] is `import ctypes` and body[1] is the DPI try/except.
     Platform-independent; runs everywhere.
  2. Subprocess smoke - runs `python main.py` as a child process and
     checks the exit code + stdout log lines. Windows-only (the DPI
     call is a no-op / raises AttributeError on other OSes).
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


def test_main_py_dpi_call_is_second_statement():
    """After `import ctypes`, the next statement must be the DPI try/except."""
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    assert len(tree.body) >= 2, "main.py must have at least 2 top-level statements"
    second = tree.body[1]
    assert isinstance(second, ast.Try), (
        f"main.py body[1] should be the try/except DPI ladder; "
        f"got {type(second).__name__}"
    )
    inner = second.body[0]
    assert isinstance(inner, ast.Expr)
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


def test_main_py_does_not_import_mss_or_tkinter_at_top_level():
    """Those imports would violate DPI-first ordering."""
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
~~~

Do NOT:
- Import main.py directly as a module - it calls ctypes and raises SystemExit; importing it inside pytest would abort the test runner. Use subprocess instead.
- Add a test that asserts pmv2=True - on non-Windows or older Windows the fallback ladder is correct behavior for OVER-05. The smoke test above only asserts that the LINE exists, not its boolean value.
- Mock ctypes - we want the real Windows call to happen in the subprocess layer.
- Use os.system("python main.py") - use subprocess.run([sys.executable, ...]) so the venv Python is used.
  </action>
  <verify>
    <automated>python -m pytest tests/test_main_entry.py -v</automated>
  </verify>
  <acceptance_criteria>
tests/test_main_entry.py exists
file contains literal "def test_main_py_first_line_is_import_ctypes"
file contains literal "def test_main_py_has_no_module_docstring"
file contains literal "def test_main_py_dpi_call_is_second_statement"
file contains literal "def test_main_py_does_not_import_mss_or_tkinter_at_top_level"
file contains literal "def test_main_py_has_specific_except_clauses"
file contains literal "def test_main_py_delegates_to_magnifier_bubble_app_main"
file contains literal "def test_main_py_runs_and_exits_zero"
file contains literal "def test_main_py_dpi_line_contains_physical_dimensions"
file uses ast.parse to inspect main.py (not runtime import)
file uses subprocess.run with [sys.executable, str(MAIN_PY)] (not os.system)
file uses pytest.mark.skipif(sys.platform != "win32", ...) on the two subprocess tests
python -m pytest tests/test_main_entry.py -v exits 0
On Windows: reports 9 passed, 0 skipped
On non-Windows: reports 7 passed, 2 skipped (the two subprocess tests skip)
  </acceptance_criteria>
  <done>
tests/test_main_entry.py passes. The static lint tests run on any platform (so CI without Windows runners still catches ordering regressions). The subprocess tests run on Windows and prove python main.py exits 0 with the three expected log lines. A future Phase 3 task that accidentally adds `import mss` to main.py will immediately fail test_main_py_does_not_import_mss_or_tkinter_at_top_level.
  </done>
</task>

</tasks>

<verification>
After all three tasks, run the full Phase 1 suite:

1. `python -m pytest tests/ -v`
   Expected: All tests from plans 02 and 03 pass.
   - tests/test_state.py: at least 16 passed
   - tests/test_dpi.py: 8 passed (Windows) or 2 passed + 6 skipped (non-Windows)
   - tests/test_main_entry.py: 9 passed (Windows) or 7 passed + 2 skipped (non-Windows)

2. `python main.py` (Windows only)
   Expected exit code: 0
   Expected stdout (three lines):
     [dpi] pmv2=True dpi=N scale=N% logical=WxH physical=WxH
     [state] snapshot after set_position(300,400): x=300 y=400 w=400 h=400 zoom=2.0 shape=circle visible=True always_on_top=True
     [app] phase 1 scaffold OK; exiting

3. Line-1 hard check: `head -n 1 main.py`
   Expected: exactly `import ctypes` (no trailing whitespace, no BOM).

4. Full phase suite alias (matches VALIDATION.md sampling contract):
   `python -m pytest tests/ -x -q`
   Expected: exit 0 in under 5 seconds.

5. Fresh-venv install + smoke (simulates clinic deployment):
   python -m venv /tmp/fresh
   /tmp/fresh/Scripts/pip install -r requirements.txt
   /tmp/fresh/Scripts/python main.py
   Expected: exit 0, three log lines. Proves requirements.txt is complete and main.py does not depend on dev-only deps.
</verification>

<success_criteria>
- `python main.py` exits with code 0 on Windows 11 (ROADMAP Success Criterion 1)
- main.py line 1 is `import ctypes` and line 2 starts the DPI try/except (ROADMAP Success Criterion 2; OVER-05)
- requirements.txt (plan 01) + main.py (this plan) survive the fresh-venv install smoke (ROADMAP Success Criterion 3)
- AppState is constructed and round-trips set_position -> snapshot in `python main.py` stdout (ROADMAP Success Criterion 4)
- python main.py prints a [dpi] line with logical + physical + dpi + scale fields (ROADMAP Success Criterion 5, automated portion; the manual 150%-display verification is tracked in VALIDATION.md as manual-only)
- python -m pytest tests/ -v is green across all three plans of Phase 1 (at least 33 tests passing on Windows, at least 25 passing + 8 skipped on non-Windows)
- test_main_entry.py statically pins OVER-05 so future phases cannot silently break DPI ordering
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundation-dpi/01-03-SUMMARY.md` summarizing:
- Final `python main.py` stdout from a Windows 11 run (the three log lines, verbatim)
- `python -m pytest tests/ -v` summary line (e.g., "33 passed in 1.24s")
- Confirmation that the fresh-venv install smoke succeeded
- Any deviations from the research code examples and why
- Confirmation of the phase-wide ROADMAP success criteria 1-5 status (each marked as passing or pending)
- Outstanding manual verification: criterion 5 on a real 150%-scaled display (flagged as post-plan human task per VALIDATION.md Manual-Only Verifications table)
</output>
