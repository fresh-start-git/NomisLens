# Phase 05 Deferred Items

Items discovered during Phase 05 execution that are OUT OF SCOPE for the
config persistence work. Pre-existing failures in unrelated subsystems.

## Pre-existing test failures (Phase 03 capture worker teardown)

Discovered during Plan 05-01 full-suite regression. Confirmed present on
master BEFORE any Plan 05-01 changes (via `git stash` probe).

**Root cause (likely):** `src/magnifier_bubble/window.py:679` calls
`self._capture_worker.join(timeout=1.0)` on an object whose `_stop`
attribute is being shadowed by something that threading tries to call as
a method but is actually an `Event` instance. Failure manifests as
`TypeError: 'Event' object is not callable` inside
`threading._wait_for_tstate_lock` when join() hits the timeout path.

Failing tests:
- `tests/test_capture_smoke.py::test_capture_worker_starts_and_frames_arrive`
- `tests/test_capture_smoke.py::test_capture_worker_achieves_30fps`
- `tests/test_capture_smoke.py::test_capture_memory_flat_over_60s`
- `tests/test_capture_smoke.py::test_no_hall_of_mirrors`
- `tests/test_window_integration.py::test_capture_worker_lifecycle`

**Separate pre-existing failure:**
- `tests/test_window_integration.py::test_source_has_pattern_2b_drag_workaround`
  asserts `"ReleaseCapture" in src` of `window.py` — the string is absent.
  Likely stale assertion from a Phase 2/3 refactor that removed
  ReleaseCapture in favor of the PostMessageW click-injection path.

**Status:** NOT regressions from Plan 05-01. Should be triaged by a
dedicated fix plan (maintenance) or rolled into the next relevant phase.
