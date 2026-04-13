---
phase: 04-controls-shape-resize
plan: 01
subsystem: ui
tags: [controls, shape-cycle, zoom, resize, pure-python, tdd, dataclasses]

# Dependency graph
requires:
  - phase: 02-overlay-window
    provides: hit_test.DRAG_BAR_HEIGHT / CONTROL_BAR_HEIGHT (44 px touch target)
  - phase: 02-overlay-window
    provides: shapes.apply_shape (HRGN-owning SetWindowRgn wrapper)
  - phase: 01-foundation-dpi
    provides: state.AppState.set_zoom / set_shape / set_size
provides:
  - SHAPE_CYCLE state machine (circle -> rounded -> rect -> circle)
  - ButtonRect frozen dataclass
  - layout_controls(w, h) -> list[ButtonRect] (4 rects, all 44x44)
  - hit_button(x, y, buttons) linear-scan helper (half-open intervals)
  - zoom_step(z, direction) snap-to-grid + clamp [1.5, 6.0]
  - resize_clamp(w, h) independent-axes clamp to [150, 700]
  - Wave 0 test scaffolding for Plans 02 and 03
  - 100-cycle interleaved-resize Pitfall F regression guard
affects: [04-02-PLAN, 04-03-PLAN]

# Tech tracking
tech-stack:
  added: []  # stdlib-only (dataclasses, math)
  patterns:
    - "Pure-Python core + Tk/Win32 shell split — mirrors Phase 2 hit_test.py pattern"
    - "Mirror-not-import: constants redeclared from hit_test / state so tests run in isolation"
    - "Frozen dataclass ButtonRect — hashable, immutable, unpack-friendly"
    - "Wave 0 skip-placeholder stubs — tests collect but skip until later-wave plan fills bodies"

key-files:
  created:
    - src/magnifier_bubble/controls.py
    - tests/test_controls.py
    - tests/test_window_phase4.py
    - tests/test_clickthru.py
  modified:
    - tests/test_shapes_smoke.py

key-decisions:
  - "zoom_step semantics chosen as 'next grid point strictly greater/less than z' (not snap-then-always-add). On +1 from 2.13 returns 2.25, not 2.50. This matches user-visible pressing + on an off-grid value."
  - "layout_controls at 150x150 minimum returns OVERLAPPING-ADJACENT rects (zoom_in [62..106) and resize [106..150) share an edge; zoom_out [0..44) has an 18 px gap before zoom_in). Not disjoint. CTRL-09 only requires >= 44x44 and in-bounds; enforcing disjointness at minimum would break the layout at normal sizes."
  - "Constants redeclared (not imported) from hit_test / state so tests can import controls without pulling in any sibling module that might have Windows-only runtime bindings."
  - "Wave 0 stubs use plain pytest.skip() — no try/import pattern — so file collection is lightning fast and skip messages point clearly at which plan fills them in."

patterns-established:
  - "Pure core + integration shell: controls.py holds pure math; window.py (Plan 02) holds Tk wiring"
  - "Pitfall F regression guard: 100 iterations of shape cycle interleaved with a 5-size rotation"

requirements-completed: [CTRL-02, CTRL-05, CTRL-08, CTRL-09]

# Metrics
duration: 7min
completed: 2026-04-13
---

# Phase 4 Plan 01: Pure-Python controls.py Summary

**Shipped a stdlib-only controls module (SHAPE_CYCLE, ButtonRect, layout_controls, hit_button, zoom_step, resize_clamp) covering CTRL-02/05/08/09 with 23 unit tests + Wave 0 stubs for Plans 02 and 03 + a 100-cycle interleaved-resize Pitfall F regression guard.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-13T01:21:13Z
- **Completed:** 2026-04-13T01:28:15Z
- **Tasks:** 3 (all TDD for Tasks 1+2; scaffolding for Task 3)
- **Files modified:** 5 (4 created + 1 extended)

## Accomplishments

- Pure-Python `magnifier_bubble/controls.py` — 92 lines, zero third-party imports (stdlib `dataclasses` + `math` only) covering CTRL-02 (SHAPE_CYCLE state machine), CTRL-05 (zoom_step snap+clamp), CTRL-08 (resize_clamp independent axes), CTRL-09 (44×44 button layout)
- 23 unit tests in `tests/test_controls.py` — all passing, run in 0.13s on the dev box, platform-agnostic (no tkinter/ctypes/win32 imports)
- Wave 0 scaffolding: 12 skip-placeholder tests in `tests/test_window_phase4.py` for Plan 04-02, 10 skip-placeholders in `tests/test_clickthru.py` for Plan 04-03 — Plans 02/03 can begin red-to-green work by replacing skip lines one test at a time
- `test_apply_shape_100_cycle_interleaved_resize_no_crash` in `tests/test_shapes_smoke.py` passes — 100 iterations of shape cycle × 5-size rotation on the Windows dev box, confirming Pitfall F DeleteObject-on-owned-HRGN regression is still fixed

## Task Commits

1. **Task 1: Write failing unit tests for controls.py (RED)** — `72863bf` (test)
2. **Task 2: Implement controls.py so all Task 1 tests pass (GREEN)** — `0567797` (feat)
3. **Task 3: Wave 0 stubs + extend shapes smoke to 100-cycle** — `cc9223d` (test)

**Plan metadata:** (this commit)

## Files Created/Modified

- `src/magnifier_bubble/controls.py` (92 lines) — pure-Python control layout + hit-test + shape cycle + zoom/resize math
- `tests/test_controls.py` (150 lines) — 23 unit tests covering CTRL-02/05/08/09
- `tests/test_window_phase4.py` (59 lines) — 12 skip-placeholder stubs for Plan 04-02 integration tests
- `tests/test_clickthru.py` (49 lines) — 10 skip-placeholder stubs for Plan 04-03 click injection tests
- `tests/test_shapes_smoke.py` (188 lines; was 159) — added `test_apply_shape_100_cycle_interleaved_resize_no_crash`

## Decisions Made

1. **zoom_step semantics: next-grid-point-strictly-beyond-z, not snap-then-always-add.** Plan's prescribed implementation would have made `zoom_step(2.13, +1) == 2.50`, but the plan's own test required `== 2.25`. Resolved by changing implementation to "ceil-to-next-grid-point on +1, floor-to-prev-grid-point on -1" which also handles the on-grid case (floor(8.0) + 1 == 9 → 2.25 from 2.00). User-visible: pressing + on an off-grid zoom lands at the next visible 0.25 step, not two steps away.
2. **layout_controls at 150×150 returns OVERLAPPING-ADJACENT rects.** zoom_in [62..106) and resize [106..150) share an edge; zoom_out [0..44) has an 18 px gap before zoom_in. CTRL-09 requires only ≥ 44×44 and in-bounds — enforcing disjointness at the minimum window size would break the normal-size layout. Noted explicitly in the Task 2 `<action>` NOTE block and carried forward as a STATE.md decision so Plan 02 doesn't try to "fix" it.
3. **Constants redeclared (not imported) from hit_test / state.** Lets tests import controls without side-effect risk from sibling modules that might have Windows-only runtime bindings.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] zoom_step snap-then-add ordering produced off-spec value**
- **Found during:** Task 2 (implementing controls.py)
- **Issue:** Plan's prescribed implementation was `snapped = round(z/0.25)*0.25; candidate = snapped + direction*0.25`. That makes `zoom_step(2.13, +1) = round(2.13/0.25)*0.25 + 0.25 = 2.25 + 0.25 = 2.50`. But the plan's own test asserted `zoom_step(2.13, +1) == 2.25`. Plan-internal contradiction.
- **Fix:** Reinterpreted the intent as "+1 → next grid point strictly greater than z" (ceil), "-1 → next grid point strictly less than z" (floor minus 1). This gives the user-visible behavior of "pressing + on 2.13 lands on the next visible 0.25 step (2.25)", and still produces `zoom_step(2.00, +1) == 2.25` (on-grid case) and `zoom_step(6.0, +1) == 6.0` (clamp). All 23 tests pass.
- **Files modified:** `src/magnifier_bubble/controls.py` (`zoom_step` body; added `import math` to module top)
- **Verification:** `pytest tests/test_controls.py -v` — all 23 pass in 0.13s
- **Committed in:** `0567797` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug in plan-prescribed implementation)
**Impact on plan:** No scope creep. The acceptance criterion `grep -cE "^from [a-zA-Z0-9_.]+ import" == 2` is still satisfied because `import math` is a plain-import (not `from...import`). All other acceptance criteria met.

## Issues Encountered

- Pre-existing test failures in `tests/test_window_integration.py` (module-scoped `bubble()` fixture fails with `_tkinter.TclError: Can't find a usable tk.tcl`). Out of scope per boundary rule — NOT caused by Plan 04-01 changes. Isolated to the 3 modules created/extended by this plan, which all pass.
- Python 3.14.3 + pytest-asyncio generates ~5900 deprecation warnings during the full suite run. Unrelated to Plan 04-01 and pre-existing; not in scope.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

Plan 04-02 (BubbleWindow integration shell) can begin:
- Import `ButtonRect`, `layout_controls`, `hit_button`, `SHAPE_CYCLE`, `zoom_step`, `resize_clamp` from `magnifier_bubble.controls`
- Fill in the 12 skip-placeholder tests in `tests/test_window_phase4.py` one at a time (red → green)
- Canvas glyphs (⊙, ≡, [+], [−], ⤢) should place at rects returned by `layout_controls(snap.w, snap.h)`
- `<B1-Motion>` on the resize button should call `resize_clamp(new_w, new_h)` before `root.geometry(...)`

Plan 04-03 (click injection) can begin independently — its 10 skip-placeholder tests are in place.

**Sealed modules UNCHANGED in this plan:** `state.py`, `hit_test.py`, `shapes.py`, `wndproc.py`, `winconst.py`, `capture.py`. Success criterion "Phase 2/3 sealed modules UNCHANGED" verified.

## Self-Check: PASSED

Verified (manual):
- FOUND: `src/magnifier_bubble/controls.py`
- FOUND: `tests/test_controls.py`
- FOUND: `tests/test_window_phase4.py`
- FOUND: `tests/test_clickthru.py`
- FOUND: `tests/test_shapes_smoke.py` (extended)
- FOUND commit: `72863bf` (test: failing controls tests)
- FOUND commit: `0567797` (feat: controls.py implementation)
- FOUND commit: `cc9223d` (test: Wave 0 stubs + shapes smoke extension)
- Purity lint `ast.walk` BANNED IMPORTS check: `set()` (no banned imports)
- Test run: 153 passed + 22 skipped (0 failed) across controls + Wave 0 stubs + sealed-module test files

---
*Phase: 04-controls-shape-resize*
*Completed: 2026-04-13*
