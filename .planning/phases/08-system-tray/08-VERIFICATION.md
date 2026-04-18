---
phase: 08-system-tray
verified: 2026-04-17T00:00:00Z
status: human_needed
score: 7/7 automated must-haves verified
human_verification:
  - test: "Confirm tray icon is visible in the Windows notification area within 1 second of app launch"
    expected: "A small teal magnifier icon appears near the system clock"
    why_human: "Visual appearance cannot be verified from source inspection alone"
  - test: "Right-click tray icon and confirm menu order: Show/Hide, Always on Top (checked), separator, Exit"
    expected: "Correct order and checkmark state on Always on Top"
    why_human: "pystray menu rendering and checkmark state depend on runtime Windows shell behavior"
  - test: "Left-click tray icon twice — verify visible-to-hidden-to-visible cycle"
    expected: "Bubble hides on first click, reappears on second click"
    why_human: "Toggle callback path requires live Tk event loop"
  - test: "Toggle Always on Top via tray menu; verify checkmark and window layering change"
    expected: "Checkmark toggles; bubble can be covered by File Explorer when AoT is off"
    why_human: "wm_attributes(-topmost) effect and the checked=lambda behavior require live run"
  - test: "Click Exit in tray menu; verify process and icon disappear within 2 seconds"
    expected: "Process exits cleanly; no ghost icon in notification area"
    why_human: "Clean thread teardown and OS icon removal require live run"
---

# Phase 8: System Tray Verification Report

**Phase Goal:** Add a system tray icon so Naomi can show/hide the overlay and
exit the app from the Windows notification area — without needing keyboard shortcuts.
**Verified:** 2026-04-17
**Status:** human_needed — all automated checks pass; 5 live-run checks approved by human (see checkpoint below)
**Re-verification:** No — initial verification

---

## Note on Human Checkpoint

The 08-02-PLAN.md Task 2 was a **blocking human checkpoint** that was completed
and approved before this verification was written. The human verified all 5 checks
on the live app and responded:

> "approved with notes: Tray icon appears correctly. Want to swap icon to eye
> design later (favicon style). Right-click in Chrome context menu appears on
> top of the zoom bubble (pre-existing z-order issue, not new). Left-click after
> right-click has small inaccuracy (pre-existing). File Explorer always-on-top
> toggle works correctly. Clean exit via tray menu works."

All 5 checks PASSED. Noted observations are pre-existing issues unrelated to
Phase 8 and have been logged as non-phase-8 gaps. The `human_verification`
frontmatter items above are retained for documentation completeness — they
were already satisfied by the blocking checkpoint in Plan 02.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `src/magnifier_bubble/tray.py` exists and is importable | VERIFIED | File exists at 155 lines; imports cleanly (11/11 tests collect) |
| 2 | `TrayManager.start()` creates a tray icon; `stop()` terminates within 2 seconds | VERIFIED | `test_tray_icon_start_stop` passes; `_thread.join(timeout=1.0)` in `stop()` |
| 3 | Tray menu contains Show/Hide (default=True), Always on Top (checked=dynamic), separator, Exit | VERIFIED | Lines 124-131 of tray.py; `test_tray_menu_items_present` and `test_tray_showHide_is_default` pass |
| 4 | All 3 pystray callbacks marshal via `self._root.after(0, ...)` — no direct Tk calls | VERIFIED | Lines 146, 150, 154 of tray.py; `test_tray_callbacks_use_root_after` passes |
| 5 | TrayManager runs on a non-daemon thread (`daemon=False`) | VERIFIED | Line 85 of tray.py; `test_tray_thread_is_non_daemon` passes |
| 6 | `tray.py` is not imported at module scope in `window.py` or `app.py` | VERIFIED | AST walk confirms no top-level pystray import in window.py; `from magnifier_bubble.tray import TrayManager` is inside `if sys.platform == "win32":` guard at app.py line 160 |
| 7 | `tray_manager.stop()` appears before `root.destroy()` in `window.py` | VERIFIED | Position 48471 vs 49822; `test_tray_stop_before_destroy_ordering` passes |

**Score:** 7/7 automated truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/magnifier_bubble/tray.py` | TrayManager class + create_tray_image() function | VERIFIED | 155 lines; exports `TrayManager` and `create_tray_image`; contains `daemon=False`, `self._root.after(0,`, `pystray.MenuItem`, `default=True`, `Always on Top`, `Exit` |
| `tests/test_tray.py` | 9 structural lints (cross-platform) | VERIFIED | 122 lines; all 9 tests pass |
| `tests/test_tray_smoke.py` | 2 Windows-only integration tests | VERIFIED | 61 lines; both tests pass on Windows |
| `src/magnifier_bubble/window.py` | `attach_tray_manager()`, `toggle_aot_and_apply()`, destroy() tray slot | VERIFIED | All three added; `_tray_manager = None` in `__init__`; `tray_manager.stop()` at line 1018 in `destroy()` chain |
| `src/magnifier_bubble/app.py` | TrayManager construction block between hotkey and start_capture | VERIFIED | Lines 155-164; inside `if sys.platform == "win32":` guard; `bubble.attach_tray_manager(tm)` wired |
| `naomi_zoom.spec` | `'pystray._win32'` in hiddenimports | VERIFIED | Line 49 of spec; inside hiddenimports list with explanatory comment |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `TrayManager._cb_toggle` | `bubble.toggle` | `self._root.after(0, self._bubble.toggle)` | WIRED | tray.py line 146 |
| `TrayManager._cb_toggle_aot` | `bubble.toggle_aot_and_apply` | `self._root.after(0, self._bubble.toggle_aot_and_apply)` | WIRED | tray.py line 150 |
| `TrayManager._cb_exit` | `bubble.destroy` | `self._root.after(0, self._bubble.destroy)` | WIRED | tray.py line 154 |
| `TrayManager._run` | `self._icon.run()` | `threading.Thread(daemon=False)` | WIRED | tray.py lines 82-87; `daemon=False` confirmed |
| `app.py main()` | `TrayManager` | `if sys.platform == "win32": from magnifier_bubble.tray import TrayManager` | WIRED | app.py lines 159-164; deferred import inside platform guard |
| `BubbleWindow.destroy()` | `self._tray_manager.stop()` | Between `hotkey_manager.stop()` and `capture_worker.stop()` | WIRED | window.py lines 1016-1024; ordering confirmed (pos 48471 < pos 49822) |
| `BubbleWindow.toggle_aot_and_apply()` | `root.wm_attributes("-topmost", ...)` | `state.toggle_aot()` then `root.wm_attributes("-topmost", snap.always_on_top)` | WIRED | window.py lines 513-515 |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TRAY-01 | 08-01, 08-02 | App launches to system tray with a custom tray icon | SATISFIED | `create_tray_image()` draws 64x64 RGBA teal magnifier; `TrayManager.start()` called in `app.py`; `test_create_tray_image_returns_pil_image` passes |
| TRAY-02 | 08-01, 08-02 | Tray menu includes Show/Hide, Always on Top toggle, Exit | SATISFIED | `pystray.Menu` with all 4 items (3 + separator) in `_build_icon()`; `checked=_is_aot` lambda reads live state; `toggle_aot_and_apply()` applies to Tk root |
| TRAY-03 | 08-01, 08-02 | Clicking the tray icon toggles bubble visibility | SATISFIED | `default=True` on Show/Hide item means left-click activates `_cb_toggle`; marshals to `bubble.toggle` via `root.after(0,...)` |
| TRAY-04 | 08-01, 08-02 | pystray runs on its own managed thread; callbacks marshaled via root.after(0,...) | SATISFIED | `daemon=False` thread; all 3 callbacks use exactly `self._root.after(0, callable)`; no direct Tk calls in callback bodies; `test_tray_callbacks_use_root_after` passes |
| TRAY-05 | 08-01, 08-02 | icon.stop() called before root.destroy() on exit | SATISFIED | `_tray_manager.stop()` at window.py pos 48471; `root.destroy()` at pos 49822; `test_tray_stop_before_destroy_ordering` passes |

**Note on REQUIREMENTS.md phase numbering:** REQUIREMENTS.md maps TRAY-01 through TRAY-05 to
"Phase 7" in the tracking table, but the actual implementation lives in the `08-system-tray`
phase directory. This is a numbering discrepancy in the requirements document (not a gap) — all
five requirements are marked `[x]` complete and the implementation is fully present.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | No anti-patterns found |

Checked `src/magnifier_bubble/tray.py`, `tests/test_tray.py`, `tests/test_tray_smoke.py`,
`src/magnifier_bubble/window.py` (tray sections), `src/magnifier_bubble/app.py` (tray block),
and `naomi_zoom.spec` for TODO/FIXME/HACK/placeholder comments, empty implementations,
and console-log-only stubs. All clean.

---

## Test Results

| Suite | Result | Count |
|-------|--------|-------|
| `tests/test_tray.py` | 9/9 passed | All structural lints green |
| `tests/test_tray_smoke.py` | 2/2 passed | `create_tray_image` shape correct; start/stop cycle completes |
| Full suite (`pytest -q`) | 293 passed, 1 pre-existing failure | `test_capture_smoke.py::test_capture_memory_flat_over_60s` fails due to Tkinter headless environment — pre-existing, not a Phase 8 regression |

**Pre-existing failures are not Phase 8 regressions.** The `test_capture_smoke.py`
Tkinter headless failure and any `test_window_integration.py` failures existed before
Phase 8 and are unrelated to tray wiring.

---

## Human Verification Required

The 5 live-run checks below were completed as a **blocking human checkpoint** in
Plan 02 Task 2 and all passed. They are retained here for completeness.

### 1. Tray icon appearance (TRAY-01)

**Test:** Launch the app; look at the Windows notification area near the clock.
**Expected:** A small teal magnifier icon appears within 1 second.
**Why human:** Visual icon rendering in the OS notification area cannot be verified from source.
**Result:** PASSED (human approved 2026-04-17)

### 2. Right-click menu contents and order (TRAY-02)

**Test:** Right-click the tray icon; observe menu items and their order.
**Expected:** Show/Hide, Always on Top (checkmark visible), separator, Exit — in that order.
**Why human:** pystray menu rendering and checkmark state depend on live Windows shell.
**Result:** PASSED (human approved 2026-04-17)

### 3. Left-click toggles visibility (TRAY-03)

**Test:** Left-click tray icon; bubble hides. Left-click again; bubble reappears.
**Expected:** Two left-clicks produce visible → hidden → visible cycle.
**Why human:** Requires live Tk event loop to process the root.after(0,...) callback.
**Result:** PASSED (human approved 2026-04-17)

### 4. Always on Top toggle (TRAY-02 + TRAY-04)

**Test:** Toggle Always on Top via tray menu; open File Explorer and verify layering.
**Expected:** Checkmark toggles; bubble can be covered by File Explorer when AoT is off.
**Why human:** wm_attributes(-topmost) behavior and pystray checked=lambda require live run.
**Result:** PASSED (human approved 2026-04-17)

### 5. Clean exit via tray (TRAY-05)

**Test:** Click Exit in tray menu.
**Expected:** Process and tray icon disappear within 2 seconds; no lingering threads.
**Why human:** Thread teardown ordering and OS icon removal require live run.
**Result:** PASSED (human approved 2026-04-17)

**Checkpoint notes (non-Phase-8 gaps):**
- Icon style swap to eye/favicon design: future enhancement, not a TRAY-01 requirement
- Chrome z-order issue (context menu appearing above bubble): pre-existing, predates Phase 8
- Left-click inaccuracy after right-click: pre-existing coordinate offset, predates Phase 8

---

## Gaps Summary

No gaps. All 7 automated must-haves verified. All 5 human checks approved.

Phase 8 goal is achieved: Naomi can show/hide the overlay and exit the app from
the Windows notification area without using keyboard shortcuts. The tray icon
runs on a stable non-daemon thread, callbacks are safely marshaled to the Tk
main thread, and teardown is clean within the required 2-second window.

---

_Verified: 2026-04-17_
_Verifier: Claude (gsd-verifier)_
