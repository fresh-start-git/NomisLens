# Phase 8: System Tray - Research

**Researched:** 2026-04-17
**Domain:** pystray 0.19.5 + tkinter threading integration on Windows 11
**Confidence:** HIGH (pystray source code read directly from .venv; all critical API behavior verified against installed package)

---

## Summary

Phase 8 adds a persistent system tray icon using pystray 0.19.5, which is already pinned in `requirements.txt` and installed in `.venv`. The library is well-suited for this project: on Windows, `icon.run()` can safely be called from a non-main thread, and `_run_detached()` spawns its own thread internally. The correct pattern for this project is **managed non-daemon thread** running `icon.run()` — matching the HotkeyManager pattern exactly. Every pystray callback fires on pystray's internal thread, so all mutations to AppState and all Tk calls must be marshaled via `root.after(0, ...)`.

The existing `destroy()` chain in `BubbleWindow` is the right integration point for `icon.stop()`. The tray manager follows the same `attach_tray_manager(mgr)` / `destroy()` duck-typed pattern established by `attach_config_writer` and `attach_hotkey_manager`. The tray Exit path calls `bubble.destroy()` via `root.after(0, ...)` — it must never call `root.destroy()` directly from pystray's thread.

`always_on_top` is stored in `AppState.StateSnapshot` and toggled via `state.toggle_aot()`, but `BubbleWindow._on_state_change` does NOT currently apply it (there is no `wm_attributes("-topmost", ...)` call in the observer). The tray's Always on Top menu item callback must call both `state.toggle_aot()` AND `root.wm_attributes("-topmost", snap.always_on_top)` on the main thread.

**Primary recommendation:** Implement `TrayManager` in `src/magnifier_bubble/tray.py` following the HotkeyManager pattern: non-daemon thread, `icon.run()` in `_run()`, `icon.stop()` in `stop()`. Wire into `app.py` and `BubbleWindow.destroy()` using the established duck-typed attach pattern.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TRAY-01 | App launches to system tray with a custom tray icon | `create_tray_image()` with PIL draws icon programmatically; `pystray.Icon` constructor takes PIL Image |
| TRAY-02 | Tray menu: Show/Hide, Always on Top toggle, Exit | `pystray.Menu` + `pystray.MenuItem`; `checked=lambda item: snap.always_on_top` for dynamic checkmark |
| TRAY-03 | Left-clicking the tray icon toggles bubble visibility | `pystray.MenuItem(..., default=True)` marks the item that fires on left-click; on Windows `HAS_DEFAULT_ACTION = True` |
| TRAY-04 | pystray on managed thread; all callbacks via `root.after(0, ...)` | Verified: `_win32.py _run_detached()` spawns a thread; our own non-daemon thread calling `icon.run()` is the pattern |
| TRAY-05 | `icon.stop()` before `root.destroy()` on exit | Enforced by `destroy()` ordering; `stop()` joins with 1 s timeout before any other teardown |
</phase_requirements>

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pystray | 0.19.5 | System tray icon + right-click menu | Already pinned in requirements.txt; installed in .venv; Windows backend confirmed |
| Pillow | 12.1.1 | PIL Image for the tray icon | Already a dependency; `ImageDraw` draws tray icon programmatically |
| threading | stdlib | Non-daemon thread for `icon.run()` | Matches HotkeyManager pattern; no extra dependency |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| PIL.ImageDraw | 12.1.1 | Draw magnifier shape on tray icon | Used in `create_tray_image()` — no external assets needed for PyInstaller |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pystray thread + `run()` | `run_detached()` | `run_detached()` on Windows spawns an internal daemon thread — we lose lifecycle control; our own non-daemon thread is cleaner for the `attach_tray_manager` / `destroy()` pattern |
| `run_detached()` | Main-thread `run()` | On Windows `run()` from non-main is safe; `run()` blocks main thread so tkinter mainloop cannot run |
| Programmatic PIL icon | External .ico asset | No external asset needed; PIL draws the icon in `create_tray_image()` — zero PyInstaller datas entry required |

**Installation:** Already installed. No new packages needed.

**Version verification:**

```
pystray 0.19.5  — verified: pip show pystray in .venv
Pillow 12.1.1   — verified: already pinned in requirements.txt
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/magnifier_bubble/
├── tray.py          # NEW: TrayManager (non-daemon thread, icon.run, icon.stop)
├── window.py        # AMEND: attach_tray_manager(), destroy() ordering
├── app.py           # AMEND: construct TrayManager after HotkeyManager, before start_capture
└── winconst.py      # NO CHANGE: no new Win32 constants needed for tray
```

```
tests/
├── test_tray.py          # NEW: structural/pure-Python lints for tray.py
└── test_tray_smoke.py    # NEW: Windows-only integration tests (skipif non-win32)
```

### Pattern 1: TrayManager — Non-Daemon Thread Running icon.run()

**What:** A class that owns the pystray icon lifecycle from construction through teardown. Mirrors HotkeyManager exactly: `start()` launches a non-daemon thread, `stop()` signals and joins it.

**Why non-daemon:** The `icon.run()` call blocks until `icon.stop()` is called. If the thread were a daemon thread and Python starts shutting down before `stop()` is called, the tray icon can be left orphaned in the Windows notification area (visible but dead). Non-daemon guarantees the `finally: icon.stop()` cleanup runs.

**When to use:** Always — this is the only pattern that satisfies TRAY-04 and TRAY-05.

**Example (verified against pystray._win32 source):**

```python
# Source: pystray._win32._run_detached() line 130-131 shows run() is safe from non-main thread
# Source: pystray._base.Icon.run() docstring says "must be called from main thread"
#         for macOS compatibility, but on Windows any thread is fine.
import threading
import pystray
from PIL import Image, ImageDraw

class TrayManager:
    def __init__(self, root, bubble):
        self._root = root      # Tk root — for root.after(0, ...) marshaling
        self._bubble = bubble  # BubbleWindow — for show/hide/destroy
        self._icon = self._build_icon()
        self._thread = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="tray-pump",
            daemon=False,       # guarantees icon.stop() in finally runs on interpreter exit
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._icon.stop()
        self._thread.join(timeout=1.0)
        self._thread = None

    def _run(self) -> None:
        try:
            self._icon.run()
        finally:
            pass  # icon.stop() already called; no Win32 owned resources to clean up

    def _build_icon(self) -> pystray.Icon:
        # Dynamic checked state reads AppState on each menu open
        def _is_aot(item):
            return self._bubble.state.snapshot().always_on_top

        menu = pystray.Menu(
            pystray.MenuItem("Show/Hide", self._on_toggle, default=True),
            pystray.MenuItem("Always on Top", self._on_toggle_aot, checked=_is_aot),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._on_exit),
        )
        return pystray.Icon(
            "NomisLens",
            icon=create_tray_image(),
            title="NomisLens",
            menu=menu,
        )

    # --- Callbacks (fire on pystray thread — must marshal to Tk main thread) ---
    def _on_toggle(self, icon, item):
        self._root.after(0, self._bubble.toggle)

    def _on_toggle_aot(self, icon, item):
        self._root.after(0, self._bubble.toggle_aot_and_apply)

    def _on_exit(self, icon, item):
        self._root.after(0, self._bubble.destroy)
```

### Pattern 2: Tray Icon Image — Programmatic PIL

**What:** `create_tray_image()` returns a 64×64 RGBA PIL Image of a magnifier (teal circle + handle on dark background). No external .ico file → no `datas=[]` entry in the spec.

**Why:** PyInstaller one-file mode extracts to a temp dir (`sys._MEIPASS`); file-based icons work but add complexity. PIL can render the icon in memory at startup from the same teal/colors the app already uses.

**Example:**

```python
def create_tray_image(size: int = 64) -> Image.Image:
    """Draw a teal magnifier icon. Returns RGBA PIL Image."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dc = ImageDraw.Draw(img)
    cx, cy = size // 2 - size // 10, size // 2 - size // 10
    r = size // 3
    # Lens circle — teal (#2ec4b6) outline on transparent background
    dc.ellipse([cx - r, cy - r, cx + r, cy + r],
               outline=(46, 196, 182, 255), width=max(2, size // 16))
    # Handle — bottom-right diagonal
    hx0 = cx + int(r * 0.7)
    hy0 = cy + int(r * 0.7)
    hx1 = size - size // 8
    hy1 = size - size // 8
    dc.line([hx0, hy0, hx1, hy1], fill=(46, 196, 182, 255), width=max(2, size // 16))
    return img
```

### Pattern 3: always_on_top Toggle — AppState + Tk wm_attributes

**What:** `AppState.toggle_aot()` flips `snap.always_on_top` and notifies observers. But `BubbleWindow._on_state_change` does NOT currently apply `always_on_top` — it is not in the observer diff. The tray callback must schedule a new method `toggle_aot_and_apply()` on `BubbleWindow` that calls `state.toggle_aot()` AND applies the setting to Tk.

**Verified gap:** Grepping `window.py` for `always_on_top` returns zero hits in `_on_state_change`. The Tk `-topmost` attribute is set once in `__init__` (Step 3) and never changed again.

**Fix pattern:**

```python
# In BubbleWindow (window.py):
def toggle_aot_and_apply(self) -> None:
    """Toggle always-on-top state and apply to the Tk window.
    Called from TrayManager._on_toggle_aot via root.after(0, ...).
    Must run on the Tk main thread.
    """
    self.state.toggle_aot()
    snap = self.state.snapshot()
    self.root.wm_attributes("-topmost", snap.always_on_top)
```

### Pattern 4: TrayManager attach + destroy() ordering

**What:** `TrayManager` uses the same duck-typed attach pattern as `ConfigWriter` and `HotkeyManager`.

**destroy() chain with tray (new slot shown):**

```
destroy():
  1. after_cancel zone_poll_id + poll_frame_queue_id
  2. Clear WS_EX_TRANSPARENT
  3. config_writer.flush_pending()     <- config flush (needs live root.after_cancel)
  4. hotkey_manager.stop()             <- WM_QUIT to hotkey worker
  5. tray_manager.stop()               <- icon.stop() + join  ← NEW SLOT
  6. capture_worker.stop() + join(1s)
  7. wndproc.uninstall canvas → frame → parent
  8. root.destroy()
```

**Why tray.stop() BEFORE capture.stop():** A late tray callback (scheduled on pystray's thread via root.after) could try to call `bubble.toggle()` after the capture worker is stopped, touching the frame queue. Stopping the tray first means no more pystray callbacks can be scheduled.

**Why tray.stop() AFTER hotkey.stop():** The hotkey worker may fire `bubble.toggle` at any moment up until `hotkey.stop()` returns. After hotkey and tray are both stopped, no external thread can schedule callbacks on the main thread.

**app.py wiring position:**

```python
# After attach_hotkey_manager, before start_capture:
if sys.platform == "win32":
    from magnifier_bubble.tray import TrayManager
    tm = TrayManager(bubble.root, bubble)
    tm.start()
    bubble.attach_tray_manager(tm)
    print("[tray] icon started", flush=True)
```

### Pattern 5: MenuItem left-click default action (TRAY-03)

**What:** On Windows, pystray fires the `default=True` menu item when the user left-clicks the tray icon. Verified: `_win32._on_notify()` handles `WM_LBUTTONUP` and calls the default menu item.

**Verified from source:** `pystray/_win32.py` line ~200: `if lparam == win32.WM_LBUTTONUP:` → activates the default menu item.

```python
pystray.MenuItem("Show/Hide", self._on_toggle, default=True)
```

### Anti-Patterns to Avoid

- **Calling root.destroy() directly from pystray callback:** Pystray callbacks run on pystray's thread, not the Tk main thread. Calling `root.destroy()` from any thread other than the Tk main thread causes "Calling Tcl from different apartment" RuntimeError or a crash. Always use `root.after(0, bubble.destroy)`.
- **Using run_detached() on Windows:** It spawns an internal daemon thread (`threading.Thread(target=lambda: self._run()).start()`). We lose control of the thread lifecycle and cannot reliably call `icon.stop()` in a specific order relative to other teardown steps.
- **Making always_on_top state reading thread-unsafe:** `icon.checked=lambda item: state.snapshot().always_on_top` — the lambda is called from pystray's thread (menu open). `AppState.snapshot()` uses a Lock, so this is safe. Do not read `snap.always_on_top` without the lock.
- **Not calling update_menu() after external state changes:** If `always_on_top` changes via a mechanism other than the tray menu itself (e.g., a future keyboard shortcut), `icon.update_menu()` must be called. For now the only toggle is the tray item, so the dynamic lambda handles it at menu-open time without needing `update_menu()`.
- **Daemon thread for the tray:** A daemon thread does not guarantee the icon is removed from the notification area on exit. Use `daemon=False` and `stop()` in `destroy()`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Shell_NotifyIcon Win32 API | Custom ctypes tray implementation | pystray 0.19.5 | pystray already handles NIM_ADD/NIM_DELETE, WM_TASKBARCREATED (tray restart), icon handles, HMENU creation/destruction — all edge cases are covered |
| Icon sizing for HiDPI | Manual DPI-aware icon scaling | pystray handles it | pystray's `_win32` backend calls `LoadImage` with LR_DEFAULTSIZE which Windows scales per-monitor |
| Threading + Tcl apartment check | Custom marshaling | `root.after(0, callback)` | This is the only documented thread-safe way to schedule Tk calls from a non-main thread in Python |

**Key insight:** The one custom piece needed is `create_tray_image()` (PIL drawing), because the app has no external icon asset. Everything else is pystray's responsibility.

---

## Common Pitfalls

### Pitfall T-1: Calling Tk from pystray thread
**What goes wrong:** `RuntimeError: Calling Tcl from different apartment` or silent crash.
**Why it happens:** Tcl/Tk is single-threaded and apartment-model. Pystray callbacks fire on pystray's own message-loop thread, not the Tk main thread.
**How to avoid:** Every pystray callback body must be exactly `self._root.after(0, callable)` — never call any Tk API or AppState.set_*() directly.
**Warning signs:** Intermittent RuntimeError in callbacks; menu items appear to work but state doesn't update.

### Pitfall T-2: root.destroy() from pystray thread
**What goes wrong:** Application hangs or crashes on exit.
**Why it happens:** Same as T-1 — `root.destroy()` is a Tk call.
**How to avoid:** Exit callback does `self._root.after(0, self._bubble.destroy)`. `bubble.destroy()` then calls `icon.stop()` in the correct sequence before `root.destroy()`.
**Warning signs:** App hangs on "Exit" from tray; ghost tray icon persists after process ends.

### Pitfall T-3: always_on_top not applied after toggle
**What goes wrong:** Tray menu "Always on Top" appears to toggle the checkmark but the window behavior doesn't change.
**Why it happens:** `AppState.toggle_aot()` updates `snap.always_on_top` and notifies observers, but `BubbleWindow._on_state_change` does NOT call `root.wm_attributes("-topmost", ...)` — verified by source inspection. The observer only handles shape/size/zoom.
**How to avoid:** Implement `BubbleWindow.toggle_aot_and_apply()` that calls `state.toggle_aot()` AND `root.wm_attributes("-topmost", snap.always_on_top)`.
**Warning signs:** Checkmark updates in tray menu but window can be covered by other windows.

### Pitfall T-4: icon.stop() hangs on Windows
**What goes wrong:** `icon.stop()` blocks for up to `SETUP_THREAD_TIMEOUT` (5 seconds) if the setup thread doesn't complete.
**Why it happens:** pystray's `stop()` joins the setup thread. If the setup thread is blocked waiting for the icon queue message (the `self.__queue.get()` in `_start_setup`), it never completes.
**How to avoid:** Do not pass a custom `setup=` to `icon.run()`. Use the default setup (which sets `visible=True`). This is the safe path.
**Warning signs:** App teardown takes 5+ seconds on exit.

### Pitfall T-5: "pystray._win32" missing at runtime in PyInstaller EXE
**What goes wrong:** `ImportError: this platform is not supported: No module named 'pystray._win32'`
**Why it happens:** pystray uses a dynamic import `from . import _win32` inside the `__init__.py`. PyInstaller does not detect dynamic platform imports.
**How to avoid:** Add `'pystray._win32'` to `hiddenimports` in `naomi_zoom.spec`. Already noted in REQUIREMENTS.md BULD-02.
**Warning signs:** App works in dev mode but fails at the tray startup line in the PyInstaller EXE.

### Pitfall T-6: Orphaned tray icon on crash / force-kill
**What goes wrong:** Ghost tray icon persists in the Windows notification area after the process is killed.
**Why it happens:** Windows clears ghost icons on the next `WM_TASKBARCREATED` message (when Explorer restarts). The pystray `_win32` backend already handles `WM_TASKBARCREATED` to re-add the icon — the reverse (cleanup on kill) is an OS limitation.
**How to avoid:** Acceptable. The ghost icon disappears when the user hovers over it (Windows hides stale icons) or on next Explorer restart. Not fixable in user code.
**Warning signs:** Ghost icon visible; clicking it does nothing. Normal behavior for killed processes.

### Pitfall T-7: Module-level import of pystray in window.py
**What goes wrong:** Breaks non-Windows CI (Linux) where pystray's `__init__.py` imports `_win32` which imports ctypes Win32 APIs.
**Why it happens:** pystray conditionally imports the platform backend on import, which works on Windows but fails on Linux if the Win32 backend is selected.
**How to avoid:** Follow the same deferred-import pattern as `clickthru.py` and `hotkey.py` — `from magnifier_bubble.tray import TrayManager` inside the `if sys.platform == "win32":` block in `app.py`. Keep `window.py` free of any `pystray` import at module scope.

---

## Code Examples

### Full TrayManager skeleton (verified pattern)

```python
# Source: pystray/_win32.py _run() + _run_detached() + _stop() inspected directly
# Source: pystray/_base.py run() + stop() inspected directly

import threading
import pystray
from PIL import Image, ImageDraw


def create_tray_image(size: int = 64) -> Image.Image:
    """Programmatic teal magnifier — no external file needed."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dc = ImageDraw.Draw(img)
    cx = cy = size // 2 - size // 8
    r = size // 3
    lw = max(2, size // 16)
    dc.ellipse([cx - r, cy - r, cx + r, cy + r],
               outline=(46, 196, 182, 255), width=lw)
    hx0 = cx + int(r * 0.7); hy0 = cy + int(r * 0.7)
    hx1 = size - size // 8;  hy1 = size - size // 8
    dc.line([hx0, hy0, hx1, hy1], fill=(46, 196, 182, 255), width=lw)
    return img


class TrayManager:
    def __init__(self, root, bubble) -> None:
        self._root = root
        self._bubble = bubble
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._icon = self._build_icon()
        self._thread = threading.Thread(
            target=self._run, name="tray-pump", daemon=False,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _run(self) -> None:
        try:
            self._icon.run()
        except Exception as exc:
            print(f"[tray] icon.run() raised: {exc}", flush=True)

    def _build_icon(self) -> pystray.Icon:
        def _is_aot(item):
            return self._bubble.state.snapshot().always_on_top

        menu = pystray.Menu(
            pystray.MenuItem("Show / Hide", self._cb_toggle, default=True),
            pystray.MenuItem("Always on Top", self._cb_toggle_aot,
                             checked=_is_aot),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._cb_exit),
        )
        return pystray.Icon(
            "NomisLens",
            icon=create_tray_image(),
            title="NomisLens",
            menu=menu,
        )

    # All callbacks: marshal to Tk main thread via root.after(0, ...)
    def _cb_toggle(self, icon, item):
        self._root.after(0, self._bubble.toggle)

    def _cb_toggle_aot(self, icon, item):
        self._root.after(0, self._bubble.toggle_aot_and_apply)

    def _cb_exit(self, icon, item):
        self._root.after(0, self._bubble.destroy)
```

### BubbleWindow additions (window.py)

```python
def attach_tray_manager(self, manager) -> None:
    """Wire a TrayManager so destroy() can stop it cleanly."""
    self._tray_manager = manager

def toggle_aot_and_apply(self) -> None:
    """Toggle always-on-top and apply to Tk. Called on main thread."""
    self.state.toggle_aot()
    snap = self.state.snapshot()
    self.root.wm_attributes("-topmost", snap.always_on_top)
```

### destroy() extension (window.py)

```python
# In destroy(), BETWEEN hotkey_manager.stop() and capture_worker.stop():
if self._tray_manager is not None:
    try:
        self._tray_manager.stop()
    except Exception as exc:
        print(f"[tray] stop failed during destroy err={exc}", flush=True)
    self._tray_manager = None
```

### naomi_zoom.spec hiddenimports addition

```python
hiddenimports=[
    # ... existing entries ...
    'pystray._win32',   # platform backend — dynamic import not detected by PyInstaller
],
```

### Dynamic checkmark pattern (verified from pystray source and docs)

```python
# checked= accepts a callable: called every time the menu is opened.
# The callable receives the MenuItem as its sole argument.
pystray.MenuItem(
    "Always on Top",
    self._cb_toggle_aot,
    checked=lambda item: self._bubble.state.snapshot().always_on_top,
)
# snapshot() is lock-protected — safe to call from pystray's thread.
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Shell_NotifyIcon direct ctypes | pystray 0.19.5 | Long-established | pystray handles WM_TASKBARCREATED (tray restart), icon handle lifecycle, HMENU |
| pystray run() from main thread | `threading.Thread(target=icon.run)` on Windows | pystray docs clarify: macOS-only restriction | On Windows, run() from non-main is safe; lets tkinter own the main thread |

**Deprecated/outdated:**
- `run_detached()` for tkinter+Windows integration: Still works but adds an internal daemon thread we can't control. Using our own non-daemon thread gives better lifecycle control.

---

## Open Questions

1. **Should always_on_top persist to config.json?**
   - What we know: `always_on_top` is in `StateSnapshot` but excluded from `_to_dict()` in `config.py` (it is not in `_PERSISTED_FIELDS`). It defaults to `True`.
   - What's unclear: Does Naomi want the always-on-top setting to survive restarts?
   - Recommendation: Do NOT persist for Phase 8. Defaults to `True` on each launch (current behavior). Leave persistence as a future enhancement. This avoids reopening the config.py / test suite impact.

2. **Minimize-to-tray vs. hide on close button?**
   - What we know: The existing close button (`✕` in top-left strip) calls `bubble.destroy()`.
   - What's unclear: Should `✕` hide the bubble (withdraw + show in tray) rather than destroy?
   - Recommendation: Keep current destroy behavior for close button. REQUIREMENTS.md has no requirement for "minimize to tray". The tray Show/Hide item is the show/hide mechanism. If Naomi prefers minimize-to-tray, it's a v2 UX change.

3. **Tooltip text for tray icon?**
   - What we know: `pystray.Icon(title=...)` sets the tooltip. Currently proposed as `"NomisLens"`.
   - Recommendation: Use `"NomisLens — Ctrl+Alt+Z to toggle"` to surface the hotkey to new clinic users.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (from requirements-dev.txt) |
| Config file | pyproject.toml (pytest.ini_options section) |
| Quick run command | `pytest tests/test_tray.py -x -q` |
| Full suite command | `pytest -x -q` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRAY-01 | TrayManager.start() creates a visible tray icon | Windows smoke (manual verify) | `pytest tests/test_tray_smoke.py::test_tray_icon_appears -x` | Wave 0 |
| TRAY-02 | Menu contains Show/Hide, Always on Top, Exit items | Structural (source scan) | `pytest tests/test_tray.py::test_tray_menu_items_present -x` | Wave 0 |
| TRAY-03 | Left-click default action wired to Show/Hide | Structural (MenuItem default=True check) | `pytest tests/test_tray.py::test_tray_showHide_is_default -x` | Wave 0 |
| TRAY-04 | All callbacks use root.after(0, ...) — no direct Tk calls | Source scan (AST / grep) | `pytest tests/test_tray.py::test_tray_callbacks_use_root_after -x` | Wave 0 |
| TRAY-04 | TrayManager runs on non-daemon thread | Structural assertion | `pytest tests/test_tray.py::test_tray_thread_is_non_daemon -x` | Wave 0 |
| TRAY-05 | icon.stop() called before root.destroy() | Source scan + smoke | `pytest tests/test_tray.py::test_tray_stop_before_destroy_ordering -x` | Wave 0 |
| TRAY-05 | Process terminates cleanly after tray Exit | Windows subprocess smoke | manual / `ULTIMATE_ZOOM_SMOKE` mode | manual |

### Structural Tests (cross-platform, no Win32)

These tests follow the established pattern from `test_hotkey.py`:

```python
# tests/test_tray.py — pure Python, runs on Linux CI

def test_tray_src_exists(): ...  # pathlib.exists() probe

def test_tray_uses_pystray(): ...  # "import pystray" in src

def test_tray_menu_items_present():
    src = _tray_src()
    assert "Show" in src or "Show / Hide" in src
    assert "Always on Top" in src
    assert "Exit" in src

def test_tray_showHide_is_default():
    src = _tray_src()
    # default=True must appear in the same MenuItem as the toggle callback
    assert "default=True" in src

def test_tray_callbacks_use_root_after():
    src = _tray_src()
    # Every callback body must schedule via root.after — direct Tk calls forbidden
    assert "root.after(0," in src or "self._root.after(0," in src
    # Direct forbidden patterns
    assert "root.destroy()" not in src   # must go through bubble.destroy()
    assert "root.withdraw()" not in src  # must go through bubble.hide()
    assert "root.deiconify()" not in src # must go through bubble.show()

def test_tray_thread_is_non_daemon():
    src = _tray_src()
    assert "daemon=False" in src

def test_tray_stop_before_destroy_ordering():
    # AST-walk window.py and verify tray_manager.stop() appears before root.destroy()
    # in the destroy() method body — same pattern as test_config_ordering in test_main_entry.py
    src = _window_src()
    stop_pos = src.find("tray_manager.stop()")
    destroy_pos = src.find("root.destroy()")
    assert stop_pos != -1, "tray_manager.stop() not found in window.py"
    assert destroy_pos != -1, "root.destroy() not found in window.py"
    assert stop_pos < destroy_pos

def test_tray_no_module_level_pystray_in_window():
    src = _window_src()
    # pystray must not be imported at window.py module scope
    # (breaks Linux CI — pystray._win32 only loadable on Windows)
    import ast
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "pystray" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                assert node.module is None or "pystray" not in node.module

def test_tray_no_module_level_pystray_in_app():
    # Same check for app.py — pystray must be inside if sys.platform == "win32": block
    src = _app_src()
    # The simplest structural check: pystray import must be inside a conditional
    assert 'import pystray' not in src.split("if sys.platform")[0]
```

### Windows-Only Smoke Tests

```python
# tests/test_tray_smoke.py
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")

def test_tray_icon_start_stop(tk_session_root):
    """TrayManager.start() creates an icon; stop() terminates cleanly within 2s."""
    from magnifier_bubble.tray import TrayManager, create_tray_image
    import time

    # Minimal stub bubble — just needs .state, .toggle, .destroy
    class _Stub:
        class state:
            @staticmethod
            def snapshot():
                from magnifier_bubble.state import StateSnapshot
                return StateSnapshot()
        @staticmethod
        def toggle(): pass
        @staticmethod
        def toggle_aot_and_apply(): pass
        @staticmethod
        def destroy(): pass

    tm = TrayManager(tk_session_root, _Stub())
    tm.start()
    time.sleep(0.3)   # allow icon to appear in shell notification area
    tm.stop()
    assert tm._thread is None or not tm._thread.is_alive()

def test_create_tray_image_returns_pil_image():
    from magnifier_bubble.tray import create_tray_image
    from PIL import Image
    img = create_tray_image()
    assert isinstance(img, Image.Image)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"
```

### Manual Verification Steps

These cannot be automated:

1. Launch app (`python main.py`) — verify tray icon appears in Windows notification area with teal magnifier glyph.
2. Right-click tray icon — verify menu shows "Show / Hide", "Always on Top" (checked), separator, "Exit".
3. Left-click tray icon — verify bubble toggles visible/hidden.
4. Click "Always on Top" — verify checkmark toggles AND bubble can be covered by other windows when unchecked.
5. Click "Exit" — verify app closes cleanly within 2 seconds and tray icon disappears.
6. After 5 minutes of menu interaction — verify no deadlock or leaked threads (`tasklist` shows one NomisLens process).

### Sampling Rate

- **Per task commit:** `pytest tests/test_tray.py -x -q`
- **Per wave merge:** `pytest -x -q` (full 230+ test suite)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_tray.py` — structural lints (cross-platform, Wave 0 scaffolding)
- [ ] `tests/test_tray_smoke.py` — Windows-only integration (TrayManager start/stop)
- [ ] `src/magnifier_bubble/tray.py` — does not exist yet (Wave 0 creates the file)

---

## Sources

### Primary (HIGH confidence)

- `C:/.../Naomi Zoom/.venv/Lib/site-packages/pystray/_win32.py` — `_run()`, `_run_detached()`, `_stop()`, `_on_notify()` read directly; confirms threading model and left-click default action dispatch
- `C:/.../Naomi Zoom/.venv/Lib/site-packages/pystray/_base.py` — `run()`, `stop()`, `_start_setup()`, `update_menu()` read directly; confirms callback threading, SETUP_THREAD_TIMEOUT=5s, daemon=False recommendation
- `C:/.../Naomi Zoom/src/magnifier_bubble/window.py` — `_on_state_change()` grep-verified: no always_on_top handling; `destroy()` chain verified; `attach_config_writer`/`attach_hotkey_manager` pattern verified
- `C:/.../Naomi Zoom/src/magnifier_bubble/state.py` — `toggle_aot()` confirmed present; `StateSnapshot.always_on_top=True` default confirmed
- `C:/.../Naomi Zoom/src/magnifier_bubble/hotkey.py` — HotkeyManager pattern used as design template (non-daemon thread, start/stop, root.after handoff)

### Secondary (MEDIUM confidence)

- pystray readthedocs search results — confirms `MenuItem(default=True)` is the left-click action on Windows; confirms `checked=lambda item: state` idiom for dynamic checkmarks
- pystray GitHub issue #55 search result — confirms `pystray._win32` must be in PyInstaller hiddenimports
- pystray thread + tkinter pattern search — confirms `threading.Thread(target=icon.run)` is safe on Windows; confirms `icon.stop()` before `root.destroy()` ordering

### Tertiary (LOW confidence)

- None. All critical claims verified against installed package source or official documentation.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pystray 0.19.5 installed, source code read directly
- Architecture: HIGH — based on direct inspection of pystray._win32, _base, and existing project patterns
- Pitfalls: HIGH — most derived from direct source inspection; T-6 (orphaned icon) is OS behavior (LOW independent verification)

**Research date:** 2026-04-17
**Valid until:** 2026-07-17 (pystray 0.19.5 is a stable release from Sep 2023; API unlikely to change)
