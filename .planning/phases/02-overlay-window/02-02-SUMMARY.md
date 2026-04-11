---
phase: 02-overlay-window
plan: 02
subsystem: ui
tags: [ctypes, win32, wndproc, setwindowrgn, hrgn, tkinter, python, pywin32]

# Dependency graph
requires:
  - phase: 01-foundation-dpi
    provides: "PMv2 DPI awareness set in main.py; dpi._u32 lazy-argtypes pattern copied verbatim by wndproc._u32"
  - phase: 02-overlay-window/01
    provides: "winconst.GWLP_WNDPROC / WM_NCHITTEST / HTCAPTION / HTTRANSPARENT / HTCLIENT constants; hit_test.compute_zone string API consumed as compute_zone_fn in Plan 03"
provides:
  - "src/magnifier_bubble/wndproc.py: WNDPROC WINFUNCTYPE, WndProcKeepalive __slots__ container, install/uninstall with LONG_PTR-safe argtypes, WM_NCHITTEST routing via c_short lParam unpack"
  - "src/magnifier_bubble/shapes.py: apply_shape(hwnd, w, h, shape) with VALID_SHAPES=('circle','rounded','rect'), ROUNDED_RADIUS=40, HRGN ownership rule (no DeleteObject on success)"
  - "tests/conftest.py: session-scoped tk_session_root + per-test tk_toplevel fixtures (shared Tk root eliminates Tcl lib-loading race)"
  - "Verified pywin32 311 has a cp314 wheel — the Phase 8 wheel-compatibility concern for 3.14 is partially de-risked (pywin32 confirmed)"
affects: [02-overlay-window/03, 04-pan-resize-shape, 05-tray-hotkeys, 06-error-handling]

# Tech tracking
tech-stack:
  added: [pywin32 (runtime verification; wheel already listed)]
  patterns:
    - "Lazy _SIGNATURES_APPLIED sentinel copied from dpi._u32: x64 LONG_PTR/HANDLE argtypes applied on first user32 access, never at import time"
    - "WndProcKeepalive __slots__ container holds strong refs to new_proc, old_proc, hwnd — the canonical Plan 03 attribute name is _wndproc_keepalive (grep-able)"
    - "Deferred runtime import (win32gui inside apply_shape) so non-Windows CI can still import the module for structural lints"
    - "Session-scoped shared Tk root fixture — avoids the Python 3.14 + tk8.6 SourceLibFile panedwindow race"

key-files:
  created:
    - "src/magnifier_bubble/wndproc.py (168 lines) — WindowProc subclass installer"
    - "src/magnifier_bubble/shapes.py (74 lines) — SetWindowRgn shape mask"
    - "tests/test_wndproc_smoke.py (271 lines) — 8 structural + 7 Windows smoke tests"
    - "tests/test_shapes_smoke.py (170 lines) — 9 structural + 5 Windows smoke tests"
  modified:
    - "tests/conftest.py — added tk_session_root (session) and tk_toplevel (function) fixtures"

key-decisions:
  - "[Rule 1 bug fix] pywin32 311 does not expose CreateEllipticRgn / CreateRectRgn — only the *Indirect variants. Swapped to CreateEllipticRgnIndirect((0,0,w,h)) / CreateRectRgnIndirect((0,0,w,h)); CreateRoundRectRgn still works with the six-int signature."
  - "[Rule 1 bug fix] Plan's verbatim docstring contained literal 'LOWORD' / 'HIWORD' / 'SetProcessDpiAwarenessContext' strings, which tripped the structural lint tests (substring check). Rewrote the comments to describe the behaviour without using the forbidden tokens."
  - "[Rule 1 test-infra fix] Added session-scoped tk_session_root fixture + per-test tk_toplevel fixture to conftest.py. Repeated tk.Tk() creation/destruction across test modules triggered a flaky 'SourceLibFile panedwindow' TclError on Python 3.14 + tk8.6 (~2/5 full-suite runs failed). Shared root eliminates the race (0/8 failures post-fix)."
  - "WndProc keepalive name is _wndproc_keepalive (grep-able) and WndProcKeepalive uses __slots__ = ('new_proc', 'old_proc', 'hwnd') as locked in the research Pattern 2 example"
  - "wndproc.py applies lazy argtypes via _SIGNATURES_APPLIED sentinel — identical pattern to Phase 1 P03 dpi._u32; no import-time user32 touching"
  - "shapes.py defers 'import win32gui' to call time so non-Windows CI can import the module for structural lints"

patterns-established:
  - "ctypes argtypes lazy-apply: LONG_PTR-safe bindings applied on first call via _SIGNATURES_APPLIED sentinel (wndproc.py, dpi.py)"
  - "GC keepalive container: WndProcKeepalive with __slots__ holding the WNDPROC thunk + old_proc address + hwnd; caller MUST store it on an instance attribute"
  - "HRGN ownership rule: CreateXxxRgn -> SetWindowRgn (ok) -> OS owns HRGN; (fail) -> app still owns, app must DeleteObject and raise"
  - "Deferred runtime import: Windows-only runtime deps (win32gui) imported inside the function body, not at module top, so structural lints run on any platform"
  - "Session-scoped Tk fixture: avoid per-test tk.Tk() churn; use Toplevel(shared_root) instead"

requirements-completed: [OVER-03, LAYT-02, LAYT-03, LAYT-04]

# Metrics
duration: 9min
completed: 2026-04-11
---

# Phase 02 Plan 02: wndproc + shapes Summary

**Windows-only WindowProc subclass (LONG_PTR-safe SetWindowLongPtrW + WM_NCHITTEST routing) and apply_shape HRGN mask, with 29 green smoke tests including a 50-message GC survival and a 50-cycle HRGN stress on a real Tk HWND.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-04-11T22:40:33Z
- **Completed:** 2026-04-11T22:49:55Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 5 (2 created src, 2 created tests, 1 modified conftest)

## Accomplishments

- `wndproc.py`: WindowProc subclass installer with LONG_PTR-safe SetWindowLongPtrW / GetWindowLongPtrW / CallWindowProcW argtypes via the lazy `_SIGNATURES_APPLIED` sentinel mirrored from Phase 1 P03 `dpi._u32`. The WM_NCHITTEST routing correctly returns `HTCAPTION` for the drag zone, `HTTRANSPARENT` for the content zone, and delegates the control zone to `CallWindowProcW` (the default Tk proc returns `HTCLIENT=1` as expected). `lParam` is unpacked via signed `ctypes.c_short` for multi-monitor safety. The `WndProcKeepalive` __slots__ container holds strong references to the new WNDPROC thunk, the old proc address, and the hwnd — Pitfall A (GC crash) is eliminated.
- `shapes.py`: `apply_shape(hwnd, w, h, shape)` for `circle` / `rounded` / `rect` via `win32gui.CreateEllipticRgnIndirect` / `CreateRoundRectRgn` / `CreateRectRgnIndirect` → `SetWindowRgn`. Exactly one `DeleteObject` call, scoped to the `if result == 0:` failure branch — HRGN ownership correctly transfers to the OS on success (Pitfall F fix). Pre-guard raises `ValueError` for unknown shapes before any win32 call, keeping structural lints non-Windows-runnable.
- Test suite: `29/29` green (15 wndproc + 14 shapes) reproducibly across 8 consecutive runs after the Tk fixture fix. Full test suite now `115/115` green (Phase 1 + Plan 01 + Plan 02). Phase 1 non-regression verified via `python main.py` producing the same three log lines as the Phase 1 P03 SUMMARY.

## Task Commits

Each task was committed atomically via TDD (RED → GREEN):

1. **Task 1 (RED): test(02-02): add failing test for wndproc WindowProc subclass** — `b509511` (test)
2. **Task 1 (GREEN): feat(02-02): implement wndproc WindowProc subclass with LONG_PTR argtypes** — `fb3189a` (feat)
3. **Task 2 (RED): test(02-02): add failing test for shapes.apply_shape** — `eec6945` (test)
4. **Task 2 (GREEN): feat(02-02): implement shapes.apply_shape with HRGN ownership rule** — `44daf1a` (feat)
5. **Rule 1 fix: fix(02-02): eliminate flaky Tk 'SourceLibFile panedwindow' error** — `e3ddd57` (fix)

**Plan metadata commit:** (final commit below)

## Files Created/Modified

- `src/magnifier_bubble/wndproc.py` — WindowProc subclass installer (WNDPROC, WndProcKeepalive, install, uninstall). Lazy `_SIGNATURES_APPLIED` argtypes apply for SetWindowLongPtrW / GetWindowLongPtrW / CallWindowProcW / GetWindowRect / SendMessageW on first call.
- `src/magnifier_bubble/shapes.py` — `apply_shape` with the three shape variants + HRGN ownership rule. `VALID_SHAPES = ("circle", "rounded", "rect")`, `ROUNDED_RADIUS = 40`. Deferred `import win32gui`.
- `tests/test_wndproc_smoke.py` — 15 tests (8 structural + 7 Windows smoke). Smoke tests verify install returns populated keepalive, WM_NCHITTEST → HTCAPTION for drag / HTTRANSPARENT for content / delegated HTCLIENT for control, 50-message GC survival, uninstall restores the original proc address.
- `tests/test_shapes_smoke.py` — 14 tests (9 structural + 5 Windows smoke). Smoke tests verify each shape does not raise, 50-cycle no-double-free stress, 10-size resize stress.
- `tests/conftest.py` — added `tk_session_root` (session-scoped) and `tk_toplevel` (function-scoped) fixtures.

## Decisions Made

1. **Used CreateEllipticRgnIndirect / CreateRectRgnIndirect** — pywin32 311 does not bind the four-int `CreateEllipticRgn` / `CreateRectRgn` forms the plan specified (verified by dir(win32gui) inspection). The Indirect variants take a 4-tuple `(left, top, right, bottom)` and are functionally equivalent. `CreateRoundRectRgn` is still bound with the direct six-int signature. The structural lint substring checks (`"CreateEllipticRgn" in src`, `"CreateRectRgn" in src`) still pass because "Indirect" is a suffix.
2. **Session-scoped Tk root fixture** — Python 3.14 + tk8.6 has a lib-loading race when `tk.Tk()` is called repeatedly in the same process, causing a flaky `SourceLibFile panedwindow` TclError (~2/5 runs failed). Fix: one Tk root per session, fresh `Toplevel` per test. 0/8 failures in the post-fix stress loop.
3. **Plan docstring rewrite** — The plan's verbatim code contained literal `LOWORD` / `HIWORD` / `SetProcessDpiAwarenessContext` strings in comments (describing what to avoid). These tripped the structural lint tests which do substring checks. Rewrote the comments to describe the behaviour ("unsigned word-extraction macros" / "change process DPI awareness") without the forbidden tokens.
4. **pywin32 311 cp314 wheel verified** — Partial de-risk of the Phase 8 wheel-compatibility concern noted in STATE.md. pywin32 wheel installed successfully. mss 10.1.0, Pillow 11.3.0, numpy 2.2.6, pyinstaller 6.11.1 still need verification at their respective plan checkpoints.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] pywin32 311 CreateEllipticRgn / CreateRectRgn are not bound**
- **Found during:** Task 2 (shapes.py GREEN phase — Windows smoke tests)
- **Issue:** The plan's verbatim code uses `win32gui.CreateEllipticRgn(0, 0, w, h)` and `win32gui.CreateRectRgn(0, 0, w, h)`, but pywin32 311 only exposes the `*Indirect` variants. `hasattr(win32gui, 'CreateEllipticRgn')` is False; `hasattr(win32gui, 'CreateRoundRectRgn')` is True.
- **Fix:** Swapped to `CreateEllipticRgnIndirect((0, 0, w, h))` and `CreateRectRgnIndirect((0, 0, w, h))` — both take a 4-tuple and are functionally equivalent. `CreateRoundRectRgn` unchanged.
- **Files modified:** `src/magnifier_bubble/shapes.py`
- **Verification:** All 14 shapes tests pass, including the 50-cycle stress and the 10-size resize stress. Structural lint substring checks still match because "CreateEllipticRgn" and "CreateRectRgn" are prefixes of the Indirect names.
- **Committed in:** `44daf1a`

**2. [Rule 1 — Bug] Plan docstring contained forbidden substring tokens**
- **Found during:** Task 1 (wndproc.py GREEN phase — initial lint run)
- **Issue:** The plan's verbatim wndproc.py docstring / inline comments contained the literal strings `LOWORD`, `HIWORD`, and `SetProcessDpiAwarenessContext` (explaining what the code is NOT doing). The structural lint tests assert these substrings are NOT in the file source, so verbatim copy would have failed two tests (`test_source_uses_c_short_not_loword_hiword`, `test_source_does_not_call_dpi_api`).
- **Fix:** Rewrote the module docstring and inline comments to convey the same warning (use `c_short`, not the unsigned word-extraction macros; DPI is main.py's job) without using the literal forbidden tokens.
- **Files modified:** `src/magnifier_bubble/wndproc.py`
- **Verification:** Both previously-failing structural tests now pass; all 15 wndproc tests green.
- **Committed in:** `fb3189a` (rewritten docstring was part of the initial GREEN commit)

**3. [Rule 1 — Test Infrastructure] Flaky Tk `SourceLibFile panedwindow` TclError under per-test tk.Tk() churn**
- **Found during:** Full-suite verification after Task 2
- **Issue:** Creating/destroying `tk.Tk()` roots in 12+ tests back-to-back triggered a Tcl lib-loading race on Python 3.14 + tk8.6 on Windows, causing intermittent `TclError: SourceLibFile panedwindow`. Full-suite reliability was ~3/5 green across a 5-run stress.
- **Fix:** Added session-scoped `tk_session_root` and function-scoped `tk_toplevel` fixtures to `tests/conftest.py`. Migrated all 12 Windows-only smoke tests in both test files to consume the new `tk_toplevel` fixture. One Tk root per session; fresh `Toplevel` per test.
- **Files modified:** `tests/conftest.py`, `tests/test_wndproc_smoke.py`, `tests/test_shapes_smoke.py`
- **Verification:** 0/8 failures in a post-fix 8-run stress. Full suite 115/115 green on every run.
- **Committed in:** `e3ddd57`

---

**Total deviations:** 3 auto-fixed (3 Rule 1 bug fixes — 2 source-code bugs from verbatim plan code not matching modern API / lint contract, 1 test-infra bug from per-test Tk root churn)
**Impact on plan:** All three auto-fixes were necessary for correctness. The plan's code examples were written assuming the older pywin32 API + a docstring-as-education style that the plan's own lint tests forbade. The Tk fixture fix is the first test-infrastructure improvement the project has needed and will pay dividends for every Phase 2+ smoke test. No scope creep.

## Issues Encountered

- **pywin32 missing from dev environment at test start** — Resolved by `pip install pywin32` (cp314 wheel was available). This is an incidental confirmation that the Phase 8 Python 3.14 wheel-compatibility concern in STATE.md is at least partially de-risked for pywin32 specifically.
- **Control-zone delegation return value** — Verified the default Tk window proc returns `HTCLIENT=1` for the in-client-area point `(400, 590)`, matching research Pattern 2's expectation. The test asserts `result != HTCAPTION` and `result != HTTRANSPARENT` rather than `== HTCLIENT` so a different default proc value (e.g., `HTNOWHERE`) would still satisfy the delegation semantics.

## User Setup Required

None — no external service configuration required. All work is local Python / ctypes / pywin32.

## Next Phase Readiness

**Plan 03 (BubbleWindow) is unblocked.** Plan 03 will import:
- `from magnifier_bubble.wndproc import install, uninstall, WndProcKeepalive`
- `from magnifier_bubble.shapes import apply_shape, VALID_SHAPES, ROUNDED_RADIUS`

Plan 03's `BubbleWindow.__init__` will:
1. Create `tk.Tk()` root, configure WS_EX_LAYERED + WS_EX_TOOLWINDOW + WS_EX_NOACTIVATE, set PMv2 DPI awareness (already handled in main.py).
2. Retrieve the toplevel HWND via `GetParent(winfo_id())`.
3. Call `shapes.apply_shape(hwnd, 400, 400, "circle")` for the initial circle shape.
4. Call `wndproc.install(hwnd, hit_test.compute_zone)` and store the returned `WndProcKeepalive` on `self._wndproc_keepalive`.
5. On `WM_DELETE_WINDOW`, call `wndproc.uninstall(self._wndproc_keepalive)` before `root.destroy()`.

**No blockers for Plan 03.** The two load-bearing failure modes (GC crash on WndProc thunk, HRGN double-free on SetWindowRgn) are both pinned and regression-tested before Plan 03's first line of BubbleWindow code.

**Phase 2 STATE update:**
- LAYT-04 (WndProc subclass + keepalive): verified end-to-end with 50-message GC survival test
- LAYT-03 (HTCAPTION drag zone routing): verified via synthetic SendMessageW
- LAYT-02 (HTTRANSPARENT content zone routing): verified via synthetic SendMessageW
- OVER-03 (WS_EX_LAYERED): Plan 03 responsibility; this plan ships the WndProc wiring that Plan 03's layered-window creation depends on

---

*Phase: 02-overlay-window*
*Completed: 2026-04-11*

## Self-Check: PASSED

- FOUND: src/magnifier_bubble/wndproc.py
- FOUND: src/magnifier_bubble/shapes.py
- FOUND: tests/test_wndproc_smoke.py
- FOUND: tests/test_shapes_smoke.py
- FOUND: tests/conftest.py (modified)
- FOUND: commit b509511 (test wndproc RED)
- FOUND: commit fb3189a (feat wndproc GREEN)
- FOUND: commit eec6945 (test shapes RED)
- FOUND: commit 44daf1a (feat shapes GREEN)
- FOUND: commit e3ddd57 (Rule 1 Tk fixture fix)
- FULL SUITE: 115/115 passed
- SMOKE SUITE: 29/29 passed across 8 consecutive runs
- PHASE 1 NON-REGRESSION: `python main.py` exits 0 with three expected log lines
