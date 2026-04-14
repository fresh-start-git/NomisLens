# Phase 06 Deferred Items

Pre-existing failures discovered while running full test suite during
Plan 06-01 execution. These are unrelated to Phase 6 Wave 0 stub work
and were present on master BEFORE plan 06-01 touched any file.

Verified by stashing all Plan 06-01 changes and running the full suite —
failures reproduced identically.

## TypeError: 'Event' object is not callable

**Tests affected (6 failures + 4 errors on pre-change baseline):**

- tests/test_capture_smoke.py::test_capture_worker_starts_and_frames_arrive
- tests/test_capture_smoke.py::test_capture_worker_achieves_30fps
- tests/test_capture_smoke.py::test_capture_memory_flat_over_60s
- tests/test_capture_smoke.py::test_no_hall_of_mirrors
- tests/test_window_integration.py::test_source_has_pattern_2b_drag_workaround
- tests/test_window_integration.py::test_capture_worker_lifecycle
- tests/test_window_config_integration.py (4 errors)

**Root cause hypothesis:** `threading.Event` used where a callable was
expected — likely `event()` instead of `event.is_set()` or `event.set()`
somewhere in capture.py or window.py setup path. Traceback lands in
`threading.py:1141` which is the `Thread._bootstrap_inner` call site,
suggesting a thread target mis-wiring.

**Action:** Deferred out of Plan 06-01 scope. This plan added only test
stubs + 9 winconst constants — none of those files touch threading or
the capture worker lifecycle. The failures should be fixed in a Phase
04-04 diagnostic plan (per existing STATE.md Pending Todos) or in a
dedicated follow-up.
