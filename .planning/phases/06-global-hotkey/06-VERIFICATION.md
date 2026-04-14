---
phase: 06-global-hotkey
verified: 2026-04-13T00:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
gaps: []
human_verification:
  - test: "Confirm REQUIREMENTS.md HOTK-02 checkbox updated to [x]"
    expected: "HOTK-02 line reads '- [x] **HOTK-02**' and traceability table shows 'Complete'"
    why_human: "REQUIREMENTS.md is a manually-maintained doc; automated checks confirmed the manual sign-off exists in 06-04-SUMMARY.md (CHECK 3 pass) but the doc itself still shows '[ ]' Pending"
  - test: "Confirm ROADMAP.md 06-04-PLAN.md line updated to [x]"
    expected: "The 06-04-PLAN.md entry has a [x] checkbox indicating the manual verification plan completed"
    why_human: "ROADMAP.md still shows '- [ ] 06-04-PLAN.md' — the plan completed but the tracking checkbox was not updated after 06-04-SUMMARY.md was committed"
---

# Phase 6: Global Hotkey Verification Report

**Phase Goal:** Register a system-wide Ctrl+Alt+Z hotkey (default; configurable) that toggles the magnifier bubble visible/hidden from any app context, with graceful failure if the hotkey is already claimed.
**Verified:** 2026-04-13
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                  | Status     | Evidence                                                                                                      |
|----|----------------------------------------------------------------------------------------|------------|---------------------------------------------------------------------------------------------------------------|
| 1  | Hotkey toggles bubble visible/hidden (HOTK-03)                                        | VERIFIED   | `BubbleWindow.show/hide/toggle` in window.py:443-458; wired via `bubble.toggle` in app.py:119; integration test `test_bubble_show_hide_toggle` passes |
| 2  | Hotkey fires while Cornerstone or any other app has focus (HOTK-02)                   | VERIFIED   | CHECK 3 in 06-04-SUMMARY.md: "pass — Fired from Cornerstone focus; no focus theft"; `RegisterHotKey(hWnd=None)` registers at thread-queue level (system-wide) |
| 3  | ctypes + user32.RegisterHotKey used; no keyboard library (HOTK-01)                    | VERIFIED   | `hotkey.py` imports only `ctypes`, `threading`, `wintypes`; `test_hotkey_uses_ctypes_not_keyboard_lib` asserts absence of `keyboard`, `pynput`, `global_hotkeys` |
| 4  | Hotkey configurable via config.json; Ctrl+Alt+Z default (HOTK-04)                     | VERIFIED   | `config.parse_hotkey` in config.py:245-275; `_HOTKEY_DEFAULT = (MOD_CONTROL | MOD_ALT, VK_Z)`; CHECK 4 manual pass confirms config.json override picked up on relaunch |
| 5  | Graceful failure if already registered; clean unregister on exit (HOTK-05)            | VERIFIED   | `HotkeyManager.start()` returns False + logs 1409 message; `finally: user32.UnregisterHotKey` in `_run()`; `daemon=False` ensures finally runs; CHECK 5B pass (clean relaunch without 1409) |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact                                  | Expected                                              | Status     | Details                                                                                              |
|-------------------------------------------|-------------------------------------------------------|------------|------------------------------------------------------------------------------------------------------|
| `src/magnifier_bubble/hotkey.py`          | HotkeyManager class, non-daemon worker, ctypes Win32  | VERIFIED   | 278 lines; `class HotkeyManager` at line 135; `daemon=False`; Register/Unregister share `_run()`     |
| `src/magnifier_bubble/winconst.py`        | 9 Phase 6 constants with MSDN-correct values          | VERIFIED   | Phase 6 additions section: MOD_ALT=0x0001, MOD_CONTROL=0x0002, MOD_SHIFT=0x0004, MOD_WIN=0x0008, MOD_NOREPEAT=0x4000, VK_Z=0x5A, WM_HOTKEY=0x0312, WM_QUIT=0x0012, ERROR_HOTKEY_ALREADY_REGISTERED=1409 |
| `src/magnifier_bubble/config.py`          | `parse_hotkey(raw)` helper; Ctrl+Alt+Z default        | VERIFIED   | `def parse_hotkey` at line 245; `_HOTKEY_DEFAULT = (MOD_CONTROL | MOD_ALT, VK_Z)` at line 242      |
| `src/magnifier_bubble/window.py`          | show/hide/toggle + attach_hotkey_manager + destroy order | VERIFIED | `attach_hotkey_manager` at line 427; `show/hide/toggle` at lines 443-458; `_hotkey_manager.stop()` in destroy at lines 754-762, BEFORE `_capture_worker.stop()` |
| `src/magnifier_bubble/app.py`             | HotkeyManager wired after attach_config_writer; --no-hotkey flag | VERIFIED | `--no-hotkey` argparse at line 36; `parse_hotkey` call at line 76; `HotkeyManager(` at line 117; `bubble.attach_hotkey_manager(hm)` at line 125 |
| `tests/test_hotkey.py`                    | 5 pure-Python structural lints (HOTK-01, HOTK-05)    | VERIFIED   | 5 test functions, all real assertions (not stubs); passes on any platform                            |
| `tests/test_hotkey_smoke.py`              | 3 Windows-only integration tests (HOTK-03, HOTK-05)  | VERIFIED   | 3 real test bodies; `pytestmark` win32-only; uses WM_HOTKEY PostThreadMessageW exercise              |
| `tests/test_config.py` (hotkey stubs)    | 3 HOTK-04 parser tests                               | VERIFIED   | `test_hotkey_roundtrip`, `test_hotkey_defaults_on_corrupt`, `test_hotkey_rejects_unknown_modifier` — all real assertions, default correctly `(MOD_CONTROL | MOD_ALT, VK_Z)` |
| `tests/test_window_phase4.py` (toggle)   | 1 HOTK-03 visibility wrapper test                    | VERIFIED   | `test_bubble_show_hide_toggle` at line 584 — real show/hide/toggle cycle against `phase4_bubble` fixture; not a stub |
| `.planning/phases/06-global-hotkey/06-04-SUMMARY.md` | Manual verification results with user sign-off | VERIFIED | Exists; all CHECKs 0-5 recorded; option-b (Ctrl+Alt+Z) chosen; status COMPLETE                |

### Key Link Verification

| From                              | To                                          | Via                                              | Status  | Details                                                                                                     |
|-----------------------------------|---------------------------------------------|--------------------------------------------------|---------|-------------------------------------------------------------------------------------------------------------|
| `hotkey.py::_run()`               | `ctypes.windll.user32.RegisterHotKey`       | Worker thread calls `user32.RegisterHotKey(None, _HOTKEY_ID, mods, vk)` | WIRED | Line 236; argtypes applied via `_apply_signatures`                                                 |
| `hotkey.py::_run()` finally block | `ctypes.windll.user32.UnregisterHotKey`     | `finally: user32.UnregisterHotKey(None, _HOTKEY_ID)` in same `_run()` function | WIRED | Line 265; AST-walk lint `test_register_and_unregister_in_same_function` enforces same-function co-location |
| `hotkey.py::_run()` WM_HOTKEY path | `root.after(0, on_hotkey)`                 | `self._root.after(0, self._on_hotkey)` inside GetMessageW loop | WIRED | Line 258; wrapped in try/except RuntimeError for teardown safety                                   |
| `app.py`                          | `magnifier_bubble.hotkey.HotkeyManager`     | `from magnifier_bubble.hotkey import HotkeyManager` + `HotkeyManager(bubble.root, bubble.toggle, ...)` | WIRED | Lines 116-122; deferred import inside `elif sys.platform == "win32"` branch                       |
| `app.py`                          | `magnifier_bubble.config.parse_hotkey`      | `config.parse_hotkey(raw_cfg.get("hotkey"))` after raw json re-read | WIRED | Line 76; graceful — never raises                                                                   |
| `window.py::destroy()`            | `HotkeyManager.stop()`                      | `self._hotkey_manager.stop()` BEFORE `_capture_worker.stop()` | WIRED | Lines 754-762 confirmed; destroy-chain ordering: config flush → hotkey stop → capture stop → wndproc uninstall → root.destroy |
| `window.py::toggle()`             | `AppState.set_visible` + `root.deiconify/withdraw` | `self.state.snapshot().visible` → `self.hide()` or `self.show()` | WIRED | Lines 453-458; `show` calls `root.deiconify + state.set_visible(True)`, `hide` calls `root.withdraw + state.set_visible(False)` |
| `config.py::parse_hotkey`         | `winconst.MOD_*`                            | `_MOD_MAP` lookup table at line 235               | WIRED   | `MOD_CONTROL`, `MOD_ALT`, `MOD_SHIFT`, `MOD_WIN` imported from winconst at line 231                        |

### Requirements Coverage

| Requirement | Source Plan(s)   | Description                                                                 | Status     | Evidence                                                                                                  |
|-------------|------------------|-----------------------------------------------------------------------------|------------|-----------------------------------------------------------------------------------------------------------|
| HOTK-01     | 06-01, 06-02, 06-03 | Ctrl+Z (or configured alt) registered via ctypes user32.RegisterHotKey; no keyboard library | SATISFIED | hotkey.py uses ctypes exclusively; 5 structural lints pass; REQUIREMENTS.md status: Complete           |
| HOTK-02     | 06-04            | Hotkey works even when Cornerstone or any other app has focus               | SATISFIED  | Manual sign-off in 06-04-SUMMARY.md CHECK 3: pass; RegisterHotKey(hWnd=None) is documented system-wide; **NOTE: REQUIREMENTS.md still shows `[ ]` Pending — stale doc, not a code gap** |
| HOTK-03     | 06-01, 06-02, 06-03 | Hotkey toggles bubble visible/hidden                                     | SATISFIED  | show/hide/toggle in window.py; root.after handoff in hotkey.py; integration test passes; CHECK 2 manual pass |
| HOTK-04     | 06-01, 06-02, 06-03 | Hotkey configurable in config.json; Ctrl+Alt+Z default (post CHECK 0)   | SATISFIED  | parse_hotkey in config.py; _HOTKEY_DEFAULT = (MOD_CONTROL \| MOD_ALT, VK_Z); CHECK 4 manual pass; 3 parser tests pass |
| HOTK-05     | 06-01, 06-02, 06-03 | Registered/unregistered cleanly; graceful failure if already registered | SATISFIED  | daemon=False; UnregisterHotKey in finally; start() returns False on 1409; CHECK 5B manual pass (clean relaunch); automated smoke tests cover 1409 path and stop() timing |

**Orphaned requirements check:** REQUIREMENTS.md maps HOTK-01..05 to Phase 6 only. All 5 are claimed by plans in this phase. No orphaned requirements.

**REQUIREMENTS.md text note:** HOTK-01 description text says "Ctrl+Z" as the registered hotkey. The CHECK 0 decision (option-b) changed the *default* to Ctrl+Alt+Z. The description's reference to Ctrl+Z is not incorrect — the hotkey is still configurable and Ctrl+Z remains a valid user choice. This is a cosmetic description drift, not a requirement gap.

### Anti-Patterns Found

| File                                    | Line | Pattern                             | Severity | Impact                                           |
|-----------------------------------------|------|-------------------------------------|----------|--------------------------------------------------|
| `.planning/REQUIREMENTS.md`             | 49   | `- [ ] **HOTK-02**`                | Info     | Stale checkbox — manual sign-off exists in 06-04-SUMMARY.md CHECK 3; no code gap |
| `.planning/REQUIREMENTS.md`             | 139  | `HOTK-02 \| Phase 6 \| Pending`   | Info     | Traceability table not updated after manual verification completed                |
| `.planning/ROADMAP.md`                  | 114  | `- [ ] 06-04-PLAN.md`             | Info     | Plan completion checkbox not checked after 06-04-SUMMARY.md committed            |
| `06-04-SUMMARY.md` CHECK 5A            | —    | `skip` for graceful 1409 live test | Warning  | The live two-terminal double-register test was not performed; covered by automated `test_second_register_fails_gracefully` which exercises the real 1409 path via `HotkeyManager` + live `RegisterHotKey` on Windows |
| `06-04-SUMMARY.md` CHECK 5C            | —    | `skip` for --no-hotkey live test   | Warning  | Manual walk-through skipped; covered by `test_main_py_no_hotkey_flag_smoke` subprocess test and AST lints in test_main_entry.py |

No blocker anti-patterns. The two Warning items are manual verification shortcuts covered by automated test equivalents.

### Human Verification Required

#### 1. Update REQUIREMENTS.md HOTK-02 checkbox

**Test:** Open `.planning/REQUIREMENTS.md`. Change `- [ ] **HOTK-02**` to `- [x] **HOTK-02**` and change the traceability table row `| HOTK-02 | Phase 6 | Pending |` to `| HOTK-02 | Phase 6 | Complete |`.
**Expected:** File reflects the manual sign-off that was recorded in 06-04-SUMMARY.md.
**Why human:** REQUIREMENTS.md is a manually-maintained planning document; the automated verifier cannot determine whether the human intentionally left the checkbox unchecked or whether it was simply not updated.

#### 2. Update ROADMAP.md 06-04-PLAN.md entry

**Test:** Open `.planning/ROADMAP.md` line 114. Change `- [ ] 06-04-PLAN.md` to `- [x] 06-04-PLAN.md`.
**Expected:** The Phase 6 plan list shows all four plans complete.
**Why human:** ROADMAP.md tracking requires human judgment about whether the plan truly meets the completion bar; 06-04-SUMMARY.md confirms it does.

### Gaps Summary

No implementation gaps. All five HOTK requirements are satisfied by code that exists, is substantive, and is wired into the running app. The only items flagged are documentation staleness (two planning-doc checkbox updates) and two manually-skipped verification sub-checks that are covered by passing automated tests.

The phase goal — "Register a system-wide Ctrl+Alt+Z hotkey that toggles the magnifier bubble visible/hidden from any app context, with graceful failure if the hotkey is already claimed" — is achieved:

- The hotkey is Ctrl+Alt+Z by default (user chose option-b in CHECK 0 to avoid Cornerstone undo collision)
- The hotkey is system-wide via `RegisterHotKey(hWnd=None)`, confirmed to work while Cornerstone has focus (CHECK 3 manual pass)
- Toggle is wired: WM_HOTKEY → root.after(0, bubble.toggle) → show()/hide() → state.set_visible + deiconify/withdraw
- Graceful failure: start() returns False with _reg_err=1409, logs a user-readable message, app continues running
- Clean unregister: daemon=False + finally block ensures UnregisterHotKey runs on the same thread that registered

---

_Verified: 2026-04-13_
_Verifier: Claude (gsd-verifier)_
