---
phase: 07-dxgi-capture-transparent-input
plan: 03
subsystem: ui
tags: [clickthru, pyinstaller, dxcam, testing, cleanup]

# Dependency graph
requires:
  - phase: 07-02
    provides: "WS_EX_TRANSPARENT zone poll replacing click injection; window.py surgery"
provides:
  - "inject_click, inject_right_click, send_rclick_at deleted from clickthru.py"
  - "_DEBUG_LOG set to None (production mode)"
  - "naomi_zoom.spec hiddenimports extended with dxcam submodules and comtypes"
  - "test_clickthru.py updated with 4 Phase 7 deletion tests, stale Phase 4 tests removed"
affects: [08-packaging, naomi_zoom.spec, tests/test_clickthru.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Delete-confirm pattern: new tests assert hasattr(module, fn) is False to enforce deletions"
    - "Production-mode guard: _DEBUG_LOG = None at module level, verified by test"

key-files:
  created: []
  modified:
    - src/magnifier_bubble/clickthru.py
    - tests/test_clickthru.py
    - naomi_zoom.spec

key-decisions:
  - "inject_click/inject_right_click/send_rclick_at deleted — Phase 7 WS_EX_TRANSPARENT zone poll makes all three obsolete; physical input falls through naturally"
  - "_DEBUG_LOG = None enforced by test_debug_log_disabled — ensures production build never writes zoom_log.txt to user filesystem"
  - "dxcam.processor._numpy_kernels NOT added to hiddenimports — it is a .pyd binary that PyInstaller collects automatically; only pure-Python modules need explicit listing"
  - "Stale Phase 4 inject_click monkeypatch tests removed — tests that monkeypatched a now-deleted function would fail with AttributeError and obscure the real test results"

patterns-established:
  - "Deletion enforcement test: use `assert not hasattr(module, fn)` to guard against accidentally re-adding deleted API surface"

requirements-completed: [CAPT-01, CAPT-02, CAPT-03, CAPT-04, CAPT-05, CAPT-06, CTRL-01]

# Metrics
duration: 5min
completed: 2026-04-18
---

# Phase 07 Plan 03: clickthru.py Cleanup + Spec Update Summary

**inject_click/inject_right_click/send_rclick_at deleted, debug logging disabled, PyInstaller spec updated with dxcam + comtypes hiddenimports, and 4 new Phase 7 deletion tests enforce the cleanup**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-18T00:10:16Z
- **Completed:** 2026-04-18T00:15:00Z
- **Tasks:** 1 (+ checkpoint awaiting human verification)
- **Files modified:** 3

## Accomplishments
- Deleted 3 functions totaling ~284 lines from clickthru.py (inject_click, inject_right_click, send_rclick_at) — Phase 4 PostMessageW injection infrastructure no longer needed
- Disabled debug logging: `_DEBUG_LOG = None` so no zoom_log.txt is written in production
- Updated module docstring to accurately describe the Phase 7 reduced surface
- Extended naomi_zoom.spec hiddenimports with full dxcam submodule list + comtypes.client so the PyInstaller bundle will include dxcam correctly
- Replaced 13 stale Phase 4 inject_click tests with 7 cleaner tests: 3 structural lints kept + 4 new Phase 7 deletion assertion tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Trim clickthru.py, disable debug log, update spec and tests** - `3e15f83` (feat)

**Plan metadata:** (pending final commit after SUMMARY)

## Files Created/Modified
- `src/magnifier_bubble/clickthru.py` - Deleted inject_click, inject_right_click, send_rclick_at; set _DEBUG_LOG=None; updated docstring
- `tests/test_clickthru.py` - Replaced 13 stale Phase 4 tests with 7 tests (3 structural lints + 4 deletion assertions)
- `naomi_zoom.spec` - Extended hiddenimports with 27 dxcam submodules + comtypes entries

## Decisions Made
- inject_click/inject_right_click/send_rclick_at deleted — Phase 7 WS_EX_TRANSPARENT zone poll makes all three obsolete; physical input falls through naturally without any synthetic injection
- _DEBUG_LOG = None enforced by test_debug_log_disabled — ensures production build never writes zoom_log.txt to user filesystem
- dxcam.processor._numpy_kernels NOT added to hiddenimports — it is a .pyd binary that PyInstaller collects automatically; only pure-Python modules need explicit listing
- Stale Phase 4 inject_click monkeypatch tests removed — tests that monkeypatched a now-deleted function would fail with AttributeError and obscure the real test results

## Deviations from Plan

None - plan executed exactly as written. The _u32() docstring still mentions "inject_click" in a comment; this is intentional since _u32() binds argtypes that remain valid for the remaining functions (IsWindowVisible used by window.py's zone poll). The comment reference is in a docstring describing original purpose, not a function definition.

## Issues Encountered

None. Pre-existing test failures (9 failures: test_controls 2, test_main_entry 2, test_window_integration 1, test_window_phase4 3, test_wndproc_smoke 1) confirmed pre-existing via git stash verification — all present before this plan's changes. My changes net-improved the suite by eliminating 3 stale Phase 4 clickthru failures, reducing from 13 to 9 pre-existing failures.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 7 automation complete. Awaiting human verification (Task 2 checkpoint) to confirm:
  - dxcam capture working (live magnified view at ~30fps)
  - Physical click pass-through via WS_EX_TRANSPARENT working
  - Right-click context menus visible in zoom lens
  - Drag, controls, close button, and hotkey all functioning

---
*Phase: 07-dxgi-capture-transparent-input*
*Completed: 2026-04-18*
