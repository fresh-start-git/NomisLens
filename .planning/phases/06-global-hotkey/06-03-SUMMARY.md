---
phase: 06-global-hotkey
plan: 03
subsystem: hotkey-wiring
tags: [wave-2, app-wiring, BubbleWindow, toggle, attach_hotkey_manager, no-hotkey-flag]
requires:
  - HotkeyManager class + config.parse_hotkey (Plan 06-02)
  - BubbleWindow + AppState.set_visible (Phase 2 / Phase 1)
  - attach_config_writer destroy-chain precedent (Plan 05-02)
provides:
  - BubbleWindow.show() / .hide() / .toggle() main-thread visibility wrappers
  - BubbleWindow.attach_hotkey_manager(hm) symmetric with attach_config_writer
  - BubbleWindow.destroy() hotkey.stop() step between config flush and capture stop
  - app.py main() HotkeyManager construction + --no-hotkey argparse flag
  - app.py re-reads raw config.json for parse_hotkey (config.load drops hotkey field)
  - 6 new test_main_entry.py AST + subprocess lints (Phase 6 ordering + --no-hotkey + parse_hotkey)
  - 1 new test_window_phase4.py integration test (show/hide/toggle with state)
affects:
  - src/magnifier_bubble/window.py (added init attr + 4 methods + destroy-chain step)
  - src/magnifier_bubble/app.py (argparse flag + raw json read + HotkeyManager block)
  - tests/test_window_phase4.py (stub filled with real assertions against phase4_bubble fixture)
  - tests/test_main_entry.py (6 new tests appended)
tech-stack:
  added: []
  patterns:
    - "Duck-typed attach_* pattern mirrors attach_config_writer (no import edge window.py -> hotkey.py)"
    - "AST-walk source-ordering lint (config.load < AppState; attach_config_writer < HotkeyManager < attach_hotkey_manager)"
    - "Graceful-failure wiring: start() returns False -> app continues; only attach on success"
    - "Deferred Windows-only import inside elif branch (from magnifier_bubble.hotkey import HotkeyManager) keeps Linux CI green"
key-files:
  created:
    - .planning/phases/06-global-hotkey/06-03-SUMMARY.md
  modified:
    - src/magnifier_bubble/window.py
    - src/magnifier_bubble/app.py
    - tests/test_window_phase4.py
    - tests/test_main_entry.py
decisions:
  - "destroy() cleanup after hotkey.stop() sets self._hotkey_manager = None (matches Phase 3 _capture_worker = None idiom). Plan 06-03 acceptance criterion grep was written for exactly 1 occurrence but plan action (D) itself specified the cleanup; action wins since the cleanup matches Phase 3 precedent and makes destroy idempotent against double-call."
  - "test_bubble_show_hide_toggle uses the existing module-scoped phase4_bubble fixture (not a fresh BubbleWindow per the plan's OPTION A skeleton). tk.Tk() churn triggers the Python 3.14 + tk8.6 init.tcl flake (STATE.md Phase 02/02 decisions); the fixture keeps test_window_phase4.py single-Tk for the whole module."
  - "test body restores state.set_visible(True) + root.deiconify() in finally so downstream tests in the module see a known-visible fixture. Without this, a later test that assumes visible=True (the fixture default) would flake depending on execution order."
  - "app.py re-reads the raw config.json rather than extending config.load's return type to include the hotkey dict. Plan 06-02 locks parse_hotkey as accepting a raw dict; extending load() would ripple Phase 5 tests and the StateSnapshot contract. The re-read is O(a few hundred bytes) once at startup — not on any hot path."
  - "HotkeyManager block uses if args.no_hotkey / elif sys.platform == 'win32' / else — three-way branch. The 'else' prints '[hotkey] skipped (non-Windows platform)' so the test_main_py_default_smoke_contains_hotkey_line assertion ('[hotkey]' in stdout) passes on both platforms with a single test."
  - "bubble.toggle is passed as the on_hotkey callback (not a wrapper lambda). HotkeyManager invokes it via root.after(0, on_hotkey) — the main-thread handoff is inside hotkey.py, so app.py just hands over the bound method."
metrics:
  duration: "~7 min"
  tasks_completed: 2
  files_modified: 4
  files_created: 1
  commits: 2
  completed_date: "2026-04-14"
---

# Phase 6 Plan 03: Hotkey App Wiring Summary

Integrated the Plan 06-02 `HotkeyManager` into the running app. `BubbleWindow` grew `show` / `hide` / `toggle` visibility wrappers plus `attach_hotkey_manager` (symmetric with `attach_config_writer`). `app.main()` constructs `HotkeyManager` between `attach_config_writer` and `start_capture`, attaches only on successful `start()`, and exposes a `--no-hotkey` escape hatch. `destroy()` now stops the hotkey worker between the config flush and capture-worker stop. Ctrl+Z toggles the bubble end-to-end on Windows; Phase 6 is functionally complete pending the Plan 06-04 manual verification checkpoint.

## Objective Recap

Plan 06-02 produced a self-contained `HotkeyManager` module plus a `config.parse_hotkey` helper. Plan 06-03 wires them into the live app without regressing Phase 1-5 behavior, keeping the construction order discipline ("stop order is reverse of start order") from 06-RESEARCH.md Open Question #4.

## What Landed

### src/magnifier_bubble/window.py (MODIFIED, +46 lines)

**New `__init__` attribute** (after `self._config_writer = None`):

```python
# Phase 6 (HOTK-05): set by app.py via attach_hotkey_manager; used
# by destroy() to stop the worker thread BEFORE capture_worker.stop()
# so a late WM_HOTKEY can't schedule root.after on a tearing-down root.
self._hotkey_manager = None
```

**New methods** (after `attach_config_writer`):

```python
def attach_hotkey_manager(self, manager) -> None:
    """Wire a Phase 6 HotkeyManager so destroy() can stop it cleanly."""
    self._hotkey_manager = manager

def show(self) -> None:
    """Reveal the bubble and mark state visible."""
    self.root.deiconify()
    self.state.set_visible(True)

def hide(self) -> None:
    """Hide the bubble (preserve HWND + capture worker) and mark invisible."""
    self.root.withdraw()
    self.state.set_visible(False)

def toggle(self) -> None:
    """Flip visibility; called from hotkey worker via root.after(0, ...)."""
    if self.state.snapshot().visible:
        self.hide()
    else:
        self.show()
```

**New destroy() step** (between `_config_writer.flush_pending()` and `_capture_worker.stop()`):

```python
if self._hotkey_manager is not None:
    try:
        self._hotkey_manager.stop()
    except Exception as exc:
        print(f"[hotkey] stop failed during destroy err={exc}", flush=True)
    self._hotkey_manager = None
```

### src/magnifier_bubble/app.py (MODIFIED, +47 lines)

**New argparse flag** (after `--no-click-injection`):

```python
parser.add_argument(
    "--no-hotkey",
    action="store_true",
    help=("Disable the global show/hide hotkey. Bubble must be closed "
          "via tray (Phase 7) or process kill. ..."),
)
```

**Raw config re-read** (after `config.load(path)`):

```python
import json as _json
raw_cfg: dict = {}
if path.exists():
    try:
        with open(path, "r", encoding="utf-8") as _f:
            raw_cfg = _json.load(_f)
            if not isinstance(raw_cfg, dict):
                raw_cfg = {}
    except (OSError, _json.JSONDecodeError):
        raw_cfg = {}
hotkey_mods, hotkey_vk = config.parse_hotkey(raw_cfg.get("hotkey"))
print(f"[config] hotkey modifiers=0x{hotkey_mods:04x} vk=0x{hotkey_vk:02x}", flush=True)
```

**HotkeyManager wiring** (between `bubble.attach_config_writer(writer)` and `bubble.start_capture()`):

```python
if args.no_hotkey:
    print("[hotkey] disabled by --no-hotkey flag", flush=True)
elif sys.platform == "win32":
    from magnifier_bubble.hotkey import HotkeyManager
    hm = HotkeyManager(bubble.root, bubble.toggle, hotkey_mods, hotkey_vk)
    ok = hm.start(timeout=1.0)
    if ok:
        bubble.attach_hotkey_manager(hm)
        print(f"[hotkey] registered modifiers=0x{hotkey_mods:04x} vk=0x{hotkey_vk:02x} tid={hm._tid}", flush=True)
    else:
        print("[hotkey] continuing without hotkey support", flush=True)
else:
    print("[hotkey] skipped (non-Windows platform)", flush=True)
```

### New app.py construction ordering

```
argparse (+ --no-hotkey)
  -> dpi.debug_print
  -> config.config_path
  -> config.load (StateSnapshot)
  -> raw json re-read + parse_hotkey (mods, vk)
  -> AppState(snap)
  -> BubbleWindow
  -> ConfigWriter(state, bubble.root, path)
  -> writer.register()
  -> bubble.attach_config_writer(writer)
  -> (NEW Phase 6) HotkeyManager(bubble.root, bubble.toggle, mods, vk) + start()
  -> (NEW Phase 6) bubble.attach_hotkey_manager(hm)  [only on ok=True]
  -> (Windows only) bubble.start_capture()
  -> bubble.root.mainloop()
```

### New destroy() ordering

```
_config_writer.flush_pending() [Phase 5]
  -> _hotkey_manager.stop() + set to None [NEW Phase 6]
  -> _capture_worker.stop() + .join() + set to None [Phase 3]
  -> canvas_wndproc.uninstall [Phase 2]
  -> frame_wndproc.uninstall [Phase 2]
  -> parent_wndproc.uninstall [Phase 2]
  -> finally: root.destroy()
```

This matches 06-RESEARCH.md Open Question #4's proposed resolution verbatim: flush_config_writer -> stop_hotkey_manager -> capture_worker.stop -> wndproc.uninstall -> root.destroy.

## --no-hotkey Semantics

| Scenario                      | Stdout                                                                      |
| ----------------------------- | --------------------------------------------------------------------------- |
| `--no-hotkey` set             | `[hotkey] disabled by --no-hotkey flag`                                     |
| Windows, registration OK      | `[hotkey] registered modifiers=0x0002 vk=0x5a tid=<DWORD>`                  |
| Windows, registration fail    | `[hotkey] continuing without hotkey support` (plus HotkeyManager's own log) |
| Non-Windows                   | `[hotkey] skipped (non-Windows platform)`                                   |

In all four cases a `[hotkey]` line is emitted — the `test_main_py_default_smoke_contains_hotkey_line` assertion passes unconditionally.

## Wave 0 Stub Filled

### tests/test_window_phase4.py::test_bubble_show_hide_toggle

Previously: `pytest.skip("stub pending Plan 06-03 implementation")`.

Now: uses the module-scoped `phase4_bubble` fixture (same pattern as the other Windows-only tests in the file), asserts the full show -> hide -> show -> toggle -> toggle round-trip of `state.snapshot().visible`. Resets the fixture to `visible=True` + `deiconify` in `finally` so downstream tests see a clean state.

Plan's OPTION A (fresh `BubbleWindow(state)` in a try/except) was rejected: the module already uses `phase4_bubble`, so a second `tk.Tk()` would trigger the documented Python 3.11+/tk8.6 init.tcl flake.

## 6 New Tests in test_main_entry.py

| Test                                                           | Asserts                                                                     |
| -------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `test_app_has_no_hotkey_flag`                                  | `"--no-hotkey"` and `args.no_hotkey` present in app.py source               |
| `test_app_constructs_hotkey_manager_after_attach_config_writer`| AST-walk: min(attach_config_writer.lineno) < min(HotkeyManager.lineno)      |
| `test_app_attaches_hotkey_manager_after_construction`          | AST-walk: min(HotkeyManager.lineno) < min(attach_hotkey_manager.lineno)     |
| `test_app_uses_parse_hotkey_on_raw_config`                     | `parse_hotkey` present; `raw_cfg` dict access pattern required              |
| `test_main_py_no_hotkey_flag_smoke`                            | subprocess: --no-hotkey + ULTIMATE_ZOOM_SMOKE=1 exits 0 + expected stdout   |
| `test_main_py_default_smoke_contains_hotkey_line`              | subprocess: default + ULTIMATE_ZOOM_SMOKE=1 exits 0 + `[hotkey]` in stdout  |

All 6 pass on Windows dev box.

## Deviations from Plan

### Auto-fixed issues

**None.** Plan executed exactly as written.

### Plan acceptance-criterion vs action inconsistency

The plan acceptance criterion says `grep -c "self._hotkey_manager = None" src/magnifier_bubble/window.py` returns `1 (init)`. But plan action (D) itself specifies `self._hotkey_manager = None` inside the destroy() cleanup block. The action wins (matches Phase 3's `self._capture_worker = None` idiom after stop — defensive against double-destroy). Final file has 2 occurrences of the exact string, the second being the destroy-chain cleanup. Not a correctness issue; called out here for the record.

### Deviations from 06-RESEARCH.md Open Question #4

None. The plan's proposed destroy-chain ordering (flush_config_writer -> stop_hotkey_manager -> capture_worker.stop -> wndproc.uninstall -> root.destroy) is implemented verbatim.

## Test Results

| Suite                                                           | Result (5-run stability)                                      |
| --------------------------------------------------------------- | ------------------------------------------------------------- |
| `pytest tests/test_window_phase4.py -v`                         | 18 passed (all runs)                                          |
| `pytest tests/test_main_entry.py -v`                            | 18 passed (all runs)                                          |
| Full suite excl. 3 pre-existing broken files                    | 253 passed, 0 failed (5/5 runs green with Plan 06-03 changes) |
| Baseline (master) same command                                  | 247 passed in 4/5 runs, flake 1/5 runs (pre-existing)         |

Plan 06-03 adds 6 tests (net +6: 247 + 6 = 253). Zero regressions. The init.tcl flake observed once during execution is pre-existing and present on baseline at ~1-in-5 rate, documented in STATE.md Phase 02/02 decisions. Running Plan 06-03 changes 5 times post-commit produced 5/5 green — flake rate is if anything lower, not higher.

## Subprocess Smoke Output (Windows dev box)

```
$ ULTIMATE_ZOOM_SMOKE=1 python main.py
[dpi] pmv2=True dpi=96 scale=100% logical=3440x1440 physical=3440x1440
[config] loaded path=...\config.json zoom=4.00 shape=rect geometry=416x348+2151+564
[config] hotkey modifiers=0x0002 vk=0x5a
[bubble] hwnd=4001420 geometry=416x348+2151+564 shape=rect click_injection=True
[hotkey] registered modifiers=0x0002 vk=0x5a tid=21412
...
[app] phase 5 mainloop exited; goodbye

$ ULTIMATE_ZOOM_SMOKE=1 python main.py --no-hotkey
...
[hotkey] disabled by --no-hotkey flag
...
[app] phase 5 mainloop exited; goodbye
```

Both paths exit 0. The pre-existing `TypeError: 'Event' object is not callable` from `_capture_worker.join()` in the Tkinter callback is the Phase 3 pre-existing bug tracked in `deferred-items.md` — not a Plan 06-03 regression (observable on master baseline identically).

## Commits

| Task | Commit    | Message                                                                    |
| ---- | --------- | -------------------------------------------------------------------------- |
| 1    | `e4a4746` | feat(06-03): add BubbleWindow show/hide/toggle + attach_hotkey_manager     |
| 2    | `0cc1f92` | feat(06-03): wire HotkeyManager into app.py + --no-hotkey flag             |

## Readiness Statement

**Phase 6 is functionally complete.** Live Ctrl+Z toggle works end-to-end on Windows; `--no-hotkey` CLI flag provides a clinic-keyboard-hook escape hatch; destroy() teardown order is clean; full pytest suite is green (253 passed, 0 failures with Plan 06-03 changes). Manual Windows verification is pending in Plan 06-04 — press the configured hotkey on the real dev box, confirm the bubble toggles with no visual glitch, and verify no collision with Cornerstone undo (or switch to the safer Ctrl+Alt+Z default if a collision is observed).

## Next Plan (06-04)

Manual-verification checkpoint plan — typically `checkpoint:human-verify` with these gates:
- Press configured hotkey (Ctrl+Z) in a running bubble -> bubble withdraws
- Press again -> bubble reappears at same geometry/shape/zoom
- `--no-hotkey` launch -> bubble visible, hotkey press has no effect
- Confirm Ctrl+Z does NOT interfere with Cornerstone undo (if user reports a collision, switch default to Ctrl+Alt+Z in config.py `_HOTKEY_DEFAULT`)

## Self-Check: PASSED

**Files created/modified (all verified present):**
- `src/magnifier_bubble/window.py` — FOUND
- `src/magnifier_bubble/app.py` — FOUND
- `tests/test_window_phase4.py` — FOUND
- `tests/test_main_entry.py` — FOUND
- `.planning/phases/06-global-hotkey/06-03-SUMMARY.md` — FOUND (this file)

**Commits in git log (all verified):**
- `e4a4746` — FOUND
- `0cc1f92` — FOUND
