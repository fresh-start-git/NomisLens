---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_plan: 3
status: unknown
stopped_at: Completed 02-02-PLAN.md (wndproc LONG_PTR subclass + shapes HRGN mask); Phase 02 plan 3/3 next
last_updated: "2026-04-11T22:53:09.041Z"
progress:
  total_phases: 8
  completed_phases: 1
  total_plans: 6
  completed_plans: 5
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-10)

**Core value:** Clicks and touches pass through the magnified content area to whatever app is underneath — the bubble enhances vision without blocking the workflow.
**Current focus:** Phase 02 — overlay-window

## Current Position

**Phase:** 02 (overlay-window) — EXECUTING
**Current Plan:** 3
**Total Plans in Phase:** 3
**Last Completed Plan:** 02-01 (winconst + hit_test pure-Python foundation)

## Performance Metrics

**Velocity:**

- Total plans completed: 4
- Average duration: 4.75 min
- Total execution time: 0.32 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation-dpi | 3 | 15 min | 5 min |
| 02-overlay-window | 1 | 4 min | 4 min |

**Recent Trend:**

- Last 5 plans: 01-01 (3 min), 01-02 (3 min), 01-03 (9 min), 02-01 (4 min)
- Trend: Phase 02 pure-Python plan 01 finished in 4 min with 2 Rule 1 test-code bug fixes (PEP 563 signature, docstring ast skip)

*Updated after each plan completion*

**Plan detail:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01-foundation-dpi P01 | 3 min | 3 | 8 |
| Phase 01-foundation-dpi P02 | 3 min | 2 | 4 |
| Phase 01-foundation-dpi P03 | 9min | 3 tasks | 4 files |
| Phase 02-overlay-window P01 | 4 min | 2 (TDD) | 4 |
| Phase 02-overlay-window P02 | 9 min | 2 tasks | 5 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Stack: Python 3.11.9 + tkinter + mss 10.1.0 + pywin32 311 + Pillow 11.3.0 + pystray 0.19.5 + PyInstaller 6.11.1 (from research/SUMMARY.md)
- Hotkey: `ctypes + user32.RegisterHotKey` directly (keyboard lib archived Feb 2026; pynput rejected for Win11 reliability)
- Resampling: Pillow BILINEAR (not LANCZOS) — 3–5x faster, needed for 30fps budget
- PhotoImage: single instance reused via `.paste()` — avoids CPython issue 124364 memory leak
- [Phase 01-foundation-dpi]: Kept src/magnifier_bubble/__init__.py at 0 bytes to prevent mss early-init DPI lock before main.py can set PMv2
- [Phase 01-foundation-dpi]: Segregated runtime vs dev deps: requirements.txt is PyInstaller input (6 pkgs); requirements-dev.txt is superset with pytest
- [Phase 01-foundation-dpi]: Deferred pyproject.toml [build-system]/[project] tables to Phase 8; Phase 1 pyproject is pytest config only
- [Phase 01-foundation-dpi/02]: AppState uses threading.Lock (not RLock); observer notifications fire AFTER releasing lock; snapshot() returns deep copy via dataclasses.asdict round-trip
- [Phase 01-foundation-dpi/02]: dpi.py has zero import-time side effects; lazy _u32() accessor + is_pmv2_active() guarded by sys.platform + try/except; SetProcessDpiAwarenessContext(-4) is main.py's job (Pattern 1), NEVER called from dpi.py
- [Phase 01-foundation-dpi/02]: is_pmv2_active() uses AreDpiAwarenessContextsEqual (not pointer identity) per research Pattern 3
- [Phase 01-foundation-dpi]: [Phase 01-foundation-dpi/03]: main.py is byte-for-byte literal except for line 2 argtypes setup; ctypes.windll.user32.SetProcessDpiAwarenessContext.argtypes = [c_void_p] is required for the DPI call to actually succeed on 64-bit Python (Rule 1 bug fix — default ctypes c_int truncates the HANDLE sentinel on x64)
- [Phase 01-foundation-dpi]: [Phase 01-foundation-dpi/03]: dpi._u32() now applies wintypes argtypes/restype on first access (guarded by _SIGNATURES_APPLIED) so GetThreadDpiAwarenessContext and AreDpiAwarenessContextsEqual see full-width HANDLEs on x64 — without this is_pmv2_active() returned False even after a successful PMv2 set
- [Phase 01-foundation-dpi]: [Phase 01-foundation-dpi/03]: test_main_entry.py uses scan-based discovery of the DPI try/except plus an explicit forbidden-imports-before-DPI ordering test, rather than a hard tree.body[1] index check — catches real Phase 3 regressions (e.g. accidental import mss in main.py) while tolerating the required argtypes setup line
- [Phase 02-overlay-window/01]: hit_test.py intentionally does NOT import winconst.py — the string->HT* bridge (drag->HTCAPTION, content->HTTRANSPARENT, control->HTCLIENT) lives in Plan 02's wndproc.py so compute_zone stays pure and CI-testable on non-Windows
- [Phase 02-overlay-window/01]: DRAG_BAR_HEIGHT = CONTROL_BAR_HEIGHT = 44 locked as hit_test.py module constants (CTRL-09 finger touch target) — Phase 4 resize grip will consume these, not hardcode
- [Phase 02-overlay-window/01]: compute_zone overlap rule: on tiny h<88 windows the drag band is tested first and wins; out-of-bounds returns "content" so WndProc produces HTTRANSPARENT and clicks pass through the SetWindowRgn-clipped corners
- [Phase 02-overlay-window/01]: winconst.py is pure constants (no functions/classes/imports beyond `from __future__ import annotations`) — tested by ast.walk lint. WS_EX_TRANSPARENT included as a DO-NOT-USE sentinel per PITFALLS.md Pitfall 1
- [Phase 02-overlay-window/01]: [Rule 1 bug fix] test_compute_zone_signature uses `inspect.signature(compute_zone, eval_str=True)` because `from __future__ import annotations` (PEP 563) makes sig.return_annotation the string "str", not the str type — without eval_str the plan-supplied test would never pass on any module with postponed annotations
- [Phase 02-overlay-window/01]: [Rule 1 bug fix] test_winconst_body_is_only_constants_and_future_import skips `ast.Expr(Constant(str))` docstring nodes before asserting the allowlist (ImportFrom + Assign) — verbatim plan code would have rejected the module docstring on body[0]
- [Phase 02-overlay-window]: [Phase 02-overlay-window/02]: [Rule 1 bug fix] pywin32 311 only binds CreateEllipticRgnIndirect / CreateRectRgnIndirect (not the 4-int forms the plan used). Swapped to the Indirect variants with a 4-tuple (left,top,right,bottom); structural lints still pass because the non-Indirect names are prefixes.
- [Phase 02-overlay-window]: [Phase 02-overlay-window/02]: [Rule 1 bug fix] wndproc.py docstring/comments cannot contain the substrings LOWORD / HIWORD / SetProcessDpiAwarenessContext because the plan's own lint tests forbid them. Rewrote the educational comments to describe the forbidden APIs without naming them literally.
- [Phase 02-overlay-window]: [Phase 02-overlay-window/02]: [Rule 1 test-infra fix] Added session-scoped tk_session_root + function-scoped tk_toplevel fixtures to tests/conftest.py. Per-test tk.Tk() churn triggers a flaky 'SourceLibFile panedwindow' TclError on Python 3.14 + tk8.6 (~2/5 full-suite runs). Shared root eliminates the race (0/8 post-fix failures). All Phase 2+ smoke tests should consume tk_toplevel.
- [Phase 02-overlay-window]: [Phase 02-overlay-window/02]: wndproc.py applies LONG_PTR-safe argtypes for SetWindowLongPtrW / GetWindowLongPtrW / CallWindowProcW / GetWindowRect / SendMessageW via a lazy _SIGNATURES_APPLIED sentinel — identical structural pattern to Phase 1 P03 dpi._u32. The WNDPROC thunk is stored on a WndProcKeepalive __slots__ container (new_proc, old_proc, hwnd) to prevent CPython GC — Pitfall A eliminated.
- [Phase 02-overlay-window]: [Phase 02-overlay-window/02]: shapes.apply_shape has EXACTLY one DeleteObject call, inside the 'if result == 0:' failure branch. On SetWindowRgn success the OS owns the HRGN and the app MUST NOT release it (Pitfall F / Pitfall 6). 50-cycle stress test (circle->rounded->rect->...) + 10-size resize stress pass with zero crashes.
- [Phase 02-overlay-window]: [Phase 02-overlay-window/02]: pywin32 311 cp314 wheel INSTALLED successfully on the Python 3.14.3 dev box — partial de-risk of the Phase 8 wheel-compatibility blocker. mss / Pillow / numpy / pyinstaller wheel checks remain pending for their respective plan gates.

### Pending Todos

None yet.

### Blockers/Concerns

- **Phase 2**: Touch click-through (WM_NCHITTEST → HTTRANSPARENT) cannot be fully verified without clinic touchscreen hardware
- **Phase 6**: Ctrl+Z vs. Cornerstone undo conflict must be confirmed with user before ship; safer default Ctrl+Alt+Z available
- **Phase 8**: Clinic AV product unknown; budget time for allowlisting on target PC
- **Phase 1 / runtime**: Cornerstone (legacy LOB) may conflict with Per-Monitor-V2 DPI awareness — needs empirical test
- **Phase 5 / runtime**: `config.json` in app directory may be blocked by clinic IT; have `%LOCALAPPDATA%` fallback ready
- **Phase 8 / packaging**: Dev box has Python 3.14.3 installed, not the research-specified 3.11.9. Phase 1 stdlib-only modules pass on 3.14.3 without issue, but PyInstaller 6.11.1 + mss 10.1.0 + pywin32 311 + Pillow 11.3.0 + numpy 2.2.6 wheel compatibility with 3.14 must be verified before Plan 03 (mss) or Phase 8 (packaging). Either install 3.11.9 side-by-side or confirm 3.14 wheels exist for all pinned deps.

## Session Continuity

Last session: 2026-04-11T22:53:09.036Z
Stopped at: Completed 02-02-PLAN.md (wndproc LONG_PTR subclass + shapes HRGN mask); Phase 02 plan 3/3 next
Resume file: None

Next step: `/gsd:execute-plan 02 02` (execute Plan 02-02 — wndproc.py WndProc subclass bridging hit_test strings to HT* constants)
