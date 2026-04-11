---
phase: 02-overlay-window
plan: 01
subsystem: ui
tags: [win32, tkinter, hit-test, pure-python, winconst, layt, ctrl-09]

# Dependency graph
requires:
  - phase: 01-foundation-dpi
    provides: "Zero-third-party stdlib module conventions (state.py), conftest win_only marker, pyproject pythonpath=['src']"
provides:
  - "src/magnifier_bubble/winconst.py - 17 Win32 sentinel values (WS_EX_*, GWL*, HT*, WM_*, LWA_*) verified against Microsoft Learn"
  - "src/magnifier_bubble/hit_test.py - pure compute_zone(client_x, client_y, w, h) -> 'drag' | 'content' | 'control' with DRAG_BAR_HEIGHT/CONTROL_BAR_HEIGHT=44 module constants"
  - "Locked string contract for Plan 02's wndproc bridge: three literals 'drag' / 'content' / 'control' map to HTCAPTION / HTTRANSPARENT / HTCLIENT"
affects: [02-overlay-window plan 02 (wndproc.py consumes both modules), 02-overlay-window plan 03 (BubbleWindow wires compute_zone into Tk events), 04-controls (44x44 touch targets in drag/control strips)]

# Tech tracking
tech-stack:
  added: []  # stdlib-only plan — no new dependencies
  patterns:
    - "Pure-Python math isolation: OS-bound wiring kept separate so CI can lint the math everywhere"
    - "ast-based structural lints: assert module bodies contain no function/class defs and no forbidden imports"
    - "Stringly-typed decoupling: hit_test returns 'drag'/'content'/'control' so the wndproc bridge (Plan 02) is the single place that imports winconst"

key-files:
  created:
    - "src/magnifier_bubble/winconst.py"
    - "src/magnifier_bubble/hit_test.py"
    - "tests/test_winconst.py"
    - "tests/test_hit_test.py"
  modified: []

key-decisions:
  - "hit_test.py intentionally does NOT import winconst.py — the string->HT* bridge lives in Plan 02's wndproc.py so the pure function stays testable on any platform"
  - "DRAG_BAR_HEIGHT = CONTROL_BAR_HEIGHT = 44 locked here for CTRL-09 finger touch target; any Phase 4 resize must update these module constants, not hardcode"
  - "Tiny-window overlap (h < 88) resolves to 'drag' first — the content zone can be empty in a degenerate 60x60 bubble rather than crashing"
  - "Out-of-bounds returns 'content' so WndProc returns HTTRANSPARENT — clicks in the SetWindowRgn-clipped corners pass through to the app below"
  - "WS_EX_TRANSPARENT included in winconst.py as a documented DO-NOT-USE sentinel (PITFALLS.md Pitfall 1) — whole-window transparency would kill the drag bar"
  - "HTBOTTOMRIGHT = 17 reserved in winconst.py now for Phase 4 resize grip to avoid re-touching the file later"
  - "[Rule 1 bug fix] test_compute_zone_signature uses inspect.signature(compute_zone, eval_str=True) — under 'from __future__ import annotations' (PEP 563) return_annotation is the string 'str', not the str type"

patterns-established:
  - "Module-purity test pattern: read source + ast.parse + walk for forbidden ImportFrom/Import + forbid FunctionDef/ClassDef in constant modules"
  - "Parametrize-driven boundary tables: 23 (cx, cy, w, h, expected) rows pin the LAYT-01/02/03 contract across 400x400, 150x150, 60x60 windows"
  - "Signature lock pattern: inspect.signature + assert params list matches exactly — catches rename regressions at test time"

requirements-completed: [LAYT-01, LAYT-02, LAYT-03]

# Metrics
duration: 4min
completed: 2026-04-11
---

# Phase 2 Plan 1: winconst + hit_test Summary

**Pure-Python foundation for Phase 2 overlay: 17 Win32 sentinel constants and a stringly-typed compute_zone hit-test, both zero-third-party and fully unit-testable on any platform.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-11T22:31:09Z
- **Completed:** 2026-04-11T22:34:54Z
- **Tasks:** 2 (TDD: 2 RED + 2 GREEN = 4 commits)
- **Files created:** 4

## Accomplishments

- `winconst.py` exports the 17 Win32 sentinel values every Phase 2 plan depends on (WS_EX_LAYERED/TOOLWINDOW/NOACTIVATE, GWL_EXSTYLE, GWLP_WNDPROC, LWA_ALPHA, HTCLIENT/HTCAPTION/HTTRANSPARENT/HTBOTTOMRIGHT, WM_NCHITTEST/NCLBUTTONDOWN/MOUSEMOVE/LBUTTONDOWN/DESTROY), each pinned against Microsoft Learn by a parametrized lint test
- `hit_test.py` exports the locked `compute_zone(client_x, client_y, w, h) -> str` contract with `DRAG_BAR_HEIGHT = CONTROL_BAR_HEIGHT = 44` CTRL-09 module constants
- 52 tests green for plan 02-01 (21 winconst + 31 hit_test), full suite 86 passed with no Phase 1 regression
- Both modules verified pure (no ctypes/tkinter/win32/mss/PIL imports) by ast-based structural lints that will catch future typos
- `src/magnifier_bubble/__init__.py` still 0 bytes (Phase 1 Plan 02 DPI-lock intact)

## Task Commits

Each task executed TDD (RED + GREEN):

1. **Task 1 RED:** test for winconst — `a3a8659` (test)
2. **Task 1 GREEN:** winconst.py pure constants — `c62f2a9` (feat)
3. **Task 2 RED:** test for hit_test.compute_zone — `a89eefe` (test)
4. **Task 2 GREEN:** hit_test.py + Rule-1 signature-test fix — `3a16d33` (feat)

No REFACTOR commits needed — both modules were already minimal.

## Files Created/Modified

- `src/magnifier_bubble/winconst.py` (51 lines) — pure Win32 constants, 17 sentinels, zero imports besides `from __future__ import annotations`
- `src/magnifier_bubble/hit_test.py` (55 lines) — `compute_zone` pure function + `DRAG_BAR_HEIGHT`/`CONTROL_BAR_HEIGHT` module constants
- `tests/test_winconst.py` (120 lines) — 17 parametrized value asserts + 4 structural lints (no third-party imports, body-is-constants-only, no function/class defs, future-import-first) → 21 passed in 0.09s
- `tests/test_hit_test.py` (151 lines) — 23 parametrized boundary rows + 4 named LAYT sanity tests + signature lock + ast purity + ast module-contract → 31 passed in 0.14s

## Test Results

```
$ python -m pytest tests/test_winconst.py -v
============================= 21 passed in 0.09s =============================

$ python -m pytest tests/test_hit_test.py -v
============================= 31 passed in 0.14s =============================

$ python -m pytest tests/test_winconst.py tests/test_hit_test.py -v
============================= 52 passed in 0.16s =============================

$ python -m pytest tests/ -x -q
============================= 86 passed in 0.52s =============================
```

Full-suite delta vs Phase 1 baseline: **+52 tests, 0 regressions.** Phase 1 tests (state, dpi, main_entry) still green alongside the new Phase 2 plan 1 tests.

## Interface for Plan 02 + Plan 03

The complete public API this plan ships (Plan 02's wndproc.py and Plan 03's BubbleWindow will import exactly these names):

```python
# From winconst.py — Plan 02 wndproc.py will consume:
from magnifier_bubble import winconst
winconst.WS_EX_LAYERED      # 0x00080000
winconst.WS_EX_TOOLWINDOW   # 0x00000080
winconst.WS_EX_NOACTIVATE   # 0x08000000
winconst.GWL_EXSTYLE        # -20
winconst.GWLP_WNDPROC       # -4
winconst.LWA_ALPHA          # 0x00000002
winconst.HTCLIENT           # 1
winconst.HTCAPTION          # 2
winconst.HTTRANSPARENT      # -1
winconst.WM_NCHITTEST       # 0x0084
winconst.WM_NCLBUTTONDOWN   # 0x00A1
# + HTBOTTOMRIGHT, WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_DESTROY, LWA_COLORKEY, WS_EX_TRANSPARENT

# From hit_test.py — Plan 02 wndproc.py + Plan 03 BubbleWindow will consume:
from magnifier_bubble.hit_test import compute_zone, DRAG_BAR_HEIGHT, CONTROL_BAR_HEIGHT
compute_zone(client_x=200, client_y=200, w=400, h=400)  # -> 'content'
DRAG_BAR_HEIGHT     # 44
CONTROL_BAR_HEIGHT  # 44
```

**Bridge contract (Plan 02 is the sole place that couples them):**

```python
# Plan 02 wndproc.py will do:
_ZONE_TO_HT = {
    "drag":    winconst.HTCAPTION,
    "content": winconst.HTTRANSPARENT,
    "control": winconst.HTCLIENT,
}
```

This decoupling is deliberate — it lets `compute_zone` be unit-tested on Linux CI and lets `winconst` be linted against Microsoft Learn without pulling in any win32 runtime.

## Decisions Made

1. **Stringly-typed return** instead of returning `winconst.HTCAPTION` / `HTTRANSPARENT` / `HTCLIENT` directly from `compute_zone`. Rationale: keeps the function pure Python, lets it be imported and tested without a win32 environment; Plan 02's wndproc.py is the intentional single bridge.
2. **`DRAG_BAR_HEIGHT` and `CONTROL_BAR_HEIGHT` module-level, not parameters.** CTRL-09 locks 44 px finger touch targets; parameterizing would invite Phase 4 to accidentally shrink them.
3. **Overlap rule: drag wins on tiny windows.** When `h < 88` the drag band covers rows that the control band would also claim. The function tests the drag band first, so degenerate 60x60 windows return "drag" for the overlapping rows — prevents index math from crashing at the contract layer.
4. **Out-of-bounds returns `"content"`.** The WndProc will convert that to HTTRANSPARENT, so clicks outside the SetWindowRgn-clipped region pass through to the app underneath the bubble — preserves LAYT-02's click-through promise even on the clipped corner pixels.
5. **`WS_EX_TRANSPARENT` included as a DO-NOT-USE sentinel.** Documented in winconst.py and tested so a future "helpful" refactor doesn't set it on the HWND and break the drag bar (PITFALLS.md Pitfall 1).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_compute_zone_signature failed under PEP 563 string annotations**

- **Found during:** Task 2 (hit_test GREEN phase)
- **Issue:** The plan-supplied test `assert sig.return_annotation is str` failed with `AssertionError: assert 'str' is str`. Because `hit_test.py` opts in to `from __future__ import annotations` (PEP 563, consistent with every other module in this package), `inspect.signature(compute_zone).return_annotation` is the literal string `'str'`, not the `str` type. The assertion `is str` would therefore never pass on any module that uses postponed annotations — a latent bug in the test itself.
- **Fix:** Added `eval_str=True` to the `inspect.signature()` call so Python resolves the forward reference back to the real `str` type at test-collection time. Post-fix: `assert sig.return_annotation is str` passes.
- **Files modified:** tests/test_hit_test.py (1 line + 3-line comment explaining why)
- **Verification:** `python -m pytest tests/test_hit_test.py::test_compute_zone_signature -v` passes. Full suite 86/86 green.
- **Committed in:** 3a16d33 (Task 2 GREEN commit — bundled with production hit_test.py since the test file had not yet been committed green)

**2. [Rule 1 - Bug] test_winconst_body_is_only_constants_and_future_import would reject the module docstring**

- **Found during:** Task 1 RED (pre-emptive — spotted while copying the test verbatim)
- **Issue:** The plan's test code asserts every top-level `ast.body[i]` is `ast.ImportFrom` or `ast.Assign`. But the winconst.py body starts with the module docstring, which parses to `ast.Expr(ast.Constant(str))`. Verbatim plan code would have failed on body[0] immediately.
- **Fix:** Added an explicit skip for docstring nodes (`ast.Expr` whose `.value` is a string `ast.Constant`) before the allowlist assertion. All other node types still rejected.
- **Files modified:** tests/test_winconst.py (added a 3-line early-continue)
- **Verification:** `python -m pytest tests/test_winconst.py::test_winconst_body_is_only_constants_and_future_import -v` passes.
- **Committed in:** a3a8659 (Task 1 RED commit — the fix was applied when the test was first authored)

---

**Total deviations:** 2 auto-fixed (2x Rule 1 bug fixes in plan-supplied test code)
**Impact on plan:** Both fixes are mandatory for the tests to work on modules that use `from __future__ import annotations` (every module in this package). No scope creep, no production code changes beyond what the plan specified. The production contracts (`compute_zone` signature and winconst values) are byte-identical to the plan.

## Issues Encountered

None. Full suite stayed green throughout; both modules were correct on the first GREEN attempt.

## Requirement Status

- **LAYT-01** (three-zone layout: drag/content/control): contract defined in hit_test.py + tested by 23-row boundary table. **Plan 02 + 03 wire to Win32 + Tk.**
- **LAYT-02** (middle content is click-through): `compute_zone(center) == "content"` pinned by dedicated test; Plan 02's wndproc bridge maps "content" -> `HTTRANSPARENT`. **Contract defined; Plan 02 wires WndProc.**
- **LAYT-03** (drag bar + control strip capture): `compute_zone` returns "drag"/"control" for top/bottom bands; Plan 02 will map "drag" -> `HTCAPTION`, "control" -> `HTCLIENT`. **Contract defined; Plan 02 wires WndProc.**

All three requirements are "math + contract done, Win32 wiring pending Plan 02".

## Phase 1 Lock Verification

- `src/magnifier_bubble/__init__.py` is still 0 bytes — the Phase 1 P02 DPI-lock holds, no new imports were added to the package `__init__`.
- `winconst.py` and `hit_test.py` are pure Python with no imports of ctypes/tkinter/win32/mss/PIL — they cannot trigger mss's early-init DPI lock even if imported before `main.py` sets PMv2.

## User Setup Required

None — pure Python stdlib modules, no external configuration, no new dependencies.

## Next Phase Readiness

- **Plan 02-02 unblocked:** Can now write `wndproc.py` with `from magnifier_bubble import winconst` + `from magnifier_bubble.hit_test import compute_zone`. The string->HT* mapping table is ready to drop in.
- **Plan 02-03 unblocked:** `BubbleWindow` can wire `compute_zone` into its Tk event handlers for drag threshold detection.
- **No new blockers.** The Python 3.14.3-vs-3.11.9 concern from STATE.md does not apply to Plans 01-02 (pure stdlib); it remains relevant only for Plan 02-03 (real Tk + pywin32) and Phase 8 packaging.

## Self-Check: PASSED

Files verified present on disk:
- src/magnifier_bubble/winconst.py
- src/magnifier_bubble/hit_test.py
- tests/test_winconst.py
- tests/test_hit_test.py
- .planning/phases/02-overlay-window/02-01-SUMMARY.md

Commits verified present in git log:
- a3a8659 (test RED for winconst)
- c62f2a9 (feat GREEN for winconst)
- a89eefe (test RED for hit_test)
- 3a16d33 (feat GREEN for hit_test + Rule 1 signature-test fix)

---
*Phase: 02-overlay-window*
*Completed: 2026-04-11*
