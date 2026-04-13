---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 04-02-PLAN.md (BubbleWindow canvas controls wiring + strip-aware HRGN bug fix)
last_updated: "2026-04-13T09:55:00Z"
progress:
  total_phases: 8
  completed_phases: 2
  total_plans: 11
  completed_plans: 9
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-10)

**Core value:** Clicks and touches pass through the magnified content area to whatever app is underneath — the bubble enhances vision without blocking the workflow.
**Current focus:** Phase 04 — controls-shape-resize

## Current Position

Phase: 04 (controls-shape-resize) — EXECUTING
Plan: 3 of 3

## Performance Metrics

**Velocity:**

- Total plans completed: 9
- Average duration: ~12 min
- Total execution time: ~1.75 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation-dpi | 3 | 15 min | 5 min |
| 02-overlay-window | 3 | 78 min | 26 min |
| 03-capture-loop | 1 | 8 min | 8 min |
| 04-controls-shape-resize | 2 | 47 min | 24 min |

**Recent Trend:**

- Last 5 plans: 03-01 (8 min), 03-02 (? min), 04-01 (7 min), 04-02 (40 min)
- Trend: Phase 04 Plan 02 hit a human-verify blocker in Task 3 (HRGN clip hid controls in circle/rounded) — fixed via strip-aware CombineRgn(RGN_OR) union; shapes.apply_shape gained backward-compat strip_top/strip_bottom kwargs; 2 extra regression tests in test_window_phase4.py (source-level kwarg check + runtime PtInRegion multi-shape hit test)

*Updated after each plan completion*

**Plan detail:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01-foundation-dpi P01 | 3 min | 3 | 8 |
| Phase 01-foundation-dpi P02 | 3 min | 2 | 4 |
| Phase 01-foundation-dpi P03 | 9min | 3 tasks | 4 files |
| Phase 02-overlay-window P01 | 4 min | 2 (TDD) | 4 |
| Phase 02-overlay-window P02 | 9 min | 2 tasks | 5 files |
| Phase 02-overlay-window P03 | 65 | 3 tasks | 7 files |
| Phase 03 P01 | 8 | 3 tasks | 3 files |
| Phase 04-controls-shape-resize P01 | 7 min | 3 tasks (TDD for 1+2) | 5 files |
| Phase 04-controls-shape-resize P02 | 40 min | 3 tasks (TDD for 1+2, human-verify for 3) | 4 files |

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
- [Phase 02-overlay-window]: Three-HWND WndProc chain required (parent + Tk frame child + canvas child) — Windows delivers WM_NCHITTEST to topmost HWND (canvas); single parent subclass insufficient for click-through
- [Phase 02-overlay-window]: Check 6 click-through gap deferred to Phase 4 — coordinate-translated WM_LBUTTONDOWN injection is the correct mechanism for a zoom app; raw HTTRANSPARENT blocked by Tk frame cross-process propagation
- [Phase 02-overlay-window]: [Phase 02-overlay-window/03]: install_child() added to wndproc.py for child HWND subclassing (canvas + frame); MA_NOACTIVATE via WM_MOUSEACTIVATE intercept at both parent and child WndProcs
- [Phase 02-overlay-window]: [Phase 02-overlay-window/03]: default shape changed to 'rect' in StateSnapshot — circle HRGN ill-defined before Phase 4 shape selector; rect gives unambiguous full-border visual
- [Phase 03]: Bumped Pillow pin from 11.3.0 to 12.1.1 -- Python 3.14.3 dev box has Pillow 12.1.1 installed; 11.3.0 has no cp314 wheel
- [Phase 03]: mss 10.1.0 confirmed importable on Python 3.14.3 (pure-Python py3-none-any wheel)
- [Phase 03]: CAPTUREBLT=0 hall-of-mirrors Path B defense set inside run() before mss.mss() construction
- [Phase 04-controls-shape-resize/01]: controls.py is stdlib-only (dataclasses + math); constants (DRAG_BAR_HEIGHT, CONTROL_BAR_HEIGHT, ZOOM_MIN/MAX/STEP, MIN_SIZE, MAX_SIZE) are REDECLARED (not imported) from hit_test / state so tests can import controls in isolation without Windows-only side effects
- [Phase 04-controls-shape-resize/01]: [Rule 1 bug fix] zoom_step semantics — plan prescribed snap-then-always-add which made zoom_step(2.13, +1) = 2.50 but plan's own test required == 2.25. Switched to "ceil-to-next-grid-point on +1, floor-to-prev-grid-point on -1" using math.floor/ceil. zoom_step(2.00, +1) == 2.25, zoom_step(2.13, +1) == 2.25, zoom_step(2.25, +1) == 2.50. User-visible behavior: pressing + on an off-grid value lands on the next visible 0.25 step.
- [Phase 04-controls-shape-resize/01]: layout_controls at the 150x150 minimum returns OVERLAPPING-ADJACENT rects (zoom_in [62..106) and resize [106..150) share an edge; zoom_out [0..44) has an 18 px gap before zoom_in). CTRL-09 only requires >= 44x44 and in-bounds — enforcing disjointness at the minimum would break the normal-size layout. Phase 04-02 must accept this and NOT attempt to fix it.
- [Phase 04-controls-shape-resize/01]: ButtonRect is a @dataclass(frozen=True) with fields (name: str, x: int, y: int, w: int, h: int). Hashable, immutable — safe for use as dict keys in Plan 04-02 observers if needed.
- [Phase 04-controls-shape-resize/01]: Wave 0 test scaffolding — tests/test_window_phase4.py (12 skip stubs for Plan 02) and tests/test_clickthru.py (10 skip stubs for Plan 03) let Plans 02/03 begin red-to-green work by replacing skip lines one test at a time. Skip messages reference the specific plan number.
- [Phase 04-controls-shape-resize/01]: tests/test_shapes_smoke.py extended with test_apply_shape_100_cycle_interleaved_resize_no_crash — 100 iterations of shape cycle interleaved with 5-size rotation on the Windows dev box. Pitfall F regression guard. Original 50-cycle test unchanged (backward compat).
- [Phase 04-controls-shape-resize/02]: [Rule 1 bug fix — Task 3 human-verify blocker] Cycling the shape button to "circle" or "rounded" made ALL controls unreachable because the HRGN clipped the full-width top/bottom strip corners. Fixed by adding optional `strip_top` / `strip_bottom` kwargs to `shapes.apply_shape` that union the shape region with two full-width strip rectangles via `CombineRgn(RGN_OR)`. Intermediate HRGNs (top_rgn, bot_rgn, shape_rgn after copy) are DeleteObject'd by us; only the final combined HRGN is passed to SetWindowRgn and becomes OS-owned on success — Pitfall 6 invariant preserved.
- [Phase 04-controls-shape-resize/02]: shapes.apply_shape signature lock relaxed — first 4 positional params (hwnd, w, h, shape) stay locked for Phase 2/3 call-site compatibility; any additional params must have defaults so older callers work unchanged. test_apply_shape_signature_locked in test_shapes_smoke.py now asserts `params[:4] == [...]` + extras-have-defaults instead of exact-4.
- [Phase 04-controls-shape-resize/02]: test_source_does_not_deleteobject_on_success in test_shapes_smoke.py tightened to `src.count("DeleteObject(rgn)") == 1` AND the call appears AFTER the `if result == 0:` line. Intermediate regions use different variable names (top_rgn, bot_rgn, shape_rgn) so their DeleteObject calls don't trip the invariant.
- [Phase 04-controls-shape-resize/02]: AppState observer `_on_state_change` diffs prev vs new snapshot — re-applies `shapes.apply_shape(strip_top=DRAG_STRIP_HEIGHT, strip_bottom=CONTROL_STRIP_HEIGHT)` on shape change, re-layouts + re-applies HRGN on size change, updates zoom text via `canvas.itemconfig` on zoom change. Observer never calls `state.set_*` (no re-entrancy).
- [Phase 04-controls-shape-resize/02]: Resize drag via `<B1-Motion>` + `root.geometry(f"{w}x{h}+{x}+{y}")` — NOT `SendMessageW(WM_SYSCOMMAND, SC_SIZE)`. Uses existing `_on_canvas_press/_on_canvas_drag/_on_canvas_release` bindings with two mutually-exclusive state slots (`_resize_origin` XOR `_drag_origin`); press decides exactly one via `hit_button`.
- [Phase 04-controls-shape-resize/02]: Regression test `test_all_buttons_hittable_in_every_shape` uses GetWindowRgn + PtInRegion to sample 5 points per button (4 corners + center) across all 3 shapes — direct Win32 proof the HRGN no longer clips control-button pixels.

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

Last session: 2026-04-13T09:55:00Z
Stopped at: Completed 04-02-PLAN.md (BubbleWindow canvas controls wiring + strip-aware HRGN bug fix)
Resume file: None

Next step: `/gsd:execute-plan 04 03` (execute Plan 04-03 — clickthru.py cross-process click injection + winconst.py extension + BubbleWindow content-zone wiring + --no-click-injection CLI fallback + Notepad/Cornerstone manual verification)
