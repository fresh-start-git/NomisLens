# Phase 6: Global Hotkey - Research

**Researched:** 2026-04-13
**Domain:** Win32 global hotkey registration via ctypes on a dedicated message-pump thread, integrated with a Tk main loop without focus-stealing
**Confidence:** HIGH

## Summary

Phase 6 registers a system-wide hotkey (default Ctrl+Z, fallback Ctrl+Alt+Z) that toggles bubble visibility regardless of which app has focus. The mechanics are well-documented Win32 primitives: `user32.RegisterHotKey` with `hWnd=NULL` posts a `WM_HOTKEY` message to the **registering thread's queue**. Because a blocking `GetMessage` loop cannot cohabit with Tk's `mainloop`, the hotkey must live on a dedicated worker thread. UnregisterHotKey has a hard rule — it must be called from the same thread that registered — which turns into a concrete architectural constraint: the worker thread must be **non-daemon** with an explicit stop signal via `PostThreadMessageW(WM_QUIT)`, because Python 3.14 kills daemon threads abruptly with no cleanup opportunity, leaking the hotkey registration until the OS reclaims it on process exit.

The entire implementation is pure stdlib (`ctypes` + `threading`) — no new dependencies. All three of the rejected alternatives (`keyboard`, `pynput`, `global-hotkeys`) either require admin rights, install low-level hooks that interfere with Cornerstone's keyboard input, or have known reliability issues on Windows 11. The only genuinely tricky bit is the cross-thread handoff: WM_HOTKEY fires on the worker thread, but `state.set_visible()` and Tk widget calls MUST run on the main thread — the pattern is `root.after(0, lambda: state.toggle_visible())`, which is already proven safe in Phase 3 (capture thread uses the same pattern via `SimpleQueue` + polling, but for a single low-frequency event `root.after(0, ...)` is the textbook answer).

**Primary recommendation:** Create `src/magnifier_bubble/hotkey.py` with a `HotkeyManager` class that owns a non-daemon `threading.Thread` running a `GetMessageW` loop. Constructor takes `(root: tk.Tk, callback: Callable[[], None], modifiers: int, vk: int)`. `start()` launches the thread and blocks on an `Event` until the thread confirms registration succeeded (so the main thread can surface a graceful error if the hotkey is taken). `stop()` calls `PostThreadMessageW(tid, WM_QUIT, 0, 0)`, then `join(timeout=1.0)`. Mirror Phase 2's `wndproc.py` LONG_PTR-safe argtypes pattern and Phase 5's duck-typed `tk.Tk` type-only import.

## User Constraints

No CONTEXT.md exists for Phase 6 (no `/gsd:discuss-phase` was run). Constraints come from the phase description and STATE.md:

### Locked Decisions (from phase description + STATE.md)

- **ctypes + user32.RegisterHotKey ONLY** — no `keyboard` library, no `pynput`, no `global-hotkeys`
- **Daemon thread with message-pump** — the phase description says "daemon"; Section `## Architecture Patterns` explains why this MUST be changed to a **non-daemon** thread to satisfy HOTK-05 (clean unregistration on exit). The message-pump requirement stands.
- **No focus stealing** — hotkey must NOT activate the bubble or pull focus from Cornerstone
- **No admin rights** — RegisterHotKey does not require elevation; the `keyboard` library does, which is why it is rejected
- **Configurable via config.json** — already the Phase 5 mechanism; Phase 6 extends the schema
- **Graceful failure** — if already registered by another app, app continues running with a logged message (not a crash, not a silent failure)
- **Default Ctrl+Z, fallback Ctrl+Alt+Z** — user must confirm Cornerstone undo conflict before clinic deploy (Blockers/Concerns in STATE.md line 155)
- **Python 3.14 GIL discipline** — must be aware of `ctypes.PyDLL` vs `ctypes.windll` for hot-path calls made from inside WNDPROC callbacks (from `MEMORY.md` → `feedback_python314_ctypes_gil.md`)

### Claude's Discretion

- Schema shape for `hotkey` key in `config.json` (recommendation: `{"modifiers": ["ctrl", "alt"], "vk": "z"}` string-form for human edits, with a parser that accepts common aliases)
- Hotkey ID constant (recommendation: `0x0001` — any value in `0x0000..0xBFFF` is valid for an application)
- Thread name for diagnostic logs (recommendation: `"hotkey-pump"`)
- Whether to add a CLI flag `--no-hotkey` as an escape hatch (recommendation: YES — same spirit as Phase 4's `--no-click-injection`)
- Whether `WM_HOTKEY` wParam filtering is worth it (recommendation: YES — cheap defensive lint, protects against phantom WM_HOTKEY from other registrations in the same thread should Phase 7 tray add more)

### Deferred Ideas (OUT OF SCOPE)

- Multiple hotkeys (zoom in/out via keyboard, shape cycle via keyboard) — ACC-03 in v2 requirements
- Hotkey rebind UI in the tray menu — Phase 7 territory
- Hook-based keyboard capture for tracking Cornerstone keypresses — explicitly rejected in STATE.md
- Auto-detection of "hotkey already registered" with automatic fallback to a different combo — adds complexity; user should just edit `config.json` instead

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HOTK-01 | Ctrl+Z registered as system-wide hotkey via ctypes + user32.RegisterHotKey | Microsoft Learn RegisterHotKey reference; MOD_CONTROL=0x0002, VK Z=0x5A; ctypes signature in Pattern 1 |
| HOTK-02 | Hotkey works when Cornerstone/any app has focus | RegisterHotKey with hWnd=NULL posts WM_HOTKEY to the **thread queue** system-wide; no focus association |
| HOTK-03 | Hotkey toggles bubble visible/hidden | AppState.toggle_visible() already exists (state.py:104); Tk widget show/hide uses root.deiconify/withdraw; Pattern 3 wires them via root.after(0, …) |
| HOTK-04 | Hotkey configurable in config.json (default Ctrl+Z; Ctrl+Alt+Z safer) | Phase 5 config.py already owns the JSON schema; Pattern 4 extends it with `hotkey` key + parser |
| HOTK-05 | Registered/unregistered cleanly on start/exit; graceful failure if taken | UnregisterHotKey MUST be called from the same thread that registered (Win32 contract); Pattern 5 uses PostThreadMessageW(WM_QUIT) to signal the worker; non-daemon thread ensures the finally-block UnregisterHotKey actually runs; GetLastError==1409 (ERROR_HOTKEY_ALREADY_REGISTERED) surfaces the graceful-failure path |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ctypes (stdlib) | Py 3.11.9 / 3.14.3 | user32 RegisterHotKey/UnregisterHotKey/GetMessageW/PostThreadMessageW bindings | Already the project's Win32 FFI path (dpi.py, wndproc.py, shapes.py, clickthru.py); zero new dependency surface |
| threading (stdlib) | Py 3.11.9 / 3.14.3 | Dedicated worker thread carrying the GetMessage loop + Event-based ready signal | Python doesn't expose a raw Win32 thread API; threading.Thread wraps CreateThread correctly and integrates with `threading.Event` for synchronization |
| tkinter.Tk.after (stdlib) | Py 3.11.9 / 3.14.3 | Main-thread marshaling from the hotkey worker to state.toggle_visible() | Single documented thread-safe Tk primitive (see Python docs note in `tkinter` module) — Phase 3 capture thread and Phase 5 ConfigWriter both proven against this pattern |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pywin32 311 | pinned | NOT used for hotkey registration — keeps its role as SetWindowRgn / CreateEllipticRgnIndirect provider in shapes.py | Already present; do NOT expand its usage into hotkey.py — ctypes is intentionally direct because `win32con.WM_HOTKEY` / `win32api.RegisterHotKey` would introduce a pywin32 dependency edge in a pure-Win32 module |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ctypes + RegisterHotKey | `keyboard` library | REJECTED — archived Feb 2026 per STATE.md; requires admin rights; installs a low-level WH_KEYBOARD_LL hook that delays every keypress system-wide and has known Win11 reliability issues |
| ctypes + RegisterHotKey | `pynput` | REJECTED — also hook-based; STATE.md explicitly says "pynput rejected for Win11 reliability" |
| ctypes + RegisterHotKey | `global-hotkeys` PyPI | Thin wrapper around RegisterHotKey; no value added over direct ctypes; extra dependency for a 70-line module |
| dedicated thread | Tk timer polling PeekMessageW | Tk's mainloop owns the main thread's message queue — racing with PeekMessageW risks stealing Tk's own events. RegisterHotKey + threaded GetMessage is the cleanest separation. |
| dedicated thread | Install WM_HOTKEY handler in existing wndproc.py | Would require passing the bubble's HWND to RegisterHotKey; WM_HOTKEY would then route through the existing WndProc chain. Valid alternative but creates coupling between Phase 2 plumbing and Phase 6 config — a regression risk for the Phase 2+3 stability the user just verified. |

**Installation:** No new packages. `requirements.txt` unchanged.

**Version verification (2026-04-13):**
- Python 3.11.9 (research-specified) and 3.14.3 (dev box) both ship `ctypes` and `threading` in stdlib. No pip install required.
- user32.dll exports verified on Windows 11: RegisterHotKey (since Vista), UnregisterHotKey (since 2000), GetMessageW (since 2000), PostThreadMessageW (since 2000). All covered by the project's minimum supported OS (Win11 clinic PC).

## Architecture Patterns

### Recommended Project Structure

```
src/magnifier_bubble/
├── hotkey.py           # NEW — HotkeyManager class + parser
├── winconst.py         # EXTEND — add MOD_* + VK_* + WM_HOTKEY + WM_QUIT + hotkey error codes
├── config.py           # EXTEND — add `hotkey` field to schema + parser + defaults
├── state.py            # unchanged — toggle_visible already exists
├── window.py           # EXTEND — add show() / hide() wrappers over root.deiconify / withdraw; register on_change observer that reacts to visible flip
└── app.py              # EXTEND — construct HotkeyManager AFTER bubble AFTER ConfigWriter; wire stop() into bubble.destroy chain
tests/
├── test_hotkey.py      # NEW — pure-Python tests (parser, error-code mapping, argtypes lint, structural ban-lints)
├── test_hotkey_smoke.py # NEW — Windows-only integration (register + programmatic PostThreadMessage(WM_HOTKEY) + stop)
└── test_config.py      # EXTEND — hotkey key round-trip + clamp/default tests
```

### Pattern 1: RegisterHotKey + GetMessage loop on a dedicated thread

**What:** A worker thread registers the hotkey (associating it with its own thread via `hWnd=NULL`), runs a blocking `GetMessageW` loop, and translates WM_HOTKEY into a main-thread callback via `root.after(0, callback)`.

**When to use:** Always, for this phase. This is the ONLY pattern that satisfies HOTK-02 (system-wide) + HOTK-03 (toggle without focus theft) + HOTK-05 (clean unregister).

**Example (skeleton; planner will flesh out):**

```python
# Source: Microsoft Learn RegisterHotKey docs — https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey
# Example is verbatim pattern from the MSDN "MOD_NOREPEAT" sample, ported to ctypes.

import ctypes
import threading
from ctypes import wintypes
from typing import Callable

# See winconst.py additions below for MOD_CONTROL, MOD_NOREPEAT, WM_HOTKEY, WM_QUIT.
MOD_ALT       = 0x0001
MOD_CONTROL   = 0x0002
MOD_SHIFT     = 0x0004
MOD_WIN       = 0x0008
MOD_NOREPEAT  = 0x4000
WM_HOTKEY     = 0x0312
WM_QUIT       = 0x0012

_HOTKEY_ID = 0x0001  # in app range [0x0000..0xBFFF]
ERROR_HOTKEY_ALREADY_REGISTERED = 1409


def _apply_signatures(user32):
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype  = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype  = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype  = ctypes.c_int  # NOT BOOL — -1 is a valid error return
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostThreadMessageW.restype  = wintypes.BOOL


class HotkeyManager:
    def __init__(self, root, on_hotkey: Callable[[], None], modifiers: int, vk: int) -> None:
        self._root = root
        self._on_hotkey = on_hotkey
        self._modifiers = modifiers | MOD_NOREPEAT  # suppress keyboard auto-repeat
        self._vk = vk
        self._tid: int = 0                         # populated by the worker
        self._ready = threading.Event()            # signal: registration attempted
        self._reg_ok = False                       # populated by the worker
        self._reg_err = 0                          # populated by the worker
        self._thread: threading.Thread | None = None

    def start(self, timeout: float = 1.0) -> bool:
        # Non-daemon: must survive long enough to UnregisterHotKey on stop().
        self._thread = threading.Thread(
            target=self._run, name="hotkey-pump", daemon=False,
        )
        self._thread.start()
        self._ready.wait(timeout=timeout)
        return self._reg_ok

    def stop(self) -> None:
        if self._thread is None or self._tid == 0:
            return
        ctypes.windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        self._thread.join(timeout=1.0)
        self._thread = None

    def _run(self) -> None:
        user32 = ctypes.windll.user32
        _apply_signatures(user32)
        kernel32 = ctypes.windll.kernel32
        self._tid = kernel32.GetCurrentThreadId()

        # Force the thread's queue to exist BEFORE PostThreadMessageW is posted to it.
        # (See MSDN PostThreadMessageW Remarks — PeekMessage on WM_USER is the documented
        # idiom. GetMessageW below will also create it, but calling it once defensively
        # eliminates a race where stop() fires before the worker reaches GetMessage.)
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0x0400, 0x0400, 0)  # WM_USER range, no-remove

        ok = user32.RegisterHotKey(None, _HOTKEY_ID, self._modifiers, self._vk)
        if not ok:
            self._reg_err = ctypes.get_last_error()
            self._reg_ok = False
            self._ready.set()
            return  # thread exits — main thread surfaces the error
        self._reg_ok = True
        self._ready.set()
        try:
            while True:
                rc = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if rc == 0 or rc == -1:
                    break  # WM_QUIT or error
                if msg.message == WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                    # Cross-thread handoff — Tk after() is the ONLY safe primitive.
                    # If the root is destroyed between WM_HOTKEY and after(), the
                    # call raises RuntimeError — swallow it.
                    try:
                        self._root.after(0, self._on_hotkey)
                    except RuntimeError:
                        pass
        finally:
            # MUST run on the same thread that registered.  Non-daemon thread +
            # explicit WM_QUIT stop signal is what guarantees this finally fires.
            user32.UnregisterHotKey(None, _HOTKEY_ID)
```

### Pattern 2: Cross-thread handoff via root.after(0, …)

**What:** The hotkey worker NEVER touches Tk state directly. It calls `root.after(0, callback)` where `callback` runs on the Tk main thread and does the actual `state.toggle_visible()` + `root.deiconify()/withdraw()` work.

**When to use:** For EVERY main-thread action triggered by the hotkey.

**Example:**

```python
# Source: Phase 5 ConfigWriter._on_change pattern (config.py:253-261)
# and Phase 3 capture worker → main thread pattern (SimpleQueue + poll).
# The after(0, fn) idiom is the only Python docs-documented thread-safe Tk call.

def _on_hotkey_from_worker(self) -> None:
    """Runs on hotkey-pump thread.  MUST NOT touch Tk widgets."""
    self._root.after(0, self._toggle_visibility)

def _toggle_visibility(self) -> None:
    """Runs on Tk main thread (scheduled by after()).  Safe to touch widgets."""
    self._state.toggle_visible()
    if self._state.snapshot().visible:
        self._root.deiconify()
    else:
        self._root.withdraw()
```

### Pattern 3: BubbleWindow.show() / hide() wrappers

**What:** Wrap `root.deiconify()` and `root.withdraw()` on BubbleWindow so the toggle logic lives in one place and the AppState observer stays coherent with the Win32 visibility state.

**When to use:** Put this on BubbleWindow, not in hotkey.py, so tray (Phase 7) can reuse it.

**Example:**

```python
# Source: Phase 4-02 _on_state_change observer pattern (window.py:537-572)

def show(self) -> None:
    self.root.deiconify()
    self.state.set_visible(True)

def hide(self) -> None:
    self.root.withdraw()
    self.state.set_visible(False)

def toggle(self) -> None:
    if self.state.snapshot().visible:
        self.hide()
    else:
        self.show()
```

### Pattern 4: config.json schema extension

**What:** Add a single `hotkey` object to the JSON with `modifiers` (list of string names) and `vk` (single-character string or symbolic name). Human-editable; reverse-parseable; defaults cleanly without migration.

**When to use:** Immediately in Phase 6. Keep the top-level schema version at 1 — the new field is additive and existing configs without it get the default (Pitfall: `config.load` already filters via `_PERSISTED_FIELDS` so adding a field requires an allowlist update).

**Example JSON:**

```json
{
  "version": 1,
  "x": 200, "y": 200, "w": 400, "h": 400,
  "zoom": 2.0, "shape": "rect",
  "hotkey": {"modifiers": ["ctrl"], "vk": "z"}
}
```

**Parser:**

```python
# Source: same graceful-load pattern as config.load() (config.py:180-220).
# Bad modifiers → default.  Bad vk → default.  Log, don't raise.

_MOD_MAP = {
    "ctrl": MOD_CONTROL,
    "alt":  MOD_ALT,
    "shift": MOD_SHIFT,
    "win":  MOD_WIN,
}

def parse_hotkey(raw) -> tuple[int, int]:
    """Parse a hotkey dict → (modifiers_bitmask, vk_code). Never raises."""
    default = (MOD_CONTROL, 0x5A)  # Ctrl+Z
    if not isinstance(raw, dict):
        return default
    mods = 0
    for name in raw.get("modifiers", ["ctrl"]):
        bit = _MOD_MAP.get(str(name).lower())
        if bit is None:
            return default  # unknown modifier → bail, don't partial-parse
        mods |= bit
    vk_raw = str(raw.get("vk", "z")).upper()
    if len(vk_raw) == 1 and "A" <= vk_raw <= "Z":
        return (mods, ord(vk_raw))  # A=0x41..Z=0x5A by design
    if len(vk_raw) == 1 and "0" <= vk_raw <= "9":
        return (mods, ord(vk_raw))  # 0=0x30..9=0x39
    # Symbolic fallbacks could be added (F1..F12 etc.); out of scope for Phase 6.
    return default
```

### Pattern 5: Non-daemon worker thread with PostThreadMessageW shutdown

**What:** The worker is `daemon=False` because `UnregisterHotKey` MUST be called from the registering thread. A daemon thread would be killed before the `finally` block runs, leaking the registration.

**When to use:** Always for this phase. The phase description says "daemon"; correct interpretation is "a thread that lives alongside the main thread and handles the hotkey pump" — the word "daemon" is conversational, not a literal `daemon=True` directive. This is a semantic conflict the planner should flag and resolve by going with `daemon=False`.

**How shutdown works:**

1. Main thread (in `bubble.destroy()`) calls `hotkey_manager.stop()`.
2. `stop()` posts `WM_QUIT` to the worker via `PostThreadMessageW(tid, WM_QUIT, 0, 0)`.
3. Worker's `GetMessageW` returns 0 (== WM_QUIT).
4. `while True` loop breaks.
5. `finally` block runs `UnregisterHotKey(None, _HOTKEY_ID)` on the same thread.
6. Worker exits; `stop()`'s `thread.join(timeout=1.0)` returns.

### Anti-Patterns to Avoid

- **daemon=True + no stop signal:** Registration leaks until process exit (OS reclaims it, but HOTK-05 explicitly says "unregistered on clean exit" — the requirement text).
- **Calling `root.after(0, ...)` from the worker thread AFTER the root is destroyed:** Raises RuntimeError. Wrap in `try/except RuntimeError: pass` — same defensive pattern as Phase 2's WndProc `tk.TclError` swallow (window.py:728-730).
- **Using `ctypes.PyDLL` for RegisterHotKey:** This is NOT a hot-path WndProc callback. `ctypes.windll` is correct. The PyDLL rule from Phase 2 Pitfall K and Phase 4-03 clickthru.py test lint (`test_clickthru_no_pydll`) applies to WndProc-reentrant calls only — and `hotkey.py`'s GetMessage loop runs on its OWN thread, not inside any WINFUNCTYPE callback.
- **Registering from the main thread then pumping on the worker:** RegisterHotKey posts WM_HOTKEY to the **registering thread's** queue — if you register from the main thread, the WM_HOTKEY lands in Tk's queue and Tk won't dispatch it to your worker. Worker must call RegisterHotKey itself.
- **Omitting MOD_NOREPEAT:** Without this flag, holding Ctrl+Z produces a stream of WM_HOTKEY messages at the keyboard repeat rate — the bubble would flicker on/off. MOD_NOREPEAT is Windows 7+ and is the documented fix.
- **Forgetting GetMessageW returns -1 on error, not BOOL:** `while GetMessageW(...)` is a classic Win32 bug (return can be nonzero, zero=WM_QUIT, or -1=error). Handle -1 explicitly — Microsoft's own docs flag this pitfall.
- **Blocking the hotkey thread on any Tk call:** Worker MUST be Tk-free. Every action crosses via `root.after(0, ...)`.
- **Registering with `hWnd=bubble._hwnd`:** Would make WM_HOTKEY route through the existing WndProc chain — viable but couples Phase 6 to Phase 2's plumbing. The `hWnd=NULL` thread-queue approach is cleaner and Microsoft's own sample uses it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Global hotkey detection | `SetWindowsHookExW(WH_KEYBOARD_LL, ...)` with your own dispatch | `RegisterHotKey` | Low-level hooks run on every keypress system-wide, slow down all keyboard input, require admin rights on some Win11 configurations, and interfere with Cornerstone's own input handling. RegisterHotKey is the OS-provided fast path designed exactly for this. |
| Cross-thread main-thread dispatch | A bespoke `queue.Queue` + `root.after(100, poll)` loop | `root.after(0, fn)` direct scheduling | Phase 3 needed `SimpleQueue` because capture produces 30 frames/second — a burst queue shape. Phase 6 has ONE infrequent event; direct `root.after(0, fn)` is simpler and has proven Tk-thread-safety. |
| Thread signalling | Boolean flag + busy-wait | `PostThreadMessageW(WM_QUIT)` | The worker is already in `GetMessageW` (blocked); a flag can't wake it. Windows' own shutdown primitive is the documented solution. |
| Hotkey string parsing (e.g. "Ctrl+Alt+Z") | A full pyparsing grammar | The `parse_hotkey(dict)` shown above | Keep the config schema as structured JSON objects, not strings. Parsers for "Ctrl+Z" strings are where bugs live (case, unicode + signs, alias drift). A `{modifiers: [list], vk: str}` shape is bullet-proof. |
| Error code mapping | Guess from the return value | `ctypes.get_last_error()` + known-code map | RegisterHotKey fails with GetLastError=1409 (`ERROR_HOTKEY_ALREADY_REGISTERED`) — that's the graceful-failure case. Other return values (0 with different error codes) should be logged verbatim. Don't try to be clever; Microsoft's error codes are documented. |

**Key insight:** Everything Phase 6 needs is already in user32 + Python stdlib. The one real decision is thread-lifecycle (non-daemon + WM_QUIT signal) — the rest is boilerplate.

## Common Pitfalls

### Pitfall 1: UnregisterHotKey fails silently because it's called from the wrong thread

**What goes wrong:** The finally block calls UnregisterHotKey, but from a different thread than RegisterHotKey. The call returns FALSE, GetLastError=1419 (`ERROR_HOTKEY_NOT_REGISTERED`), and the hotkey stays live.

**Why it happens:** Win32 ties hotkey ownership to the registering thread's ID. If you register from the worker and stop() unregisters from main, Windows sees "no such hotkey for caller."

**How to avoid:** Put both RegisterHotKey AND UnregisterHotKey in the worker's `_run()` method. The main thread only signals "please stop" via PostThreadMessageW(WM_QUIT). The worker itself runs the finally.

**Warning signs:** On app exit, the hotkey still blocks its combo for ~minutes (until the OS cleans up the dead thread's registrations), OR a subsequent app launch sees GetLastError=1409 because the old registration is still held.

### Pitfall 2: Daemon thread killed before finally runs

**What goes wrong:** Thread is `daemon=True`, main exits, worker is abruptly terminated by the interpreter (Python 3.14 semantics: "abruptly stopped at shutdown"). The UnregisterHotKey in the `finally` never runs.

**Why it happens:** Daemon threads are designed for "I don't care about cleanup." Phase 6 DOES care about cleanup (HOTK-05).

**How to avoid:** `daemon=False` + explicit `stop()` call in `bubble.destroy()` (which runs BEFORE root.destroy() at the top of the try block — mirror the Phase 5 ConfigWriter flush ordering).

**Warning signs:** Second app launch logs GetLastError=1409 for a hotkey that was never intentionally stolen.

### Pitfall 3: Race between stop() and the worker's RegisterHotKey

**What goes wrong:** Main thread calls `stop()` immediately after `start()` but before the worker reaches `RegisterHotKey`. `PostThreadMessageW` fires but the worker's message queue might not exist yet (queues are lazy-created on first User/GDI call in a thread).

**Why it happens:** Python threading.Thread.start() returns after OS thread creation but before user code runs.

**How to avoid:** Use a `threading.Event` (`_ready`) the worker sets right after registration (success or failure). `start()` waits on this before returning, so the caller can trust that the thread queue exists and (if registration succeeded) the hotkey is live. Additionally, call `PeekMessageW(..., WM_USER, WM_USER, PM_NOREMOVE)` near the top of `_run()` to force the thread queue into existence before PostThreadMessageW could ever fire.

**Warning signs:** Intermittent stop() hangs until join() timeout; UnregisterHotKey never runs.

### Pitfall 4: Calling root.after() from the worker after root is destroyed

**What goes wrong:** User presses hotkey during app shutdown. Worker sees WM_HOTKEY, calls `self._root.after(0, self._toggle)`, but `self._root` is mid-teardown. RuntimeError.

**Why it happens:** Destroy ordering: `bubble.destroy()` calls `hotkey_manager.stop()` (good), but between WM_HOTKEY arriving in the queue and the worker seeing it, the main thread might already be tearing Tk down.

**How to avoid:** Wrap the `after(0, ...)` call in `try/except RuntimeError: pass`. Same defensive style as window.py:728 swallowing TclError on destroy.

**Warning signs:** Stderr shows `RuntimeError: main thread is not in main loop` on app close. Cosmetic; the app still exits cleanly.

### Pitfall 5: MOD_NOREPEAT missing; holding the hotkey floods WM_HOTKEY messages

**What goes wrong:** User holds Ctrl+Z (keyboard auto-repeat ~30Hz). Worker gets 30 WM_HOTKEY per second, schedules 30 toggles per second. Bubble flickers uncontrollably.

**Why it happens:** RegisterHotKey without MOD_NOREPEAT treats each auto-repeated keydown as a fresh hotkey press.

**How to avoid:** Always OR `MOD_NOREPEAT` (0x4000) into the modifiers bitmask. Windows 7 / Vista SP2+ — universally available on Win11.

**Warning signs:** Flicker during held keypress. Easy to miss in development (most devs tap rather than hold).

### Pitfall 6: GetMessageW return value misinterpreted

**What goes wrong:** `while user32.GetMessageW(...):` — the Win32 ABI returns -1 on error (e.g., invalid pointer). Python sees -1 as truthy, loop continues spinning on a broken call.

**Why it happens:** The function is documented `BOOL` but actually returns `int` with three legal values (nonzero, 0=WM_QUIT, -1=error). Microsoft's own docs call this pitfall out explicitly (quoted in Sources).

**How to avoid:** Declare `user32.GetMessageW.restype = ctypes.c_int` (NOT wintypes.BOOL). Check `rc == 0 or rc == -1` and break in both cases. If -1, log `ctypes.get_last_error()`.

**Warning signs:** 100% CPU after a thread queue becomes invalid (e.g., forcibly terminated root window).

### Pitfall 7: LONG_PTR-style pointer truncation on x64 (DWORD tid works, argtypes still matter)

**What goes wrong:** A missing `argtypes = [wintypes.DWORD, ...]` on PostThreadMessageW causes Python to marshal the tid as default `c_int` which is 32-bit but signed — `GetCurrentThreadId` returns an unsigned DWORD that may set the sign bit for large TIDs.

**Why it happens:** Same family of bug as Phase 1-03 dpi.py and Phase 2-02 wndproc.py. ctypes default int marshaling fails when the native call expects specific width/sign.

**How to avoid:** Apply argtypes/restype on first access via the `_apply_signatures(user32)` helper pattern (see hotkey.py skeleton above). Mirror Phase 2 wndproc.py `_SIGNATURES_APPLIED` sentinel.

**Warning signs:** PostThreadMessageW returns 0 and GetLastError=1444 (ERROR_INVALID_THREAD_ID) on stop() even though the thread is alive.

### Pitfall 8: Hotkey stolen by Windows PowerToys / third-party software in clinic environment

**What goes wrong:** The clinic PC has PowerToys, Microsoft OneNote, or screen-capture software installed, all of which register Ctrl+* hotkeys.

**Why it happens:** RegisterHotKey is first-come-first-served system-wide.

**How to avoid:** On GetLastError==1409, print a CLEAR message: `[hotkey] Ctrl+Z is already registered by another app; bubble will not respond to the hotkey. Edit config.json to change the hotkey (e.g., {"modifiers": ["ctrl", "alt"], "vk": "z"}) and relaunch.` App continues running — tray will still provide Show/Hide in Phase 7.

**Warning signs:** User complains "hotkey doesn't work" — log scroll will show the 1409.

### Pitfall 9: Docstring containing banned substrings trips the module's own structural lint

**What goes wrong:** Historically recurrent across this codebase — Phase 2-02, Phase 4-03, Phase 5-01 all hit it. Module docstring mentions `keyboard` (the banned library) or `pynput` (the banned library) and the structural lint fails.

**Why it happens:** Tests use `src.count("keyword")` or substring checks on the source file to enforce "this module must not import X." The lint cannot distinguish "documented the forbidden thing" from "actually uses it."

**How to avoid:** Write docstrings that describe forbidden alternatives WITHOUT naming them literally ("low-level hook libraries are rejected in favor of this approach"), OR scope the lint to non-docstring nodes only (parse AST, skip `ast.Expr(Constant(str))` first).

**Warning signs:** Tests fail with `assert 'keyboard' not in source` or similar; grep shows the only occurrence is a harmless docstring comment.

### Pitfall 10: Hotkey fires during Cornerstone typing (modifier-noise theft)

**What goes wrong:** User is typing into Cornerstone and happens to hit Ctrl+Z to undo. The bubble also toggles because Ctrl+Z is OUR hotkey too.

**Why it happens:** RegisterHotKey is global — first-come-first-served. When we register Ctrl+Z, Cornerstone's in-app Ctrl+Z handling is blocked for the same combo.

**How to avoid:** This is the real reason STATE.md says "confirm Ctrl+Z vs. Cornerstone undo conflict with user before clinic deploy, safer default is Ctrl+Alt+Z." Phase 6 must include a Wave 0 task: "Get user decision on Ctrl+Z vs Ctrl+Alt+Z default." The safer default (Ctrl+Alt+Z) should be the fallback in `config.py` if we can't get a quick answer — it's unlikely to conflict with any real app.

**Warning signs:** User reports "every time I undo in Cornerstone the bubble disappears." Swap default to Ctrl+Alt+Z and rebuild.

## Code Examples

### WM_HOTKEY wParam/lParam decoding

```python
# Source: Microsoft Learn WM_HOTKEY — https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-hotkey
# wParam = hotkey ID (what we passed to RegisterHotKey)
# lParam = (vk << 16) | modifier_flags  — low word mods, high word vk
#
# For Phase 6 we only register ONE hotkey so wParam is always our _HOTKEY_ID (0x0001).
# We defensively filter on it anyway, in case Phase 7's tray adds a second hotkey later.

if msg.message == WM_HOTKEY and msg.wParam == _HOTKEY_ID:
    # Optional: unpack lParam for logging / diagnostics
    # mods = msg.lParam & 0xFFFF
    # vk   = (msg.lParam >> 16) & 0xFFFF
    try:
        self._root.after(0, self._on_hotkey)
    except RuntimeError:
        pass
```

### Graceful failure path (GetLastError==1409)

```python
# Source: STATE.md + Microsoft Learn RegisterHotKey "Return value" section
# + AmazingAlgorithms blog post on error 1409 (verified via MSDN for the constant)

if not ok:
    err = ctypes.get_last_error()
    if err == 1409:  # ERROR_HOTKEY_ALREADY_REGISTERED
        print(
            "[hotkey] registration failed: another app is already using "
            f"this combination (GetLastError={err}). The bubble will "
            "still run, but will not respond to the hotkey. "
            "Edit config.json to change the hotkey and relaunch.",
            flush=True,
        )
    else:
        print(f"[hotkey] registration failed: GetLastError={err}", flush=True)
    self._reg_ok = False
    self._ready.set()
    return  # _run exits; main thread sees start() returned False
```

### winconst.py additions

```python
# --- Phase 6 additions ---

# RegisterHotKey modifier flags (winuser.h).
MOD_ALT      = 0x0001
MOD_CONTROL  = 0x0002
MOD_SHIFT    = 0x0004
MOD_WIN      = 0x0008
MOD_NOREPEAT = 0x4000  # Windows 7+; suppresses auto-repeat flood.

# Virtual-key codes we actually care about for the default / fallback hotkey.
# The full A-Z / 0-9 range is ASCII-uppercase (A=0x41..Z=0x5A, 0=0x30..9=0x39).
VK_Z = 0x5A

# Thread-queue message used by GetMessage to distinguish hotkey events.
WM_HOTKEY = 0x0312
# Posted by PostThreadMessageW to break the worker out of GetMessage.
WM_QUIT   = 0x0012

# Well-known RegisterHotKey error code — SurfacE gracefully, don't crash.
ERROR_HOTKEY_ALREADY_REGISTERED = 1409
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `keyboard` library | direct ctypes + RegisterHotKey | Feb 2026 (library archived) | STATE.md already documents this; no work for Phase 6 |
| `pynput` low-level hooks | direct ctypes + RegisterHotKey | n/a (never used in this project) | Documented in STATE.md decisions |
| Daemon thread with busy-wait flag | Non-daemon thread + PostThreadMessageW(WM_QUIT) | Py 3.14 daemon-thread cleanup semantics tightened | Planner MUST push back on the phase description's "daemon thread" wording |
| `hWnd=bubble._hwnd` + WM_HOTKEY in wndproc.py | `hWnd=NULL` + own worker thread | Architectural preference — decouples Phase 6 from Phase 2 | Cleaner, but this is a judgment call the planner could revisit |

**Deprecated/outdated:**
- `keyboard` library — archived on PyPI, no longer maintained.
- Win7-only `RegisterHotKey` quirks (pre-Vista) — we target Win11 only; all Vista+ features (including MOD_NOREPEAT) are guaranteed.

## Open Questions

1. **Default hotkey: Ctrl+Z vs Ctrl+Alt+Z?**
   - What we know: STATE.md "Blockers/Concerns" line 155 says the Ctrl+Z vs Cornerstone undo conflict must be confirmed with the user. ROADMAP.md "Research Flags" line 172 reiterates this.
   - What's unclear: Has the user been asked? No CONTEXT.md exists for this phase, so probably not.
   - Recommendation: Plan should include a Wave 0 human-verify task that asks the user "Does Cornerstone use Ctrl+Z for undo?" and defaults to `Ctrl+Alt+Z` in `config.py` if the answer is "yes" or "unknown." If the answer is "no" or "I want Ctrl+Z anyway," default to `Ctrl+Z`. This is a 1-minute conversation, not research.

2. **Does the hotkey need to work when the bubble is `withdraw`n?**
   - What we know: Ordinary Win32 hotkeys work regardless of window state. RegisterHotKey with hWnd=NULL is completely decoupled from any window. So yes.
   - What's unclear: Does Tk's `withdraw()` leave the window's message queue alive? Yes, per tkdocs — withdraw is cosmetic, not destructive.
   - Recommendation: No action. The design above handles this automatically — the worker thread is independent, `root.after(0, ...)` works on a withdrawn root, and `deiconify()` un-withdraws.

3. **Should we register a SECOND hotkey for "always on top" toggle or for Exit?**
   - What we know: Requirements list only HOTK-01 through HOTK-05, all targeting a SINGLE show/hide toggle. Multi-hotkey is v2 (ACC-03).
   - What's unclear: Nothing — out of scope.
   - Recommendation: Design HotkeyManager for ONE hotkey. If Phase 7 tray wants another (e.g., "toggle always-on-top"), Phase 7 plan can either instantiate a second HotkeyManager (cheap — each takes its own thread) or refactor to a list-of-hotkeys variant. Don't over-engineer Phase 6.

4. **Where does HotkeyManager construction go in app.py main()?**
   - What we know: Construction order chain is documented in STATE.md for Phase 5-02: `argparse → dpi.debug_print → config.config_path → config.load → AppState(snap) → BubbleWindow → ConfigWriter → attach_config_writer → start_capture → mainloop`.
   - What's unclear: Where Phase 6 splices in.
   - Recommendation: Between `attach_config_writer` and `start_capture`. HotkeyManager needs `bubble.root` (live), `state` (to toggle visible), and the parsed `hotkey` config (available after `config.load`). Add `bubble.attach_hotkey_manager(hm)` to symmetrize with `attach_config_writer`. Stop ordering in `bubble.destroy()`: flush_config_writer (current top of try) → **stop hotkey manager** → capture_worker.stop() → wndproc.uninstall() → root.destroy(). Put the hotkey stop BEFORE capture stop so any late WM_HOTKEY can't call `root.after(0, ...)` on a capture-teardown racing root.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ (from requirements-dev.txt) |
| Config file | pyproject.toml `[tool.pytest.ini_options]` (pythonpath=["src"], testpaths=["tests"]) |
| Quick run command | `pytest tests/test_hotkey.py -x` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HOTK-01 | RegisterHotKey invoked via ctypes (NOT keyboard/pynput) | unit (structural lint) | `pytest tests/test_hotkey.py::test_hotkey_uses_ctypes_not_keyboard_lib -x` | Wave 0 |
| HOTK-01 | MOD_* + VK_* constants match MSDN values | unit | `pytest tests/test_hotkey.py::test_winconst_mod_values_match_msdn -x` | Wave 0 |
| HOTK-01 | argtypes applied on RegisterHotKey / UnregisterHotKey / GetMessageW / PostThreadMessageW | unit (structural) | `pytest tests/test_hotkey.py::test_hotkey_applies_argtypes -x` | Wave 0 |
| HOTK-02 | Hotkey fires while Cornerstone has focus | manual-only | human-verify in Phase 6 plan | n/a — requires real Cornerstone focus |
| HOTK-03 | Pressing hotkey toggles visible flag in AppState | integration (Windows) | `pytest tests/test_hotkey_smoke.py::test_wm_hotkey_toggles_visible_via_after -x` | Wave 0 |
| HOTK-03 | BubbleWindow.show/hide/toggle wraps state + deiconify/withdraw | unit | `pytest tests/test_window_phase4.py::test_bubble_show_hide_toggle -x` (extend existing file) | existing — EXTEND |
| HOTK-04 | parse_hotkey round-trips through config.json | unit | `pytest tests/test_config.py::test_hotkey_roundtrip -x` (extend existing file) | existing — EXTEND |
| HOTK-04 | parse_hotkey defaults on corrupt/missing fields | unit | `pytest tests/test_config.py::test_hotkey_defaults_on_corrupt -x` | existing — EXTEND |
| HOTK-04 | parse_hotkey rejects unknown modifier names | unit | `pytest tests/test_config.py::test_hotkey_rejects_unknown_modifier -x` | existing — EXTEND |
| HOTK-05 | start() returns False + logs when hotkey taken (simulate by registering twice) | integration (Windows) | `pytest tests/test_hotkey_smoke.py::test_second_register_fails_gracefully -x` | Wave 0 |
| HOTK-05 | stop() posts WM_QUIT and joins within 1s | integration (Windows) | `pytest tests/test_hotkey_smoke.py::test_stop_posts_quit_and_joins -x` | Wave 0 |
| HOTK-05 | UnregisterHotKey called from the SAME thread that registered | unit (structural) | `pytest tests/test_hotkey.py::test_register_and_unregister_in_same_function -x` | Wave 0 |
| HOTK-05 | Thread is `daemon=False` | unit (structural) | `pytest tests/test_hotkey.py::test_hotkey_thread_is_non_daemon -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_hotkey.py -x` (pure-Python lints, runs anywhere including Linux CI)
- **Per wave merge:** `pytest` (full suite; Windows-only smoke tests auto-skip on Linux via `@pytest.mark.skipif(sys.platform != "win32", ...)`)
- **Phase gate:** Full suite green + manual verification on Windows 11 dev box per the 5 Success Criteria + answer user question on Ctrl+Z default before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_hotkey.py` — covers HOTK-01, HOTK-04 (structural), HOTK-05 (structural). Pure-Python; creates AST lints and argtypes-presence assertions.
- [ ] `tests/test_hotkey_smoke.py` — covers HOTK-03, HOTK-05 (integration). Windows-only; uses `@pytest.mark.skipif(sys.platform != "win32")` fixture pattern already established in `test_shapes_smoke.py` / `test_capture_smoke.py` / `test_config_smoke.py`.
- [ ] Extend `tests/test_config.py` with hotkey parser tests (HOTK-04 unit layer).
- [ ] Extend `tests/test_window_phase4.py` OR new `tests/test_window_visibility.py` with `show()` / `hide()` / `toggle()` smoke tests using the `tk_toplevel` fixture already defined in `tests/conftest.py`.
- [ ] Add `--no-hotkey` CLI flag support in `app.py` + structural lint in `tests/test_main_entry.py` (parallel to the existing `--no-click-injection` pattern established in Phase 4-03).
- [ ] `WM_HOTKEY` + `MOD_*` + `VK_Z` + `WM_QUIT` + `ERROR_HOTKEY_ALREADY_REGISTERED` additions to `winconst.py` with a `test_winconst_phase6_values` assertion.

## Sources

### Primary (HIGH confidence)

- [Microsoft Learn — RegisterHotKey](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey) — signature, MOD_* values including MOD_NOREPEAT (0x4000), id range, F12 reservation, thread-queue posting when hWnd=NULL, note that the function fails if trying to associate with another thread's window
- [Microsoft Learn — UnregisterHotKey](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-unregisterhotkey) — "Frees a hot key previously registered by the calling thread" — this sentence is the load-bearing contract for why the worker must own both ends
- [Microsoft Learn — WM_HOTKEY message](https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-hotkey) — message id 0x0312, wParam = hotkey id, lParam low word = modifier flags + high word = vk, "The message is placed at the top of the message queue associated with the thread that registered the hot key"
- [Microsoft Learn — GetMessage](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getmessage) — return value semantics (nonzero, 0=WM_QUIT, -1=error), thread-queue filtering when hWnd=NULL, explicit pitfall-warning about `while(GetMessage(...))` antipattern
- [Microsoft Learn — PostThreadMessageW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-postthreadmessagew) — thread queue must exist before the post; PeekMessage(WM_USER,...) idiom to force queue creation; marshalling notes
- [Microsoft Learn — MSG structure](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-msg) — HWND + UINT + WPARAM + LPARAM + DWORD + POINT + DWORD layout
- [Microsoft Learn — Virtual-Key Codes](https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes) — A=0x41..Z=0x5A, 0=0x30..9=0x39 are symbolic letter/number codes (ASCII uppercase)
- [Python docs — threading.Thread.daemon](https://docs.python.org/3/library/threading.html#threading.Thread.daemon) — "Daemon threads are abruptly stopped at shutdown. Their resources ... may not be released properly. If you want your threads to stop gracefully, make them non-daemonic."
- Local memory `feedback_python314_ctypes_gil.md` — PyDLL vs windll discipline; applies to hot-path WNDPROC callbacks only, NOT to a GetMessage loop on a non-GUI worker thread

### Secondary (MEDIUM confidence)

- [AmazingAlgorithms — "How to fix ERROR_HOTKEY_ALREADY_REGISTERED"](https://amazingalgorithms.com/blog/hot-key-is-already-registered-error_hotkey_already_registered-0x581-error-code-1409-windows-error/) — corroborates 0x581=1409 error code; cross-verified against Microsoft Learn RegisterHotKey "Return value" section
- Microsoft Q&A thread ["error while registering the hotkey in C#"](https://learn.microsoft.com/en-us/answers/questions/1020405/error-while-registering-the-hotkey-in-c) — community confirmation that 1409 surfaces when another app has the combo
- [Jitsi Community — "Problem with RegisterHotKey: 1409"](https://community.jitsi.org/t/jitsi-users-problem-with-registerhotkey-1409/9170) — real-world occurrence, underscores the "first-come-first-served" nature

### Tertiary (LOW confidence — not relied on for decisions)

- Various finxter.com blog posts on Python hotkeys (recommend `keyboard`/`pynput` — contrary to STATE.md decisions; used only to confirm the libraries we reject exist as known alternatives)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pure stdlib, Microsoft Learn confirms every API surface
- Architecture: HIGH — patterns verified against official MSDN samples (RegisterHotKey page's own MOD_ALT+b example uses the same hWnd=NULL + GetMessage loop we're adopting)
- Pitfalls: HIGH — every pitfall is either explicitly documented by Microsoft (GetMessage -1 return, MOD_NOREPEAT flood, thread-owned unregister) or comes from this project's own STATE.md history (docstring-lint foot-gun, LONG_PTR argtypes discipline, Tk thread safety)

**Research date:** 2026-04-13
**Valid until:** 2026-05-13 (30 days; Win32 API surface is extremely stable, Python 3.14 threading semantics locked for the release line)
