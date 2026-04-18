---
phase: 08-system-tray
plan: 01
subsystem: ui
tags: [pystray, PIL, threading, tray-icon, tkinter]

# Dependency graph
requires:
  - phase: 06-global-hotkey
    provides: HotkeyManager non-daemon thread pattern (start/stop/attach duck-typed)
  - phase: 01-foundation-dpi
    provides: AppState.StateSnapshot with always_on_top field

provides:
  - TrayManager class with non-daemon thread lifecycle
  - create_tray_image() function (64x64 RGBA teal magnifier, no external assets)
  - tests/test_tray.py: 9 structural lints (cross-platform)
  - tests/test_tray_smoke.py: 2 Windows-only integration tests

affects:
  - 08-02 (Plan 02 wires TrayManager into window.py destroy() and app.py main())

# Tech tracking
tech-stack:
  added: []  # pystray 0.19.5 already pinned; PIL already pinned
  patterns:
    - "Non-daemon thread for icon.run() matching HotkeyManager pattern"
    - "All pystray callbacks marshal via self._root.after(0, callable)"
    - "Deferred pystray import: app.py import inside if sys.platform == 'win32' block"
    - "Programmatic PIL icon avoids PyInstaller datas entries"

key-files:
  created:
    - src/magnifier_bubble/tray.py
    - tests/test_tray.py
    - tests/test_tray_smoke.py
  modified: []

key-decisions:
  - "daemon=False on TrayManager thread: guarantees icon.stop() finalizer runs on interpreter exit, preventing orphaned tray icons (Pitfall T-6)"
  - "Docstrings must not contain literal forbidden patterns: module docstring 'root.destroy()' tripped the callbacks-use-root-after lint — rewrote to avoid naming banned APIs literally (same class of bug as Phase 2-02 LOWORD/HIWORD, Phase 4-03 SendMessageW/PyDLL, Phase 5 threading.Timer)"
  - "test_tray_stop_before_destroy_ordering intentionally deferred: tests window.py wiring which is Plan 02's responsibility; this is Wave 0 scaffolding"
  - "Tooltip text: 'NomisLens — Ctrl+Alt+Z to toggle' surfaces hotkey to clinic users (Research open question 3 resolved)"

patterns-established:
  - "Pattern T-1: TrayManager mirrors HotkeyManager exactly — start()/stop()/attach_tray_manager duck-typed"
  - "Pattern T-2: All pystray callback bodies are exactly self._root.after(0, callable) — no direct Tk API calls"
  - "Pattern T-3: Programmatic PIL icon (create_tray_image) avoids external .ico asset and PyInstaller datas entry"

requirements-completed: [TRAY-01, TRAY-02, TRAY-03, TRAY-04, TRAY-05]

# Metrics
duration: 5min
completed: 2026-04-18
---

# Phase 8 Plan 01: System Tray Summary

**pystray TrayManager with non-daemon thread, teal PIL magnifier icon, and marshaled callbacks via root.after(0,...) — 8/9 structural lints green, both smoke tests pass on Windows**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-18T03:12:35Z
- **Completed:** 2026-04-18T03:17:45Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `create_tray_image()`: 64x64 RGBA PIL teal magnifier icon drawn in memory — no external .ico asset required, no PyInstaller datas entry needed
- `TrayManager`: non-daemon thread calling `icon.run()`, `stop()` signals `icon.stop()` + joins within 1s — mirrors HotkeyManager pattern exactly
- Menu: Show / Hide (default=True for left-click), Always on Top (dynamic `checked=lambda` reading AppState.snapshot()), separator, Exit
- All 3 callbacks marshal to Tk main thread via `self._root.after(0, callable)` — Pitfall T-1/T-2 prevented
- 9 structural lints in `test_tray.py` (cross-platform) + 2 Windows smoke tests in `test_tray_smoke.py`
- Full suite: 293 passed, 1 expected deferred failure (window.py ordering — Plan 02)

## Task Commits

Each task was committed atomically:

1. **Task 1: Wave 0 — Write test stubs for tray module** - `1683dad` (test)
2. **Task 2: Implement src/magnifier_bubble/tray.py** - `517702b` (feat)

## Files Created/Modified

- `src/magnifier_bubble/tray.py` — TrayManager class + create_tray_image() function (154 lines)
- `tests/test_tray.py` — 9 structural lints, cross-platform (97 lines)
- `tests/test_tray_smoke.py` — 2 Windows-only smoke tests (56 lines)

## Decisions Made

- `daemon=False` on TrayManager thread guarantees icon.stop() finalizer runs on interpreter exit, preventing orphaned ghost tray icons (Pitfall T-6 mitigation)
- Tooltip set to "NomisLens — Ctrl+Alt+Z to toggle" to surface the hotkey to Naomi and clinic staff (Research open question 3 resolved in favor of descriptive text)
- `test_tray_stop_before_destroy_ordering` intentionally fails in Plan 01 — it is Wave 0 scaffolding that tests Plan 02's window.py wiring. Not a regression.
- Deferred import pattern maintained: `from magnifier_bubble.tray import TrayManager` will live inside `if sys.platform == "win32":` in app.py (Plan 02)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Module docstring contained literal 'root.destroy()' string**

- **Found during:** Task 2 (implement tray.py)
- **Issue:** The module docstring described what NOT to do using the exact string `root.destroy()`. The structural lint `test_tray_callbacks_use_root_after` asserts `"root.destroy()" not in src` — which would trip on docstring text even though tray.py was correctly implemented.
- **Fix:** Rewrote the docstring line from "Never call root.destroy() from pystray thread" to "Never call Tk teardown methods from pystray thread" — describes the forbidden behavior without naming it literally.
- **Files modified:** `src/magnifier_bubble/tray.py`
- **Verification:** `test_tray_callbacks_use_root_after` now passes.
- **Committed in:** `517702b` (Task 2 commit — fixed before commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug in docstring content tripping structural lint)

**Impact on plan:** Required fix for correctness. This is the 4th occurrence of the "docstring names a banned string" class of bug (prior: Phase 2-02 LOWORD/HIWORD, Phase 4-03 SendMessageW/PyDLL, Phase 5-01 threading.Timer). Pattern now well-established — future plan authors should note that structural ban-lints apply to the entire file source including docstrings.

## Issues Encountered

None beyond the auto-fixed docstring issue above.

## Next Phase Readiness

- `src/magnifier_bubble/tray.py` is ready for wiring in Plan 02
- Plan 02 must add to `window.py`:
  - `attach_tray_manager(self, manager)` method
  - `toggle_aot_and_apply(self)` method (toggles state + applies `-topmost` to Tk)
  - `destroy()` chain: `tray_manager.stop()` between `hotkey_manager.stop()` and `capture_worker.stop()`
  - `_tray_manager = None` initialization in `__init__`
- Plan 02 must add to `app.py`:
  - `if sys.platform == "win32":` block importing TrayManager, constructing, starting, and attaching it
- `test_tray_stop_before_destroy_ordering` will go green once Plan 02 writes the wiring

## Self-Check: PASSED

- FOUND: src/magnifier_bubble/tray.py
- FOUND: tests/test_tray.py
- FOUND: tests/test_tray_smoke.py
- FOUND: .planning/phases/08-system-tray/08-01-SUMMARY.md
- FOUND commit: 1683dad (test stubs)
- FOUND commit: 517702b (tray.py implementation)

---
*Phase: 08-system-tray*
*Completed: 2026-04-18*
