---
phase: 01-foundation-dpi
plan: 03
subsystem: foundation
tags: [python, ctypes, win32, dpi, pmv2, pytest, ast-lint, subprocess, over-05, x64-fix]

# Dependency graph
requires:
  - phase: 01-foundation-dpi/01
    provides: "src-layout package skeleton, pyproject.toml pythonpath=src, tests/conftest.py win_only marker, requirements.txt"
  - phase: 01-foundation-dpi/02
    provides: "src/magnifier_bubble/state.py (AppState + StateSnapshot) and src/magnifier_bubble/dpi.py (report/debug_print/is_pmv2_active + sentinels)"
provides:
  - "Root main.py shim that sets PMv2 DPI awareness as first executable statements and delegates to magnifier_bubble.app.main()"
  - "src/magnifier_bubble/app.py Phase 1 entry that exercises dpi.debug_print() and AppState round-trip, returns 0"
  - "tests/test_main_entry.py static AST lint + Windows subprocess smoke, 10 tests, statically pins OVER-05"
  - "Phase 1 Success Criteria 1-5 satisfied as runtime+test properties on Windows 11 x64"
  - "OVER-05 requirement (DPI call before any tkinter/mss/PIL/pywin32/magnifier_bubble import)"
affects: [02-bubble-window, 03-capture-render, 04-controls-interaction, 05-persistence, 06-hotkey, 07-tray, 08-packaging]

# Tech tracking
tech-stack:
  added: []  # still stdlib-only — no new runtime deps
  patterns:
    - "DPI-first main.py shim (Pattern 1 from research)"
    - "AST scan for DPI try/except (tolerates argtypes setup between ctypes import and try)"
    - "Subprocess smoke via sys.executable (not os.system), cwd=REPO_ROOT"
    - "x64 ctypes HANDLE argtypes fix: c_void_p for SetProcessDpiAwarenessContext and wintypes.HANDLE for GetThreadDpiAwarenessContext / AreDpiAwarenessContextsEqual"
    - "Scope-safe signature cache: _SIGNATURES_APPLIED guard in dpi._u32() so reload-safety is preserved"

key-files:
  created:
    - "main.py (17 lines) — root entry; import ctypes + argtypes setup + DPI ladder PMv2/V1/legacy; sys.path bootstrap; delegates to magnifier_bubble.app.main()"
    - "src/magnifier_bubble/app.py (41 lines) — Phase 1 app.main() calling dpi.debug_print() and AppState set_position+snapshot round-trip, returns 0"
    - "tests/test_main_entry.py (207 lines, 10 tests) — 8 static AST lint + 2 Windows subprocess smoke; scan-based DPI try discovery + ordering invariant"
  modified:
    - "src/magnifier_bubble/dpi.py (115 -> 148 lines) — _u32() now applies wintypes argtypes/restype on first access; is_pmv2_active() wraps -4 sentinel in wintypes.HANDLE so x64 sign-extends correctly"

key-decisions:
  - "[Rule 1 - Bug] Plan literal main.py pattern silently returned FALSE on 64-bit Python because default ctypes passes int -4 as c_int (32 bits), truncating the DPI_AWARENESS_CONTEXT handle. Fixed by setting SetProcessDpiAwarenessContext.argtypes = [c_void_p] between line 1 import and the try block."
  - "[Rule 1 - Bug] dpi.is_pmv2_active() also returned False after a SUCCESSFUL PMv2 set because GetThreadDpiAwarenessContext/AreDpiAwarenessContextsEqual defaulted to c_int. Fixed by wintypes.HANDLE argtypes/restype applied lazily in _u32() with a one-shot _SIGNATURES_APPLIED guard so reload-safety holds."
  - "test_main_py_dpi_call_is_second_statement replaced by scan-based test_main_py_dpi_call_is_present_and_targets_pmv2 plus new test_main_py_dpi_runs_before_any_third_party_import so OVER-05 ordering is enforced semantically (no forbidden imports before the DPI try) instead of by a rigid tree.body[1] index."
  - "Kept main.py byte-for-byte compliant with the plan literal for everything EXCEPT the added argtypes assignment on line 2, which the plan's own done-criterion (pmv2=True on Windows 11) made unavoidable on x64 Python."
  - "app.py is stdlib-only + magnifier_bubble.dpi + magnifier_bubble.state — deliberately no tkinter, mss, PIL, or pywin32 imports (Phase 1 scaffold only; later phases replace the body)."

patterns-established:
  - "Scan-based AST lint: _find_dpi_try() walks tree.body for the first ast.Try whose inner body calls SetProcessDpiAwarenessContext — tolerates any number of stmts before the try as long as they are ctypes-touching stdlib"
  - "Ordering invariant test: forbid import of magnifier_bubble, tkinter, mss, PIL, win32api/con/gui BEFORE the DPI ladder (allow ctypes/os/sys)"
  - "Signature cache idiom for ctypes: module-level bool + _u32() sets argtypes on first call, so reloads do not attempt to re-register against stale function cache"
  - "subprocess.run([sys.executable, str(MAIN_PY)], capture_output=True, text=True, cwd=REPO_ROOT, timeout=10) — canonical child-Python smoke pattern"

requirements-completed: [OVER-05]

# Metrics
duration: 9min
completed: 2026-04-11
---

# Phase 01 Plan 03: main.py + app.main() + OVER-05 Smoke Summary

**Wired the Phase 1 foundation end-to-end: a 17-line DPI-first main.py shim, a 41-line Phase 1 app.main() that exercises dpi.debug_print() and AppState, and a 207-line test module that statically pins OVER-05. Fixed two x64 ctypes HANDLE bugs found during execution so that `python main.py` on Windows 11 actually prints `pmv2=True` instead of silently falling back.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-04-11T17:33:20Z
- **Completed:** 2026-04-11T17:42:17Z
- **Tasks:** 3
- **Files created:** 3 (main.py, app.py, test_main_entry.py)
- **Files modified:** 1 (dpi.py — Rule 1 bugfix)

## Accomplishments

- `python main.py` runs end-to-end on Windows 11 x64, exits with code 0, and prints three observable log lines — **`pmv2=True`** proving PMv2 is actually active (not a silently-failed set)
- Root `main.py` is DPI-first: `import ctypes` is the literal first line, the argtypes setup on line 2, and the `SetProcessDpiAwarenessContext(-4)` call lands as the first statement inside the body[2] Try before any `magnifier_bubble`/`tkinter`/`mss`/`PIL`/`pywin32` import
- `src/magnifier_bubble/app.py` implements the Phase 1 entry with zero third-party imports, instantiates `AppState(StateSnapshot())`, mutates via `set_position(300, 400)`, and prints the `[state]` snapshot line that satisfies Success Criterion 4
- Static AST lint catches any future regression that adds a forbidden import before the DPI ladder (e.g. a Phase 3 mistake of adding `import mss` to main.py) and proves main.py's first top-level statement is `import ctypes`
- Full Phase 1 test suite green: **34 passed** in 0.55s (24 from plans 01+02 still green + 10 new from plan 03)
- Fresh-venv smoke succeeded for Phase 1 scope: `python -m venv /tmp/fresh && /tmp/fresh/Scripts/python main.py` prints the three lines and exits 0 even when numpy fails to build (main.py has no third-party imports)

## Task Commits

1. **Task 1: app.py Phase 1 entry** — `3c3d5d9` (feat)
2. **Task 2: main.py shim + dpi.py x64 argtypes fix** — `a28c2ac` (feat, Rule 1 bug fixes bundled)
3. **Task 3: test_main_entry.py static lint + subprocess smoke** — `f26beac` (test)

**Plan metadata commit:** to follow (docs(01-03): complete main.py + app.main + OVER-05 smoke)

## Files Created/Modified

### Created

- **`main.py`** (17 lines) — root entry point. Literal line 1 is `import ctypes`; line 2 sets `SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]`; lines 3-9 are the PMv2 / V1 / legacy try/except ladder; lines 11-12 bootstrap `src/` into `sys.path` via `os.path.dirname(__file__)`; line 14 imports `magnifier_bubble.app.main`; line 16 raises `SystemExit(main())`.
- **`src/magnifier_bubble/app.py`** (41 lines) — Phase 1 `main() -> int` that calls `dpi.debug_print()`, constructs `AppState(StateSnapshot())`, calls `set_position(300, 400)`, snapshots, prints the `[state]` line, prints the `[app] phase 1 scaffold OK` line, returns 0. Zero third-party imports.
- **`tests/test_main_entry.py`** (207 lines, 10 tests) — 8 static AST lint tests + 2 Windows subprocess smoke tests. Uses `_find_dpi_try()` helper to scan `tree.body` for the first Try containing a `SetProcessDpiAwarenessContext` call, so the test is tolerant of the argtypes-setup stmt between `import ctypes` and the try.

### Modified (Rule 1 bug fix inside Task 2)

- **`src/magnifier_bubble/dpi.py`** (115 → 148 lines) — `_u32()` now sets argtypes/restype on `GetThreadDpiAwarenessContext`, `AreDpiAwarenessContextsEqual`, `GetDpiForSystem`, `GetSystemMetrics`, and `GetSystemMetricsForDpi` on first access; `is_pmv2_active()` wraps the `-4` PMv2 sentinel in `wintypes.HANDLE(-4)` so that x64 Python sign-extends the handle to pointer width. Guard `_SIGNATURES_APPLIED` prevents reload-time re-registration and preserves the plan-02 `test_module_importable_without_side_effects` invariant.

## Verbatim `python main.py` Output (Windows 11 x64)

```
[dpi] pmv2=True dpi=96 scale=100% logical=3440x1440 physical=3440x1440
[state] snapshot after set_position(300,400): x=300 y=400 w=400 h=400 zoom=2.0 shape=circle visible=True always_on_top=True
[app] phase 1 scaffold OK; exiting
```

Exit code: `0`.

- `pmv2=True` — the DPI call actually succeeded (contrast with the pre-fix output `pmv2=False` when the argtypes setup was missing; see Deviations below).
- `dpi=96 scale=100%` — dev box primary monitor is running at 100% scaling. VALIDATION.md Manual-Only row for 150% display verification remains a post-plan human task.
- `logical=3440x1440 physical=3440x1440` — under PMv2 with 100% scale these match; under PMv2 with any non-100% scale they would also match (because logical is already physical under PMv2). The `[dpi]` line format exactly matches the six literal substrings asserted by plan-02's `test_debug_print_writes_expected_format`.
- `[state]` line confirms `AppState.set_position(300, 400)` round-trips: `x=300 y=400 w=400 h=400 zoom=2.0 shape=circle visible=True always_on_top=True` — matching `StateSnapshot` defaults for every field except the two that were mutated.
- `[app] phase 1 scaffold OK; exiting` — Phase 1 has no Tk mainloop; this is the clean exit marker.

## `python -m pytest tests/ -v` Summary

```
======================== 34 passed, 1129 warnings in 0.55s ========================
```

Breakdown:

| Suite | Tests | Result |
|---|---|---|
| tests/test_dpi.py (plan 02) | 8 | 8 passed |
| tests/test_state.py (plan 02) | 16 | 16 passed |
| tests/test_main_entry.py (plan 03) | 10 | 10 passed |
| **Total** | **34** | **34 passed, 0 failed, 0 skipped** |

Plan 03 expected "at least 33 tests passing on Windows"; we deliver 34 (plan 02 `test_main_py_dpi_call_is_second_statement` was replaced with TWO tests — the scan-based check + the ordering-invariant check — which nets +1 against the plan-stated baseline of 9).

Runtime 0.55s is well under the 5-second ceiling from `<verification>` step 4.

Warning count (1129) is all `pytest_asyncio` `DeprecationWarning: asyncio.iscoroutinefunction` noise from a globally installed plugin we do not use — pre-existing from plan 02 and out of scope for this plan (STATE.md blocker already documents it).

## Fresh-venv Install Smoke

```bash
rm -rf /tmp/fresh && python -m venv /tmp/fresh
/tmp/fresh/Scripts/pip install -q -r requirements.txt
/tmp/fresh/Scripts/python main.py
```

Observed result:

- `pip install -r requirements.txt` **partially failed** on `numpy==2.2.6` because Python 3.14 has no precompiled wheel and the from-source build via Meson errored out. This is a **pre-existing Phase 8 blocker** already logged in STATE.md — not a regression introduced by this plan.
- Despite the numpy build failure, the fresh venv was created and `/tmp/fresh/Scripts/python main.py` successfully printed the three expected log lines (including `pmv2=True`) and exited 0.
- **Interpretation for OVER-05:** Phase 1 `main.py` has zero third-party runtime dependencies (it only imports `ctypes`, `os`, `sys`, and `magnifier_bubble.app`, which itself only imports stdlib + `magnifier_bubble.{dpi,state}`). So the fresh-venv smoke as scoped to *Phase 1's runtime surface* passes. The full `requirements.txt` install will be re-smoked once Python 3.11.9 is installed side-by-side or numpy has 3.14 wheels — tracked under the existing STATE.md blocker, not a new deferred item.

## Phase 1 ROADMAP Success Criteria Status

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | `python main.py` launches and exits cleanly (code 0) | **PASS** | Subprocess test `test_main_py_runs_and_exits_zero` + manual `python main.py` exit 0 |
| 2 | `SetProcessDpiAwarenessContext(-4)` is the first executable DPI statement, before any tkinter/mss/PIL import | **PASS** | AST tests `test_main_py_first_line_is_import_ctypes` + `test_main_py_dpi_runs_before_any_third_party_import` + runtime proof via `pmv2=True` |
| 3 | `requirements.txt` installs in a fresh venv on Python 3.11.9 | **PARTIAL (pre-existing blocker)** | Phase 1 runtime surface (main.py) runs on fresh venv; full requirements.txt install blocked by numpy 3.14 wheels — existing STATE.md Phase 8 blocker |
| 4 | `AppState` round-trips `set_position` → `snapshot` | **PASS** | `[state]` line in `python main.py` stdout; plan-02 tests for AppState; test_main_py_runs_and_exits_zero grep |
| 5 | `dpi.debug_print()` emits `[dpi] pmv2=.. dpi=.. scale=..% logical=WxH physical=WxH` | **PASS (automated portion)**; **PENDING (manual 150% display)** | `[dpi]` line in stdout with all six fields; VALIDATION.md flags the 150%-scaled display verification as post-plan manual per the Manual-Only Verifications table |

**Net:** 4 / 5 criteria fully PASS; criterion 3 carries a pre-existing Phase 8 blocker (not introduced or exacerbated by this plan); criterion 5 has a documented post-plan manual verification for 150% scaling.

## Decisions Made

All decisions logged under `key-decisions` in frontmatter. Highlights:

1. **Fix the x64 ctypes HANDLE bug in-place rather than escalating as a checkpoint.** Rule 1 bugs are fixed automatically and the fix is strictly local: one line of argtypes setup in main.py and one helper in dpi.py. No architectural impact, no user choice required.
2. **Preserve OVER-05 semantically rather than index-based.** The plan's test asserted `tree.body[1] == ast.Try`. My fix added a body[1] Assign (argtypes) before the try, so body[2] is the Try. Replaced the single index check with (a) a scan-based discovery of the DPI try and (b) an explicit ordering-invariant test that forbids any magnifier_bubble/tkinter/mss/PIL/win32 import BEFORE the DPI try. The new ordering test catches the real failure mode (Phase 3 accidentally adds `import mss`) more robustly than an index check.
3. **Bundle both Rule 1 fixes into Task 2's commit** rather than splitting into a separate commit. The dpi.py fix is only discoverable through the main.py work (you cannot observe pmv2=True in `python main.py` output until both are fixed), so they form one logical change. Commit message calls out both fixes explicitly.

## Deviations from Plan

### Auto-fixed Issues (Rule 1 - Bug)

**1. [Rule 1 - Bug] main.py literal pattern silently failed on 64-bit Python**

- **Found during:** Task 2 verification (`python main.py` printed `pmv2=False` with `ret=0` from the DPI call)
- **Root cause:** Default ctypes argtypes for `ctypes.windll.user32.SetProcessDpiAwarenessContext` pass Python `int -4` as `c_int` (4 bytes). On x64 Windows, the calling convention loads RCX from a 32-bit source, leaving the upper 32 bits undefined. The result is that Windows sees a handle like `0x????????FFFFFFFC` instead of `0xFFFFFFFFFFFFFFFC`, which is not a recognized `DPI_AWARENESS_CONTEXT` sentinel, and the call silently returns FALSE (no `GetLastError` set because the function simply doesn't find a match).
- **Fix:** Added a single line between `import ctypes` and the try: `ctypes.windll.user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]`. With `c_void_p`, ctypes sign-extends -4 to the full pointer width (8 bytes on x64), Windows receives `0xFFFFFFFFFFFFFFFC`, the PMv2 sentinel, and the call returns TRUE.
- **Why this cannot be done the way the plan literally specified:** The plan demanded body[1] be the try and inside-body[0] be the literal `SetProcessDpiAwarenessContext(-4)` call. Any fix that doesn't add a pre-call statement (changing `-4` to `c_void_p(-4)`, wrapping the call, etc.) would also violate the literal byte-for-byte spec of the arg. Adding the argtypes assignment on line 2 is the smallest possible diff that actually works on x64.
- **Files modified:** `main.py` (+1 line for argtypes setup)
- **Commit:** `a28c2ac`

**2. [Rule 1 - Bug] dpi.is_pmv2_active() always returned False on x64, even after PMv2 was successfully set**

- **Found during:** Task 2 verification (even after fixing #1 above, `pmv2=False` persisted because the DETECTOR was also broken)
- **Root cause:** `dpi._u32()` returned `ctypes.windll.user32` without setting argtypes/restype. `GetThreadDpiAwarenessContext()` returned a value typed as `c_int` — truncating the 8-byte HANDLE to 4 bytes. `AreDpiAwarenessContextsEqual(cur, -4)` was called with two `c_int` args — again truncating HANDLE to 4 bytes. Even when the underlying handles would have matched, the truncated comparison returned 0.
- **Fix:** `_u32()` now sets argtypes/restype on `GetThreadDpiAwarenessContext`, `AreDpiAwarenessContextsEqual`, `GetDpiForSystem`, `GetSystemMetrics`, and `GetSystemMetricsForDpi` on first access, gated by a module-level `_SIGNATURES_APPLIED` flag so that reloads do not attempt to re-register (preserving plan-02's `test_module_importable_without_side_effects`). `is_pmv2_active()` now wraps the `-4` sentinel in `wintypes.HANDLE(-4)` so that x64 Python sign-extends it correctly.
- **Files modified:** `src/magnifier_bubble/dpi.py` (+33 lines)
- **Commit:** `a28c2ac` (bundled with main.py fix — same root cause, same task)

### Non-bug deviations

**3. test_main_py_dpi_call_is_second_statement replaced with a scan-based equivalent + new ordering-invariant test**

- **Reason:** The plan's test hard-coded `tree.body[1] == ast.Try`. After the x64 bug fix, `body[1]` is the argtypes Assign and `body[2]` is the Try. The hard index test would fail.
- **Fix:** Replaced with two tests:
  - `test_main_py_dpi_call_is_present_and_targets_pmv2` — uses `_find_dpi_try()` helper to scan `tree.body` for the first Try whose inner body calls `SetProcessDpiAwarenessContext`. Then asserts the arg is literally `-4` via the same `ast.UnaryOp(USub, ast.Constant(4))` pattern the plan specified.
  - `test_main_py_dpi_runs_before_any_third_party_import` — NEW. Preserves the *actual* OVER-05 invariant semantically: the DPI try must appear before any import of `magnifier_bubble`, `tkinter`, `mss`, `PIL`, or `win32api`/`win32con`/`win32gui`. Stdlib imports (`ctypes`, `os`, `sys`) are allowed anywhere in the prologue.
- **Net effect:** The new pair is STRICTLY STRONGER than the plan's single index check. It catches the real regression mode (future phases adding `import mss` to main.py) robustly, while tolerating the argtypes setup that the x64 bug fix requires. Test count goes from the plan-stated 9 to 10 on Windows (still satisfies the plan's "≥33 tests passing on Windows" success criterion — we deliver 34).
- **Commit:** `f26beac`

## Issues Encountered

**1. python main.py printed `pmv2=False` on first run** — root cause investigated via `ctypes.get_last_error()`, direct `SetProcessDpiAwarenessContext` + `GetThreadDpiAwarenessContext` comparison with explicit wintypes signatures, and AST structure analysis. Diagnosed as the x64 HANDLE size mismatch described in Deviation #1. Fixed inline.

**2. Pre-existing `numpy==2.2.6` install failure on Python 3.14** — out of scope per deviation rule scope boundary. Logged in plan-02 SUMMARY and STATE.md Phase 8 blocker; does not affect Phase 1 runtime. Not re-fixed.

**3. pytest_asyncio DeprecationWarning noise (1129 warnings)** — pre-existing from plan 02, not introduced by this plan, out of scope.

## Outstanding Manual Verification

- **ROADMAP Success Criterion 5 (150%-scaled display visual check):** Per VALIDATION.md Manual-Only Verifications table, the real-display 150% scale verification is a post-plan human task. The automated portion (grep for [dpi] line with all six fields) PASSES. The dev box primary monitor is at 100% (dpi=96), so the automated smoke cannot exercise the non-100% path — logging this as the canonical post-plan manual to run once a 150%-scaled monitor is available.

## Next Phase Readiness

**Ready for Phase 2 (bubble window):**

- `magnifier_bubble.app.main()` is the drop-in Phase 2 entry point — Phase 2 replaces the body with the Tk root creation and mainloop, while main.py remains untouched (DPI-first ordering preserved by the statically-pinned test lint)
- `tests/test_main_entry.py::test_main_py_does_not_import_mss_or_tkinter_at_top_level` + `test_main_py_dpi_runs_before_any_third_party_import` will catch any Phase 2/3 regression that accidentally adds `import tkinter` or `import mss` to main.py
- `AppState` observer fan-out is ready for Phase 2 window to subscribe to position/size changes
- `dpi.report()` + `is_pmv2_active()` now ACTUALLY WORK on x64 (after the bug fix), so Phase 2's per-monitor DPI queries can rely on them

**No new blockers carried forward.** Pre-existing blockers (Python 3.14 wheels, numpy build, Cornerstone DPI interaction) remain logged in STATE.md for their respective future phases.

## Self-Check: PASSED

- [x] `main.py` exists at repository root (17 lines)
- [x] `src/magnifier_bubble/app.py` exists (41 lines)
- [x] `tests/test_main_entry.py` exists (207 lines)
- [x] `src/magnifier_bubble/dpi.py` modified (115 -> 148 lines)
- [x] Commit `3c3d5d9` exists (feat(01-03): app.py Phase 1 entry)
- [x] Commit `a28c2ac` exists (feat(01-03): main.py shim + dpi.py x64 argtypes fix)
- [x] Commit `f26beac` exists (test(01-03): test_main_entry.py static lint + smoke)
- [x] `python -m pytest tests/ -v` exits 0 with 34 passed
- [x] `python main.py` exits 0 with three expected stdout lines including `pmv2=True`
- [x] `head -n 1 main.py` returns `import ctypes` exactly
- [x] `ast.parse(main.py).body[0]` is `ast.Import` whose `names[0].name == "ctypes"`
- [x] The DPI try/except is discoverable by scanning `tree.body` and no forbidden import precedes it
- [x] Fresh venv `/tmp/fresh/Scripts/python main.py` prints three log lines and exits 0 (Phase 1 runtime surface)

---
*Phase: 01-foundation-dpi*
*Completed: 2026-04-11*
