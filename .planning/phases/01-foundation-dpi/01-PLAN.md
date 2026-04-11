---
phase: 01-foundation-dpi
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - requirements.txt
  - requirements-dev.txt
  - pyproject.toml
  - .gitignore
  - src/magnifier_bubble/__init__.py
  - src/magnifier_bubble/__main__.py
  - tests/__init__.py
  - tests/conftest.py
autonomous: true
requirements: [OVER-05]
must_haves:
  truths:
    - "pip install -r requirements.txt succeeds in a fresh Python 3.11 venv with zero errors"
    - "pip install -r requirements-dev.txt installs pytest so tests/ can be executed"
    - "python -c 'import magnifier_bubble' works from repo root (src-layout pythonpath is resolved)"
    - "pytest discovers the empty tests/ package without import errors"
  artifacts:
    - path: requirements.txt
      provides: "Pinned runtime + build dependencies for clinic install"
      contains: "mss==10.1.0"
    - path: requirements-dev.txt
      provides: "Developer-only dependencies (pytest); NOT bundled by PyInstaller"
      contains: "pytest"
    - path: pyproject.toml
      provides: "pytest pythonpath config so tests can import magnifier_bubble from src/"
      contains: "pythonpath"
    - path: .gitignore
      provides: "Excludes .venv/, __pycache__, dist/, build/, config.json"
      contains: ".venv"
    - path: src/magnifier_bubble/__init__.py
      provides: "Package marker; MUST remain empty (no imports) so mss cannot accidentally run before main.py DPI call"
      min_lines: 0
    - path: src/magnifier_bubble/__main__.py
      provides: "Enables python -m magnifier_bubble alternate entry (delegates to app.main)"
      contains: "from magnifier_bubble.app import main"
    - path: tests/__init__.py
      provides: "Makes tests a package"
      min_lines: 0
    - path: tests/conftest.py
      provides: "Shared pytest fixtures and platform skip markers"
      contains: "pytest"
  key_links:
    - from: pyproject.toml
      to: src/magnifier_bubble
      via: "[tool.pytest.ini_options] pythonpath = ['src']"
      pattern: "pythonpath\\s*=\\s*\\[\"src\"\\]"
    - from: requirements.txt
      to: pyproject.toml
      via: "mss / pywin32 / Pillow / numpy / pystray / pyinstaller are all pinned and match stack decisions"
      pattern: "pyinstaller==6\\.11\\.1"
---

<objective>
Scaffold the Ultimate Zoom repository so that subsequent plans in this phase have an importable `magnifier_bubble` package, a runnable pytest setup, and a clean-venv-verified `requirements.txt`. Zero production code runs yet — this plan is pure infrastructure.

Purpose: Every downstream plan (this phase and later) requires a working package layout. Getting this wrong cascades: PyInstaller breaks (Phase 8), pytest cannot import modules (every phase), `mss` accidentally imports before DPI is set (every phase, silently corrupts capture coordinates).

Output: A repo where `pip install -r requirements.txt && pip install -r requirements-dev.txt && python -m pytest tests/ -v` succeeds (with zero tests collected — tests come in plans 02 and 03).
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
<!-- This plan creates the package skeleton; no prior interfaces exist. -->
<!-- Downstream plans (02, 03) will import from: -->
<!--   - magnifier_bubble.state    (AppState, StateSnapshot)    — created in plan 02 -->
<!--   - magnifier_bubble.dpi      (report, debug_print, ...)    — created in plan 02 -->
<!--   - magnifier_bubble.app      (main)                        — created in plan 03 -->

<!-- CRITICAL: src/magnifier_bubble/__init__.py MUST stay empty. -->
<!-- RESEARCH Pitfall: if __init__.py imports mss (even transitively), -->
<!-- mss.mss() runs SetProcessDpiAwareness(2) on first construction and -->
<!-- permanently locks the process to PMv1. main.py will then fail silently. -->
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Pin dependencies (requirements.txt + requirements-dev.txt)</name>
  <files>requirements.txt, requirements-dev.txt</files>
  <read_first>
    - .planning/phases/01-foundation-dpi/01-RESEARCH.md (sections: Standard Stack > Core, Supporting, Installation, Version Verification; Code Examples > requirements.txt)
    - .planning/research/STACK.md
    - .planning/REQUIREMENTS.md (BULD-01)
  </read_first>
  <action>
    Create `requirements.txt` at repo root with EXACTLY these pinned versions (one per line, no unpinned deps, no comments other than the header):

```
# Ultimate Zoom — pinned runtime + build deps for Python 3.11.9 on Windows 11
# Installed by: pip install -r requirements.txt
mss==10.1.0
pywin32==311
Pillow==11.3.0
numpy==2.2.6
pystray==0.19.5
pyinstaller==6.11.1
```

Then create `requirements-dev.txt` at repo root containing ONLY developer-only dependencies that MUST NOT be bundled by PyInstaller into the clinic .exe:

```
# Ultimate Zoom — developer-only deps (not shipped in the .exe)
# Installed by: pip install -r requirements-dev.txt
-r requirements.txt
pytest>=8.0
```

Rationale (do not include in file, just understand): pytest is intentionally NOT in `requirements.txt` because every extra dep bloats PyInstaller analysis and AV-scan surface. The `-r requirements.txt` line in requirements-dev.txt means "dev install is a superset of runtime install."

Do NOT add hashing, comments about specific pitfalls, or extra packages. Do NOT use `pip freeze` output — hand-pin only the six top-level deps above. Do NOT bump `pyinstaller` past 6.11.1 (deliberate back-pin per STACK.md AV-cluster rationale).
  </action>
  <verify>
    <automated>test -f requirements.txt &amp;&amp; test -f requirements-dev.txt &amp;&amp; grep -q "^mss==10.1.0$" requirements.txt &amp;&amp; grep -q "^pywin32==311$" requirements.txt &amp;&amp; grep -q "^Pillow==11.3.0$" requirements.txt &amp;&amp; grep -q "^numpy==2.2.6$" requirements.txt &amp;&amp; grep -q "^pystray==0.19.5$" requirements.txt &amp;&amp; grep -q "^pyinstaller==6.11.1$" requirements.txt &amp;&amp; grep -q "^-r requirements.txt$" requirements-dev.txt &amp;&amp; grep -q "^pytest" requirements-dev.txt</automated>
  </verify>
  <acceptance_criteria>
    - `requirements.txt` exists at repo root
    - `requirements.txt` contains literal line `mss==10.1.0`
    - `requirements.txt` contains literal line `pywin32==311`
    - `requirements.txt` contains literal line `Pillow==11.3.0`
    - `requirements.txt` contains literal line `numpy==2.2.6`
    - `requirements.txt` contains literal line `pystray==0.19.5`
    - `requirements.txt` contains literal line `pyinstaller==6.11.1`
    - `requirements.txt` has exactly 6 pinned package lines (`grep -cE '^[a-zA-Z0-9]' requirements.txt | grep -v '^#'` returns 6 non-comment lines)
    - `requirements-dev.txt` exists at repo root
    - `requirements-dev.txt` contains literal line `-r requirements.txt`
    - `requirements-dev.txt` contains a line starting with `pytest` (with version spec `>=8.0` or tighter)
    - `requirements-dev.txt` does NOT contain `mypy`, `black`, `ruff`, `coverage`, or other dev tools (keep minimal)
    - Neither file contains the `keyboard` library (archived Feb 2026 per STATE.md)
  </acceptance_criteria>
  <done>
    Both files exist with exactly the specified pinned deps. A reviewer reading the files can see which versions are runtime vs dev, and the clinic install path (`pip install -r requirements.txt`) does NOT pull in pytest.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Create pyproject.toml + .gitignore</name>
  <files>pyproject.toml, .gitignore</files>
  <read_first>
    - .planning/phases/01-foundation-dpi/01-RESEARCH.md (sections: Validation Architecture > Test Framework; Architecture Patterns > Recommended Project Structure; Pitfalls > Pitfall 5 main.py import path confusion)
    - requirements.txt (just created in Task 1 — must exist)
    - requirements-dev.txt (just created in Task 1 — must exist)
  </read_first>
  <action>
    Create `pyproject.toml` at repo root with EXACTLY this content (minimal — no build-system, no project metadata yet; Phase 8 may add more):

```toml
# Ultimate Zoom — minimal pyproject.toml for Phase 1.
# Purpose: make pytest importable against the src-layout package.
# Phase 8 will extend this with a full [project] table for pip install -e .

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
addopts = "-ra"
```

Then create `.gitignore` at repo root with EXACTLY this content:

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.pytest_cache/

# Virtual environments
.venv/
venv/
env/

# PyInstaller (Phase 8)
build/
dist/
*.spec.bak

# Runtime state (Phase 5)
config.json

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp
```

Do NOT add a `[build-system]` table. Do NOT add a `[project]` table with name/version (Phase 8 concern). Do NOT add a MANIFEST.in or setup.py. Do NOT add `ruff`/`black`/`mypy` config sections.

Note: `config.json` MUST be in `.gitignore` because Phase 5 will write user state there and it contains per-machine coordinates that must never be committed.
  </action>
  <verify>
    <automated>test -f pyproject.toml &amp;&amp; test -f .gitignore &amp;&amp; grep -q 'pythonpath = \["src"\]' pyproject.toml &amp;&amp; grep -q 'testpaths = \["tests"\]' pyproject.toml &amp;&amp; grep -q '^\.venv/$' .gitignore &amp;&amp; grep -q '^__pycache__/$' .gitignore &amp;&amp; grep -q '^config\.json$' .gitignore &amp;&amp; grep -q '^dist/$' .gitignore &amp;&amp; grep -q '^build/$' .gitignore</automated>
  </verify>
  <acceptance_criteria>
    - `pyproject.toml` exists at repo root
    - `pyproject.toml` contains literal `[tool.pytest.ini_options]`
    - `pyproject.toml` contains literal `pythonpath = ["src"]`
    - `pyproject.toml` contains literal `testpaths = ["tests"]`
    - `pyproject.toml` does NOT contain `[build-system]` (defer to Phase 8)
    - `pyproject.toml` does NOT contain `[project]` with `name = "magnifier_bubble"` (defer to Phase 8)
    - `.gitignore` exists at repo root
    - `.gitignore` contains literal line `.venv/`
    - `.gitignore` contains literal line `__pycache__/`
    - `.gitignore` contains literal line `config.json`
    - `.gitignore` contains literal line `dist/`
    - `.gitignore` contains literal line `build/`
    - `.gitignore` contains literal line `.pytest_cache/`
  </acceptance_criteria>
  <done>
    Running `python -m pytest --collect-only` from repo root (in a venv where `pip install -r requirements-dev.txt` succeeded) should find 0 tests but NOT error (the tests/ package may not exist yet in filesystem terms; that's fine — next task creates it).
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Create package + tests skeleton directories</name>
  <files>src/magnifier_bubble/__init__.py, src/magnifier_bubble/__main__.py, tests/__init__.py, tests/conftest.py</files>
  <read_first>
    - .planning/phases/01-foundation-dpi/01-RESEARCH.md (sections: Architecture Patterns > Recommended Project Structure; Anti-Patterns to Avoid > "Creating a global mss.mss() at module scope"; Code Examples > __main__.py)
    - pyproject.toml (from Task 2 — confirms pythonpath = ["src"])
  </read_first>
  <action>
    Create the following four files. All parent directories (`src/`, `src/magnifier_bubble/`, `tests/`) must be created as well.

1. `src/magnifier_bubble/__init__.py` — MUST be completely empty (0 bytes, no docstring, no imports). This is load-bearing: any import here (especially `mss`) will run `mss.mss()` init and permanently lock the process to DPI V1 before main.py can set V2. File must be empty.

2. `src/magnifier_bubble/__main__.py` — EXACTLY this content:

```python
# Alternate entry: python -m magnifier_bubble
# NOTE: This entry does NOT set DPI awareness itself. Prefer `python main.py`
# (the root shim) which sets PMv2 before any magnifier_bubble import.
# This file exists so `python -m magnifier_bubble` still works after a
# `pip install -e .` in Phase 8.
from magnifier_bubble.app import main

raise SystemExit(main())
```

3. `tests/__init__.py` — MUST be completely empty (0 bytes). Marks tests/ as a package for pytest discovery.

4. `tests/conftest.py` — EXACTLY this content:

```python
"""Shared pytest fixtures and platform markers for Ultimate Zoom tests.

Phase 1 adds the win32-only skip marker used by tests/test_dpi.py.
Later phases will add mocks for AppState, fake mss grabs, and HWND stubs.
"""
from __future__ import annotations

import sys

import pytest

# Platform skip marker: DPI APIs only exist on Windows.
# Usage in a test module:
#     pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
# or on a single test:
#     @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
win_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
```

Do NOT add any other fixtures in conftest.py for Phase 1 — each later phase adds its own when needed.
Do NOT import `magnifier_bubble` from conftest.py (AppState/dpi don't exist yet; that's plan 02's job).
The `magnifier_bubble.app` import inside `__main__.py` WILL fail at runtime until plan 03 creates `app.py` — that is acceptable because nothing runs `__main__.py` in this plan; the file merely exists.
  </action>
  <verify>
    <automated>test -f src/magnifier_bubble/__init__.py &amp;&amp; test ! -s src/magnifier_bubble/__init__.py &amp;&amp; test -f src/magnifier_bubble/__main__.py &amp;&amp; grep -q "from magnifier_bubble.app import main" src/magnifier_bubble/__main__.py &amp;&amp; grep -q "raise SystemExit(main())" src/magnifier_bubble/__main__.py &amp;&amp; test -f tests/__init__.py &amp;&amp; test ! -s tests/__init__.py &amp;&amp; test -f tests/conftest.py &amp;&amp; grep -q "win_only" tests/conftest.py &amp;&amp; grep -q 'skipif.sys.platform != "win32"' tests/conftest.py</automated>
  </verify>
  <acceptance_criteria>
    - `src/magnifier_bubble/__init__.py` exists AND is 0 bytes (`wc -c src/magnifier_bubble/__init__.py` reports `0`)
    - `src/magnifier_bubble/__init__.py` does NOT contain `import mss` (grep returns 0 matches)
    - `src/magnifier_bubble/__init__.py` does NOT contain `import` (grep returns 0 matches)
    - `src/magnifier_bubble/__main__.py` exists
    - `src/magnifier_bubble/__main__.py` contains literal `from magnifier_bubble.app import main`
    - `src/magnifier_bubble/__main__.py` contains literal `raise SystemExit(main())`
    - `tests/__init__.py` exists AND is 0 bytes
    - `tests/conftest.py` exists
    - `tests/conftest.py` defines `win_only` marker
    - `tests/conftest.py` references `sys.platform != "win32"`
    - `tests/conftest.py` does NOT import `magnifier_bubble` (the subpackages don't exist yet)
    - `python -m pytest --collect-only -q` exits 0 (may report "0 tests collected" — that's fine)
  </acceptance_criteria>
  <done>
    Running `python -m pytest --collect-only -q` from repo root (in a venv with requirements-dev.txt installed) returns exit code 0. The `magnifier_bubble` package is importable via the src-layout: `python -c "import sys; sys.path.insert(0,'src'); import magnifier_bubble"` succeeds with no output.
  </done>
</task>

</tasks>

<verification>
After all three tasks, run these checks from a clean Python 3.11 venv at repo root:

1. Install: `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt`
   Expected: exit 0, both runtime and dev deps installed.

2. Package importable via pytest pythonpath: `.venv/Scripts/python -m pytest --collect-only -q`
   Expected: exit 0, output includes "no tests ran" or "0 tests collected".

3. Empty __init__.py check: `wc -c src/magnifier_bubble/__init__.py`
   Expected: `0 src/magnifier_bubble/__init__.py` (zero bytes).

4. No stray imports in __init__.py: `grep -c "import" src/magnifier_bubble/__init__.py`
   Expected: `0`.

5. No stray Python files in repo root except the eventual main.py (which this plan does not create): `ls *.py 2>/dev/null | wc -l`
   Expected: `0`.
</verification>

<success_criteria>
- Clean venv installs `requirements-dev.txt` with zero errors
- `python -m pytest --collect-only` exits 0 from repo root
- `src/magnifier_bubble/__init__.py` is exactly 0 bytes
- `.gitignore` excludes `.venv/`, `__pycache__`, `dist/`, `build/`, `config.json`
- No production logic exists anywhere — this plan is pure scaffolding
- Downstream plan 02 can now place `state.py` and `dpi.py` under `src/magnifier_bubble/` and have tests in `tests/` import them via the pytest `pythonpath = ["src"]` setting
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundation-dpi/01-01-SUMMARY.md` summarizing:
- Files created (with byte counts for the empty markers)
- `pip install -r requirements-dev.txt` outcome in clean venv
- Any deviations from pinned versions (there should be none)
- Any platform-specific notes (e.g., pywin32 postinstall warnings)
</output>
