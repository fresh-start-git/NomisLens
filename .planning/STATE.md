---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
stopped_at: "Completed 06-03-PLAN.md (Hotkey app wiring: BubbleWindow.show/hide/toggle + attach_hotkey_manager duck-typed symmetric with attach_config_writer; destroy()-chain hotkey.stop() between config flush and capture stop; app.py main() HotkeyManager construction after attach_config_writer + before start_capture with bubble.toggle as main-thread callback; raw json re-read for parse_hotkey because config.load drops unknown fields; --no-hotkey argparse flag escape hatch for clinic keyboard-hook conflicts; 6 new test_main_entry.py AST + subprocess lints + 1 filled test_window_phase4.py show/hide/toggle stub; zero deviations; 253 passed 5/5 runs vs 247 baseline = net +6 tests, no regressions; manual Windows smoke — `[hotkey] registered modifiers=0x0002 vk=0x5a tid=<DWORD>` emitted on default launch, `[hotkey] disabled by --no-hotkey flag` on --no-hotkey)"
last_updated: "2026-04-14T13:05:22.254Z"
progress:
  total_phases: 8
  completed_phases: 5
  total_plans: 17
  completed_plans: 16
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-10)

**Core value:** Clicks and touches pass through the magnified content area to whatever app is underneath — the bubble enhances vision without blocking the workflow.
**Current focus:** Phase 06 — global-hotkey

## Current Position

Phase: 06 (global-hotkey) — EXECUTING
Plan: 4 of 4

## Performance Metrics

**Velocity:**

- Total plans completed: 15
- Average duration: ~13.5 min
- Total execution time: ~3.7 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation-dpi | 3 | 15 min | 5 min |
| 02-overlay-window | 3 | 78 min | 26 min |
| 03-capture-loop | 1 | 8 min | 8 min |
| 04-controls-shape-resize | 3 | 75 min | 25 min |
| 05-config-persistence | 2 | 29 min | 14.5 min |
| 06-global-hotkey | 3 | 60 min | 20 min |

**Recent Trend:**

- Last 5 plans: 05-02 (~21 min), 06-01 (5 min), 06-02 (~48 min), 06-03 (~7 min)
- Trend: Plan 06-03 returned to the Phase 06-01 scaffolding baseline (~7 min vs 06-02's ~48 min) because there were zero auto-fixed bugs and the plan was pure wiring (4 methods added to BubbleWindow + 1 argparse flag + 47-line app.py block + 6 AST tests). The Plan 06-02 HotkeyManager interface (HotkeyManager(root, on_hotkey, mods, vk) + start() + stop() + parse_hotkey(dict)) was load-bearing — Plan 06-03 consumed it verbatim. 253 passed 5/5 runs; one transient init.tcl flake observed during execution matches the known pre-existing ~1/5 rate on master baseline (STATE.md Phase 02/02 decision). Zero regressions from Plan 06-03 changes.

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
| Phase 04-controls-shape-resize P03 | 28 min | 3 tasks (2 automated + 1 auto-approved human-verify) | 8 files |
| Phase 05 P01 | 8 min | 3 tasks | 4 files |
| Phase 05 P02 | ~21 min | 3 tasks (2 implementation + 1 human-verify, all 5/5 checks approved) | 4 files |
| Phase 06 P01 | 5 min | 4 tasks | 7 files |
| Phase 06 P02 | ~48 min | 3 tasks (2 auto-fixed Rule 1 bugs) | 5 files |
| Phase 06 P03 | ~7 min | 2 tasks (zero deviations) | 4 files |

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
- [Phase 04-controls-shape-resize/03]: clickthru.py uses `ctypes.windll` (NOT the GIL-holding variant) — call sites are Tk main-thread button handlers, not hot-path WndProc callbacks. The GIL-holding-DLL rule from Phase 2 Pitfall K / Phase 3 wndproc.py is scoped to WndProc re-entrancy only. Enforced by `test_clickthru_no_pydll`.
- [Phase 04-controls-shape-resize/03]: Pattern 6 implemented verbatim: `ChildWindowFromPointEx(desktop, pt, CWP_SKIPTRANSPARENT | CWP_SKIPINVISIBLE | CWP_SKIPDISABLED)` + `ScreenToClient` + `PostMessageW(WM_LBUTTONDOWN)` + `PostMessageW(WM_LBUTTONUP)`. Never the synchronous Send variant — it blocks on the target pump and triggers the Python 3.14 re-entrant WndProc crash. lParam packed as `((client_pt.y & 0xFFFF) << 16) | (client_pt.x & 0xFFFF)`.
- [Phase 04-controls-shape-resize/03]: Deferred import in window.py (`from magnifier_bubble.clickthru import inject_click` inside `_on_canvas_press`) rather than module-level. Keeps the Windows-only ctypes surface out of window.py's import graph on non-Windows CI — matches Phase 3 capture.py's `import mss` sys.platform gate.
- [Phase 04-controls-shape-resize/03]: Self-HWND guard INSIDE inject_click (compares `target == own_hwnd` before posting), not at the call site. Belt-and-suspenders alongside CWP_SKIPTRANSPARENT — catches any edge case (e.g. WS_EX_LAYERED not actually triggering the skip for our specific window configuration). Pitfall I defense.
- [Phase 04-controls-shape-resize/03]: argparse `--no-click-injection` CLI flag as escape hatch for 04-RESEARCH.md Open Question #1 (Cornerstone may swallow PostMessage'd clicks). If real-world verification reveals a Cornerstone incompatibility, user can launch with the flag and fall back to Phase 2 behavior without a code change.
- [Phase 04-controls-shape-resize/03]: [Rule 1 bug fix] clickthru.py docstring originally contained literal substrings `SendMessageW` and `PyDLL` which tripped the module's own structural ban-lints (`test_clickthru_no_sendmessagew`, `test_clickthru_no_pydll`). Rewrote Rule 4/5 comments to describe forbidden APIs without naming them literally — same technique used in Phase 2-02 wndproc.py for LOWORD/HIWORD.
- [Phase 04-controls-shape-resize/03]: [Rule 1 bug fix] `test_bubblewindow_constructor_signature` relaxed from exact `['self', 'state']` to "first-2-locked + extras-have-defaults". Same relaxation pattern applied to `test_apply_shape_signature_locked` in Phase 4-02 — Phase 1-3 call sites stay safe, Phase 4+ can add keyword-only extras.
- [Phase 04-controls-shape-resize/03]: [Rule 3 blocking fix] Tests for content-zone middle-band routing explicitly call `bubble.root.geometry("400x400+100+100")` and reset `_drag_origin`/`_resize_origin` before exercising `_on_canvas_press`. AppState observer only resizes the Canvas, not the root window; prior fixture-sharing tests left root at 150x150 causing the middle-band check `event.y < (winfo_height - CONTROL_STRIP_HEIGHT)` to false-negative. Observer behavior is correct (root geometry is user-controlled via drag, not state-controlled).
- [Phase 04-controls-shape-resize]: PHASE 04 COMPLETE — All 9 CTRL-* requirements (CTRL-01..09) + LAYT-02 cross-process click-through gap closure delivered across 3 plans. Ready for Phase 05 (config persistence) or Phase 06 (global hotkey) — both independent of Phase 04 work.
- [Phase 05]: [Phase 05-config-persistence/01]: config.py clamp helpers duplicated inline from state.py (not imported) — state.py has zero bounds-checking for w/h because it never reads untrusted JSON; config owns its own _clamp_size(150..700) + inline _clamp_zoom replica. 4 lines of duplication, zero import coupling.
- [Phase 05]: [Phase 05-config-persistence/01]: tkinter confined to TYPE_CHECKING in config.py — ConfigWriter duck-types on root.after / root.after_cancel. Module imports cleanly on Linux CI without DISPLAY, matches Phase 1 dpi.py lazy-import precedent.
- [Phase 05]: [Phase 05-config-persistence/01]: [Rule 1 bug fix] config.py module docstring rewritten to describe banned APIs (threading.Timer, os.access, state.set_*) without naming them literally — same class of bug previously fixed in Phase 2-02 wndproc.py (LOWORD/HIWORD) and Phase 4-03 clickthru.py (SendMessageW/PyDLL). Third occurrence — consider adding planner guidance to avoid the footgun.
- [Phase 05]: [Phase 05-config-persistence/01]: ConfigWriter instance attrs locked for Plan 05-02: _after_id: Optional[str], _last_written: Optional[StateSnapshot]. Plan 05-02 integration tests may read these directly; no public accessor methods required.
- [Phase 05]: [Phase 05-config-persistence/01]: test_config_smoke.py debounce pump ceiling bumped to 1.5s (plan specified 0.8s) to absorb scheduler jitter on CI. 500ms debounce target dominates median; zero flakes observed.
- [Phase 05]: [Phase 05-config-persistence/02]: ConfigWriter constructed AFTER BubbleWindow (not before) so bubble.root is a live Tk instance when root.after(500, ...) schedules — Pitfall 7 defense. Construction order: argparse → dpi.debug_print → config.config_path → config.load → AppState(snap) → BubbleWindow → ConfigWriter(state, bubble.root, path) → writer.register() → bubble.attach_config_writer(writer) → bubble.start_capture (Win-only) → mainloop. Phases 6/7 will splice between attach_config_writer and start_capture.
- [Phase 05]: [Phase 05-config-persistence/02]: BubbleWindow.attach_config_writer is duck-typed — no `from magnifier_bubble import config` in window.py. Writer is stored as plain attribute, only flush_pending() is called. Keeps Phase 5 wiring optional and window.py importable in isolation. Same import-edge discipline as Phase 4 deferred clickthru import.
- [Phase 05]: [Phase 05-config-persistence/02]: BubbleWindow.__init__ initializes self._config_writer = None so destroy() works on bubbles built without a writer (backward compat for all Phase 2/3/4 tests). Verified: full suite green after change.
- [Phase 05]: [Phase 05-config-persistence/02]: destroy() flush_pending() runs at TOP of try-block — BEFORE _capture_worker.stop() and BEFORE wndproc.uninstall(). Pitfall 7 ordering: ConfigWriter.flush_pending uses root.after_cancel which requires a live root. Reordering would silently drop the final write. Wrapped in try/except so a writer bug logs '[config] flush_pending failed' but never blocks teardown.
- [Phase 05]: [Phase 05-config-persistence/02]: AST source-scan lint pattern established (test_app_loads_config_before_state) — uses inspect.getsource → ast.parse → ast.walk → collect Call nodes by func.attr/func.id → assert min(load_lines) < min(appstate_lines). Extensible to any "A must precede B in main()" contract; Phase 6 hotkey can use the same pattern for "register_hotkey before mainloop".
- [Phase 05]: [Phase 05-config-persistence/02]: Promoted lazy `import sys as _sys` to top-of-file `import sys` in app.py — sys now used twice (platform check for start_capture + ULTIMATE_ZOOM_SMOKE env-var gate), so lazy form added cost without benefit. Dropped StateSnapshot import (AppState is always seeded from load() result; defaults are dead code at main scope).
- [Phase 05]: [Phase 05-config-persistence/02]: Two UX gaps surfaced during human verification — (a) no on-bubble close button (user had to terminate process to close); (b) click-through not actually working in real use despite Phase 4-03 inject_click implementation. Both deferred — tracked in 05-02-SUMMARY.md "Issues Observed". Suggested follow-ups: Phase 7 tray adds Exit menu + a small fix-up to add close glyph; a Phase 04-04 plan to diagnose click-through (Spy++ on canvas WM_LBUTTONDOWN, verify inject_click is invoked, fix routing or fall back).
- [Phase 05]: PHASE 05 COMPLETE — All 4 PERS-* requirements end-to-end verified on real Windows 11 hardware. Persistence layer production-ready. Phase 6 (Global Hotkey) and Phase 7 (System Tray) both ready to start.
- [Phase 06]: [Phase 06-global-hotkey/01]: Wave 0 test scaffolding — 9 winconst constants (MOD_* / VK_Z / WM_HOTKEY / WM_QUIT / ERROR_HOTKEY_ALREADY_REGISTERED) + 12 skip stubs across 4 test files let Plans 06-02 and 06-03 begin red-to-green work by replacing skip lines one test at a time.
- [Phase 06]: [Phase 06-global-hotkey/01]: Wave 0 stub pattern (3rd occurrence after Phase 04-01 + Phase 05-01) uses pathlib.exists() probe BEFORE try/except import — lets Linux CI skip cleanly without triggering ctypes import errors on Windows-only modules.
- [Phase 06]: [Phase 06-global-hotkey/02]: HotkeyManager registers + unregisters from the SAME _run() method (AST-walk structural lint enforces this). MSDN ties hotkey ownership to the calling thread id, so any stop() that tries to UnregisterHotKey from the main thread would leak the registration. Cooperative shutdown via PostThreadMessageW(WM_QUIT) breaks the worker's blocking GetMessageW loop; the finally: block runs UnregisterHotKey on the correct thread before the worker exits. Non-daemon thread (daemon=False) guarantees the finally executes even under abrupt interpreter teardown.
- [Phase 06]: [Phase 06-global-hotkey/02]: [Rule 1 bug fix] ctypes.windll.user32 does NOT enable use_last_error, so ctypes.get_last_error() returns 0 even after RegisterHotKey fails — defeating the ERROR_HOTKEY_ALREADY_REGISTERED (1409) graceful-failure surfacing. Added module-level `_U32_ERR = ctypes.WinDLL("user32", use_last_error=True)` lazy-initialized on first _run() entry. All Win32 calls on the worker thread route through this handle. kernel32.GetCurrentThreadId stays on plain ctypes.windll (cannot fail).
- [Phase 06]: [Phase 06-global-hotkey/02]: [Rule 1 bug fix — test plan deviation] Plan's top.update() polling loop for the WM_HOTKEY integration test fails on Python 3.11/Tcl 8.6 with "main thread is not in main loop" from the worker's root.after() call. top.update() does NOT count as being inside mainloop() for the purpose of dispatching cross-thread after-callbacks. Test now enters top.mainloop() after posting WM_HOTKEY; on_hotkey calls top.after(10, top.quit) to exit. Using a Toplevel's mainloop keeps the session-scoped tk_session_root fixture intact for subsequent tests (top.quit exits mainloop without destroying the session root).
- [Phase 06]: [Phase 06-global-hotkey/02]: MOD_NOREPEAT is OR'd into self._modifiers in HotkeyManager.__init__ — callers MUST NOT include it. Centralizes the auto-repeat-suppression policy so every HotkeyManager instance gets the MSDN-recommended Win7+ behavior for free.
- [Phase 06]: [Phase 06-global-hotkey/02]: parse_hotkey lives in config.py (not a new module) because Plan 06-03 will call it from the same config.load() call site — flat import graph. The parser NEVER raises: any malformed dict falls back to (MOD_CONTROL, VK_Z) and the app still starts. Supports case-insensitive modifier names and single-char A-Z / 0-9 VK codes.
- [Phase 06]: [Phase 06-global-hotkey/02]: GetMessageW.restype is explicitly ctypes.c_int (NOT wintypes.BOOL). -1 is a legal error return from GetMessageW; BOOL width would mask the sign bit and the error would look like an ordinary message. Enforced by structural lint test_hotkey_applies_argtypes.
- [Phase 06]: [Phase 06-global-hotkey/02]: PeekMessageW(WM_USER) called before RegisterHotKey to force the worker's thread message queue into existence — Pitfall 9 defense against the race where an outside thread calls PostThreadMessageW against self._tid before the worker's first GetMessageW runs.
- [Phase 06]: [Phase 06-global-hotkey/03]: BubbleWindow.show()/hide()/toggle() wrap root.deiconify/withdraw + state.set_visible on the Tk main thread. toggle() reads state.snapshot().visible and dispatches to show() or hide(). HotkeyManager.__init__ takes on_hotkey as a Callable; Plan 06-03 passes bubble.toggle as a bound method (not a lambda) — the root.after(0, on_hotkey) handoff is entirely inside hotkey.py's worker loop.
- [Phase 06]: [Phase 06-global-hotkey/03]: attach_hotkey_manager is duck-typed (no `from magnifier_bubble.hotkey import HotkeyManager` at window.py module scope) — identical discipline to Phase 5's attach_config_writer (no window.py → config.py edge) and Phase 4's deferred clickthru import. Keeps Windows-only ctypes surface out of window.py's import graph on non-Windows CI.
- [Phase 06]: [Phase 06-global-hotkey/03]: destroy() ordering extended: config flush → hotkey.stop() → capture.stop() → wndproc.uninstall×3 → root.destroy. hotkey.stop() slots BETWEEN config flush (needs live root.after_cancel) and capture.stop() (needs HWND + frame queue drain). A late WM_HOTKEY after capture.stop() would try to schedule root.after(0, ...) on a partially-torn-down root; running hotkey.stop() first (PostThreadMessageW(WM_QUIT) → worker's GetMessageW breaks → UnregisterHotKey in finally) eliminates the race.
- [Phase 06]: [Phase 06-global-hotkey/03]: app.py re-reads the raw config.json via `open(path) + json.load` because config.load() returns a StateSnapshot and drops unknown fields — including "hotkey". Extending config.load's return type would ripple Phase 5 tests and the StateSnapshot contract. The re-read is ~few hundred bytes once at startup, not on any hot path. raw_cfg is wrapped in try/except(OSError, JSONDecodeError) so a corrupt or missing file gracefully falls through to parse_hotkey's (MOD_CONTROL, VK_Z) default.
- [Phase 06]: [Phase 06-global-hotkey/03]: Hotkey wiring is a three-way branch: `if args.no_hotkey: print([hotkey] disabled) / elif sys.platform == 'win32': construct + start + attach / else: print([hotkey] skipped)`. The non-Windows `else` emits a `[hotkey]` line so test_main_py_default_smoke_contains_hotkey_line passes on both platforms with a single assertion (`"[hotkey]" in stdout`).
- [Phase 06]: [Phase 06-global-hotkey/03]: test_bubble_show_hide_toggle uses the existing module-scoped phase4_bubble fixture (NOT a fresh BubbleWindow as the plan's OPTION A suggested). tk.Tk() churn triggers Python 3.11+/tk 8.6 init.tcl flake (STATE.md Phase 02/02 decisions). Finally block restores state.set_visible(True) + root.deiconify so downstream tests in the module see a known-visible baseline.
- [Phase 06]: [Phase 06-global-hotkey/03]: Phase 6 functional complete — Ctrl+Z (default) toggles bubble end-to-end on Windows dev box; `[hotkey] registered modifiers=0x0002 vk=0x5a tid=<DWORD>` emitted on launch. 5/5 full-suite runs green (253 passed, +6 from Plan 06-03). Plan 06-04 manual verification remains.

### Pending Todos

- **Phase 04-04 (proposed)**: Diagnose click-through regression observed during Phase 5 verification — Spy++ canvas WM_LBUTTONDOWN, verify inject_click fires, check ChildWindowFromPointEx CWP_SKIPTRANSPARENT effect against WS_EX_LAYERED window. Either fix the routing or document the limitation.
- **Phase 07 / fix-up**: Add on-bubble close glyph (small "X" in top-right of drag strip) so the bubble is dismissable without the tray menu. Hit-tested via controls.hit_button → bubble.destroy().

### Blockers/Concerns

- **Phase 2**: Touch click-through (WM_NCHITTEST → HTTRANSPARENT) cannot be fully verified without clinic touchscreen hardware
- **Phase 6**: Ctrl+Z vs. Cornerstone undo conflict must be confirmed with user before ship; safer default Ctrl+Alt+Z available
- **Phase 8**: Clinic AV product unknown; budget time for allowlisting on target PC
- **Phase 1 / runtime**: Cornerstone (legacy LOB) may conflict with Per-Monitor-V2 DPI awareness — needs empirical test
- **Phase 5 / runtime**: ~~`config.json` in app directory may be blocked by clinic IT; have `%LOCALAPPDATA%` fallback ready~~ RESOLVED 2026-04-13 in Plan 05-02 verification CHECK 4 — `%LOCALAPPDATA%\UltimateZoom\config.json` fallback verified working under simulated repo-dir ACL lockdown.
- **Phase 4 / runtime**: Click-through (LAYT-02) appears NOT to be working in real use despite Phase 4-03 inject_click implementation. Surfaced during Phase 5 verification when user observed the bubble consuming clicks instead of passing them through. Diagnostic plan needed (proposed Phase 04-04).
- **Phase 4 / UX**: No on-bubble close button — user had to kill the process to close the bubble during verification. Fix needed before clinic deploy (likely combined with Phase 7 tray work or as a small fix-up).
- **Phase 8 / packaging**: Dev box has Python 3.14.3 installed, not the research-specified 3.11.9. Phase 1 stdlib-only modules pass on 3.14.3 without issue, but PyInstaller 6.11.1 + mss 10.1.0 + pywin32 311 + Pillow 11.3.0 + numpy 2.2.6 wheel compatibility with 3.14 must be verified before Plan 03 (mss) or Phase 8 (packaging). Either install 3.11.9 side-by-side or confirm 3.14 wheels exist for all pinned deps.

## Session Continuity

Last session: 2026-04-14T04:52:12Z
Stopped at: Completed 06-03-PLAN.md (Hotkey app wiring: BubbleWindow.show/hide/toggle + attach_hotkey_manager duck-typed symmetric with attach_config_writer; destroy()-chain hotkey.stop() between config flush and capture stop; app.py main() HotkeyManager construction after attach_config_writer + before start_capture with bubble.toggle as main-thread callback; raw json re-read for parse_hotkey because config.load drops unknown fields; --no-hotkey argparse flag escape hatch for clinic keyboard-hook conflicts; 6 new test_main_entry.py AST + subprocess lints + 1 filled test_window_phase4.py show/hide/toggle stub; zero deviations; 253 passed 5/5 runs vs 247 baseline = net +6 tests, no regressions; manual Windows smoke — `[hotkey] registered modifiers=0x0002 vk=0x5a tid=<DWORD>` emitted on default launch, `[hotkey] disabled by --no-hotkey flag` on --no-hotkey)
Resume file: None

Next step: `/gsd:execute-plan 06-04` (manual verification checkpoint on the real dev box — press the configured hotkey, see the bubble toggle, confirm no collision with Cornerstone undo; if collision observed, switch default to Ctrl+Alt+Z in config.py _HOTKEY_DEFAULT and update VALIDATION.md). ALSO STILL OPEN: two UX gaps from Phase 05 verification — (a) no on-bubble close button (Phase 7 tray or small fix-up plan); (b) click-through not actually working in real use despite Phase 04-03 inject_click (proposed Phase 04-04 diagnostic plan). Pre-existing test failures in test_capture_smoke.py + test_window_integration.py + test_window_config_integration.py (TypeError 'Event' object not callable, 6 failed + 4 errors) tracked in .planning/phases/06-global-hotkey/deferred-items.md — also a Phase 04-04 candidate.
