---
phase: 05-config-persistence
verified: 2026-04-13T21:30:00Z
status: passed
score: 15/15 must-haves verified
re_verification: false
human_verification:
  - test: "Move/resize/zoom/shape-cycle the bubble, close it, relaunch — confirm bubble appears at last-used geometry, zoom, and shape"
    expected: "Bubble opens at exactly the last persisted position/size/zoom/shape, not default values"
    why_human: "Requires a running Windows process and visual inspection of window geometry; cannot be verified by static analysis"
  - test: "Tap the [+] button 10 times rapidly in under 2 seconds, then wait 600 ms without further interaction"
    expected: "Exactly one config.json write occurs (one mtime update), not 10"
    why_human: "Debounce timing is real-time behavior; requires filesystem mtime observation during live app execution"
  - test: "While the app is running, close via WM_DELETE_WINDOW immediately after a zoom change (before the 500 ms debounce fires)"
    expected: "config.json contains the zoomed value — not the pre-change value — confirming flush_pending ran during destroy()"
    why_human: "Requires timing the close relative to the debounce window and reading the resulting file; cannot be replicated with static analysis"
  - test: "Lock the app directory with icacls to deny write access, then launch the app"
    expected: "App starts without error; config.json appears in %LOCALAPPDATA%\\UltimateZoom\\ instead"
    why_human: "LOCALAPPDATA fallback depends on actual ACL behavior on the target Windows machine"
---

# Phase 5: Config Persistence Verification Report

**Phase Goal:** Make the bubble remember where it was, how big it was, how zoomed in it was, and what shape it was the last time the user closed it, so every launch picks up exactly where the user left off.
**Verified:** 2026-04-13T21:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria + PLAN must_haves)

| #  | Truth | Status | Evidence |
|----|-------|--------|---------|
| 1  | Pure-Python config module exists exposing config_path, load, write_atomic, ConfigWriter | VERIFIED | `src/magnifier_bubble/config.py` (294 lines) exports all four symbols; stdlib-only at module scope |
| 2  | config_path() returns app-dir Path when writable, else %LOCALAPPDATA%\UltimateZoom\ | VERIFIED | Lines 110-125: writability probe via actual file create/remove; LOCALAPPDATA env var fallback; home-dir last resort |
| 3  | write_atomic produces valid JSON with {version, x, y, w, h, zoom, shape} — no visible/always_on_top | VERIFIED | `_to_dict()` (lines 133-145) explicitly lists only 7 fields; visible/always_on_top excluded by design |
| 4  | write_atomic uses NamedTemporaryFile(dir=parent) + flush + fsync + os.replace | VERIFIED | Lines 160-172: all four calls present in correct order; confirmed by grep |
| 5  | load() NEVER raises on missing/corrupt/partial/out-of-range input; clamps values | VERIFIED | Lines 180-220: handles FileNotFoundError (returns defaults), JSONDecodeError, non-dict root, out-of-range zoom/size, invalid shape |
| 6  | ConfigWriter debounces via root.after(500) with after_cancel-then-reschedule (single write per burst) | VERIFIED | `_on_change()` (lines 253-261): cancels `_after_id` then reschedules with `_DEBOUNCE_MS=500` |
| 7  | ConfigWriter.flush_pending() cancels timer AND writes synchronously if state differs from last-written | VERIFIED | Lines 279-294: after_cancel clears `_after_id`, then calls `_write_now()` which checks `snap == self._last_written` |
| 8  | ConfigWriter.register() is the only method touching state.on_change — read-only observer | VERIFIED | `register()` (line 250-251) wires `_on_change`. No `state.set_*` calls anywhere in config.py |
| 9  | app.py main() calls config.load BEFORE constructing AppState | VERIFIED | Lines 44-55: `path = config.config_path()`, `snap = config.load(path)`, then `state = AppState(snap)` |
| 10 | AppState is constructed with loaded snapshot, not StateSnapshot() defaults | VERIFIED | `AppState(snap)` at line 55; AppState.__init__ accepts optional initial and uses it if not None |
| 11 | BubbleWindow.attach_config_writer stores the reference; destroy() calls flush_pending BEFORE capture stop | VERIFIED | window.py lines 408-417 (attach), lines 695-706 (flush_pending at TOP of destroy try-block before _capture_worker.stop) |
| 12 | ConfigWriter constructed AFTER BubbleWindow so root.after has a live Tk root (Pitfall 7) | VERIFIED | app.py lines 58-77: bubble constructed first, then `config.ConfigWriter(state, bubble.root, path)` |
| 13 | writer.register() wires AppState.on_change before mainloop | VERIFIED | app.py lines 76-77: `writer.register()` then `bubble.attach_config_writer(writer)`, then `bubble.root.mainloop()` |
| 14 | Corrupt/missing config.json falls back to StateSnapshot() defaults silently | VERIFIED | load() returns `StateSnapshot()` for FileNotFoundError (silent); prints log for JSONDecodeError but returns defaults |
| 15 | AST lint in test_main_entry.py asserts config.load precedes AppState construction | VERIFIED | `test_app_loads_config_before_state` (line 234) and `test_app_wires_config_writer` (line 279) both present using ast.parse + ast.walk |

**Score:** 15/15 truths verified

---

### Required Artifacts

| Artifact | Min Lines | Actual | Status | Key Evidence |
|----------|-----------|--------|--------|-------------|
| `src/magnifier_bubble/config.py` | 150 | 294 | VERIFIED | Contains `class ConfigWriter`, `write_atomic`, `load`, `config_path`; stdlib-only at module scope |
| `tests/test_config.py` | 250 | 321 | VERIFIED | Contains `def test_` multiple times; imports `from magnifier_bubble import config` (line 17) |
| `tests/test_config_smoke.py` | 60 | 146 | VERIFIED | Contains `pytest.mark.skipif` (line 21) gating on `sys.platform != "win32"` |
| `src/magnifier_bubble/app.py` | 70 | 96 | VERIFIED | Contains `config.load` (line 45); wires ConfigWriter after BubbleWindow |
| `src/magnifier_bubble/window.py` | 700 | 730 | VERIFIED | Contains `attach_config_writer` (line 408) and `flush_pending` call in destroy() (line 701) |
| `tests/test_main_entry.py` | 80 | 301 | VERIFIED | Contains `test_app_loads_config_before_state` and `ast.walk`/`ast.parse` calls |
| `tests/test_window_config_integration.py` | (new) | 95 | VERIFIED | Contains 4 tests using `types.SimpleNamespace` fake-writer spy for destroy() contract |

---

### Key Link Verification

| From | To | Via | Status | Evidence |
|------|----|-----|--------|---------|
| `config.py` | `os.replace` | atomic-rename staging | WIRED | Line 172: `os.replace(tmp_name, str(path))` |
| `config.py` | `os.fsync` | disk-flush before rename | WIRED | Line 170: `os.fsync(tf.fileno())` — appears before os.replace |
| `config.py` | `tempfile.NamedTemporaryFile` | same-dir staging (Pitfall 2) | WIRED | Lines 160-167: `NamedTemporaryFile(... dir=str(path.parent) ...)` |
| `config.py` | `root.after_cancel` | debounce cancel-reschedule | WIRED | Lines 258, 290: `self._root.after_cancel(self._after_id)` in both `_on_change` and `flush_pending` |
| `tests/test_config.py` | `config.py` | import | WIRED | Line 17: `from magnifier_bubble import config` |
| `app.py` | `config.py` | module import | WIRED | Line 18: `from magnifier_bubble import config, dpi` |
| `app.py` | `AppState(snap)` | loaded snapshot seeded | WIRED | Line 55: `state = AppState(snap)` where `snap = config.load(path)` |
| `app.py` | `bubble.attach_config_writer(writer)` | writer handed to bubble | WIRED | Line 77: `bubble.attach_config_writer(writer)` |
| `window.py` | `self._config_writer.flush_pending()` | destroy() flush BEFORE teardown | WIRED | Lines 699-706: guarded `if self._config_writer is not None` at TOP of destroy try-block |
| `test_main_entry.py` | `ast.walk(module)` | static AST call-order scan | WIRED | Lines 247, 251: `ast.parse(src)` then `ast.walk(tree)` |

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| PERS-01 | 05-01, 05-02 | config.json saved in app executable directory | SATISFIED | `config_path()` returns app-dir primary; writability-probe fallback to LOCALAPPDATA; `_app_dir()` uses `sys.executable` when frozen |
| PERS-02 | 05-01, 05-02 | Config written on every change using 500 ms debounce + atomic os.replace() | SATISFIED | `ConfigWriter._on_change` debounces at 500 ms; `write_atomic` uses `os.replace`; registered via `writer.register()` in app.py before mainloop |
| PERS-03 | 05-01, 05-02 | On launch, app restores last known position/size/zoom/shape | SATISFIED | `config.load(path)` called before `AppState(snap)` in app.py main(); `load()` clamps and validates all fields; graceful defaults on corruption |
| PERS-04 | 05-01, 05-02 | Pending write flushed before exit (WM_DELETE_WINDOW) | SATISFIED | `destroy()` calls `self._config_writer.flush_pending()` at TOP of try-block before capture worker stop and WndProc teardown |

All 4 PERS-* requirements are mapped to Phase 5 plans. No orphaned requirements for this phase.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `window.py` | 403 | `# Phase 3: capture worker placeholder (started by app.py via start_capture)` | Info | Comment describing attribute init; not a stub — `_capture_worker` is correctly set to `None` until `start_capture()` is called. No impact on Phase 5 functionality. |

No blockers. No stubs. No empty implementations in Phase 5 artifacts.

---

### Human Verification Required

#### 1. Full Round-Trip State Restore

**Test:** Move the bubble to a corner, resize it, zoom to 4x, cycle to "circle" shape, close the app via WM_DELETE_WINDOW (or add a close button), relaunch.
**Expected:** Bubble appears at the corner position, with the resized dimensions, zoom at 4x, and circular shape — not the StateSnapshot() defaults (200,200, 400x400, zoom=2.0, rect).
**Why human:** Requires a running Tk app on Windows, visual confirmation of window placement, and no programmatic way to measure window geometry against persisted JSON without actually running the app.

#### 2. Debounce Single-Write Confirmation

**Test:** While running, tap [+] ten times rapidly (within 2 seconds). Watch config.json's mtime in Explorer or via `Get-Item config.json | select LastWriteTime` in PowerShell.
**Expected:** Exactly one mtime update approximately 500 ms after the last tap — not 10 updates.
**Why human:** Debounce timing is live scheduler behavior. Static analysis confirms the code is structured correctly; only live execution can confirm the scheduler honors the 500 ms window.

#### 3. Flush-on-Shutdown Mid-Debounce

**Test:** Tap [+] once, then immediately close the app via WM_DELETE_WINDOW before 500 ms elapses. Relaunch and check the zoom level.
**Expected:** Zoom reflects the [+] tap (not the pre-tap value), confirming flush_pending() ran during destroy() and caught the pending debounce.
**Why human:** Requires precise timing of the close relative to the debounce window; not reproducible via static analysis.

#### 4. LOCALAPPDATA Fallback Under ACL Lockdown

**Test:** Lock the app directory with `icacls . /deny Everyone:(W)`, launch the app.
**Expected:** App launches without error; config.json appears in `%LOCALAPPDATA%\UltimateZoom\config.json`.
**Why human:** ACL behavior on clinic hardware differs from dev environment; requires actual Windows ACL manipulation.

---

### Gaps Summary

No gaps. All 15 must-have truths verified. All 4 PERS-* requirements satisfied by actual implementation in the codebase. All key links confirmed wired with grep evidence. No stub implementations or orphaned artifacts detected.

The four human verification items above are standard integration-level checks that cannot be confirmed by static analysis. They were performed on the Windows 11 dev box during Plan 05-02's Task 3 checkpoint (all 5 manual checks signed off, per SUMMARY), so the automated verification is consistent with that manual sign-off.

---

_Verified: 2026-04-13T21:30:00Z_
_Verifier: Claude (gsd-verifier)_
