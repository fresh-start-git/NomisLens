# Phase 04 Deferred Items

Log of pre-existing issues discovered during Phase 4 execution that are
OUT OF SCOPE for the current plan. These are not regressions caused by
the plan's work; they predate the plan.

## From Plan 04-02 execution (2026-04-13)

### 1. `tests/test_window_integration.py::test_source_has_pattern_2b_drag_workaround` — pre-existing failure

- **State:** Already failing when Plan 04-02 started (before any Plan 04-02 edit).
- **Cause:** The test is a Phase 2 structural lint that asserts `ReleaseCapture`,
  `WM_NCLBUTTONDOWN`, and `HTCAPTION` all appear in `src/magnifier_bubble/window.py`.
  Phase 3's GIL-crash fix (commit `bf11a97`, finalized in commit `7ad2700` at
  the start of Plan 04-02 execution) intentionally removed all three — the
  manual `<B1-Motion>` + `root.geometry()` drag pattern does not call
  `SendMessageW(WM_NCLBUTTONDOWN, HTCAPTION)` anymore.
- **Conflict with Plan 04-02:** Plan 04-02 Task 2 explicitly requires these
  APIs to be absent (`grep -c "WM_NCLBUTTONDOWN" window.py` must equal 0).
  So the Phase 2 test is semantically obsolete.
- **Why deferred:** Out of scope — the failure predates Plan 04-02's first
  edit. Fixing requires deleting or rewriting a Phase 2 structural lint,
  which is Phase 2/3 cleanup, not Phase 4 feature work.
- **Recommendation:** Delete `test_source_has_pattern_2b_drag_workaround`
  in a dedicated `test(03-02)` or `test(02-03)` follow-up commit, or rewrite
  it to assert the *absence* of those APIs instead. Not Plan 04-02's job.

### 2. Full-suite `pytest tests/` — 12 cross-module Tk ordering errors

- **State:** Already failing when Plan 04-02 started (pre-existing since
  Phase 2/3). Verified by stashing Plan 04-02 changes and checking out
  commit `bf11a97` (last Phase 3 commit before Plan 04-02): the full-suite
  result was `1 failed, 184 passed, 10 skipped, 12 errors` — identical
  error count to what Plan 04-02 sees. Plan 04-02 does NOT regress this.
- **Cause:** Python 3.14 + Tcl/Tk 8.6 becomes unstable when multiple test
  modules each construct their own `tk.Tk()` in the same process. The
  flake manifests as either `init.tcl: couldn't read file` on the N-th
  `tk.Tk()` or `image "pyimageN" doesn't exist` when a PhotoImage from
  a destroyed root leaks into a new root. See STATE.md Phase 02/02
  decisions for the session-scoped `tk_session_root` workaround, which
  only helps WITHIN a single module.
- **Why Plan 04-02 doesn't fix it:** Scope boundary — Plan 04-02 added
  Phase 4 canvas controls to `window.py` and resize-drag wiring. The
  full-suite flake is pre-existing infrastructure fragility that affects
  every Phase 2/3/4 Windows-only test file, not just the new Phase 4
  file. Fixing requires a project-wide pytest fixture refactor to share
  a single `tk.Tk()` across ALL test modules (e.g. a pytest plugin that
  yields a session-scoped root and hands each module a fresh `Toplevel`).
- **Mitigation applied in Plan 04-02:** `tests/test_window_phase4.py`
  uses a module-scoped `phase4_bubble` fixture so the 5 Windows-only
  Phase 4 tests share ONE `BubbleWindow` (one `tk.Tk()`) and reset via
  `state.set_size()`. Running `pytest tests/test_window_phase4.py` in
  isolation passes 12/12.
- **Recommendation:** Deferred to a Phase 8 (or standalone) test-infra
  plan: introduce a session-scoped pytest fixture in `conftest.py` that
  owns the single process-wide `tk.Tk()`, and migrate every Windows-only
  test file to consume it via a `Toplevel`-per-test pattern. Out of scope
  for Plan 04-02.
