# Architecture Research — Magnifier Bubble (Ultimate Zoom)

**Domain:** Windows 11 desktop overlay / real-time screen magnifier in Python
**Researched:** 2026-04-10
**Confidence:** HIGH

---

## TL;DR — The Architecture in One Paragraph

Three threads, one process: the **Tk main thread** owns all UI and is the only thread allowed to touch widgets and win32 window handles. A **capture worker thread** drives an mss grab → Pillow resize → ImageTk loop and pushes finished `PhotoImage` objects to the main thread via `root.after(0, ...)`. A **hotkey thread** blocks on `GetMessageW` waiting for `WM_HOTKEY` and similarly hands toggles back via `root.after`. Pystray runs on its own thread that it manages internally. A small **AppState** module is the single source of truth for position, size, zoom, and shape; every mutation goes through it, and it debounces writes to `config.json`. The UI is one `tkinter.Toplevel` window whose WndProc has been subclassed (via `SetWindowLongPtrW` with `GWLP_WNDPROC`) to return `HTTRANSPARENT` for the middle zone and `HTCAPTION` for the drag bar. A single `SetWindowRgn` call applies shape masking to the whole window; the three zones are simply `tkinter.Frame`s stacked inside that shaped region.

---

## System Overview

### High-Level Component Diagram

```
┌───────────────────────────────────────────────────────────────────────┐
│                             Process (single)                          │
│                                                                       │
│  ┌─────────────────────┐   put_nowait   ┌───────────────────────┐    │
│  │  Capture Thread     │ ──────────────>│   Frame Queue         │    │
│  │  (daemon)           │                │   (maxsize=2)         │    │
│  │                     │                └──────────┬────────────┘    │
│  │  mss → numpy/rgb →  │                           │                 │
│  │  Pillow.resize →    │                           │ root.after(0,…) │
│  │  ImageTk.PhotoImage │                           ▼                 │
│  └─────────────────────┘         ┌──────────────────────────────┐   │
│           ▲                      │      Tk Main Thread          │   │
│           │ reads (x,y,w,h,zoom) │  ┌────────────────────────┐  │   │
│           │                      │  │    Root Toplevel       │  │   │
│  ┌────────┴────────┐             │  │   (overrideredirect)   │  │   │
│  │    AppState     │◄────────────┤  │                        │  │   │
│  │  (thread-safe)  │ read/write  │  │  ┌──────────────────┐  │  │   │
│  │  + observers    │             │  │  │  Drag Bar Frame  │  │  │   │
│  └────────┬────────┘             │  │  │  (HTCAPTION)     │  │  │   │
│           │ on_change            │  │  ├──────────────────┤  │  │   │
│           ▼                      │  │  │ Content Canvas   │  │  │   │
│  ┌─────────────────┐             │  │  │ (HTTRANSPARENT)  │  │  │   │
│  │ ConfigStore     │             │  │  │  image=PhotoImg  │  │  │   │
│  │  debounced      │             │  │  ├──────────────────┤  │  │   │
│  │  config.json    │             │  │  │ Control Strip    │  │  │   │
│  └─────────────────┘             │  │  │ (HTCLIENT)       │  │  │   │
│                                  │  │  └──────────────────┘  │  │   │
│  ┌─────────────────┐             │  │    │                   │  │   │
│  │  Hotkey Thread  │   after(0)  │  │    ▼ pywin32 calls:   │  │   │
│  │  (daemon)       │ ──────────> │  │  SetWindowLongPtr      │  │   │
│  │                 │  toggle_vis │  │  (WS_EX_LAYERED,       │  │   │
│  │ RegisterHotKey  │             │  │   WS_EX_TOOLWINDOW)    │  │   │
│  │ GetMessageW loop│             │  │  SetWindowRgn(shape)   │  │   │
│  └─────────────────┘             │  │  Subclassed WndProc    │  │   │
│                                  │  │    → WM_NCHITTEST      │  │   │
│                                  │  └────────────────────────┘  │   │
│                                  └──────────────┬───────────────┘   │
│                                                 │ root.after(0,...)  │
│                                                 ▲                    │
│  ┌─────────────────┐                            │                    │
│  │  Pystray Thread │ ───────────────────────────┘                    │
│  │  (pystray mgmt) │  menu clicks enqueue commands                   │
│  │                 │                                                 │
│  │  Icon.run()     │                                                 │
│  └─────────────────┘                                                 │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
                       │
                       ▼
               ┌───────────────┐
               │   config.json │  (app directory, written via atomic
               │               │   replace from the Tk main thread)
               └───────────────┘
```

### Thread Roles at a Glance

| Thread | Count | Lifetime | Job | May Touch Tk Widgets? |
|--------|-------|----------|-----|------------------------|
| **Tk main** | 1 | entire app | UI, win32 window ops, config writes, event dispatch | YES (it owns them) |
| **Capture** | 1 | entire app, daemon | mss grab → resize → PhotoImage → queue | **NO** — posts via `root.after` / `queue.Queue` |
| **Hotkey** | 1 | entire app, daemon | `RegisterHotKey` + `GetMessageW` loop | **NO** — posts via `root.after` |
| **Pystray** | 1 | entire app, daemon | `Icon.run()` loop (pystray owns this thread) | **NO** — posts via `root.after` |

**The rule is enforced by convention:** only code inside a `root.after(0, fn)` callback may call tkinter methods or pywin32 functions that take `hwnd`. Everything else is off-limits from worker threads.

---

## Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `app.py` (entry point) | Wire everything together; start threads; enter `root.mainloop()` | Module-level `main()` function, no class |
| `window.py` — `BubbleWindow` | Create the Toplevel, apply extended styles, install WndProc subclass, manage the three-zone layout, apply SetWindowRgn on shape/size change | `tk.Toplevel` + pywin32 calls in `__init__` and `on_resize` |
| `wndproc.py` — `subclass_wndproc` | Install a Python WndProc that handles WM_NCHITTEST (returning HTCAPTION/HTTRANSPARENT/HTCLIENT based on zone) and delegates all other messages to `CallWindowProc` | `ctypes.WINFUNCTYPE` + `SetWindowLongPtrW(hwnd, GWLP_WNDPROC, new_wndproc)` — the original proc is saved and called via `CallWindowProcW` |
| `capture.py` — `CaptureWorker` | Own an `mss.mss()` instance; loop at target fps; read current (x,y,w,h,zoom) from `AppState`; produce `PhotoImage`; enqueue | `threading.Thread(daemon=True)` with a `queue.Queue(maxsize=2)` or direct `root.after(0, update, photo)` |
| `state.py` — `AppState` | Thread-safe store of `{x, y, w, h, zoom, shape, visible, always_on_top}`; exposes getters, setters, and `on_change(callback)` | Simple class with `threading.Lock`; observers fire synchronously in whichever thread called the setter |
| `config.py` — `ConfigStore` | Load `config.json` at startup; subscribe to `AppState` changes; debounce writes (500 ms) using `root.after(500, ...)`; write atomically via `os.replace` | Pure Python, lives on the Tk main thread |
| `hotkey.py` — `HotkeyService` | Register Ctrl+Z via `user32.RegisterHotKey`; run a `GetMessageW` loop on its own thread; on WM_HOTKEY, call `root.after(0, state.toggle_visible)` | `threading.Thread(daemon=True)` + ctypes |
| `tray.py` — `TrayService` | Create the `pystray.Icon` with Show/Hide, Always on Top toggle, Exit; launch `Icon.run_detached()` (or `Icon.run()` in a spawned thread); each menu action calls `root.after(0, handler)` | `pystray.Icon` + `pystray.Menu` |
| `shapes.py` — `apply_shape(hwnd, w, h, shape)` | Build an HRGN and hand it to `SetWindowRgn`; do not free it afterward | Thin wrapper around `win32gui.CreateEllipticRgn` / `CreateRoundRectRgn` / `CreateRectRgn` |
| `hit_test.py` — `compute_zone(x, y, w, h)` | Given a window-relative point, return `"drag"`, `"content"`, or `"control"`; used by the WndProc | Pure function — no side effects, no win32 imports |

**Why split `BubbleWindow` from `subclass_wndproc`:** the Python WndProc callback must be kept alive for the lifetime of the window (Windows calls it directly; if Python GCs it, the process crashes). Keeping it in a dedicated module makes the "store this reference on the window instance" rule explicit and testable.

---

## Recommended Project Structure

```
Ultimate-Zoom/
├── src/
│   └── magnifier_bubble/
│       ├── __init__.py
│       ├── __main__.py          # python -m magnifier_bubble entry
│       ├── app.py               # main() — wires everything, starts threads, mainloop
│       │
│       ├── state.py             # AppState — single source of truth
│       ├── config.py            # ConfigStore — debounced JSON persistence
│       │
│       ├── window.py            # BubbleWindow — Toplevel + styles + zones
│       ├── wndproc.py           # WndProc subclassing (ctypes)
│       ├── hit_test.py          # Pure zone-from-point function
│       ├── shapes.py            # SetWindowRgn wrapper
│       │
│       ├── capture.py           # CaptureWorker thread (mss → PhotoImage)
│       ├── hotkey.py            # HotkeyService thread (RegisterHotKey + MSG loop)
│       ├── tray.py              # TrayService (pystray)
│       │
│       ├── widgets/
│       │   ├── __init__.py
│       │   ├── drag_bar.py      # Top strip with grip + shape-cycle button
│       │   ├── content.py       # Middle canvas that holds the PhotoImage
│       │   └── control_strip.py # Bottom strip with -/+, level, resize grip
│       │
│       └── winconst.py          # WS_EX_LAYERED, GWL_EXSTYLE, HTTRANSPARENT, …
│
├── assets/
│   ├── bubble.ico               # Tray + .exe icon
│   └── version.txt              # PyInstaller version resource
│
├── build.bat                    # Single-click build script
├── magnifier_bubble.spec        # PyInstaller spec (checked in, not generated)
├── requirements.txt             # Pinned runtime deps
├── requirements-dev.txt         # + pyinstaller
├── config.json                  # Created on first run (gitignored)
└── README.md
```

### Structure Rationale

- **`src/magnifier_bubble/` layout:** src-layout prevents "works in dev, fails in .exe" import shadowing. PyInstaller's analysis happens against the installed package, not against random sibling modules.
- **Flat module layout (not nested packages):** the app is small (~1500 LOC target). Over-nesting hurts discoverability more than it helps. The one sub-package (`widgets/`) exists because the three zones are genuinely similar UI fragments that benefit from being grouped.
- **`state.py` at the top level, not under `core/`:** `AppState` is imported by almost every other module. Keeping it shallow keeps import paths short and cuts circular-import risk.
- **`wndproc.py` separate from `window.py`:** the WndProc involves ctypes `WINFUNCTYPE` callbacks and lifetime-of-the-window references. Isolating it makes the "never let this callback get GC'd" invariant visible in one file.
- **`winconst.py` standalone:** one place to dump `WS_EX_LAYERED = 0x00080000`, `HTTRANSPARENT = -1`, etc. Every file that needs these imports from the same place, avoiding copy-paste drift.
- **`magnifier_bubble.spec` checked in:** `.spec` is the declarative build config. CLI flags go stale; a spec file is reproducible.

---

## Architectural Patterns

### Pattern 1: Producer / Consumer with `root.after` bridge

**What:** The capture worker produces frames as fast as the resize budget allows, then hands each frame to the Tk main thread via `root.after(0, update_image, photo)`. The queue is intentionally tiny (`maxsize=2`) so that if Tk falls behind, the worker drops frames instead of growing memory without bound.

**When to use:** Every time a worker thread needs to mutate a Tk widget. This is the only sanctioned path from a background thread into tkinter.

**Trade-offs:**
- (+) Thread-safe by construction — the actual widget update happens on the Tk main thread.
- (+) Back-pressure is automatic if you bound the queue.
- (−) Adds one event-loop hop of latency (~1 ms), which is negligible at 30 fps.
- (−) `root.after(0, ...)` coalesces multiple calls into the same event loop iteration — fine for us, but don't rely on strict ordering between different callback sources.

**Example:**

```python
# capture.py
class CaptureWorker(threading.Thread):
    def __init__(self, state, on_frame):
        super().__init__(daemon=True, name="capture")
        self.state = state
        self.on_frame = on_frame  # callable taking a PhotoImage
        self._stop = threading.Event()

    def run(self):
        with mss.mss() as sct:
            target_dt = 1 / 30
            while not self._stop.is_set():
                t0 = time.perf_counter()
                x, y, w, h, zoom = self.state.capture_region()
                shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
                img = Image.frombytes("RGB", shot.size, shot.rgb)
                img = img.resize(
                    (int(w * zoom), int(h * zoom)),
                    Image.Resampling.BILINEAR,
                )
                photo = ImageTk.PhotoImage(img)
                # on_frame is (lambda p: root.after(0, window.update_image, p))
                self.on_frame(photo)
                dt = time.perf_counter() - t0
                if dt < target_dt:
                    time.sleep(target_dt - dt)
```

```python
# window.py
class BubbleWindow:
    def update_image(self, photo):  # runs on Tk main thread
        self.canvas.itemconfig(self._img_item, image=photo)
        self.canvas.image = photo  # prevent GC — critical
```

### Pattern 2: Subclassed WndProc via ctypes, with lifetime discipline

**What:** Replace the window's WndProc with a Python function that handles WM_NCHITTEST and delegates everything else. Use `SetWindowLongPtrW(hwnd, GWLP_WNDPROC, new_wndproc)` (preferred over `SetWindowSubclass` because comctl32's subclass helpers cannot be used across threads and only work on user-controlled windows — tkinter's HWND is technically a child of its own window class).

**When to use:** The one and only time we need to intercept messages that Tk's binding system can't see — `WM_NCHITTEST`, `WM_SYSCOMMAND` if we ever want custom min/max, etc.

**Trade-offs:**
- (+) Per-pixel hit testing with full control; no need to juggle multiple top-level windows.
- (+) Gives us free OS-level dragging by returning HTCAPTION for the drag bar — no manual drag handlers needed.
- (−) Lifetime is fragile: if Python garbage-collects the `WINFUNCTYPE` callback while the window is alive, the next message crashes the process. **The callback must be stored on an object that outlives the window.**
- (−) "Replace, not insert" — you must call the saved previous WndProc via `CallWindowProcW` for any message you don't handle, or Tk stops working.
- (−) Cannot use comctl32's `SetWindowSubclass` helper here because it requires the calling thread to own the window and has limits with foreign window classes.

**Example:**

```python
# wndproc.py
import ctypes
from ctypes import wintypes, WINFUNCTYPE

WNDPROC = WINFUNCTYPE(
    ctypes.c_ssize_t,                     # LRESULT (Py_ssize_t ≈ LONG_PTR)
    wintypes.HWND, wintypes.UINT,
    wintypes.WPARAM, wintypes.LPARAM,
)
user32 = ctypes.windll.user32
GWLP_WNDPROC = -4
WM_NCHITTEST = 0x0084
HTTRANSPARENT = -1
HTCAPTION = 2
HTCLIENT = 1

def install(hwnd, compute_zone):
    """Replace hwnd's WndProc. Returns a 'keepalive' object the caller MUST
    store; losing the reference will crash the process."""
    old_proc = user32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)

    def py_wndproc(h, msg, wparam, lparam):
        if msg == WM_NCHITTEST:
            # LPARAM is packed screen-space coords; convert to window-relative
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            rect = wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(rect))
            zone = compute_zone(x - rect.left, y - rect.top,
                                rect.right - rect.left,
                                rect.bottom - rect.top)
            if zone == "drag":    return HTCAPTION
            if zone == "content": return HTTRANSPARENT
            # "control" falls through to default (buttons work normally)
        return user32.CallWindowProcW(old_proc, h, msg, wparam, lparam)

    new_proc = WNDPROC(py_wndproc)
    user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, new_proc)

    class Keepalive:
        pass
    ka = Keepalive()
    ka.new_proc = new_proc    # keep the WINFUNCTYPE alive
    ka.old_proc = old_proc    # in case we ever want to uninstall
    return ka
```

```python
# window.py (snippet)
class BubbleWindow:
    def __init__(self, root, state):
        ...
        self._wndproc_keepalive = wndproc.install(self.hwnd, self._zone_at)
        # ↑ attribute name is deliberate: grep-ability when debugging crashes
```

### Pattern 3: Shape Mask Over the Whole Window

**What:** Apply `SetWindowRgn` once to the root HWND. The region clips both drawing and hit-testing, so corners of the bounding box automatically pass clicks through to whatever is underneath. All three zone-frames live inside that shaped region.

**When to use:** Any time the shape changes (user cycles circle → rounded → rect) or the window resizes. Call `apply_shape(hwnd, new_w, new_h, shape)` at the tail end of the resize/shape handler.

**Trade-offs:**
- (+) One win32 call handles both visual clipping and hit-testing.
- (+) Works with layered windows (WS_EX_LAYERED) on Windows 8+, so we can still have per-pixel alpha for the drag bar / control strip strips.
- (−) Ownership gotcha: after a successful `SetWindowRgn`, the OS owns the HRGN. Do not `DeleteObject` it. Double-freeing crashes the process.
- (−) Region coordinates are **window** coordinates, not client or screen.
- (−) Must be reapplied on every resize; the old region becomes invalid implicitly.

**Example:**

```python
# shapes.py
import win32gui

def apply_shape(hwnd, w, h, shape):
    if shape == "circle":
        rgn = win32gui.CreateEllipticRgn(0, 0, w, h)
    elif shape == "rounded":
        rgn = win32gui.CreateRoundRectRgn(0, 0, w, h, 40, 40)
    else:
        rgn = win32gui.CreateRectRgn(0, 0, w, h)
    win32gui.SetWindowRgn(hwnd, rgn, True)
    # DO NOT delete rgn — Windows owns it now.
```

**Interaction with the three-zone layout:** because the region is applied to the one top-level window, the three `tkinter.Frame`s (drag / content / control) automatically share the same clipping. We don't need separate regions per zone; we just let the zones lay themselves out inside the shaped region. When the shape is a circle, the drag bar and control strip get clipped to the circle's top/bottom chord, which is exactly the desired behavior — they become visually "arc-shaped" strips, and because `SetWindowRgn` also clips hit testing, the parts outside the circle pass clicks through naturally.

### Pattern 4: Single Source of Truth with Debounced Persistence

**What:** `AppState` holds the canonical values. `ConfigStore` subscribes to state changes, but instead of writing `config.json` on every mutation, it schedules a write 500 ms in the future via `root.after`. Each additional mutation resets the timer. The actual write uses `os.replace` for atomicity.

**When to use:** Every config-relevant setter (`set_position`, `set_zoom`, `set_shape`, etc.) goes through `AppState`. ConfigStore is the only writer to `config.json`.

**Trade-offs:**
- (+) Dragging the window doesn't hammer the disk (otherwise every pixel of motion = one write).
- (+) Atomic writes mean a power loss never leaves a half-written config.
- (+) 500 ms debounce is short enough that a user who edits and immediately closes the app still gets their config saved, because the Tk `WM_DELETE_WINDOW` handler flushes any pending write before exit.
- (−) If the app crashes hard in the 500 ms window, the latest change is lost. Acceptable for this use case.

**Example:**

```python
# config.py
import json, os, tempfile

class ConfigStore:
    DEBOUNCE_MS = 500

    def __init__(self, path, root, state):
        self.path = path
        self.root = root
        self.state = state
        self._pending = None
        state.on_change(self._schedule)

    def _schedule(self):
        if self._pending is not None:
            self.root.after_cancel(self._pending)
        self._pending = self.root.after(self.DEBOUNCE_MS, self._flush)

    def _flush(self):
        self._pending = None
        data = self.state.snapshot()
        dir_ = os.path.dirname(os.path.abspath(self.path)) or "."
        with tempfile.NamedTemporaryFile(
            "w", dir=dir_, delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f, indent=2)
            tmp = f.name
        os.replace(tmp, self.path)   # atomic on Windows (rename-replace)

    def flush_now(self):
        """Call from WM_DELETE_WINDOW handler before exit."""
        if self._pending is not None:
            self.root.after_cancel(self._pending)
            self._flush()
```

### Pattern 5: Cross-Thread Command Inbox via `root.after`

**What:** Pystray, hotkey thread, and any future background source post commands to the Tk main thread by calling `root.after(0, handler, *args)`. This is tkinter's own thread-safe scheduler — it appends the callable to the main event loop's queue without going through Python-level locks.

**When to use:** Any thread that wants to trigger a UI-visible change. Pystray menu callbacks are the most common case.

**Trade-offs:**
- (+) No separate queue, no polling, no `self.after(100, check_queue)` glue.
- (+) Tk's `after(0, ...)` is documented as safe from other threads (it's one of the few tkinter operations that is).
- (−) You must capture a reference to `root` in every thread that wants to post — pass it into each Service at construction time.
- (−) Coalescing can mean "multiple clicks in the same tick" collapse to multiple sequential callbacks, which is what we want but worth being aware of for things like counters.

**Example:**

```python
# tray.py
class TrayService:
    def __init__(self, root, state):
        self.root = root
        self.state = state
        self.icon = pystray.Icon(
            "magnifier_bubble",
            icon=Image.open("assets/bubble.ico"),
            menu=pystray.Menu(
                pystray.MenuItem(
                    "Show/Hide",
                    lambda icon, item: root.after(0, state.toggle_visible),
                ),
                pystray.MenuItem(
                    "Always on Top",
                    lambda icon, item: root.after(0, state.toggle_aot),
                    checked=lambda item: state.always_on_top,
                ),
                pystray.MenuItem(
                    "Exit",
                    lambda icon, item: root.after(0, state.request_exit),
                ),
            ),
        )

    def start(self):
        # pystray on Windows is safe to run from a non-main thread
        self.icon.run_detached()
```

### Pattern 6: Hotkey Thread with Its Own Message Pump

**What:** The hotkey thread owns its own Win32 message queue. `RegisterHotKey(None, ...)` posts `WM_HOTKEY` to the calling thread's queue. We run a `GetMessageW` loop there (blocking). When a hotkey fires, we dispatch back to Tk via `root.after(0, ...)`.

**When to use:** This is the *only* way to get reliable global hotkeys without admin privileges, without an unmaintained third-party library, and without fighting Windows 11 low-level hook throttling.

**Trade-offs:**
- (+) OS-blessed: `RegisterHotKey` is how AutoHotKey, Windows' own shortcuts, and Visual Studio implement global shortcuts.
- (+) No admin required for Ctrl+Z.
- (+) Unaffected by the target app's keyboard interception.
- (−) Needs its own thread because `GetMessageW` blocks.
- (−) Cannot share the hotkey across threads — the thread that calls `RegisterHotKey` is the thread that receives the `WM_HOTKEY` messages. Don't try to move it.
- (−) Must `UnregisterHotKey` on shutdown, or the combo is stuck until the OS cleans up the dead thread.

**Example:** see STACK.md §4 for the full code sketch. Architectural point: the thread's `run()` method takes `post_toggle: Callable[[], None]` as its only dependency, where the caller binds it as `lambda: root.after(0, state.toggle_visible)`. This keeps the hotkey module ignorant of both tkinter and AppState.

---

## Data Flow

### Startup Flow

```
main()
  │
  ├── Load config.json (if exists) → seed AppState
  │
  ├── Create Tk root + BubbleWindow (main thread)
  │     ├── overrideredirect(True), topmost, WS_EX_LAYERED, WS_EX_TOOLWINDOW
  │     ├── Subclass WndProc (install + stash keepalive)
  │     └── apply_shape(hwnd, w, h, shape)
  │
  ├── Create ConfigStore(root, state) → subscribes to AppState
  │
  ├── Start CaptureWorker(state, on_frame=lambda p: root.after(0, win.update_image, p))
  │
  ├── Start HotkeyService(on_trigger=lambda: root.after(0, state.toggle_visible))
  │
  ├── Start TrayService(root, state).start()
  │
  ├── root.protocol("WM_DELETE_WINDOW", lambda: (config.flush_now(),
  │                                              state.request_exit()))
  │
  └── root.mainloop()   # returns only when state.request_exit → root.destroy
```

### Per-Frame Flow (the hot loop)

```
CaptureWorker                          Tk main thread
───────────────                        ──────────────
state.capture_region()  ◄──── (read snapshot under lock)
      ↓
sct.grab(region)          ~3 ms
      ↓
Image.frombytes(...)      ~2 ms
      ↓
img.resize(BILINEAR)      ~5-8 ms
      ↓
ImageTk.PhotoImage(img)   ~3 ms
      ↓
root.after(0,
  win.update_image,                    ─────┐
  photo)                                    ▼
                                       canvas.itemconfig(img_item, image=photo)
                                       canvas.image = photo   # keep GC at bay
                                       (next frame the loop overwrites this)
```

Total wall-clock per frame: ~15–18 ms for a 400×400 region. 33 ms budget for 30 fps. Comfortable margin.

### Hotkey Flow

```
User presses Ctrl+Z (anywhere on desktop)
      ↓
Windows posts WM_HOTKEY to hotkey thread's message queue
      ↓
Hotkey thread's GetMessageW returns
      ↓
Thread calls root.after(0, state.toggle_visible)
      ↓
Tk main thread picks it up on next iteration
      ↓
state.toggle_visible():
  - flips state.visible
  - fires observers → window.apply_visibility() (withdraw/deiconify)
  - fires observers → ConfigStore._schedule() (debounced write)
```

### Tray Menu Flow

```
User right-clicks tray icon, selects "Always on Top"
      ↓
pystray thread invokes our menu callback
      ↓
Callback: root.after(0, state.toggle_aot)
      ↓
Tk main thread picks it up
      ↓
state.toggle_aot():
  - flips state.always_on_top
  - fires observers:
      • window.apply_topmost()  → root.wm_attributes("-topmost", v)
      • config._schedule()      → debounced write
  - pystray's Menu.checked lambda re-reads state.always_on_top next draw
```

### Drag Flow (free — no code needed)

```
User touches the top drag bar
      ↓
Windows sends WM_NCHITTEST to our subclassed WndProc
      ↓
compute_zone(x, y, w, h) → "drag"
      ↓
WndProc returns HTCAPTION
      ↓
Windows treats the hit as a title-bar drag and moves the window for us
      ↓
On button release, Tk fires <Configure> → window.on_move_or_resize()
      ↓
state.set_position(new_x, new_y)
      ↓
config._schedule() (debounced)
```

This is the main win of the WndProc-subclass approach: **dragging is free**. We never write a Python-side `<Button-1>`/`<B1-Motion>` handler.

### Resize Flow

```
User drags the resize grip in the bottom-right corner
      ↓
Widget-level <B1-Motion> handler updates state.set_size(w, h)
      ↓
state observers fire:
  • window.apply_size()   → root.geometry(f"{w}x{h}+{x}+{y}")
  • window.reapply_shape() → apply_shape(hwnd, w, h, state.shape)
  • config._schedule()    → debounced write
      ↓
Next CaptureWorker iteration reads new (w, h) on its next poll
```

### State Management

```
                    ┌────────────────────┐
                    │     AppState       │
                    │  (threading.Lock)  │
                    └─────────┬──────────┘
                              │
                observers[] ──┤
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
  BubbleWindow           ConfigStore           (other…)
  (apply_size,           (_schedule→
   apply_shape,            _flush→
   apply_topmost,          os.replace)
   apply_visibility)
```

Observers run synchronously in whichever thread called the setter. **Rule:** never call state setters from a worker thread. Always go through `root.after(0, ...)`. That way the observers always fire on the Tk main thread, where they can safely touch the window and schedule `root.after` timers.

---

## Build Order (Phase Dependencies)

Use this as input to roadmap phase ordering — each step has prerequisites.

1. **`winconst.py` + `hit_test.py`** (pure Python, no deps)
   - No dependencies. Can be fully unit-tested.
2. **`state.py` (AppState)** — single source of truth
   - Depends on: nothing.
   - Enables everything else to have a coherent data model.
3. **`shapes.py` (SetWindowRgn wrapper)** — isolated win32
   - Depends on: `winconst.py`.
   - Can be tested by creating a throwaway Tk window and applying a region.
4. **`wndproc.py` (WndProc subclass)** — isolated ctypes
   - Depends on: `winconst.py`, `hit_test.py`.
   - Can be tested with a throwaway Tk window and a mouse-move log.
5. **`window.py` (BubbleWindow) — Phase: "The bubble exists and is shaped"**
   - Depends on: 2, 3, 4.
   - First milestone where you see something on screen.
6. **`capture.py` (CaptureWorker) — Phase: "The bubble shows live pixels"**
   - Depends on: 5.
   - Second milestone; at this point you have a working magnifier with no controls.
7. **`widgets/control_strip.py` + `widgets/drag_bar.py`** — Phase: "The bubble has controls"
   - Depends on: 5, 6.
   - Adds zoom buttons, shape cycle, resize grip.
8. **`config.py` (ConfigStore)** — Phase: "Settings persist"
   - Depends on: 2, 5, 7.
   - Becomes meaningful once there are user-modifiable settings to persist.
9. **`hotkey.py` (HotkeyService)** — Phase: "Global hotkey works"
   - Depends on: 5.
   - Completely independent of capture / config / tray — can be built any time after the window exists.
10. **`tray.py` (TrayService)** — Phase: "The bubble has a tray icon"
    - Depends on: 5 (for Show/Hide), 2 (for state toggles).
    - Can share phase with 9 if desired.
11. **`magnifier_bubble.spec` + `build.bat`** — Phase: "Ships as .exe"
    - Depends on: everything in 1–10.
    - Last step before clinic deployment.

**Parallelizable pairs after phase 5:**
- 6 (capture) and 9 (hotkey) have no shared files and can be built simultaneously.
- 8 (config) and 10 (tray) can be built simultaneously once 7 is done.

**Why this order:** each step produces a visible/testable artifact. The longest "nothing to show yet" period is between steps 1 and 5, which is unavoidable because everything depends on having a window on screen.

---

## PyInstaller Spec Structure

The build is not just "add hidden imports." The spec file has to orchestrate several Windows-specific concerns that only pywin32 apps need.

```python
# magnifier_bubble.spec
# Build with:  pyinstaller magnifier_bubble.spec
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

hiddenimports = [
    # pystray picks its backend via importlib at runtime, PyInstaller can't see it
    "pystray._win32",
    # Pillow's Tk bridge is loaded dynamically through PIL/_tkinter_finder
    "PIL._tkinter_finder",
    # win32timezone is needed by pywin32's datetime marshalling if anything touches it
    "win32timezone",
]

# pywin32 has a post-install step (pywin32_postinstall.py -install) that places
# pywintypesXY.dll and pythoncomXY.dll into the package's pywin32_system32 folder.
# PyInstaller's pywin32 hook knows to look there, BUT only if the post-install
# actually ran in the build venv. Document this as a build prerequisite rather
# than trying to script it from inside the spec.

a = Analysis(
    ["src/magnifier_bubble/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        ("assets/bubble.ico", "assets"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Aggressive exclusions keep .exe small and cut AV false-positive surface
        "tkinter.test",
        "test",
        "unittest",
        "pydoc",
        "doctest",
        "xml",
        "email",
        "http",
        "pdb",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MagnifierBubble",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                # DO NOT COMPRESS — major AV false-positive trigger
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # GUI app, no console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/bubble.ico",
    version="assets/version.txt",
    uac_admin=False,          # do NOT request admin — RegisterHotKey Ctrl+Z does not need it
    uac_uiaccess=False,
    manifest=None,
)
```

**Build prerequisites (document in README):**

```bat
REM build.bat
python -m venv .venv-build
call .venv-build\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt

REM pywin32 post-install writes pywintypes3XX.dll into site-packages/pywin32_system32
REM PyInstaller's pywin32 hook needs this to bundle the DLLs correctly.
python .venv-build\Scripts\pywin32_postinstall.py -install

pyinstaller --clean --noconfirm magnifier_bubble.spec
```

**Why each flag matters:**
- `upx=False`: UPX-packed binaries are the #1 cause of Defender and third-party AV flagging Python apps. At ~40 MB uncompressed we lose nothing meaningful by skipping it.
- `console=False`: we don't want a stray cmd window popping up alongside the bubble.
- `uac_admin=False`: explicitly NOT admin. If the user right-clicks the .exe and picks "Run as administrator," the hotkey still works the same; admin is unnecessary.
- `excludes=[...]`: the biggest .exe wins come from excluding `tkinter.test`, `test`, `unittest`, `pydoc`, and `xml`/`email`/`http`. For this app none are used transitively.
- `version="assets/version.txt"`: gives the .exe proper "File description / Product name / Version" in Windows Explorer Properties. Clinic IT will ask about this.
- `icon="assets/bubble.ico"`: must be a real .ico (multi-resolution), not a .png renamed.

---

## Scaling Considerations

This is a single-user desktop app. "Scale" here means "bigger capture regions at higher zoom factors," not users.

| Bubble size × zoom | Notes |
|--------------------|-------|
| 150×150 at 1.5× | ~0.05 megapixels processed per frame. Trivial, <5 ms total. |
| 400×400 at 3× | ~1.4 megapixels after resize. ~15 ms total. Comfortable for 30 fps. |
| 700×700 at 6× | ~17 megapixels after resize. **This is the edge case.** At max bubble + max zoom, resize can hit ~25–30 ms, right at the 33 ms budget. |
| 700×700 at 6× on a weak clinic PC | May drop to 20–25 fps. Acceptable per spec ("30fps minimum in the magnification loop" — if the user picks the extreme settings, graceful degradation is fine). |

### Scaling Priorities

1. **First bottleneck: Pillow resize at max settings.**
   Mitigation: switch from `BILINEAR` to `NEAREST` when the user picks 6× on a 700×700 bubble. `NEAREST` is ~3× faster than BILINEAR and at 6× upscale the visual difference is "slightly more pixelated edges" — acceptable for a reading-assist tool where the priority is responsiveness. Make this a config-driven option.
2. **Second bottleneck: `ImageTk.PhotoImage` construction cost.**
   Mitigation: reuse a single `PhotoImage` by using its `.paste(img)` method on subsequent frames instead of allocating a new one. This avoids a per-frame Python object creation.
3. **Third bottleneck: mss grab on a 4K display with a 700×700 region.**
   Unlikely to matter — mss grabs only the requested region, and a 700×700 grab is bounded regardless of display resolution.

**When to optimize:** only after profiling on the target clinic PC. Do not pre-optimize; BILINEAR + fresh PhotoImage per frame is plenty for the typical 300×300 @ 3× case.

---

## Anti-Patterns

### Anti-Pattern 1: Running capture on the Tk main thread

**What people do:** Put the mss grab + resize + update inside `root.after(33, self.tick)` and call it a day. Looks simple.
**Why it's wrong:** `sct.grab` + `Image.resize` + `PhotoImage` together cost 15–25 ms. During that time the Tk mainloop is blocked: no clicks, no drags, no repaints. Dragging the bubble becomes laggy as the grab size grows.
**Do this instead:** Capture on a worker thread, post finished PhotoImages via `root.after(0, ...)`. The main loop stays responsive.

### Anti-Pattern 2: Using `keyboard.add_hotkey` or `pynput.GlobalHotKeys`

**What people do:** `pip install keyboard; keyboard.add_hotkey('ctrl+z', toggle)` — easy, one line.
**Why it's wrong:** `keyboard` is archived/unmaintained as of Feb 2026 and requires admin for `suppress=True`. `pynput` has documented Win11 GlobalHotKeys reliability issues. Both use low-level hooks that Windows can throttle.
**Do this instead:** Direct `user32.RegisterHotKey` via ctypes. It's the OS-blessed API, needs no admin for Ctrl+Z, and is the approach this architecture relies on.

### Anti-Pattern 3: Trying to call tkinter from the capture thread

**What people do:** Pass `self.canvas` into the worker and call `canvas.itemconfig(...)` directly from `run()`.
**Why it's wrong:** Tkinter is not thread-safe. It mostly-sort-of-works until one day it deadlocks the mainloop or segfaults during shutdown. Bug reports on this exact pattern exist across tkinter's entire history.
**Do this instead:** All worker threads post via `root.after(0, fn, *args)`. Tkinter documents this specific call as safe from other threads.

### Anti-Pattern 4: Letting the subclassed WndProc get garbage-collected

**What people do:** `user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, WNDPROC(py_wndproc))` as a one-liner.
**Why it's wrong:** The `WNDPROC(py_wndproc)` temporary has no Python reference, gets GC'd the instant the line returns, and the next Windows message calls into freed memory. Crash.
**Do this instead:** Store the `WNDPROC(...)` wrapper on an instance attribute that lives as long as the window (e.g., `self._wndproc_keepalive`). Make this invariant explicit in code comments.

### Anti-Pattern 5: Deleting the HRGN after `SetWindowRgn`

**What people do:** "Clean up resources, delete the HRGN when done."
**Why it's wrong:** After a successful `SetWindowRgn`, the OS owns the HRGN. `DeleteObject` on it is a double-free. Crashes on the next window operation.
**Do this instead:** Create the HRGN, pass it to `SetWindowRgn`, walk away. Windows frees it when the window is destroyed or replaced with a new region.

### Anti-Pattern 6: Writing config.json on every pixel of drag motion

**What people do:** Subscribe to `<Configure>` and call `config.save()` inside the handler.
**Why it's wrong:** A 500 ms drag generates 200+ save calls on a 60 Hz drag. Disk IO stalls, `config.json` ends up half-written if you exit mid-drag.
**Do this instead:** Debounce with `root.after(500, flush)`; cancel and reschedule on each change. Flush synchronously in `WM_DELETE_WINDOW`.

### Anti-Pattern 7: Multiple Toplevels for the three zones

**What people do:** "I need different click-through behavior per zone, so I'll make three floating Toplevel windows and align them manually."
**Why it's wrong:** Alignment during drag/resize is fragile. Three HWNDs means three sets of SetWindowLong calls to keep in sync. Shape masking across three windows requires three separate HRGNs that don't overlap cleanly.
**Do this instead:** One Toplevel. Three `tkinter.Frame`s inside it. WM_NCHITTEST decides per-pixel which zone a click belongs to. One SetWindowRgn for the whole thing.

### Anti-Pattern 8: Creating `mss.mss()` inside the capture loop

**What people do:** `with mss.mss() as sct: shot = sct.grab(region)` inside the tick.
**Why it's wrong:** `mss.mss()` allocates device contexts. Creating and destroying it 30 times per second is wasteful and has been observed to leak DC handles under some drivers.
**Do this instead:** Create one `mss.mss()` on the capture thread outside the loop; reuse it for every frame; destroy at shutdown.

### Anti-Pattern 9: Putting `Icon.run()` on the Tk main thread

**What people do:** "Main threads are for mainloops. Pystray has a main loop. Let me run it on the main thread and push tkinter to a worker."
**Why it's wrong:** tkinter's mainloop MUST be on the main thread on Windows, and its internal state is tied to the thread that created it. Moving Tk off main breaks quietly.
**Do this instead:** Tkinter on the main thread. On Windows, pystray is documented as safe to run on any thread — use `Icon.run_detached()` or a `threading.Thread(target=icon.run, daemon=True)`.

---

## Integration Points

### External Services

| "Service" | Integration Pattern | Notes |
|-----------|---------------------|-------|
| Windows `user32.dll` | `ctypes` (for WndProc, RegisterHotKey) + `pywin32` (for SetWindowRgn, SetWindowLong, SetLayeredWindowAttributes) | Mix is fine — `pywin32` gives ergonomic wrappers for most calls, `ctypes` handles the WNDPROC/WINFUNCTYPE cases pywin32 doesn't cleanly expose |
| Windows `gdi32.dll` | `pywin32` (`win32gui.Create*Rgn`) | Only for shape HRGNs |
| Filesystem (`config.json`) | `json` + `os.replace` for atomic writes | Written only from Tk main thread |
| Tray icon (Shell_NotifyIcon) | `pystray` | Isolated in `tray.py`; only sees `root` and `state` |
| Idexx Cornerstone | **None** — pure "I stay out of its way" | This is critical: we never call into Cornerstone, never intercept its input. Our presence is transparent. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `CaptureWorker` ↔ `BubbleWindow` | `root.after(0, window.update_image, photo)` | One-way: capture → window. Capture never reads from window. |
| `CaptureWorker` ↔ `AppState` | `state.capture_region()` reads under lock | Capture reads only. State writes happen elsewhere. |
| `HotkeyService` ↔ `AppState` | `root.after(0, state.toggle_visible)` | One-way: hotkey → state. Hotkey thread never reads state directly. |
| `TrayService` ↔ `AppState` | `root.after(0, state.toggle_*)` for writes; `lambda: state.always_on_top` for checked-state reads | Pystray's `checked` callbacks run on the pystray thread but only read atomic booleans. Writes always go through `root.after`. |
| `AppState` ↔ `ConfigStore` | Observer pattern — ConfigStore subscribes via `state.on_change(callback)` | Observer fires on whatever thread mutated the state; since we enforce "all writes from Tk main," it always fires on the main thread. |
| `AppState` ↔ `BubbleWindow` | Observer pattern — `state.on_change` calls `window.apply_*` | Same as above — observer always fires on Tk main thread. |
| `BubbleWindow` ↔ `wndproc` | `install(hwnd, compute_zone)` returns keepalive; window stores it | Keepalive must outlive the window. Test: grep for any code path that nulls `_wndproc_keepalive`. There shouldn't be one. |
| `BubbleWindow` ↔ `shapes` | `apply_shape(hwnd, w, h, shape)` — fire-and-forget | Called from `apply_size` and `apply_shape_change` observers |

---

## Thread Safety Rules (Check-Sheet)

Enforce by code review. These are the rules that keep the architecture sound:

- [ ] Only the **Tk main thread** may call `root.*`, `canvas.*`, `widget.*` methods (except `root.after` which is thread-safe).
- [ ] Only the **Tk main thread** may call any `win32gui.*` function that takes an HWND.
- [ ] Only the **Tk main thread** may write to `AppState`.
- [ ] Any worker thread that needs to update the UI or mutate state MUST go through `root.after(0, ...)`.
- [ ] `CaptureWorker` holds its `mss.mss()` instance privately; no other thread touches it.
- [ ] The `WNDPROC` wrapper created in `wndproc.install()` MUST be stored on an object that outlives the window.
- [ ] `ConfigStore._flush` writes via `os.replace` (atomic); never direct `open(path, "w")`.
- [ ] On `WM_DELETE_WINDOW`: call `config.flush_now()` BEFORE `root.destroy()` so any debounced write lands.
- [ ] `HotkeyService` owns its `RegisterHotKey` registration; only its own thread calls `UnregisterHotKey` on shutdown.
- [ ] `TrayService.icon.stop()` must be called on app exit, or the tray icon may persist as a ghost until hover.

---

## Sources

### Authoritative (HIGH confidence)
- [Microsoft Learn: SetWindowLongPtrA function](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowlongptra) — GWLP_WNDPROC semantics, CallWindowProc requirement
- [Microsoft Learn: About Window Procedures](https://learn.microsoft.com/en-us/windows/win32/winmsg/about-window-procedures) — subclassing rules, CallWindowProc
- [Microsoft Learn: Subclassing Controls](https://learn.microsoft.com/en-us/windows/win32/controls/subclassing-overview) — comparison between GWL_WNDPROC and SetWindowSubclass; explicit note that SetWindowSubclass "cannot be used to subclass a window across threads"
- [Microsoft Learn: Using Window Procedures](https://learn.microsoft.com/en-us/windows/win32/winmsg/using-window-procedures) — WindowProc contract
- [Microsoft Learn: WM_NCHITTEST message](https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-nchittest) — HTTRANSPARENT, HTCAPTION return values
- [Microsoft Learn: SetWindowRgn function](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowrgn) — HRGN ownership transfer rule
- [Microsoft Learn: RegisterHotKey function](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey) — MOD_NOREPEAT, WM_HOTKEY routing
- [pystray 0.19.5: FAQ](https://pystray.readthedocs.io/en/latest/faq.html) — "On Windows, calling run() from a thread other than the main thread is safe"
- [pystray 0.19.5: Reference](https://pystray.readthedocs.io/en/latest/reference.html) — `Icon.run_detached()`, `setup` parameter
- [pystray 0.19.5: Usage](https://pystray.readthedocs.io/en/latest/usage.html) — menu construction, thread model
- [PyInstaller 6 Spec Files](https://pyinstaller.org/en/stable/spec-files.html) — Analysis/PYZ/EXE classes, hiddenimports parameter

### Reference patterns (MEDIUM confidence — community patterns, verified against official docs)
- [tkthread on PyPI](https://pypi.org/project/tkthread/) — documentation that tkinter is not thread-safe and documenting the `root.after` bridge pattern
- [Python Tutorial: How to Use Thread in Tkinter Applications](https://www.pythontutorial.net/tkinter/tkinter-thread/) — queue.Queue + root.after pattern reference
- [Stack Overflow / community: Responsive Tkinter GUIs with Threads and Queues](https://runebook.dev/en/docs/python/library/tkinter/threading-model) — standard producer/consumer pattern for tkinter
- [pystray issue #94](https://github.com/moses-palmer/pystray/issues/94) — confirmation that `Icon.stop()` is the right shutdown path
- [pywin32 311 on PyPI](https://pypi.org/project/pywin32/) — post-install script location and purpose

### Related STACK.md decisions (full rationale in that file)
- `.planning/research/STACK.md` §2 — WM_NCHITTEST click-through strategy and Python WndProc GC gotcha
- `.planning/research/STACK.md` §4 — RegisterHotKey thread model
- `.planning/research/STACK.md` §5 — SetWindowRgn ownership rule
- `.planning/research/STACK.md` §6 — PyInstaller spec configuration
- `.planning/research/STACK.md` "Pipeline: mss → Tk PhotoImage" — frame timing budget

---
*Architecture research for: Windows 11 desktop magnifier overlay in Python 3.11*
*Researched: 2026-04-10*
