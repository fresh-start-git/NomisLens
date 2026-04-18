---
phase: 09-build-and-package
plan: 01
subsystem: infra
tags: [pyinstaller, build, readme, gitignore, packaging]

# Dependency graph
requires:
  - phase: 08-system-tray
    provides: pystray._win32 hiddenimport already in spec; full Phase 1-8 codebase complete

provides:
  - tests/test_build.py: 8 structural lint tests for spec/build.bat/README (BULD-02/03/05)
  - naomi_zoom.spec: PIL._tkinter_finder and win32timezone hiddenimports added (BULD-02)
  - build.bat: venv-aware one-click build script for clinic IT (BULD-03)
  - README.md: plain-English setup guide with 7 required sections (BULD-05)
  - .gitignore: zoom_log.txt, .claude/, .remember/, theme.json entries added

affects: [09-02-human-verify, future-packaging, clinic-deploy]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Structural lint pattern (file-read / string-scan) applied to build artifacts"
    - "Wave 0 RED scaffold created before GREEN implementation (TDD for build artifacts)"

key-files:
  created:
    - tests/test_build.py
    - build.bat
    - README.md
  modified:
    - naomi_zoom.spec
    - .gitignore

key-decisions:
  - "build.bat uses 'python -m PyInstaller' not bare 'pyinstaller' to avoid PATH issues with the project venv"
  - "README tone: plain English for clinic staff ('Double-click NomisLens.exe'), not technical"
  - "test_gitignore checks .claude/ and .remember/ (agent scaffolding) to prevent accidental GitHub push of internal tooling"

patterns-established:
  - "Structural lint pattern for non-Python artifacts (read file, assert string presence) — same CI-safe approach as AST-walk lints in prior phases"

requirements-completed: [BULD-01, BULD-02, BULD-03, BULD-05]

# Metrics
duration: 8min
completed: 2026-04-18
---

# Phase 9 Plan 01: Build Artifacts Summary

**PyInstaller spec hardened with PIL._tkinter_finder + win32timezone, build.bat created, plain-English README written, .gitignore extended — 8 structural lint tests all GREEN, 302 passed (net +8, zero regressions)**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-04-18T13:12:27Z
- **Completed:** 2026-04-18T13:15:33Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Created tests/test_build.py with 8 structural lint tests covering BULD-02 (spec hiddenimports + upx=False), BULD-03 (build.bat content), and BULD-05 (README sections) — all pass GREEN
- Added `PIL._tkinter_finder` and `win32timezone` to naomi_zoom.spec hiddenimports (prevents ImageTk crash and pywin32 ImportError on EXE launch)
- Created build.bat with venv activation, errorlevel guards, and pause-on-completion for clinic IT
- Wrote README.md with all 7 required sections in plain-English tone for non-technical clinic staff
- Hardened .gitignore: added zoom_log.txt, .claude/, .remember/, theme.json

## Task Commits

Each task was committed atomically:

1. **Task 1: Create tests/test_build.py with structural lint tests** - `0afc9b8` (test)
2. **Task 2: Fix naomi_zoom.spec hiddenimports and create build.bat** - `c127147` (feat)
3. **Task 3: Write README.md and harden .gitignore** - `4364183` (feat)

## Files Created/Modified

- `tests/test_build.py` - 8 structural lint tests for Phase 9 build artifacts
- `naomi_zoom.spec` - Added PIL._tkinter_finder and win32timezone to hiddenimports
- `build.bat` - Venv-aware build script for clinic IT
- `README.md` - Plain-English setup guide for clinic staff
- `.gitignore` - Added debug log, agent scaffolding, and theme state exclusions

## Decisions Made

- `build.bat` uses `python -m PyInstaller` (not bare `pyinstaller`) to avoid PATH ambiguity when venv is active — consistent with research recommendation
- README tone is "Double-click NomisLens.exe on your desktop" — not CLI jargon — suitable for non-technical clinic staff
- `test_gitignore_excludes_debug_artifacts` checks `.claude/` and `.remember/` to prevent internal agent tooling from being pushed to the public GitHub repo

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All automated artifacts for BULD-01/02/03/05 are complete
- 09-02-PLAN.md (human verification) can proceed: run build.bat, smoke-test dist/NomisLens.exe, push to GitHub (BULD-04/06)
- Pre-existing concern: clinic AV product unknown; budget time for allowlisting on target PC

---
*Phase: 09-build-and-package*
*Completed: 2026-04-18*

## Self-Check: PASSED

- tests/test_build.py: FOUND
- naomi_zoom.spec: FOUND
- build.bat: FOUND
- README.md: FOUND
- .gitignore: FOUND
- 09-01-SUMMARY.md: FOUND
- Commit 0afc9b8 (Task 1): FOUND
- Commit c127147 (Task 2): FOUND
- Commit 4364183 (Task 3): FOUND
