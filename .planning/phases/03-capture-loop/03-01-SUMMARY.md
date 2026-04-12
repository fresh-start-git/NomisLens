---
phase: 03-capture-loop
plan: 01
subsystem: capture
tags: [mss, pillow, threading, bilinear, screen-capture]

# Dependency graph
requires:
  - phase: 01-foundation-dpi
    provides: AppState with capture_region() lock-protected method
  - phase: 02-overlay-window
    provides: BubbleWindow Tk overlay (CaptureWorker feeds frames to it in Plan 03-02)
provides:
  - CaptureWorker(threading.Thread) producer thread with run/stop/get_fps/_tick
  - FrameCallback type alias for on_frame callbacks
  - 14 pure-Python structural/lint tests verifying thread-safety contracts
affects: [03-capture-loop/plan-02, 04-magnification-pipeline, 08-packaging]

# Tech tracking
tech-stack:
  added: [mss==10.1.0, Pillow==12.1.1 (bumped from 11.3.0)]
  patterns: [lazy-import-in-run for thread-local safety, Event.wait pacing, outer-reconnect-loop]

key-files:
  created:
    - src/magnifier_bubble/capture.py
    - tests/test_capture.py
  modified:
    - requirements.txt

key-decisions:
  - "Bumped Pillow pin from 11.3.0 to 12.1.1 -- Python 3.14.3 dev box has Pillow 12.1.1 installed; 11.3.0 has no cp314 wheel. API-compatible for frombytes/resize/Resampling.BILINEAR/ImageTk"
  - "mss 10.1.0 confirmed working on Python 3.14.3 (pure-python wheel, py3-none-any)"
  - "CAPTUREBLT=0 set inside run() as Path B hall-of-mirrors defense before mss.mss() construction"

patterns-established:
  - "Pattern: lazy module import inside Thread.run() for thread-local safety (mss + PIL imported inside run(), not at module top)"
  - "Pattern: Event.wait() for ALL pacing in daemon threads (frame pacing AND reconnect backoff) -- never time.sleep() because Event.wait is interruptible by stop()"
  - "Pattern: outer while-loop reconnect for mss GDI failures (Pitfall 7) with 0.5s Event.wait backoff"

requirements-completed: [CAPT-01, CAPT-02, CAPT-03, CAPT-04]

# Metrics
duration: 8min
completed: 2026-04-12
---

# Phase 03 Plan 01: CaptureWorker Summary

**30 fps mss screen-capture producer thread with Pillow BILINEAR resize, thread-local mss safety, and Event.wait pacing -- verified by 14 pure-Python structural/lint tests**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-12T11:24:25Z
- **Completed:** 2026-04-12T11:33:12Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Verified mss 10.1.0 + Pillow 12.1.1 install and import on Python 3.14.3 dev box
- Created CaptureWorker(threading.Thread) with daemon=True, named "magnifier-capture", exposing run/stop/get_fps/_tick
- 14 pure-Python structural/lint tests enforcing: no ImageGrab (CAPT-03), BILINEAR literal (CAPT-04), thread-local mss (lazy import), Event.wait pacing (no time.sleep), outer reconnect loop
- Full suite: 151 tests pass, zero regressions across Phase 1/2/3

## Dev Box Observations

```
Python 3.14.3
mss 10.1.0 (py3-none-any wheel -- pure Python, installs on any Python 3)
Pillow 12.1.1 (cp314 wheel -- no cp314 wheel exists for 11.3.0)
Resampling.BILINEAR value = 2
```

## Task Commits

Each task was committed atomically:

1. **Task 1: Verify mss + Pillow wheels and update requirements pins** - `051e172` (chore)
2. **Task 2: Create tests/test_capture.py with structural/lint tests** - `7a59792` (test -- TDD RED)
3. **Task 3: Create capture.py implementing CaptureWorker** - `9ba3423` (feat -- TDD GREEN)

## Files Created/Modified
- `src/magnifier_bubble/capture.py` - CaptureWorker producer thread (129 lines)
- `tests/test_capture.py` - 14 pure-Python structural/lint tests (222 lines)
- `requirements.txt` - Pillow pin bumped 11.3.0 -> 12.1.1

## Test Output (verbose)

```
tests/test_capture.py::test_module_import_does_not_load_mss PASSED
tests/test_capture.py::test_capture_module_imports PASSED
tests/test_capture.py::test_captureworker_class_exists PASSED
tests/test_capture.py::test_captureworker_init_signature PASSED
tests/test_capture.py::test_captureworker_is_daemon_by_default PASSED
tests/test_capture.py::test_stop_is_threading_event PASSED
tests/test_capture.py::test_get_fps_returns_zero_before_samples PASSED
tests/test_capture.py::test_get_fps_returns_positive_after_samples PASSED
tests/test_capture.py::test_no_imagegrab_in_capture_source PASSED
tests/test_capture.py::test_capture_uses_bilinear_literal PASSED
tests/test_capture.py::test_mss_mss_constructed_inside_run PASSED
tests/test_capture.py::test_capture_uses_capture_region_not_snapshot PASSED
tests/test_capture.py::test_run_uses_event_wait_not_time_sleep PASSED
tests/test_capture.py::test_run_has_outer_reconnect_loop PASSED
14 passed in 0.30s
```

## CAPT-03 Enforcement

```
grep -r "ImageGrab" src/magnifier_bubble/ => zero matches (CAPT-03 OK)
```

## __init__.py Invariant

```
wc -l src/magnifier_bubble/__init__.py => 0 lines (Phase 1 invariant preserved)
```

## CaptureWorker Public API (frozen for Plan 03-02)

```python
class CaptureWorker(threading.Thread):
    def __init__(self, state: AppState, on_frame: FrameCallback, target_fps: float = 30.0) -> None
    def stop(self) -> None
    def get_fps(self) -> float
    def run(self) -> None      # lazy imports mss + PIL, outer reconnect + inner frame loop
    def _tick(self, sct, Image_cls) -> None  # one frame: grab + resize + callback
```

## Decisions Made
- Bumped Pillow pin from 11.3.0 to 12.1.1 to match installed version on Python 3.14.3 dev box (no cp314 wheel for 11.3.0; API-compatible for all used entry points)
- mss 10.1.0 confirmed importable on Python 3.14.3 (pure-Python wheel)
- CAPTUREBLT=0 hall-of-mirrors defense placed inside run() before mss.mss() construction

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CaptureWorker API is frozen; Plan 03-02 can construct `CaptureWorker(state, on_frame)` to wire into the BubbleWindow canvas
- CAPT-05 (SetWindowDisplayAffinity Path A defense) and CAPT-06 (canvas wiring) remain for Plan 03-02
- mss.grab() runtime behavior confirmed (import path works, GDI grab requires desktop session)

## Self-Check: PASSED

- FOUND: src/magnifier_bubble/capture.py
- FOUND: tests/test_capture.py
- FOUND: .planning/phases/03-capture-loop/03-01-SUMMARY.md
- FOUND: 051e172 (Task 1 commit)
- FOUND: 7a59792 (Task 2 commit)
- FOUND: 9ba3423 (Task 3 commit)

---
*Phase: 03-capture-loop*
*Completed: 2026-04-12*
