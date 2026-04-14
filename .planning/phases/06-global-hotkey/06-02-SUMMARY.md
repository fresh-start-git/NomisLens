---
phase: 06-global-hotkey
plan: 02
subsystem: hotkey-core
tags: [wave-1, ctypes, RegisterHotKey, worker-thread, GetMessageW, parse_hotkey]
requires:
  - winconst.py Phase 6 additions (Plan 06-01)
  - Wave 0 skip stubs (Plan 06-01) across test_hotkey.py / test_hotkey_smoke.py / test_config.py
  - Tk conftest fixtures: tk_session_root, tk_toplevel (Phase 02)
provides:
  - HotkeyManager class (start/stop lifecycle, Tk main-thread callback handoff)
  - config.parse_hotkey(raw) -> (modifiers, vk) graceful parser
  - 11 Wave 0 stubs flipped from skip to real assertions (5 test_hotkey + 3 test_hotkey_smoke + 3 test_config)
  - Real GetLastError surfacing via WinDLL(..., use_last_error=True)
  - MOD_NOREPEAT always-on policy (callers never OR it themselves)
affects:
  - src/magnifier_bubble/hotkey.py (CREATED, 277 lines)
  - src/magnifier_bubble/config.py (added parse_hotkey helper + _MOD_MAP)
  - tests/test_hotkey.py (5 stubs → real lints)
  - tests/test_hotkey_smoke.py (3 stubs → real Win32 integration)
  - tests/test_config.py (3 parser stubs → real assertions)
tech-stack:
  added: []
  patterns:
    - "Worker-thread-owned Win32 resource (Register + Unregister share the same _run() function per MSDN)"
    - "Non-daemon worker + PostThreadMessageW(WM_QUIT) cooperative shutdown"
    - "Lazy-argtypes sentinel (_SIGNATURES_APPLIED) mirrors wndproc.py idiom"
    - "WinDLL(use_last_error=True) for real GetLastError access across ctypes calls"
    - "PeekMessageW(WM_USER) to force the worker's message queue into existence BEFORE any outside thread posts to it"
key-files:
  created:
    - src/magnifier_bubble/hotkey.py
    - .planning/phases/06-global-hotkey/06-02-SUMMARY.md
  modified:
    - src/magnifier_bubble/config.py
    - tests/test_hotkey.py
    - tests/test_hotkey_smoke.py
    - tests/test_config.py
decisions:
  - "WinDLL('user32', use_last_error=True) introduced (deviation from plan) because ctypes.windll loads WITHOUT save/restore of GetLastError — _reg_err was always 0 otherwise, defeating the ERROR_HOTKEY_ALREADY_REGISTERED graceful-failure path. Module caches the handle in _U32_ERR on first use."
  - "MOD_NOREPEAT is OR'd into self._modifiers in __init__ — callers MUST NOT include it. Enforced by the 'Pitfall 5' comment at the OR site; ensures the auto-repeat-suppression policy is centralized."
  - "UnregisterHotKey lives in the SAME _run() method's finally block as RegisterHotKey, enforced by an AST-walk structural lint (test_register_and_unregister_in_same_function). This is not a Python requirement, it's a Win32 requirement — RegisterHotKey ties ownership to the calling thread id."
  - "Integration test test_wm_hotkey_toggles_visible_via_after uses top.mainloop() + top.after(10, top.quit) to exit, NOT top.update() as the plan specified. Cross-thread root.after() from the worker requires the main thread to be INSIDE mainloop() on Python 3.11/Tcl 8.6 — the polling loop variant raises 'main thread is not in main loop'. Using a Toplevel's mainloop keeps the session-scoped tk_session_root fixture intact for subsequent tests."
  - "parse_hotkey is placed in config.py (not a new module) because Plan 06-03 will call it from the same config.load() call site and a top-level helper keeps the import graph flat. The parser never raises — any malformed dict falls back to (MOD_CONTROL, VK_Z) and the app still starts."
metrics:
  duration: "~48 min"
  tasks_completed: 3
  files_modified: 4
  files_created: 1
  commits: 3
  completed_date: "2026-04-14"
---

# Phase 6 Plan 02: Hotkey Core Summary

Self-contained RegisterHotKey worker-thread module (`hotkey.py` / `HotkeyManager`) plus a `config.parse_hotkey` dict-to-(mods, vk) helper, with every Wave 0 stub flipped from skip to real assertion. Zero changes to `window.py` / `app.py` — that's Plan 06-03. The worker-thread lifecycle contract (register → GetMessageW loop → WM_QUIT → UnregisterHotKey on SAME thread) is proved by three live Win32 integration tests.

## Objective Recap

Build the pure-Python hotkey core as a standalone module so Plan 06-03 can wire it into `app.py` without touching Win32 internals. Everything live in this summary is behind a test — no code paths without coverage.

## What Landed

### src/magnifier_bubble/hotkey.py (CREATED, 277 lines)

**Public surface:**

```python
class HotkeyManager:
    def __init__(self, root, on_hotkey: Callable[[], None], modifiers: int, vk: int) -> None: ...
    def start(self, timeout: float = 1.0) -> bool: ...   # True iff RegisterHotKey succeeded
    def stop(self) -> None: ...                          # Posts WM_QUIT, joins < 1s
    # Post-start() state for graceful-failure surfacing:
    _reg_ok: bool    # True iff RegisterHotKey returned nonzero
    _reg_err: int    # GetLastError value on failure (1409 if already registered)
```

**Lifecycle contract:**

```
main thread                       worker thread (daemon=False, name='hotkey-pump')
----------                        --------------------------------------------
mgr = HotkeyManager(...)
mgr.start(timeout=1.0) ──────────▶ _run() entered
                                   PeekMessageW(WM_USER) — force queue into existence
                                   RegisterHotKey(_HOTKEY_ID, mods | MOD_NOREPEAT, vk)
                                   _ready.set()  ◀──────── start() returns _reg_ok
                                   GetMessageW loop:
                                       WM_HOTKEY  → self._root.after(0, on_hotkey)
                                       WM_QUIT    → break
mgr.stop() ──────────────────────▶ PostThreadMessageW(_tid, WM_QUIT)
                                   finally: UnregisterHotKey(_HOTKEY_ID)
                                   thread exits
_thread.join(timeout=1.0)          ◀────────────────────
```

**Module-level state:**

| Name                 | Purpose                                                                   |
| -------------------- | ------------------------------------------------------------------------- |
| `_HOTKEY_ID = 0x0001`| App-range hotkey id (MSDN requires 0x0000..0xBFFF for in-process binding) |
| `_SIGNATURES_APPLIED`| One-shot sentinel for lazy argtypes/restype application                   |
| `_U32_ERR`           | Cached `WinDLL("user32", use_last_error=True)` handle (see deviations)    |

**Win32 signatures applied lazily (10 argtype/restype pairs):**

- `RegisterHotKey`: HWND, c_int, UINT, UINT → BOOL
- `UnregisterHotKey`: HWND, c_int → BOOL
- `GetMessageW`: POINTER(MSG), HWND, UINT, UINT → **c_int** (NOT BOOL — Pitfall 6: -1 is a legal error return)
- `PostThreadMessageW`: DWORD, UINT, WPARAM, LPARAM → BOOL
- `PeekMessageW`: POINTER(MSG), HWND, UINT, UINT, UINT → BOOL

### src/magnifier_bubble/config.py (extended)

**New surface (inserted between `load()` and `ConfigWriter`):**

```python
_MOD_MAP: dict[str, int] = {
    "ctrl":  MOD_CONTROL, "alt": MOD_ALT,
    "shift": MOD_SHIFT,   "win": MOD_WIN,
}
_HOTKEY_DEFAULT: tuple[int, int] = (MOD_CONTROL, VK_Z)

def parse_hotkey(raw) -> tuple[int, int]:
    """Parse a hotkey config dict -> (modifiers_bitmask, vk_code).

    Never raises. Default (MOD_CONTROL, VK_Z) on any malformed input.
    """
```

**Error behavior (all return `(MOD_CONTROL, VK_Z)`):**

| Input                                           | Returns default | Reason                       |
| ----------------------------------------------- | --------------- | ---------------------------- |
| `None` / `42` / `"ctrl+z"` / `[]`               | yes             | Not a dict                   |
| `{}`                                            | yes             | `mods==0` after lookup       |
| `{"modifiers": "ctrl"}`                         | yes             | Modifiers not a list         |
| `{"modifiers": ["fn"], "vk": "z"}`              | yes             | Unknown modifier             |
| `{"modifiers": ["ctrl", ""], "vk": "z"}`        | yes             | Empty modifier               |
| `{"modifiers": ["ctrl"], "vk": "zz"}`           | yes             | VK not 1 char                |
| `{"modifiers": ["ctrl"], "vk": "!"}`            | yes             | VK not A-Z / 0-9             |
| `{"modifiers": [], "vk": "z"}`                  | yes             | mods bitmask 0               |

**Valid examples:**

```python
parse_hotkey({"modifiers": ["ctrl"],         "vk": "z"}) == (MOD_CONTROL,               VK_Z)
parse_hotkey({"modifiers": ["ctrl", "alt"],  "vk": "z"}) == (MOD_CONTROL | MOD_ALT,     VK_Z)
parse_hotkey({"modifiers": ["shift", "win"], "vk": "a"}) == (MOD_SHIFT   | MOD_WIN,     ord("A"))
parse_hotkey({"modifiers": ["CTRL"],         "vk": "Z"}) == (MOD_CONTROL,               VK_Z)   # case-insensitive
parse_hotkey({"modifiers": ["ctrl"],         "vk": "5"}) == (MOD_CONTROL,               ord("5"))
```

## Wave 0 Stubs Filled (11 total)

### tests/test_hotkey.py (5 pure-Python structural lints — runs on any platform)

| Test                                               | Asserts                                                                          |
| -------------------------------------------------- | -------------------------------------------------------------------------------- |
| `test_hotkey_uses_ctypes_not_keyboard_lib`         | `ctypes.windll` present; `keyboard` / `pynput` / `global_hotkeys` forbidden       |
| `test_winconst_mod_values_match_msdn`              | MOD_* / VK_Z / WM_HOTKEY / WM_QUIT / ERROR_HOTKEY_ALREADY_REGISTERED vs MSDN      |
| `test_hotkey_applies_argtypes`                     | RegisterHotKey / UnregisterHotKey / GetMessageW / PostThreadMessageW argtypes set|
| `test_hotkey_thread_is_non_daemon`                 | `daemon=False` present, `daemon=True` absent (Pitfall 2)                         |
| `test_register_and_unregister_in_same_function`    | AST walk: Register + Unregister share at least one containing function (Pitfall 1)|

### tests/test_hotkey_smoke.py (3 Windows-only live integration tests)

All three use the obscure `Ctrl+Alt+Shift+Win+F12 (0x7B)` combo to avoid dev-box collisions with PowerToys / Cornerstone / OS bindings.

| Test                                         | Asserts                                                                      |
| -------------------------------------------- | ---------------------------------------------------------------------------- |
| `test_wm_hotkey_toggles_visible_via_after`   | PostThreadMessageW(WM_HOTKEY) → root.after callback fires exactly once       |
| `test_second_register_fails_gracefully`      | Second `start()` on same combo returns False with `_reg_err == 1409`         |
| `test_stop_posts_quit_and_joins`             | `stop()` completes in < 1s; `_thread` is nulled afterward                    |

### tests/test_config.py (3 HOTK-04 parser stubs)

| Test                                       | Asserts                                                   |
| ------------------------------------------ | --------------------------------------------------------- |
| `test_hotkey_roundtrip`                    | 5 valid parses (incl. case-insensitivity + digit VKs)      |
| `test_hotkey_defaults_on_corrupt`          | 9 corrupt-input paths all return `_HOTKEY_DEFAULT`         |
| `test_hotkey_rejects_unknown_modifier`     | 4 unknown-modifier paths all return `_HOTKEY_DEFAULT`      |

## All 10 Research-Plan Pitfalls Mitigated

Cross-references to `.planning/phases/06-global-hotkey/06-RESEARCH.md`:

| # | Pitfall                                                            | Mitigation                                                                                |
| - | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| 1 | Unregister MUST run on the same thread as Register                  | `finally:` block inside `_run()` — enforced by AST-walk lint                              |
| 2 | Daemon thread killed before `finally` → leaked registration         | `daemon=False` + cooperative `PostThreadMessageW(WM_QUIT)` shutdown                       |
| 3 | Low-level input-hook libs need admin + fragile on Win11            | Banned by substring lint — module uses `RegisterHotKey` only                              |
| 4 | `root.after(0, fn)` is the only thread-safe Tk handoff              | WM_HOTKEY handler calls `self._root.after(0, self._on_hotkey)`                            |
| 5 | Auto-repeat floods WM_HOTKEY without MOD_NOREPEAT                   | `self._modifiers = modifiers \| MOD_NOREPEAT` in `__init__` — always applied              |
| 6 | `GetMessageW.restype = BOOL` masks the -1 error return              | Explicit `GetMessageW.restype = ctypes.c_int` + `if rc == 0 or rc == -1: break`            |
| 7 | x64 LONG_PTR/HWND truncation without argtypes                       | Every Win32 function called has argtypes applied via `_apply_signatures` (Pitfall 6 + 7)  |
| 8 | `ctypes.windll` doesn't save GetLastError across calls              | `_U32_ERR = WinDLL("user32", use_last_error=True)` — real 1409 surfaces on double-register |
| 9 | Thread queue may not exist when outside thread posts to `_tid`      | `PeekMessageW(WM_USER)` called before any outside thread can post                         |
| 10| RuntimeError on `root.after` during Tk teardown                     | `try: self._root.after(0, …) except RuntimeError: pass` — worker still reaches finally    |

## Integration Surface for Plan 06-03

Plan 06-03 (`app.py` wiring) only needs to touch three hooks:

```python
# 1. In app.py __init__ or setup:
from magnifier_bubble.hotkey import HotkeyManager
from magnifier_bubble.config import parse_hotkey

raw_cfg = json.loads(path.read_text())          # whatever load() already does
mods, vk = parse_hotkey(raw_cfg.get("hotkey"))   # graceful -- never raises

self._hk = HotkeyManager(self._root, self._on_hotkey_toggle, mods, vk)
if not self._hk.start(timeout=1.0):
    # _reg_err is already logged by hotkey.py; app continues without hotkey.
    pass

# 2. In WM_DELETE_WINDOW / shutdown:
self._hk.stop()

# 3. The toggle callback (Plan 06-03 adds BubbleWindow.show/hide/toggle):
def _on_hotkey_toggle(self):
    self._window.toggle()
```

Plan 06-03's test stub `test_window_visibility_hotkey_toggle` in `test_window_phase4.py` auto-unskips the moment `BubbleWindow` grows `show` / `hide` / `toggle` methods.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ctypes.get_last_error() returned 0 instead of real GetLastError**
- **Found during:** Task 3 smoke test `test_second_register_fails_gracefully`
- **Issue:** The plan's `user32 = ctypes.windll.user32` loader does NOT enable ctypes' save/restore of GetLastError. After RegisterHotKey fails, `ctypes.get_last_error()` returns 0, so `_reg_err = 0` and the graceful-failure path that surfaces ERROR_HOTKEY_ALREADY_REGISTERED (1409) to the user never fires.
- **Fix:** Added module-level `_U32_ERR: ctypes.WinDLL | None = None` lazily initialized inside `_run()` as `ctypes.WinDLL("user32", use_last_error=True)`. All Win32 calls on the worker thread route through this handle. The `kernel32.GetCurrentThreadId` call stays on plain `ctypes.windll.kernel32` because it cannot fail.
- **Files modified:** `src/magnifier_bubble/hotkey.py` (lines 66-74, 220-225)
- **Commit:** `e32bdf7`

**2. [Rule 1 - Bug] Plan's `top.update()` polling loop triggered "main thread is not in main loop" in cross-thread test**
- **Found during:** Task 3 smoke test `test_wm_hotkey_toggles_visible_via_after`
- **Issue:** The plan specified a `while counter['n'] == 0: top.update(); time.sleep(...)` polling loop to wait for the worker's `root.after(0, on_hotkey)` to fire. On Python 3.11 / Tcl 8.6, `top.update()` does NOT count as being inside mainloop() for the purpose of dispatching cross-thread after-callbacks — the worker's `after()` call raised `RuntimeError: main thread is not in main loop`.
- **Fix:** Test now enters `top.mainloop()` after posting WM_HOTKEY, and `on_hotkey` calls `top.after(10, top.quit)` to exit the mainloop once the counter is incremented. A 2-second watchdog thread calls `top.after(0, top.quit)` as a safety net. `top.quit()` on a Toplevel exits the mainloop WITHOUT destroying the session root fixture, so subsequent tests see a clean fixture state.
- **Files modified:** `tests/test_hotkey_smoke.py` (test body + docstring)
- **Commit:** `e32bdf7`

### No Rule 2 / Rule 3 / Rule 4 deviations

Plan otherwise executed exactly as written. Wave 0 stubs flipped 1-for-1, argtype coverage matches the plan's list, lifecycle contract matches the plan's sequence diagram.

## Test Results

| Suite                                                           | Result                               |
| --------------------------------------------------------------- | ------------------------------------ |
| `pytest tests/test_hotkey.py -v`                                | 5 passed                             |
| `pytest tests/test_hotkey_smoke.py -v`                          | 3 passed                             |
| `pytest tests/test_config.py -v`                                | 31 passed (includes 3 HOTK-04 tests) |
| `pytest tests/test_winconst.py -v`                              | 35 passed (Plan 06-01 values)        |
| Full suite excl. pre-existing broken files                      | 250 passed, 1 skipped                |

The 2 excluded files (`test_capture_smoke.py`, `test_window_integration.py`) have pre-existing `TypeError: 'Event' object is not callable` failures unrelated to Plan 06-02 — documented in `.planning/phases/06-global-hotkey/deferred-items.md` and confirmed identical on master baseline BEFORE Plan 06-02 changes.

## Commits

| Task | Commit    | Message                                                             |
| ---- | --------- | ------------------------------------------------------------------- |
| 1    | `5af10a8` | feat(06-02): implement HotkeyManager in hotkey.py                   |
| 2    | `9974680` | feat(06-02): add config.parse_hotkey + fill HOTK-04 test stubs      |
| 3    | `e32bdf7` | test(06-02): fill HOTK-01/HOTK-05 structural + integration stubs    |

## Next Plan (06-03)

Plan 06-03 (`app.py` wiring) consumes the surface in **Integration Surface for Plan 06-03** above. After Plan 06-03 lands:

- `test_window_phase4.py::test_window_visibility_hotkey_toggle` auto-unskips (HOTK-03)
- `ConfigWriter` persists the `hotkey` field round-trip (HOTK-04 full closure)
- Ctrl+Z (or user-customized combo) toggles the bubble end-to-end

## Self-Check: PASSED

**Files created/modified (all verified present):**
- `src/magnifier_bubble/hotkey.py` — FOUND
- `src/magnifier_bubble/config.py` — FOUND
- `tests/test_hotkey.py` — FOUND
- `tests/test_hotkey_smoke.py` — FOUND
- `tests/test_config.py` — FOUND
- `.planning/phases/06-global-hotkey/06-02-SUMMARY.md` — FOUND

**Commits in git log (all verified):**
- `5af10a8` — FOUND
- `9974680` — FOUND
- `e32bdf7` — FOUND
