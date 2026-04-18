---
phase: 08-system-tray
plan: 02
subsystem: ui
tags: [pystray, tkinter, system-tray, threading, pyinstaller]

# Dependency graph
requires:
  - phase: 08-system-tray/01
    provides: TrayManager class with start()/stop(), create_tray_image(), all callbacks via root.after(0,...)
  - phase: 06-global-hotkey
    provides: HotkeyManager attach/stop pattern replicated for TrayManager

provides:
  - BubbleWindow.attach_tray_manager() — duck-typed wiring method matching attach_hotkey_manager pattern
  - BubbleWindow.toggle_aot_and_apply() — toggles AppState.always_on_top AND applies -topmost to Tk root
  - BubbleWindow.destroy() tray stop slot (AFTER hotkey.stop(), BEFORE capture.stop())
  - app.py TrayManager construction block (deferred import inside if sys.platform == 'win32')
  - naomi_zoom.spec pystray._win32 hiddenimport for PyInstaller packaging
  - Manual verification checkpoint: live tray icon, menu items, left-click toggle, AoT toggle, clean exit

affects:
  - Phase 09-packaging (naomi_zoom.spec now includes pystray._win32)

# Tech tracking
tech-stack:
  added: []  # pystray 0.19.5 already pinned from Plan 01
  patterns:
    - "Pattern T-4: tray_manager.stop() slots between hotkey_manager.stop() and capture_worker.stop() — same ordering contract as hotkey"
    - "Pattern T-5: Deferred pystray import lives in app.py inside if sys.platform == 'win32' block — never at module scope in window.py"
    - "Pattern T-6: 5th occurrence of docstring-contains-banned-literal bug class — literal 'root.destroy()' in docstring/comments tripped src.find() lint"

key-files:
  created:
    - .planning/phases/08-system-tray/08-02-SUMMARY.md
  modified:
    - src/magnifier_bubble/window.py
    - src/magnifier_bubble/app.py
    - naomi_zoom.spec

key-decisions:
  - "tray_manager.stop() placed between hotkey_manager.stop() and capture_worker.stop() — same rationale as hotkey: prevents late tray callbacks from scheduling root.after on a partially-torn-down root"
  - "toggle_aot_and_apply() bridges AppState.toggle_aot() with Tk wm_attributes('-topmost',...) — _on_state_change does not handle always_on_top field (shape/size/zoom only)"
  - "Three docstring/comment lines containing literal 'root.destroy()' rewritten to avoid tripping test_tray_stop_before_destroy_ordering src.find() — 5th occurrence of this pattern"

patterns-established:
  - "Pattern T-4: Phase 8 teardown ordering: hotkey.stop() → tray.stop() → capture.stop() → wndproc.uninstall×3 → root teardown"
  - "Pattern T-5: Structural ban-lints using src.find() apply to the ENTIRE file including docstrings and inline comments — not just executable code"

requirements-completed: [TRAY-01, TRAY-02, TRAY-03, TRAY-04, TRAY-05]

# Metrics
duration: ~10min
completed: 2026-04-18
---

# Phase 8 Plan 02: TrayManager Wiring Summary

**TrayManager wired into window.py destroy() chain and app.py main() with pystray._win32 hiddenimport — 294 tests pass (all 9 test_tray.py structural lints now green); awaiting 5-step manual verification checkpoint**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-18T03:20:59Z
- **Completed:** 2026-04-18T03:30:00Z (Task 1 complete; Task 2 is human-verify checkpoint)
- **Tasks:** 1 of 2 complete (Task 2 awaits human verification)
- **Files modified:** 3

## Accomplishments

- `window.py`: `attach_tray_manager()` added — duck-typed, mirrors `attach_hotkey_manager` exactly
- `window.py`: `toggle_aot_and_apply()` added — bridges `AppState.toggle_aot()` with `root.wm_attributes("-topmost", ...)` (Pitfall T-3)
- `window.py`: `destroy()` chain extended — `tray_manager.stop()` inserted between `hotkey_manager.stop()` and `capture_worker.stop()`
- `app.py`: `TrayManager` construction block added — deferred import inside `if sys.platform == "win32"`, between hotkey wiring and `start_capture`
- `naomi_zoom.spec`: `'pystray._win32'` added to `hiddenimports` (dynamic platform import not detected by PyInstaller analysis)
- All 9 structural lints in `tests/test_tray.py` now PASS (294 total, up from 293 — zero regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire TrayManager into window.py and app.py, update spec** - `5005454` (feat)
2. **Task 2: Manual verification — 5-step Phase 8 success criteria check** - PENDING (human-verify checkpoint)

## Files Created/Modified

- `src/magnifier_bubble/window.py` — Added `_tray_manager = None` init, `attach_tray_manager()`, `toggle_aot_and_apply()`, tray stop slot in `destroy()`; rewrote 3 literal `root.destroy()` occurrences in docstrings/comments
- `src/magnifier_bubble/app.py` — Added TrayManager construction block (9 lines) between hotkey block and `start_capture`
- `naomi_zoom.spec` — Added `'pystray._win32'` to `hiddenimports` list with explanatory comment

## Decisions Made

- `tray_manager.stop()` placed between `hotkey_manager.stop()` and `capture_worker.stop()` in `destroy()` — prevents late tray callbacks from scheduling `root.after` on a partially-torn-down root (same rationale as hotkey worker)
- `toggle_aot_and_apply()` is a separate method from `toggle()` because `_on_state_change` only handles shape/size/zoom; always_on_top is not observed by the state change handler and requires explicit `wm_attributes` call
- No import of `tray.py` at `window.py` module scope — same duck-typed discipline as `attach_config_writer` and `attach_hotkey_manager`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Three docstring/comment lines contained literal 'root.destroy()' strings**

- **Found during:** Task 1 (Wire TrayManager into window.py)
- **Issue:** `test_tray_stop_before_destroy_ordering` uses `src.find('root.destroy()')` to find the FIRST occurrence in `window.py`. Three comment/docstring lines contained the literal substring before the actual `self.root.destroy()` call: (1) `_zone_transparency_poll` docstring ("before root.destroy()"), (2) destroy() comment ("BEFORE root.destroy()" for zone poll cancel), (3) destroy() comment ("BEFORE root.destroy()" for frame queue cancel). The test found position 38215 (in the docstring) while `tray_manager.stop()` was at 48402 — causing the ordering assertion to fail.
- **Fix:** Rewrote all three occurrences to describe Tk root teardown without naming `root.destroy()` literally: "before the Tk root teardown", "BEFORE Tk root teardown" (×2).
- **Files modified:** `src/magnifier_bubble/window.py`
- **Verification:** `src.find('root.destroy()')` now returns 49822 (actual `self.root.destroy()` call in `finally` block), while `tray_manager.stop()` is at 48471 — ordering assertion passes.
- **Committed in:** `5005454` (fixed before commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — 5th occurrence of "docstring/comment contains banned literal" class of bug; prior: Phase 2-02 LOWORD/HIWORD, Phase 4-03 SendMessageW/PyDLL, Phase 5-01 threading.Timer, Phase 8-01 root.destroy() in module docstring)

**Impact on plan:** Required fix for test correctness. No scope creep. Pattern is now well-documented — future plan authors should note that `src.find()`-based ordering lints apply to entire file source including docstrings and inline comments.

## Issues Encountered

None beyond the auto-fixed docstring issue above.

## Checkpoint: Task 2 — Manual Verification

**Status:** PENDING — awaiting human verification

Task 2 requires running the live app and performing 5 verification checks:
1. CHECK 1 — Tray icon appears (TRAY-01): teal magnifier icon in notification area within 1 second
2. CHECK 2 — Right-click menu contents (TRAY-02): Show/Hide + Always on Top (checked) + separator + Exit
3. CHECK 3 — Left-click toggles visibility (TRAY-03): two left-clicks produce visible→hidden→visible
4. CHECK 4 — Always on Top toggle + behavior (TRAY-02 + TRAY-04): checkmark toggles AND window layering changes
5. CHECK 5 — Clean exit via tray (TRAY-05): process exits within 2 seconds, icon disappears

**Launch command:**
```
cd "C:\Users\Jsupport\OneDrive - Ackley Athletics LLC\JB\Naomi Zoom"
.venv\Scripts\python.exe main.py
```

## Next Phase Readiness

After Task 2 (human-verify) approval:
- Phase 8 (system tray) is complete — all TRAY-01 through TRAY-05 requirements met
- Phase 9 (packaging) can begin — naomi_zoom.spec already has `pystray._win32` hiddenimport

## Self-Check: PASSED

- FOUND: src/magnifier_bubble/window.py (modified — attach_tray_manager, toggle_aot_and_apply, destroy() tray slot)
- FOUND: src/magnifier_bubble/app.py (modified — TrayManager block)
- FOUND: naomi_zoom.spec (modified — pystray._win32 hiddenimport)
- FOUND commit: 5005454 (feat(08-02): wire TrayManager into window.py, app.py, and spec)
- TEST: 9/9 test_tray.py structural lints PASS
- TEST: 294/294 full suite PASS (zero regressions)

---
*Phase: 08-system-tray*
*Completed: 2026-04-18 (Task 1 of 2)*
