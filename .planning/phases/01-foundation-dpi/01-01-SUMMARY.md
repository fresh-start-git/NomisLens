---
phase: 01-foundation-dpi
plan: 01
subsystem: infra
tags: [python, pytest, src-layout, pyinstaller, mss, pywin32, Pillow, numpy, pystray]

requires: []
provides:
  - Importable magnifier_bubble package via pytest pythonpath=["src"] src-layout
  - Pinned runtime dependencies (mss 10.1.0, pywin32 311, Pillow 11.3.0, numpy 2.2.6, pystray 0.19.5, pyinstaller 6.11.1)
  - Pytest testing infrastructure with Windows-only skip marker (win_only)
  - Clean-venv-verified install path (pip install -r requirements-dev.txt succeeds in fresh Python 3.11.9 venv)
  - Git ignore rules for .venv, build artifacts, and runtime config.json
affects: [02-plan (state.py/dpi.py go under src/magnifier_bubble/), 03-plan (app.py + main.py shim), all-later-phases (pytest + package structure)]

tech-stack:
  added:
    - mss==10.1.0 (screen capture)
    - pywin32==311 (DPI API, Win32 HWND ops)
    - Pillow==11.3.0 (resampling)
    - numpy==2.2.6 (Pillow backend)
    - pystray==0.19.5 (tray icon)
    - pyinstaller==6.11.1 (frozen .exe build; back-pinned per AV cluster)
    - pytest>=8.0 (dev-only; NOT shipped in .exe)
  patterns:
    - "src-layout with pythonpath config in pyproject.toml [tool.pytest.ini_options]"
    - "Empty __init__.py as load-bearing design (prevents mss early-init DPI lock)"
    - "Dev deps segregated from runtime deps (requirements-dev.txt uses -r requirements.txt)"
    - "Windows-only test skip via conftest.py win_only marker"

key-files:
  created:
    - requirements.txt (6 pinned runtime deps)
    - requirements-dev.txt (runtime + pytest)
    - pyproject.toml (pytest pythonpath=src, testpaths=tests)
    - .gitignore (Python, venv, build, config.json)
    - src/magnifier_bubble/__init__.py (0 bytes, intentionally empty)
    - src/magnifier_bubble/__main__.py (python -m magnifier_bubble entry)
    - tests/__init__.py (0 bytes, package marker)
    - tests/conftest.py (win_only skip marker)
  modified: []

key-decisions:
  - "Kept src/magnifier_bubble/__init__.py at exactly 0 bytes to prevent any accidental mss import that would lock DPI awareness to V1 before main.py can set V2"
  - "Excluded pytest from requirements.txt to minimize PyInstaller analysis surface and AV-scan cluster size"
  - "Back-pinned pyinstaller to 6.11.1 per STACK.md guidance (newer 6.12+ increases AV false-positive cluster)"
  - "Deferred [build-system] and [project] metadata tables to Phase 8 — Phase 1 pyproject.toml is minimal pytest config only"

patterns-established:
  - "src-layout + pytest pythonpath: tests import magnifier_bubble via pyproject.toml config, no sys.path hacks"
  - "Empty package init as explicit anti-pattern guard: load-bearing emptiness to defer mss construction"
  - "Runtime/dev dep segregation: requirements.txt is the sole input to PyInstaller; requirements-dev.txt is superset for local dev"

requirements-completed: [OVER-05]

duration: 3min
completed: 2026-04-11
---

# Phase 01 Plan 01: Project Scaffolding Summary

**Python 3.11 src-layout scaffold with pinned Windows runtime deps (mss, pywin32, Pillow, numpy, pystray, pyinstaller) verified via clean-venv install and pytest collection**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-04-11T17:17:19Z
- **Completed:** 2026-04-11T17:20:35Z
- **Tasks:** 3/3
- **Files created:** 8
- **Files modified:** 0

## Accomplishments

- Pinned all 6 runtime dependencies to exact versions matching STACK.md (mss 10.1.0, pywin32 311, Pillow 11.3.0, numpy 2.2.6, pystray 0.19.5, pyinstaller 6.11.1)
- Created src-layout package skeleton with load-bearing empty `__init__.py` (prevents mss early-init DPI lock)
- Verified `pip install -r requirements-dev.txt` succeeds in a fresh Python 3.11.9 venv with zero errors and installs all 17 transitive packages cleanly
- Confirmed pytest collects the empty test suite without ImportError (exit 5 = "no tests collected", matching plan's `done` criteria)
- Established Windows-only test skip marker (`win_only`) in `tests/conftest.py` for downstream DPI tests in plans 02/03

## Task Commits

Each task was committed atomically:

1. **Task 1: Pin dependencies (requirements.txt + requirements-dev.txt)** - `744f628` (chore)
2. **Task 2: Create pyproject.toml + .gitignore** - `1d976a4` (chore)
3. **Task 3: Create package + tests skeleton directories** - `338e644` (chore)

**Plan metadata:** _pending — final docs commit below_

## Files Created/Modified

- `requirements.txt` - 6 pinned runtime deps for clinic install (mss, pywin32, Pillow, numpy, pystray, pyinstaller)
- `requirements-dev.txt` - Inherits runtime via `-r requirements.txt`, adds `pytest>=8.0` (NOT shipped in .exe)
- `pyproject.toml` - Minimal pytest config (pythonpath=src, testpaths=tests, addopts=-ra); deferred [build-system]/[project] to Phase 8
- `.gitignore` - Python artifacts, .venv/, build/, dist/, .pytest_cache/, config.json (Phase 5 runtime state), OS/IDE noise
- `src/magnifier_bubble/__init__.py` - Exactly 0 bytes; load-bearing emptiness prevents mss early-init DPI lock
- `src/magnifier_bubble/__main__.py` - 362 bytes; `python -m magnifier_bubble` entry delegating to `magnifier_bubble.app.main` (app.py arrives in Plan 03)
- `tests/__init__.py` - Exactly 0 bytes; pytest package marker
- `tests/conftest.py` - 624 bytes; defines `win_only = pytest.mark.skipif(sys.platform != "win32", ...)` for Windows-only DPI tests

## Decisions Made

- **Followed plan as specified.** All pinned versions, file contents, and structural decisions came from 01-PLAN.md and RESEARCH.md.
- Rationale captured in plan's `<action>` blocks (empty `__init__.py`, runtime/dev segregation, pyinstaller 6.11.1 back-pin, deferred pyproject sections) was preserved verbatim without modification.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

**Pytest exit code semantics (non-issue, noted for clarity):**

The plan's `<verification>` section (step 2) says `python -m pytest --collect-only -q` should "exit 0, output includes 'no tests ran' or '0 tests collected'". In practice, pytest has returned exit code **5** ("no tests collected") since pytest 5.0 (2019) — this is the standard and correct behavior for an empty suite. The plan's `<done>` criteria for Task 3 explicitly accepts this outcome ("may report '0 tests collected' — that's fine"), so the INTENT (collection runs without ImportError) is fully satisfied. No action needed; no bug in the scaffolding. Noting here so future plan readers don't flag exit 5 as a regression.

**Clean install verification results:**

- `py -3.11 -m venv .venv` succeeded (Python 3.11.9)
- `pip install -r requirements-dev.txt` installed 17 packages (6 top-level runtime + pytest + 10 transitive) with zero errors
- No pywin32 postinstall warnings observed
- `pytest --collect-only` exit 5 ("no tests collected in 0.01s") — expected empty-suite behavior
- `python -c "import sys; sys.path.insert(0,'src'); import magnifier_bubble"` exit 0 — package importable via src-layout

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Ready for Plan 02 (state + DPI):** Plan 02 can now place `state.py` and `dpi.py` under `src/magnifier_bubble/`; tests in `tests/` will auto-import them via pytest `pythonpath = ["src"]`.
- **Ready for Plan 03 (app.py + main.py shim):** The `__main__.py` stub already imports from `magnifier_bubble.app`; Plan 03 creates the `app.py` module and the `main.py` root shim.
- **No blockers.** The Cornerstone × PMv2 DPI compatibility concern (STATE.md) is a Plan 02/Plan 03 runtime-test concern, not a scaffolding concern.
- **Clean-venv install path validated** — clinic deployment dry-run in Phase 8 can reuse the same `pip install -r requirements.txt` step with confidence.

## Self-Check: PASSED

All claimed files verified present on disk:
- `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `.gitignore`
- `src/magnifier_bubble/__init__.py` (0 bytes), `src/magnifier_bubble/__main__.py`
- `tests/__init__.py` (0 bytes), `tests/conftest.py`
- `.planning/phases/01-foundation-dpi/01-01-SUMMARY.md` (this file)

All claimed commits verified in git log:
- `744f628` (Task 1), `1d976a4` (Task 2), `338e644` (Task 3)

---
*Phase: 01-foundation-dpi*
*Plan: 01*
*Completed: 2026-04-11*
