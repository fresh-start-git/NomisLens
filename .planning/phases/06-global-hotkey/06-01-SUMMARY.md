---
phase: 06-global-hotkey
plan: 01
subsystem: hotkey-scaffolding
tags: [wave-0, test-stubs, winconst, msdn-lint]
requires:
  - winconst.py Phase 4 additions (Phase 04)
  - tk_toplevel fixture (Phase 02)
  - conftest.py win_only marker (Phase 01)
provides:
  - 9 hotkey Win32 constants for Plans 06-02 / 06-03 to consume
  - 5 pure-Python structural lint stubs for hotkey.py (HOTK-01 + HOTK-05)
  - 3 Windows-only integration stubs for hotkey.py (HOTK-03 + HOTK-05)
  - 3 parser stubs in test_config.py (HOTK-04)
  - 1 visibility-wrapper stub in test_window_phase4.py (HOTK-03)
  - 9 parametrized winconst value lints enforcing MSDN-documented values
affects:
  - src/magnifier_bubble/winconst.py (append-only Phase 6 section)
  - tests/test_winconst.py (append-only parametrize entries)
  - tests/test_config.py (append-only section at EOF)
  - tests/test_window_phase4.py (append-only section at EOF)
tech-stack:
  added: []
  patterns:
    - "Wave 0 skip-stub pattern (3rd occurrence: Phase 04-01, Phase 05-01, Phase 06-01)"
    - "Pathlib-based module-existence probe before import (skip-friendly on Linux CI)"
    - "Parametrized winconst value lint against Microsoft Learn constants"
key-files:
  created:
    - tests/test_hotkey.py
    - tests/test_hotkey_smoke.py
    - .planning/phases/06-global-hotkey/deferred-items.md
  modified:
    - src/magnifier_bubble/winconst.py
    - tests/test_winconst.py
    - tests/test_config.py
    - tests/test_window_phase4.py
decisions:
  - "Wave 0 stubs use a pathlib.exists() probe BEFORE try/except import so linters on non-Windows CI can still skip cleanly without triggering ctypes import errors (pattern established Phase 04-01)"
  - "test_hotkey.py tests are pure-Python structural lints; test_hotkey_smoke.py holds all Windows-only integration — same separation as Phase 5 config / config_smoke split"
  - "All 3 test_config.py hotkey parser stubs guarded by `parse_hotkey` ImportError (not module-level skip) so the rest of test_config.py keeps running"
  - "test_window_phase4.py visibility stub guarded by hasattr(BubbleWindow, 'show'/'hide'/'toggle') — Plan 06-03 adds the methods to trigger auto-unskip"
metrics:
  duration: "~5.4 min"
  tasks_completed: 4
  files_modified: 4
  files_created: 3
  commits: 4
  completed_date: "2026-04-14"
---

# Phase 6 Plan 01: Hotkey Test Scaffolding Summary

Wave 0 test scaffolding + Win32 constant extension for Phase 6 RegisterHotKey work — 9 constants added to winconst.py with MSDN-verified values, 9 parametrized lints asserting those values, and 12 skip stubs across 4 test files that Plans 06-02 / 06-03 will flip to real assertions one test at a time.

## Objective Recap

Lay the Wave 0 foundation so Plans 02/03 can start red-to-green immediately:
- Every HOTK-* test referenced in 06-VALIDATION.md exists as a skip stub
- winconst.py exports every RegisterHotKey / GetMessage / error constant Plan 02 needs
- Full test suite stays green (no regressions)

## Constants Added to winconst.py

All 9 constants appended to the end of winconst.py in a `# ---- Phase 6 additions ----` section. Values cross-referenced against MSDN (same discipline as Phase 2/4 winconst extensions):

| Constant                           | Value     | Purpose                                                     |
| ---------------------------------- | --------- | ----------------------------------------------------------- |
| `MOD_ALT`                          | `0x0001`  | RegisterHotKey modifier: Alt                                |
| `MOD_CONTROL`                      | `0x0002`  | RegisterHotKey modifier: Ctrl                               |
| `MOD_SHIFT`                        | `0x0004`  | RegisterHotKey modifier: Shift                              |
| `MOD_WIN`                          | `0x0008`  | RegisterHotKey modifier: Windows key                        |
| `MOD_NOREPEAT`                     | `0x4000`  | Win7+ auto-repeat suppression                               |
| `VK_Z`                             | `0x5A`    | Virtual key code for default Ctrl+Alt+Z                     |
| `WM_HOTKEY`                        | `0x0312`  | GetMessage identifier for RegisterHotKey events             |
| `WM_QUIT`                          | `0x0012`  | PostThreadMessageW breakout signal                          |
| `ERROR_HOTKEY_ALREADY_REGISTERED`  | `1409`    | Graceful-fail error code for double-register                |

## Test File Inventory

**New files (2):**

| File                         | Tests | Platform       | Status            |
| ---------------------------- | ----- | -------------- | ----------------- |
| `tests/test_hotkey.py`       | 5     | any            | all skip (stub)   |
| `tests/test_hotkey_smoke.py` | 3     | Windows-only   | all skip (stub)   |

Test names — exact match to 06-VALIDATION.md:
- `tests/test_hotkey.py`:
  - `test_hotkey_uses_ctypes_not_keyboard_lib` (HOTK-01)
  - `test_winconst_mod_values_match_msdn` (HOTK-01)
  - `test_hotkey_applies_argtypes` (HOTK-01)
  - `test_hotkey_thread_is_non_daemon` (HOTK-05)
  - `test_register_and_unregister_in_same_function` (HOTK-05)
- `tests/test_hotkey_smoke.py`:
  - `test_wm_hotkey_toggles_visible_via_after` (HOTK-03)
  - `test_second_register_fails_gracefully` (HOTK-05)
  - `test_stop_posts_quit_and_joins` (HOTK-05)

**Extended files (3):**

| File                               | New stubs | New lints | Existing tests |
| ---------------------------------- | --------- | --------- | -------------- |
| `tests/test_winconst.py`           | 0         | 9 (pass)  | unchanged      |
| `tests/test_config.py`             | 3 (skip)  | —         | unchanged      |
| `tests/test_window_phase4.py`      | 1 (skip)  | —         | unchanged      |

Extended test names:
- `tests/test_config.py` (HOTK-04):
  - `test_hotkey_roundtrip`
  - `test_hotkey_defaults_on_corrupt`
  - `test_hotkey_rejects_unknown_modifier`
- `tests/test_window_phase4.py` (HOTK-03):
  - `test_bubble_show_hide_toggle`

## Verification Results

- `pytest tests/test_winconst.py -v` → **35 passed** (9 new Phase 6 lints all green)
- `pytest tests/test_hotkey.py tests/test_hotkey_smoke.py -v` → **8 skipped** (all 5+3 stubs) with messages referencing Plan 06-02
- `pytest tests/test_config.py tests/test_window_phase4.py -v` → **45 passed, 4 skipped** (3 parser stubs + 1 visibility stub, all reference 06-02 / 06-03)
- `pytest tests/` full-suite regression on my diff: **zero new failures** (the 6 pre-existing capture/window-integration failures reproduced identically on pre-change master — documented in `deferred-items.md`)

## Deviations from Plan

**None - plan executed exactly as written.**

Every constant value, test name, stub skeleton, and file-write location matched the plan verbatim. No Rule 1/2/3 auto-fixes required; no Rule 4 architectural questions surfaced. The one judgment call (documenting pre-existing unrelated test failures in deferred-items.md rather than fixing them) is an explicit scope-boundary decision, not a plan deviation.

## How Plan 06-02 Consumes These Stubs

Plan 06-02 (hotkey.py implementation) will:
1. Create `src/magnifier_bubble/hotkey.py` — this alone flips every `_require_hotkey()` skip from "hotkey.py not yet implemented" to "stub pending Plan 06-02 implementation" (the per-test skip line inside each body).
2. Replace each `pytest.skip("stub pending Plan 06-02 implementation")` line with the real assertion body:
   - HOTK-01 lints in `test_hotkey.py` use `_hotkey_src()` string matches (no "import keyboard", "import ctypes" present, argtypes applied, etc.)
   - HOTK-05 lint `test_hotkey_thread_is_non_daemon` loads the module and inspects the created Thread object's `.daemon` attribute (must be False)
   - Integration tests in `test_hotkey_smoke.py` use the `tk_toplevel` fixture to verify PostThreadMessageW marshalling and WM_HOTKEY round-trips

Plan 06-02 also lands `config.parse_hotkey` — the 3 stubs in `test_config.py` auto-unskip from their import-guard (they progress to the stub-pending skip, which 06-02 then replaces).

Plan 06-03 adds `BubbleWindow.show()/hide()/toggle()` — the `test_bubble_show_hide_toggle` stub auto-progresses from hasattr-guard to stub-pending, and 06-03 replaces the stub-pending skip with the real assertion.

## Follow-Up Items (in `deferred-items.md`)

6 pre-existing failures + 4 errors reproducing `TypeError: 'Event' object is not callable` in `test_capture_smoke.py`, `test_window_integration.py`, and `test_window_config_integration.py` — out of Plan 06-01 scope (confirmed identical failure set on pre-change baseline via `git stash`). Noted for a future Phase 04-04 diagnostic plan (per existing STATE.md Pending Todos).

## Self-Check: PASSED

- [x] tests/test_hotkey.py exists (created, 5 stubs)
- [x] tests/test_hotkey_smoke.py exists (created, 3 stubs)
- [x] src/magnifier_bubble/winconst.py has 9 Phase 6 constants
- [x] tests/test_winconst.py has 9 new parametrize entries (35 tests pass)
- [x] tests/test_config.py has 3 new parser stubs at EOF
- [x] tests/test_window_phase4.py has 1 new visibility stub at EOF
- [x] Commit f508908 exists (Task 1: winconst + lint)
- [x] Commit 6597d97 exists (Task 2: test_hotkey.py)
- [x] Commit bab465e exists (Task 3: test_hotkey_smoke.py)
- [x] Commit 1667fe6 exists (Task 4: test_config.py + test_window_phase4.py + deferred-items.md)
