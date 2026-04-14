---
phase: 05-config-persistence
plan: 02
subsystem: infra
tags: [config, json, persistence, tkinter, debounce, observer, ast-lint, integration]

# Dependency graph
requires:
  - phase: 05-config-persistence
    provides: config.config_path / config.load / config.write_atomic / config.ConfigWriter (Plan 05-01)
  - phase: 02-overlay-window
    provides: BubbleWindow class with destroy() WM_DELETE_WINDOW handler
  - phase: 01-foundation-dpi
    provides: AppState observer, app.main() entry shape
provides:
  - app.py main() integrated with config load BEFORE AppState construction (PERS-03 startup wiring)
  - app.py ConfigWriter construction AFTER BubbleWindow with bubble.root (PERS-02 wiring)
  - BubbleWindow.attach_config_writer(writer) — duck-typed setter for the writer reference
  - BubbleWindow.destroy() flush_pending() at TOP of try-block, BEFORE capture/WndProc teardown (PERS-04 shutdown flush)
  - AST/source-scan lints in tests/test_main_entry.py guarding call ordering
  - Four-test BubbleWindow destroy-flush contract suite in tests/test_window_config_integration.py
  - Manual verification on Windows 11 dev box (5/5 checks passed)
affects: [phase-06, phase-07, phase-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Public method stores duck-typed shutdown hook; destroy() flushes SYNC before teardown (re-usable for Phase 6 hotkey cleanup + Phase 7 tray cleanup)"
    - "AST source-scan lint asserts call ordering in main() (extends Phase 1 DPI-before-import lint pattern to integration boundaries)"
    - "Duck-typed integration without import edge — window.py never imports magnifier_bubble.config so Phase 5 stays loose-coupled to Phase 2"
    - "Try/except wrapper around shutdown-hook call so a writer bug never strands the process with a live window"

key-files:
  created:
    - tests/test_window_config_integration.py
  modified:
    - src/magnifier_bubble/app.py
    - src/magnifier_bubble/window.py
    - tests/test_main_entry.py

key-decisions:
  - "ConfigWriter constructed AFTER BubbleWindow (not before) so bubble.root is a live Tk instance when root.after(500, ...) schedules — Pitfall 7 defense"
  - "writer.register() + bubble.attach_config_writer(writer) both fire BEFORE bubble.root.mainloop() so user mutations reach the observer from the very first event"
  - "BubbleWindow does NOT import magnifier_bubble.config — writer is duck-typed (only flush_pending() is called). Keeps Phase 5 wiring optional and window.py testable in isolation"
  - "self._config_writer initialized to None in __init__ so destroy() works on bubbles built without a writer (Phase 2/3/4 tests + non-Phase-5 paths stay green)"
  - "flush_pending() wrapped in try/except inside destroy() — a writer bug logs '[config] flush_pending failed' but never blocks capture/WndProc teardown"
  - "flush_pending() runs at the TOP of destroy()'s try-block, BEFORE _capture_worker.stop() and BEFORE wndproc.uninstall() — Pitfall 7 ordering: must execute while root.after_cancel still has a live Tk root"
  - "Promoted lazy 'import sys as _sys' to top-of-file 'import sys' — sys is now used in two places (platform check + smoke gate) so the lazy form added cost without benefit"
  - "Dropped StateSnapshot import from app.py — AppState is now ALWAYS seeded from config.load() (which never raises and always returns a StateSnapshot), so the dataclass default-construction path is dead code"

patterns-established:
  - "AST lint pattern: scan target module via inspect.getsource → ast.parse → ast.walk → collect Call nodes → assert min(load_lines) < min(appstate_lines). Extensible to any 'A must precede B in main()' contract"
  - "Fake-writer spy via types.SimpleNamespace + counter closure — isolates BubbleWindow.destroy() from the full AppState/ConfigWriter stack while still proving the call contract"
  - "Plan 05-02 establishes the canonical app.main() shape for Phases 6-8: argparse → dpi.debug_print → config load → AppState → BubbleWindow → ConfigWriter → register → attach → start_capture → mainloop. Phase 6 hotkey will splice between attach_config_writer and start_capture; Phase 7 tray will splice before start_capture"

requirements-completed: [PERS-01, PERS-02, PERS-03, PERS-04]

# Metrics
duration: 21min
completed: 2026-04-13
---

# Phase 05 Plan 02: Config Persistence Integration Summary

**Wired Plan 05-01's config module into app startup (load before AppState) and BubbleWindow shutdown (flush_pending before Tk teardown), closing PERS-03 restore-on-launch and PERS-04 flush-on-shutdown end-to-end with 5/5 manual checks signed off on the Windows 11 dev box.**

## Performance

- **Duration:** ~21 min (8 min implementation across 2 commits + ~13 min human verification)
- **Started:** 2026-04-13T20:30:09Z (immediately after Plan 05-01 docs commit)
- **Task 1 commit:** 2026-04-13T20:34:02Z
- **Task 2 commit:** 2026-04-13T20:37:01Z
- **Human verification approved:** 2026-04-13T~20:51Z
- **Tasks:** 3 (2 implementation + 1 human-verify checkpoint)
- **Files modified:** 4 (3 modified, 1 created)

## Accomplishments

- `src/magnifier_bubble/app.py` main() now loads persisted config BEFORE constructing AppState — bubble launches restore last position/size/zoom/shape (PERS-03).
- `src/magnifier_bubble/app.py` constructs ConfigWriter AFTER BubbleWindow with `bubble.root`, calls `writer.register()` to wire the AppState.on_change observer, and hands the writer to `bubble.attach_config_writer(writer)` so destroy() can flush (PERS-02 + PERS-04 startup-side wiring).
- `src/magnifier_bubble/window.py` BubbleWindow gains `_config_writer` attribute, `attach_config_writer()` public method, and a try/except-guarded `flush_pending()` call at the TOP of destroy()'s try-block — synchronous flush before capture/WndProc teardown so the WM_DELETE_WINDOW path catches any pending debounce write (PERS-04).
- `tests/test_main_entry.py` extended with two AST/source-scan lint tests (`test_app_loads_config_before_state` + `test_app_wires_config_writer`) — structural guarantees against future regression of the call ordering and ConfigWriter wiring.
- `tests/test_window_config_integration.py` new file with four Windows-only unit tests using a `types.SimpleNamespace` fake-writer spy: attribute-set verification, exactly-one flush-on-destroy, no-AttributeError-without-writer, and exception-swallow robustness.
- All 5 manual checks on the Windows 11 dev box passed: happy-path round-trip, burst-debounce (single write after 10 rapid taps), flush-on-shutdown (mid-debounce close still persists), %LOCALAPPDATA% fallback under repo-dir ACL lockdown, and corrupt-config graceful degradation.
- Phase 5 is COMPLETE — all 4 PERS-* requirements end-to-end verified on real hardware. Both plans (05-01 + 05-02) green.

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire config.load + ConfigWriter into app.py main()** — `8b8ffa5` (feat)
2. **Task 2: BubbleWindow.attach_config_writer + destroy() flush** — `0380522` (feat)
3. **Task 3: Human verification checkpoint** — no commit (pure observation/sign-off; user replied `approved` for all 5 checks)

_Note: Tasks 1 and 2 were declared `tdd="true"` in the plan but the implementation arrived in a single commit per task rather than the canonical RED → GREEN split. The new tests landed alongside the production change in the same commit; both `feat(05-02): wire config load ...` and `feat(05-02): add BubbleWindow.attach_config_writer ...` include their respective test additions. Test-then-implementation discipline preserved within each commit; granularity below the per-task commit not exposed in git history._

**Plan metadata:** (final docs commit covers this SUMMARY + STATE.md + ROADMAP.md updates)

## Files Created/Modified

- `src/magnifier_bubble/app.py` — modified: main() now resolves config_path → load → AppState(snap) → BubbleWindow → ConfigWriter(state, bubble.root, path) → register → attach_config_writer → start_capture → mainloop. Top-of-file `import sys` (was lazy `import sys as _sys`). Dropped StateSnapshot import. New `[config] loaded path=... zoom=... shape=... geometry=...` boot print. Phase 5 docstring + goodbye line. (+43 -34)
- `src/magnifier_bubble/window.py` — modified: `self._config_writer = None` initialized in __init__; new `attach_config_writer(writer)` public method (duck-typed, no config import); destroy() try-block now opens with a try/except-wrapped `self._config_writer.flush_pending()` BEFORE the existing capture worker stop and WndProc uninstall chain. (+33 -0)
- `tests/test_main_entry.py` — modified: appended two new AST/source-scan lint tests; extended subprocess smoke assertions to check for the new `[config] loaded` line and the Phase 5 goodbye line. (+85 -0)
- `tests/test_window_config_integration.py` — new: four Windows-only unit tests using `types.SimpleNamespace` fake-writer spies to verify the destroy-flush contract in isolation from the full AppState/ConfigWriter stack. (+95 -0)

## Decisions Made

- **ConfigWriter construction order**: writer is constructed AFTER `BubbleWindow(state)` because `tk.Tk.after(500, ...)` requires a live root. Constructing earlier would either crash or register against a dead root. Tradeoff: writer can't observe pre-bubble mutations, but app.py never mutates state before the bubble exists, so the window is empty.
- **Duck-typed integration**: `BubbleWindow.attach_config_writer` accepts ANY object with a `flush_pending()` method — no import of `magnifier_bubble.config` in window.py. Keeps the import graph free of Phase 5 coupling so the bubble can still be constructed in isolation (current Phase 2/3/4 tests do exactly this) and so future test stubs don't need to subclass ConfigWriter.
- **Backward-compat None default**: `self._config_writer = None` initialized in __init__ even though attach is mandatory in production. Cost: one branch in destroy(). Benefit: every existing test that constructs a BubbleWindow without wiring Phase 5 keeps working unchanged. Confirmed by full suite green.
- **Try/except around flush_pending in destroy()**: a writer bug must NEVER strand the process with a live Tk window + live capture thread + live WndProc. Wrapping the flush call in try/except + a `[config]` prefixed error log lets shutdown proceed even if the writer is broken — verified by `test_destroy_swallows_flush_exception`.
- **Flush-before-everything-else ordering**: `flush_pending()` runs at the TOP of destroy()'s try-block — BEFORE `_capture_worker.stop()`, BEFORE any `wndproc.uninstall(...)`, BEFORE `self.root.destroy()`. Pitfall 7 from 05-RESEARCH.md: `root.after_cancel` requires a live root, and `ConfigWriter.flush_pending` uses `after_cancel` to drain a pending debounce. Reordering would silently drop the final write.
- **AST lint over runtime check**: `test_app_loads_config_before_state` parses app.py source and asserts `min(load_lines) < min(appstate_lines)` rather than spawning a subprocess and grepping output. Faster (no subprocess), deterministic (no flake), and surfaces the exact line numbers in the failure message. Same technique already used by Phase 1's main.py DPI-first lint — Phase 5 extends the pattern to integration boundaries.

## Deviations from Plan

None — plan executed exactly as written across both implementation tasks. The verbatim main() body specified in Task 1 and the verbatim destroy() body specified in Task 2 were used unchanged. All acceptance criteria green on first verification run. All 5 manual checks passed without follow-up.

## Issues Encountered

None. Pre-existing test failures in Phase 3 capture-worker teardown (documented in `deferred-items.md` from Plan 05-01) remained unchanged; none introduced by this plan.

## User Setup Required

None — no external service configuration. Config persistence uses local filesystem only (app directory primary, %LOCALAPPDATA%\UltimateZoom fallback).

## Issues Observed (Deferred to Future Phases)

During the Task 3 human verification, the user surfaced two UX gaps that are NOT scoped to Phase 5 but should be addressed before clinic deployment:

1. **No close button on the bubble window** — the user had to terminate the Python process (Ctrl-C in console / Task Manager) to close the bubble. The bubble currently has no on-window UI affordance for shutdown. WM_DELETE_WINDOW is wired (and Phase 5 verified that the destroy chain runs cleanly on it), but there is no visible button or gesture to fire it. Likely fix: small "X" glyph in the top-right of the drag strip, hit-tested via `controls.hit_button` and dispatched to `bubble.destroy()`. **Suggested home: Phase 7 (System Tray) Exit menu — and also a separate small fix-up plan to add an on-bubble close button so the bubble is dismissable without the tray.**
2. **No click-through on the overlay window** — the user observed that clicks in the middle content zone are NOT passing through to the application underneath. This was supposed to be closed by Phase 4 Plan 04-03 (`clickthru.inject_click` via `PostMessageW + ChildWindowFromPointEx CWP_SKIPTRANSPARENT`), but real-world use during Phase 5 verification revealed the click-through is either not firing or not reaching the target window. Possible causes: (a) the canvas is intercepting clicks before they reach `_on_canvas_press`'s click-injection branch; (b) `CWP_SKIPTRANSPARENT` is not actually skipping our WS_EX_LAYERED window; (c) the target HWND lookup is returning the desktop instead of the underlying app. **Suggested home: a Phase 4 fix-up plan (call it 04-04) — investigate with Spy++ on the canvas WM_LBUTTONDOWN path, verify `inject_click` is invoked, and either fix the routing or add a fallback path.** Note: the `--no-click-injection` CLI flag is also currently the OPPOSITE of helpful here — the user wants click-through ON, not OFF. Reproduce + diagnose before patching.

Both items are tracked here for the Phase 4 fix-up + Phase 7 tray work. Neither blocks Phase 5 sign-off.

## Next Phase Readiness

- **Phase 5 COMPLETE.** All four PERS-* requirements (PERS-01 atomic write, PERS-02 debounced observer, PERS-03 restore on launch, PERS-04 flush on shutdown) end-to-end verified on real Windows 11 hardware. Persistence layer is production-ready.
- **Phase 6 (Global Hotkey) ready to start.** Independent of Phase 4/5 wiring; can begin immediately. The canonical app.main() shape established here gives Phase 6 a clean splice point: insert hotkey thread construction between `bubble.attach_config_writer(writer)` and `start_capture()`, and add a `bubble.attach_hotkey(hk)` shutdown hook mirroring `attach_config_writer` for clean unregistration.
- **Phase 7 (System Tray) ready to start.** Same splice-point pattern; tray icon construction goes between attach_config_writer and start_capture, with a `bubble.attach_tray(icon)` shutdown hook.
- **Two deferred UX gaps (close button, click-through)** flagged above for follow-up plans. Neither is a Phase 5 regression.

---
*Phase: 05-config-persistence*
*Completed: 2026-04-13*

## Self-Check: PASSED

- FOUND: src/magnifier_bubble/app.py (modified per commit 8b8ffa5)
- FOUND: src/magnifier_bubble/window.py (modified per commit 0380522)
- FOUND: tests/test_main_entry.py (modified per commit 8b8ffa5)
- FOUND: tests/test_window_config_integration.py (created per commit 0380522)
- FOUND: commit 8b8ffa5 (Task 1 — feat: wire config load + ConfigWriter into app.py main())
- FOUND: commit 0380522 (Task 2 — feat: add BubbleWindow.attach_config_writer + destroy flush)
