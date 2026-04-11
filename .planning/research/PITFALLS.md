# Pitfalls Research — Magnifier Bubble (Ultimate Zoom)

**Domain:** Windows 11 desktop overlay / real-time screen magnifier in Python (tkinter + pywin32 + mss + pystray)
**Researched:** 2026-04-10
**Confidence:** HIGH (every critical pitfall verified against Microsoft Learn, pywin32/pystray/mss issue trackers, or the `SetWindowRgn` / `RegisterHotKey` / `SetWindowLongPtr` primary docs)

This document catalogs the mistakes that will cost you days of debugging if you skip them. Every pitfall is specific to this stack, this domain, and this deployment target (a clinic touchscreen PC running Idexx Cornerstone).

---

## Critical Pitfalls

### Pitfall 1: Whole-window WS_EX_TRANSPARENT kills the drag bar and buttons

**What goes wrong:**
You read "click-through overlay" and slap `WS_EX_TRANSPARENT | WS_EX_LAYERED` on the whole Tk window. Everything passes through — including clicks on the top drag bar and the [−] / [+] / [⤢] buttons at the bottom. The bubble renders correctly but is completely uninteractive; the only escape is the tray icon or the Ctrl+Z hotkey. You cannot reproduce the bug by printing log messages because the button handlers are never called — Windows never even routed the click to your process.

**Why it happens:**
`WS_EX_TRANSPARENT` is all-or-nothing at the window level. It instructs the hit-test system to treat the *entire* window as "not me, ask the next window down." There is no per-region exclusion built into the extended style bits — you have to opt out with a `WM_NCHITTEST` subclass.

**How to avoid:**
Do NOT set `WS_EX_TRANSPARENT` on the whole window. Instead:

1. Set only `WS_EX_LAYERED | WS_EX_TOOLWINDOW` (and optionally `WS_EX_NOACTIVATE` to avoid focus theft from Cornerstone).
2. Subclass `WndProc` via `SetWindowLongPtr(hwnd, GWL_WNDPROC, my_wndproc)` and handle `WM_NCHITTEST` yourself.
3. In the handler, convert `lParam` to client coords (`GetClientRect` + `ScreenToClient`) and return:
   - `HTCAPTION` for pixels inside the top drag-bar rect (gives free OS-level dragging plus double-click-to-maximize, which you probably want to intercept/disable).
   - `HTTRANSPARENT` for pixels inside the middle magnified-content rect (Windows will route the click to the window underneath).
   - `HTCLIENT` for pixels inside the bottom button strip.
   - `HTBOTTOMRIGHT` for the resize grip corner (gives free OS-level diagonal resize).

```python
# Essentials — keep a reference to the WNDPROC or it will be GC'd and crash
import ctypes
from ctypes import wintypes

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t,  # LRESULT on 64-bit
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
)

def _wndproc(hwnd, msg, wparam, lparam):
    if msg == 0x0084:  # WM_NCHITTEST
        # GET_X_LPARAM / GET_Y_LPARAM from lParam (SCREEN coords)
        sx = ctypes.c_short(lparam & 0xFFFF).value
        sy = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        # Convert to client coords, classify zone, return one of:
        # 1 (HTCLIENT) / 2 (HTCAPTION) / -1 (HTTRANSPARENT) / 17 (HTBOTTOMRIGHT)
        ...
    return ctypes.windll.user32.CallWindowProcW(OLD_WNDPROC, hwnd, msg, wparam, lparam)

self._wndproc_ref = WNDPROC(_wndproc)   # CRITICAL: keep this on self, not a local
OLD_WNDPROC = ctypes.windll.user32.SetWindowLongPtrW(hwnd, -4, self._wndproc_ref)
```

**Warning signs:**
- Buttons visually render but don't respond to clicks or touches.
- Tk `Button.command` callbacks never fire.
- Dragging the "drag bar" does nothing.
- You end up adding `print("click!")` statements inside handlers that never run.

**Phase to address:** Phase 2 (basic overlay window) — do not advance from Phase 2 until drag, click, and click-through all work simultaneously on a test layout.

---

### Pitfall 2: Python garbage-collects the WndProc callback → crash on first message

**What goes wrong:**
You wire up a WndProc subclass (as in Pitfall 1) by passing `WNDPROC(_wndproc)` directly to `SetWindowLongPtr` without storing the ctypes callback object anywhere. The code "works" at first — the window shows up fine. Then, milliseconds to seconds later (whenever the Python cycle collector runs), the callback object is garbage-collected, Windows still has a raw function pointer that now points to freed memory, the next `WM_PAINT` or `WM_MOUSEMOVE` fires, and the process crashes with an access violation. The crash is often non-deterministic because GC timing varies.

**Why it happens:**
`ctypes.WINFUNCTYPE(...)` creates a Python object that holds the generated trampoline. When Python reclaims the object, the trampoline memory is freed, but Windows has no way to know — it still holds the raw address you gave it via `SetWindowLongPtr`. This is one of the most common and hardest-to-debug ctypes mistakes on Windows.

**How to avoid:**
**Always** store the `WNDPROC(...)` result on a long-lived object (typically `self` on your main class). Also store the *original* wndproc you got back from `SetWindowLongPtr` so you can restore it on shutdown. On shutdown, restore the old wndproc BEFORE destroying the window.

```python
class Overlay:
    def __init__(self, ...):
        ...
        self._wndproc_ref = WNDPROC(self._wndproc)   # lives as long as self
        self._old_wndproc = user32.SetWindowLongPtrW(hwnd, GWL_WNDPROC, self._wndproc_ref)

    def destroy(self):
        # Restore first, THEN destroy the window.
        user32.SetWindowLongPtrW(self._hwnd, GWL_WNDPROC, self._old_wndproc)
        self.root.destroy()
```

**Warning signs:**
- Crash is random but always within the first few seconds after launch.
- Windows Error Reporting dialog mentions `ACCESS_VIOLATION` in `python311.dll` or `user32.dll`.
- Moving the mouse over the bubble immediately triggers the crash (because mouse movement floods `WM_NCHITTEST`).
- The crash disappears if you add a `time.sleep(1000)` somewhere (coincidentally delaying GC).

**Phase to address:** Phase 2 (basic overlay window) — bake the `self._wndproc_ref` pattern into the first WndProc subclass you write. Do not "fix it later."

---

### Pitfall 3: Touch input bypasses the click-through because WM_POINTER is routed differently

**What goes wrong:**
You carefully implement `WM_NCHITTEST → HTTRANSPARENT` for the middle zone. It works perfectly with a mouse. You demo it on a regular PC. You ship to the clinic. The touchscreen user puts a finger on the magnified content, and the bubble accepts the touch/swipe as its own event instead of passing it to Cornerstone. Or the inverse: drag-bar touches sometimes don't register.

**Why it happens:**
Windows 8+ routes touch and pen through `WM_POINTER` messages. In modern apps, `WM_POINTER` is the primary and `WM_TOUCH`/`WM_MOUSE` are synthesized fallbacks. `WM_NCHITTEST` DOES still run for pointer input — Windows uses the hit-test result to decide where to route the `WM_POINTER*` messages — but there are subtleties:

- `WS_EX_TRANSPARENT` alone does not always pass touch through the same way it passes mouse through; the pointer input system may still synthesize messages to your window for the non-primary touch paths.
- A layered window (`WS_EX_LAYERED`) without `UpdateLayeredWindow` (which is our case — we use `SetLayeredWindowAttributes` instead) has slightly different hit-testing than a non-layered window, and interactions with high-DPI pen/touch can produce coordinate-mapping surprises.
- `WS_EX_NOACTIVATE` is *required* alongside the click-through strategy for touch, or a tap on the bubble can momentarily give your overlay focus, blocking Cornerstone from receiving a subsequent keystroke.

**How to avoid:**
1. Add `WS_EX_NOACTIVATE` to the extended style bits alongside `WS_EX_LAYERED | WS_EX_TOOLWINDOW`. This prevents the bubble from stealing focus on any kind of click/tap.
2. Return `HTTRANSPARENT` from `WM_NCHITTEST` for the middle zone — this is the canonical hit-test pass-through and Windows honors it for pointer input.
3. Do NOT also set `WS_EX_TRANSPARENT` on the whole window. It is not needed once `WM_NCHITTEST → HTTRANSPARENT` is in place, and mixing them creates extra edge cases.
4. **Test on an actual touchscreen** before declaring Phase 2 complete. A mouse is not a valid substitute. If you don't have a touchscreen handy, use the Windows 11 "Simulate touch input with a single finger" developer option (Settings → System → For developers), or test on a laptop that has a touchscreen.
5. When the user drags via the top handle, test with BOTH finger and mouse — `HTCAPTION` should handle both identically.
6. Consider handling `WM_POINTERDOWN` / `WM_POINTERUPDATE` explicitly only if you see misbehavior; otherwise, let `WM_NCHITTEST` do its job.

**Warning signs:**
- "Works for me" on dev PC with a mouse, "broken" on clinic PC with finger input.
- Taps on the magnified area scroll the bubble instead of Cornerstone.
- A second tap on the magnified area sometimes "takes focus" (you see the border flicker).
- Cornerstone stops receiving keyboard input after a touch lands on the bubble (focus-theft symptom).

**Phase to address:** Phase 2 (overlay window), and MUST be re-verified in Phase 3 or wherever touch testing first happens on real hardware. Add an explicit acceptance criterion: "tested with finger input on a touchscreen, not just a mouse."

---

### Pitfall 4: mss captures the overlay itself → feedback loop on Windows 7, but SAFE on Windows 8+ (with caveats)

**What goes wrong:**
The naive fear: "if I capture the screen region under my overlay, mss will capture my own overlay and I'll get a recursive hall-of-mirrors effect." This fear is MOSTLY unfounded on Windows 10/11 because of how layered windows and GDI compositing work — but there are specific conditions under which it CAN happen, and you need to understand them.

**Why it happens (or doesn't):**
- `mss` uses GDI `BitBlt` under the hood with the `SRCCOPY` flag only (not `CAPTUREBLT`).
- On Windows 8+, layered windows (`WS_EX_LAYERED`) are composited by DWM and, by default, **are NOT included** in a `BitBlt(SRCCOPY)` from the screen DC. This is the exact opposite of Windows 7 behavior.
- This means: as long as our overlay window has `WS_EX_LAYERED` set (which it must, for `SetLayeredWindowAttributes` to work), and as long as mss does not pass `CAPTUREBLT`, **our overlay will be automatically excluded from the capture**. No feedback loop.
- **BUT**: if you ever remove `WS_EX_LAYERED` (e.g., during experimentation), or if mss changes its behavior in a future release to use `CAPTUREBLT`, or if another capture library is used, the feedback loop returns instantly.

**How to avoid:**
1. **Never remove `WS_EX_LAYERED`** from the overlay, even temporarily. Set it once at startup and leave it alone. If you need to disable layering for debugging, also hide the bubble during tests.
2. Verify empirically on your target Windows 11 version that a `sct.grab()` of the exact region under the bubble does NOT include the bubble. Write a test script that saves one frame to disk and inspect it. Do this ONCE at the start of Phase 3.
3. If you ever see your own border/UI in the captured frame, the cause is either (a) `WS_EX_LAYERED` got dropped, (b) mss is passing `CAPTUREBLT`, or (c) you're running on Windows 7 (not a target).
4. As a belt-and-suspenders defense, you can briefly hide the window (`ShowWindow(hwnd, SW_HIDE)`) before capture and show it after — but this causes ugly flicker at 30 fps and should NOT be used. The layered-window exclusion is reliable; trust it.
5. Do NOT try to "subtract the bubble rect" from the capture region — the middle zone is what the user wants magnified. The whole point is that the capture region IS under the bubble.

**Warning signs:**
- You see a tiny infinite-mirror effect inside the bubble (classic feedback loop).
- Captured frames show the bubble border or buttons.
- Switching to an experimental code branch (that disables `WS_EX_LAYERED` for any reason) suddenly makes the bubble show itself.

**Phase to address:** Phase 3 (capture loop) — write a one-off verification test before committing to the architecture. Document the result in a comment in the capture module.

---

### Pitfall 5: DPI unawareness → mss captures the wrong pixels on high-DPI displays

**What goes wrong:**
A Windows 11 PC is set to 150% scale. Your app is DPI-unaware. `winfo_width()` and `winfo_x()` return logical (pre-scale) coordinates, but `mss.grab()` operates in physical pixel coordinates. You capture the region at `(bubble_x, bubble_y, bubble_w, bubble_h)` computed from Tk, but what you actually get is a region offset and/or sized wrong by 1.5×. On the user's screen, the magnifier shows pixels from an area up and to the left of where the bubble actually is. The user thinks the app is broken. You spend two days trying to fix it thinking it's a capture bug.

**Why it happens:**
- By default, a Python process on Windows 10/11 is "System DPI Aware" or "Unaware" depending on which libraries it imports — and the state can flip mid-process because some packages (`mouseinfo`, `pyautogui`, `pyscreeze`, matplotlib's Tk backend) call `SetProcessDpiAwareness(...)` during import.
- Tkinter in Python 3.11 is *not* automatically DPI-aware on Windows.
- `mss` respects the process's DPI awareness setting: if unaware, `EnumDisplayMonitors` returns virtualized (scaled) coordinates, and the capture is off.
- The combination of tkinter + mss + unspecified DPI awareness on a 150% scale display is the single most common "it works on dev, broken on clinic PC" bug for this kind of app.

**How to avoid:**
**Set DPI awareness to Per-Monitor-V2 explicitly, as the very first thing your program does, before importing tkinter.** Also confirm at runtime.

```python
# At the top of main.py — BEFORE importing tkinter, mss, or anything else that might set it
import ctypes
try:
    # Per-Monitor V2 (Windows 10 1703+) — best behavior for DPI changes across monitors
    ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
except (AttributeError, OSError):
    try:
        # Fallback: Per-Monitor (Windows 8.1+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()        # System-aware (legacy)

# NOW import tkinter and the rest
import tkinter as tk
import mss
...
```

**Additional defenses:**
1. Use `GetDpiForWindow(hwnd)` to get the real DPI of the monitor containing the bubble, and compute physical coords from logical coords as `physical = int(logical * dpi / 96)`. In practice, if you're Per-Monitor-V2 aware and the window is positioned by Tk, `winfo_x/y/width/height` will return physical pixels directly on Windows, so you can pass them to mss as-is. **But verify this with a test!**
2. Add a PyInstaller manifest entry to set DPI awareness at the OS manifest level as well, so it's correct even before Python code runs. Use a `version_file` or embed a manifest with:
   ```xml
   <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">PerMonitorV2</dpiAwareness>
   ```
3. Test at 100%, 125%, 150%, and 175% scale before shipping. If you only test at 100%, you will ship a broken app.

**Warning signs:**
- The magnified content is offset from the bubble's position (by ~25% of the window size on a 125% scale, ~50% on 150%, etc.).
- Resizing the bubble changes the offset.
- Moving the bubble to the right edge of a high-DPI display captures pixels from beyond the screen edge (black bars).
- "Works on my machine" but not on the clinic PC.
- Everything works at 100% scale but breaks at 150%.

**Phase to address:** Phase 1 (project scaffolding) — make `SetProcessDpiAwarenessContext` literally the first line of `main.py`. Test with multiple scaling percentages in Phase 3 (capture loop).

---

### Pitfall 6: Double-freeing the HRGN after SetWindowRgn crashes the process

**What goes wrong:**
You create a region via `CreateEllipticRgn`, pass it to `SetWindowRgn`, and then — following "good C practice" — call `DeleteObject(rgn)` to clean up. On a later `SetWindowRgn` call (the next resize), or on window close, the process crashes with a heap corruption. Hard to diagnose because the crash is separated in time from the actual bug.

**Why it happens:**
Microsoft Learn is explicit: "After a successful call to `SetWindowRgn`, the system owns the region specified by the region handle `hRgn`. The operating system does not make a copy of the region. Thus, you should not make any further function calls with this region handle. In particular, do not delete this region handle. The system deletes the region handle when it no longer needed."

Calling `DeleteObject` on an OS-owned HRGN is a double-free. It may not crash immediately; it typically crashes when the OS later tries to delete it (next `SetWindowRgn`, or window destruction).

**How to avoid:**

```python
def apply_shape(self, shape):
    import win32gui
    w, h = self.width, self.height
    if shape == "circle":
        rgn = win32gui.CreateEllipticRgn(0, 0, w, h)
    elif shape == "rounded":
        rgn = win32gui.CreateRoundRectRgn(0, 0, w, h, 40, 40)
    else:
        rgn = win32gui.CreateRectRgn(0, 0, w, h)

    # Pass it to SetWindowRgn. If the call succeeds, DO NOT delete rgn.
    # If it fails (returns 0), WE still own it and must delete it.
    result = win32gui.SetWindowRgn(self.hwnd, rgn, True)
    if result == 0:
        # Failure — we still own the region handle
        win32gui.DeleteObject(rgn)
    # else: success — the OS owns rgn now. Do NOT touch it.
```

Wrap this in a comment: `# HRGN ownership: see Microsoft Learn SetWindowRgn docs. Do NOT DeleteObject on success.`

**Warning signs:**
- Heap corruption crash on window resize.
- Crash on app shutdown (`WM_DESTROY` triggers OS cleanup of what we already freed).
- Running under Application Verifier shows a "double free" or "invalid handle" hit on an HRGN.

**Phase to address:** Phase 4 (shape masking) — bake the ownership-handling idiom into the very first `apply_shape` implementation with a comment explaining why.

---

### Pitfall 7: Not calling SetWindowRgn after resize → shape doesn't update

**What goes wrong:**
You set the shape to "circle" and the bubble is a circle. Beautiful. Then the user resizes the bubble bigger. The outer window grows but the circular region stays at the old size — the user now sees a big rectangular window with a circular "cutout" of the correct shape in the upper-left corner and dead space in the new area. Or the new area is clipped. Either way, the shape no longer matches the window.

**Why it happens:**
A window region is attached by value at the time of `SetWindowRgn`. Windows does not automatically grow or shrink the region when the window is resized — the region is in window-relative coordinates but its DIMENSIONS are fixed. You must re-create the region and call `SetWindowRgn` again every time the window's size changes.

**How to avoid:**

1. Bind to `<Configure>` on the Tk root (fires on every move AND resize):
   ```python
   root.bind("<Configure>", self._on_configure)
   ```
2. In the handler, detect resize (not move) by comparing previous dimensions, and re-apply the shape:
   ```python
   def _on_configure(self, event):
       if event.width != self._last_w or event.height != self._last_h:
           self._last_w, self._last_h = event.width, event.height
           self.apply_shape(self._current_shape)   # re-creates region + SetWindowRgn
       # No need to re-apply on pure move — regions are window-relative, not screen-relative
   ```
3. Do NOT re-apply on pure moves — that's wasted work. Region coordinates are relative to the window's upper-left, so moving the window does not invalidate them. Only resize requires a new region.
4. Debounce if `<Configure>` fires many times per second during interactive resize — re-creating a region on every pixel of drag is fine performance-wise but can look flickery.

**Warning signs:**
- After resize, the visible bubble content is the wrong shape (rectangular in a "circle" mode, or clipped).
- Corners of the new window area are blocked from clicks because the old region still thinks that area is outside the window.
- Dragging the resize grip works but the shape "lags."

**Phase to address:** Phase 4 (shape masking) — pair the initial `apply_shape` implementation with the `<Configure>` binding. Treat "resize updates shape" as a Phase 4 acceptance criterion.

---

### Pitfall 8: pystray blocks the main thread → tkinter deadlock

**What goes wrong:**
You call `icon.run()` on the main thread. It blocks forever and never returns control to Python, so `root.mainloop()` never starts, the window never appears, and the tray icon is the only thing you see. Or — if you do it in the other order (`root.mainloop()` first) — `mainloop()` blocks, you never reach `icon.run()`, and there's no tray icon. Or you try threading them both and get `RuntimeError: Calling Tcl from different apartment` because you touched Tk from pystray's thread.

**Why it happens:**
- Both libraries have their own blocking event loop.
- Tkinter REQUIRES that the `mainloop()` runs on the same thread that created the root and that all Tk calls happen on that thread (on Windows this manifests as the "different apartment" Tcl error).
- pystray's `Icon.run()` is blocking and, on macOS, must be main-thread-only. On Windows, it can run on a worker thread.
- Since Tk must be on main and pystray can be on worker (on Windows), **pystray goes on a thread; tkinter stays on main**.

**How to avoid:**

```python
import threading, pystray
from PIL import Image

def _setup_tray(app):
    image = Image.open("assets/bubble.ico")
    menu = pystray.Menu(
        pystray.MenuItem("Show/Hide", lambda: app.thread_safe_toggle()),
        pystray.MenuItem("Always on Top", lambda i, it: app.thread_safe_toggle_top(), checked=lambda it: app.always_on_top),
        pystray.MenuItem("Exit", lambda: app.thread_safe_exit()),
    )
    icon = pystray.Icon("ultimate_zoom", image, "Ultimate Zoom", menu)
    icon.run()   # blocks this worker thread

# In main:
app = Overlay(...)
tray_thread = threading.Thread(target=_setup_tray, args=(app,), daemon=True)
tray_thread.start()
app.root.mainloop()   # blocks main thread; Tk happy
```

**CRITICAL: all Tk operations triggered by pystray menu items MUST be marshalled to the main thread.** pystray menu callbacks fire on the pystray thread. If they touch Tk directly, you get the "different apartment" error. Use `root.after(0, lambda: do_tk_thing())` to schedule the actual work on the Tk main thread:

```python
class Overlay:
    def thread_safe_toggle(self):
        self.root.after(0, self._toggle_visibility)

    def _toggle_visibility(self):
        # This runs on the Tk main thread — safe to touch widgets
        if self.root.state() == "withdrawn":
            self.root.deiconify()
        else:
            self.root.withdraw()
```

**Warning signs:**
- `RuntimeError: main thread is not in main loop`
- `RuntimeError: Calling Tcl from different apartment`
- Tray icon appears but clicking menu items does nothing, or crashes.
- Either the window or the tray works but not both.
- Exit leaves zombie processes (pystray thread didn't stop).

**Phase to address:** Phase 5 (tray icon) — implement the threading + `root.after(0, ...)` pattern on day one. Add a code comment: "pystray thread → Tk main thread marshalling via root.after(0, ...)". Also plan for clean shutdown: `icon.stop()` MUST be called before `root.destroy()` or the daemon thread won't exit cleanly on some Windows setups (see pystray issue #94).

---

### Pitfall 9: Ctrl+Z hotkey conflicts with Cornerstone's undo → user can't undo in Cornerstone

**What goes wrong:**
You call `RegisterHotKey(None, 1, MOD_CONTROL, VK_Z)`. It succeeds. Your Ctrl+Z-toggles-the-bubble feature works globally. Then the user is typing in a Cornerstone patient record, makes a typo, presses Ctrl+Z to undo... and the bubble hides/shows instead. Cornerstone never receives the Ctrl+Z. The user can't undo anything in Cornerstone while the magnifier is running.

**Why it happens:**
`RegisterHotKey` is a *system-wide* intercept. When it succeeds, Windows dispatches `WM_HOTKEY` to your thread's message queue BEFORE delivering the key event to the foreground window. There is no mechanism in `RegisterHotKey` to "also forward the keystroke to the focused app." The whole point of the API is exclusive capture.

Cornerstone's Ctrl+Z (in-app undo) is NOT a registered global hotkey — it's just a WM_KEYDOWN handler inside Cornerstone. That means our `RegisterHotKey` wins every time, and Cornerstone's undo handler never fires.

PROJECT.md specifies Ctrl+Z as the v1 default, but this is a UX bomb.

**How to avoid:**

1. **Make the hotkey combo configurable in `config.json`** from day one. Default to Ctrl+Z if PROJECT.md says so, but let it be changed without a rebuild.

   ```json
   {
     "hotkey": { "modifiers": ["ctrl"], "key": "z" },
     ...
   }
   ```

2. **Surface the conflict to the end user.** In the README, explicitly warn: "While Ultimate Zoom is running, Ctrl+Z toggles the magnifier instead of undoing in Cornerstone. If you need Cornerstone's undo, either edit `config.json` to use a different hotkey (e.g., Ctrl+Alt+Z) or exit Ultimate Zoom first."

3. **Recommended default to offer user:** `Ctrl+Alt+Z` or `Ctrl+Shift+Z`. These do not conflict with any Cornerstone action and are still discoverable. Even better: a dedicated key with no common conflicts like `Pause/Break` or `Scroll Lock`, or a function key (`F9`/`F12`).

4. **Confirm the conflict explicitly with the end user** before shipping. Ask: "Do you ever use Ctrl+Z inside Cornerstone? If yes, we should pick a different shortcut."

5. Document in PROJECT.md Key Decisions table that Ctrl+Z was chosen as the spec default but is configurable, and that a UX review with the end user is required before clinic rollout.

**Warning signs:**
- User reports "my undo broke in Cornerstone after installing the magnifier."
- Calls to support about "missing text" in patient records (they typed, hit Ctrl+Z to undo a typo, the bubble toggled, they didn't realize their typo wasn't undone, they retyped over their actual text).
- In testing, try Ctrl+Z in a Notepad window while the app runs — notepad undo should NOT fire.

**Phase to address:** Phase 6 (hotkey) — configurable hotkey is a Phase 6 requirement, not a v2 feature. Plus: require explicit end-user confirmation before shipping.

---

### Pitfall 10: Global hotkey already registered → silent failure, no visual feedback

**What goes wrong:**
You run the app a second time (double-click the .exe while the first copy is running, or the first copy crashed and left its hotkey registered in a dead process... actually no, `RegisterHotKey` is per-process and dies with the process... or so you'd think, but see below). The second instance's `RegisterHotKey` call fails. Your code logs an error to stdout (which doesn't exist in a --noconsole PyInstaller build, so it goes to `NUL`). The app launches, the UI works, but Ctrl+Z does nothing. User thinks the app is broken.

**Why it happens:**
- `RegisterHotKey` fails with `ERROR_HOTKEY_ALREADY_REGISTERED` if another process (or another thread in your own process) has already registered the same combo.
- A PyInstaller `--noconsole` build has no stdout/stderr; `print("error")` goes nowhere.
- Users can double-click the icon multiple times and end up with two instances, neither of which knows about the other, and the second silently fails.
- If the first instance crashed while holding the hotkey, Windows normally releases it — BUT if the crash didn't go through `UnregisterHotKey` AND the process is still alive in some zombie state (can happen with PyInstaller onefile extraction hanging), the hotkey can leak.

**How to avoid:**

1. **Single-instance lock**. Use a named mutex at startup:
   ```python
   import ctypes
   mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\UltimateZoomSingleton")
   if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
       # Another instance is running — activate it (if we can) and exit
       ctypes.windll.user32.MessageBoxW(0, "Ultimate Zoom is already running.", "Ultimate Zoom", 0x40)
       sys.exit(0)
   ```
2. **Verify `RegisterHotKey` success and show a visible error** (not a log message):
   ```python
   if not user32.RegisterHotKey(None, HOTKEY_ID, mods, vk):
       err = ctypes.GetLastError()
       # Show a proper MessageBox, not print()
       ctypes.windll.user32.MessageBoxW(
           0,
           f"Could not register global hotkey (error {err}).\n"
           f"Another program may be using this combo.\n"
           f"You can still use the tray icon to show/hide the bubble.",
           "Ultimate Zoom",
           0x30,  # MB_ICONWARNING
       )
   ```
3. **Always call `UnregisterHotKey` in a `finally` or `atexit`**:
   ```python
   import atexit
   atexit.register(lambda: user32.UnregisterHotKey(None, HOTKEY_ID))
   ```
   (Not strictly necessary because the OS releases hotkeys when the process dies, but defensive.)
4. **Install a top-level exception handler** so crashes don't skip cleanup:
   ```python
   try:
       main()
   except Exception:
       import traceback
       traceback.print_exc(file=open("crash.log", "w"))
       raise
   finally:
       user32.UnregisterHotKey(None, HOTKEY_ID)
   ```

**Warning signs:**
- App launches, UI works, hotkey does nothing.
- Two tray icons appear.
- `crash.log` exists from a previous run but the app is "working fine" now.
- User reports intermittent hotkey behavior across reboots.

**Phase to address:** Phase 6 (hotkey) for the registration-failure handling; Phase 7 (tray/persistence) for the single-instance mutex. Do BOTH before shipping.

---

### Pitfall 11: PyInstaller hidden imports missing → .exe launches on dev box, crashes on clinic PC

**What goes wrong:**
Everything works when you run `python main.py` from your venv. You build with PyInstaller, the `.exe` launches on your dev box because pywin32 system DLLs are still on `PATH`. You copy the `.exe` to the clinic PC. On first launch: a flash of a window, then instant close. No error message. No crash dialog (because `--noconsole`). The user thinks the app is corrupt.

**Why it happens:**
PyInstaller misses modules in three specific failure patterns for this stack:

1. **pywin32**: `pywin32` ships `pywintypes311.dll` and `pythoncom311.dll` in `site-packages/pywin32_system32/`. PyInstaller's pywin32 hook has to copy these and prepend the `pywin32_system32` directory to `sys.path` at runtime. In some PyInstaller versions this hook is fragile, particularly when switching between venvs or when both `pywin32` and the legacy `pypiwin32` are installed.
2. **pystray**: pystray picks its backend at runtime via `importlib.import_module('pystray._win32')`. PyInstaller's static analysis does not see this, so `pystray._win32` is not bundled. You get `No module named 'pystray._win32'` on launch.
3. **PIL/Pillow**: `PIL._tkinter_finder` is a submodule that binds PIL to Tk at runtime. It too is picked dynamically and must be listed as a hidden import for `ImageTk.PhotoImage` to work.

**How to avoid:**

Add to your `.spec` file:
```python
a = Analysis(
    ['main.py'],
    ...
    hiddenimports=[
        'pystray._win32',
        'PIL._tkinter_finder',
        'win32timezone',       # sometimes needed by pywin32 on launch
        'pywintypes',          # defensive — ensure the .dll-loader module is seen
        'win32con',
        'win32gui',
        'win32api',
    ],
    ...
)
```

Other required PyInstaller settings:
- `console=False` (GUI app)
- `upx=False` (UPX triggers AV false positives)
- `icon='assets/bubble.ico'`
- Bundle a version file for proper Explorer Properties → Details.
- Do NOT use `--onedir` for clinic deployment — single `.exe` per PROJECT.md.
- **Build from a clean venv** that has ONLY the packages in `requirements.txt`. PyInstaller will otherwise pull in every module on sys.path and bloat the output + increase attack surface for AV false positives.
- **Test the built .exe on a PC without Python installed** (a VM or a second machine) before assuming it works. "Works in the build venv" does not prove the built .exe is self-contained.

**Warning signs:**
- `.exe` launches briefly and disappears on the clinic PC.
- `ModuleNotFoundError: No module named 'pystray._win32'` (visible if you run it from cmd with a console build).
- `ImportError: DLL load failed while importing win32api`
- `PIL.ImageTk._tkinter_finder` not found.
- App works from `python main.py` but not from the built `.exe`.
- App works from the built `.exe` on your dev box but not on a clean VM.

**Phase to address:** Phase 8 (build & package) — set up the `.spec` file with all hidden imports on day one of that phase. Add a "test on clean VM" acceptance criterion. Include the `.spec` file in version control.

---

### Pitfall 12: PhotoImage recreation per frame → Tk memory leak on Windows

**What goes wrong:**
In your 30 fps capture loop you do:
```python
img = Image.frombytes("RGB", size, raw)
img = img.resize(...)
photo = ImageTk.PhotoImage(img)
self.label.config(image=photo)
self.label.image = photo   # keep reference
```

Looks correct. You even assigned `self.label.image = photo` so the image isn't GC'd. You run it for 10 minutes in testing — fine. You leave it running at the clinic for a 9-hour shift. Memory climbs to 1.5 GB and the PC starts thrashing.

**Why it happens:**
CPython issue 124364 documents a real memory leak in tkinter on Windows specifically: updating `Label` or `Canvas` image items with new `PhotoImage` objects repeatedly does not fully release the previous image's memory on Windows (the issue is Windows-specific and not reproduced on Linux). The leak is small per frame (KB-scale) but at 30 fps over hours, it adds up. In addition to the CPython leak, there are application-level mistakes that compound it:

- Keeping old `ImageTk.PhotoImage` references around (e.g., appending to a list "just in case").
- Forgetting to reassign `self.label.image` — the old PhotoImage stays referenced by the widget until a new one replaces it, but the OLD Python variable (`photo`) gets discarded, potentially creating orphaned Tk handles.
- Creating a NEW `ImageTk.PhotoImage` when you could have reused an existing one with updated pixel data.

**How to avoid:**

1. **Reuse a single `ImageTk.PhotoImage` and update its bytes with `paste()`** instead of creating a new one every frame:
   ```python
   # Once at init:
   self._photo = ImageTk.PhotoImage("RGB", (self.content_w, self.content_h))
   self.label.config(image=self._photo)
   self.label.image = self._photo

   # Every frame:
   self._photo.paste(new_pil_image)   # in-place update — no new PhotoImage
   ```
2. **Explicitly del the old photo** before creating a new one if you must create a new one (e.g., after a resize changes content dimensions):
   ```python
   if hasattr(self, '_photo'):
       del self._photo
       self.label.image = None
   self._photo = ImageTk.PhotoImage(img)
   self.label.config(image=self._photo)
   self.label.image = self._photo
   ```
3. **Monitor memory in Phase 3** (capture loop). Let the app run for 30 minutes, watch Task Manager → Memory. If it grows more than 20 MB over a half hour, investigate.
4. **Garbage-collect explicitly on a timer** (every 60 seconds, call `gc.collect()`). Small hack, but on a stuck Tk memory situation it usually helps.
5. **Use a `Canvas` with `create_image()` + `itemconfig(img, image=...)`** instead of a `Label` — the canvas image item is slightly more forgiving of image churn, and it's also what you'll want anyway for overlaying the border stroke.
6. **Do NOT use Pillow's `Image.Resampling.LANCZOS` for the main loop.** LANCZOS is 3–5× slower than BILINEAR. For upscaling (1.5×–6×), LANCZOS provides little visible benefit (there's nothing to preserve when going up). Use `BILINEAR` or `BICUBIC`. LANCZOS can be an optional "high quality, lower frame rate" mode in config.

**Warning signs:**
- Task Manager shows Python/app memory creeping up steadily during use.
- After an hour of use, the magnifier feels laggy.
- Closing the app doesn't free the memory immediately (Tk holding references until process exit).
- CPU usage is high because GC is pressure-running.

**Phase to address:** Phase 3 (capture loop) — implement the `paste()` reuse pattern from the start. Add a "memory does not grow after 30 minutes" acceptance criterion.

---

### Pitfall 13: config.json write race condition → corrupted config on crash

**What goes wrong:**
PROJECT.md says "persist config to config.json on every change." You implement:
```python
with open("config.json", "w") as f:
    json.dump(self.config, f)
```
This runs every time the user resizes, drags, or changes zoom. The user drags the bubble. Windows crashes (or the user pulls the plug, or the app is killed mid-write, or anti-virus locks the file). On next launch, `config.json` is zero bytes or half-written. Your `json.load()` raises, the app refuses to start — or worse, you catch the error and reset to defaults, silently losing all the user's customization.

**Why it happens:**
A plain `open(f, "w")` truncates the file first, then writes. Between truncate and write-complete, the file is in an inconsistent state. Any crash during that window leaves a corrupted file. At 30 fps + drag events + resize events, the write happens many times per second, and the window of vulnerability is non-trivial over hours of use.

**How to avoid:**

1. **Write atomically**: write to a temp file in the same directory, then `os.replace` it over the target. On Windows, `os.replace` maps to `MoveFileEx` with `MOVEFILE_REPLACE_EXISTING`, which is atomic at the directory-entry level.

```python
import os, json, tempfile

def save_config(config, path="config.json"):
    dir_ = os.path.dirname(os.path.abspath(path)) or "."
    # Temp in SAME directory — different filesystems can break atomicity
    fd, tmp = tempfile.mkstemp(prefix=".config.", suffix=".tmp", dir=dir_)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
            f.flush()
            os.fsync(f.fileno())   # force to physical disk
        os.replace(tmp, path)       # atomic rename on both POSIX and Windows
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise
```

2. **Debounce writes.** Do NOT write on every mouse-move during a drag. Instead, update the in-memory config on every change, and flush to disk 500ms after the last change:
   ```python
   def _schedule_save(self):
       if self._save_after_id:
           self.root.after_cancel(self._save_after_id)
       self._save_after_id = self.root.after(500, self._actual_save)
   ```
3. **Handle read failures gracefully**:
   ```python
   def load_config(path="config.json"):
       try:
           with open(path, "r", encoding="utf-8") as f:
               return json.load(f)
       except (FileNotFoundError, json.JSONDecodeError, OSError):
           return DEFAULT_CONFIG.copy()
   ```
4. **Also flush on clean shutdown** — register an `atexit` hook plus handle `WM_CLOSE` to flush any pending debounced save immediately.
5. **Keep a .bak**: write a backup on successful save, so if config.json ever comes back corrupt, you can fall back to the previous good copy.

**Warning signs:**
- `JSONDecodeError` on startup logs.
- `config.json` is zero bytes after an unexpected shutdown.
- Users report "my settings didn't save" after reboots.
- Anti-virus locks flagging the app (AV software that aggressively scans frequently-written files).

**Phase to address:** Phase 7 (persistence + tray) — the very first config-save implementation should use the atomic-write pattern. Do not write a "simple version first, atomic later" — it's the same amount of code.

---

### Pitfall 14: Capture thread doesn't marshal frames to Tk → "different apartment" crashes

**What goes wrong:**
You correctly put the capture loop on a worker thread for performance. Inside the loop, you directly call `self.label.config(image=photo)` or `self.canvas.itemconfig(img_id, image=photo)`. On Windows, you immediately get `RuntimeError: main thread is not in main loop` or `Tcl_AsyncDelete: async handler deleted by the wrong thread`, and the app crashes.

**Why it happens:**
Tkinter is not thread-safe on Windows (or anywhere, really — the documentation is coy but the practical rule is: touch Tk from one thread only). Tcl/Tk uses an apartment-threaded model on Windows and will raise or crash if a different thread modifies widgets.

**How to avoid:**

Two patterns, pick one:

**Pattern A — `root.after(0, callback)` from the worker thread:**
```python
def capture_loop(self):
    while self.running:
        frame = self._capture()   # runs on worker
        # Schedule the Tk update on the main thread
        self.root.after(0, self._update_image, frame)
        time.sleep(1/30)

def _update_image(self, frame):  # runs on main thread via after()
    self._photo.paste(frame)
    self.label.config(image=self._photo)
```
Note: `root.after(0, ...)` from a non-Tk thread is itself technically undefined on some platforms, but on Windows it has been reliable in practice. Still, for maximum safety, use Pattern B.

**Pattern B — queue + main-thread polling (more idiomatic, robust across all platforms):**
```python
import queue

class Overlay:
    def __init__(self):
        self._frame_q = queue.Queue(maxsize=2)   # small queue — drop old frames
        ...
        self._poll_queue()   # start the Tk-side poll

    def _poll_queue(self):   # runs on main thread
        try:
            while True:
                frame = self._frame_q.get_nowait()
                self._photo.paste(frame)
                self.label.config(image=self._photo)
        except queue.Empty:
            pass
        self.root.after(16, self._poll_queue)   # ~60 Hz poll

    def _capture_loop(self):   # runs on worker thread
        with mss.mss() as sct:
            while self.running:
                shot = sct.grab(self._region)
                img = Image.frombytes("RGB", shot.size, shot.rgb).resize(...)
                try:
                    self._frame_q.put_nowait(img)
                except queue.Full:
                    pass   # drop this frame if UI can't keep up
                time.sleep(1/30)
```

**Also:** use a small queue (maxsize=2). If the UI thread can't keep up, drop frames rather than build up latency. A 5-second-old magnified view is worse than no view at all for a clinic workflow.

**Warning signs:**
- `RuntimeError: main thread is not in main loop`
- `Tcl_AsyncDelete: async handler deleted by the wrong thread`
- Crashes that happen specifically during drag + capture (concurrency bug exposed).
- "Freezing" behavior where the capture loop runs but the UI never updates.

**Phase to address:** Phase 3 (capture loop) — pick the queue pattern from the start. Do NOT write the capture loop on the main Tk thread "for simplicity."

---

### Pitfall 15: overrideredirect + taskbar/Alt-Tab behavior is not deterministic across Tk versions

**What goes wrong:**
You use `root.overrideredirect(True)` to remove the title bar. On Windows 11 with Python 3.11's bundled Tk, the window correctly doesn't appear in the taskbar — perfect. You ship. A user with a slightly different Tk build (or an older Python 3.11 patch version, or after a Windows update) starts seeing the bubble appear in Alt+Tab. Or the taskbar. Or it loses topmost-ness on focus change.

**Why it happens:**
`overrideredirect(True)` is implementation-defined on Windows. Different Tk versions produce different extended window styles. The "reliable" trick is to ALSO set `WS_EX_TOOLWINDOW` explicitly via pywin32, regardless of what Tk does — this reliably excludes the window from both the taskbar and Alt+Tab on all Windows versions.

Also: `overrideredirect` can break `wm_attributes("-topmost", True)` on some Tk versions — the topmost style gets lost because `overrideredirect` strips styles. The fix is to re-apply topmost AFTER overrideredirect.

**How to avoid:**

```python
# Order matters. Do not change this order without testing all four cases on Win11.
root = tk.Tk()
root.withdraw()                                   # hide so we don't flash a taskbar entry
root.overrideredirect(True)                       # strips chrome
root.wm_attributes("-topmost", True)              # must come AFTER overrideredirect
root.geometry(f"{w}x{h}+{x}+{y}")

# Now set the extended style explicitly via pywin32, belt-and-suspenders
hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
current = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
new = current | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new)

root.deiconify()                                  # show, now with correct styles
```

**Warning signs:**
- Bubble shows up in Alt+Tab.
- Bubble appears in the Windows 11 taskbar.
- Bubble loses focus behavior is weird (sometimes stays on top, sometimes doesn't).
- Taskbar flickers when the bubble launches.

**Phase to address:** Phase 2 (basic overlay window) — use the withdraw/style/deiconify pattern from the first commit. Test: (a) app does not show in taskbar, (b) app does not show in Alt+Tab, (c) app stays topmost when Cornerstone is focused, (d) launching the app does not flicker the taskbar.

---

## Technical Debt Patterns

Shortcuts that may seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Capture on Tk main thread (no worker) | Simpler code, no queue | UI freezes during drag, 30 fps unreachable | Never — fails perf requirement |
| Use `PIL.ImageGrab` instead of mss | One less dependency | 5–10× slower, can't hit 30 fps | Never — explicitly forbidden in PROJECT.md |
| Use `keyboard` library for global hotkey | 3 lines instead of ~30 | Library is archived/unmaintained; shipping unmaintained deps to a clinic is a liability | Never |
| Use `pynput.keyboard.GlobalHotKeys` | Simpler API | Documented Win11 reliability issues (see pyinstaller #9255) | Only if RegisterHotKey is unavailable (it won't be) |
| Non-atomic `open("config.json", "w")` | 1 line instead of 10 | Corrupted config on crash, user support calls | Never once a user has any state to lose |
| Log hotkey registration failure via `print()` | Works in dev | Invisible in --noconsole build; user thinks hotkey is broken | Never — use MessageBoxW for user-facing errors |
| `Image.Resampling.LANCZOS` in main loop | Prettier magnification | 3–5× slower; blows 33 ms budget | As opt-in "high quality still" mode, never as the running default |
| Recreate `ImageTk.PhotoImage` every frame | Simplest possible code | Slow GC-unfriendly memory churn on Windows; tkinter issue 124364 leak | Prototype phase only; MUST switch to paste() reuse before user testing |
| `DeleteObject` the HRGN "just to be safe" | Feels defensive | Double-free crash later; hard to diagnose | Never — the OS owns it after successful SetWindowRgn |
| Hardcode Ctrl+Z without making it configurable | Matches PROJECT.md spec verbatim | Any UX conflict with Cornerstone requires a rebuild | Acceptable only if end-user confirms they never use Cornerstone's undo |
| Store `WNDPROC(_callback)` in a local variable | Code is shorter | Python GC crashes the process on any later message | Never — always store on self |
| Build PyInstaller .exe from your main dev venv | Skip the clean venv step | Bloated output with unrelated packages; AV false positives; slower startup | Never for clinic deployment; acceptable for throwaway dev builds |
| Use `--onedir` for deployment | Faster startup | PROJECT.md specifies `--onefile`; harder to copy to a clinic PC | Never for v1; --onedir is OK as a dev-only debug build |
| UPX-compress the .exe | Smaller .exe | Massive AV false-positive increase | Never |
| Skip single-instance mutex | Less code | Two instances = double hotkey, double tray icon, silent failure | Never once hotkey is implemented |
| Skip DPI awareness call | Works at 100% scale on dev machine | Completely broken at 125% / 150% / 175% on user machines | Never — set Per-Monitor-V2 as first line of main |

---

## Integration Gotchas

Common mistakes when connecting to the external services and APIs this app uses.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `mss` + tkinter | Creating `mss.mss()` inside the capture loop | Create ONCE on the capture thread, reuse |
| `mss` + mixed screen coords | Passing Tk logical pixel coords to mss without DPI conversion | Set Per-Monitor-V2 awareness; use physical pixels consistently |
| `mss` + own overlay | Fear that the overlay will be captured (and naive "hide before capture" flicker) | Trust `WS_EX_LAYERED` exclusion from `BitBlt(SRCCOPY)` on Win8+; verify once and document |
| `pywin32` + tkinter hwnd | Using `root.winfo_id()` directly (it's the child widget's handle, not the Toplevel) | Use `ctypes.windll.user32.GetParent(root.winfo_id())` to get the toplevel HWND |
| `pywin32` `SetWindowRgn` | `DeleteObject` after successful call | Only DeleteObject if SetWindowRgn returns 0 (failure) |
| `pywin32` `SetWindowLongPtr` WndProc | Losing the Python callback reference to GC | Store on `self._wndproc_ref` permanently |
| `pystray` + `tkinter` | Calling `Icon.run()` on main thread; touching Tk from pystray callbacks | pystray on worker thread; all Tk access via `root.after(0, ...)` |
| `pystray` + PyInstaller | Missing `pystray._win32` hidden import | Add `hiddenimports=['pystray._win32', 'PIL._tkinter_finder']` to .spec |
| `RegisterHotKey` lifecycle | Never unregistering, leaving it for OS cleanup | Call `UnregisterHotKey` in `atexit` AND on shutdown path |
| `RegisterHotKey` thread model | Calling `GetMessage` on the Tk main thread (blocks mainloop) | Hotkey listener on dedicated daemon thread; communicate via queue or `root.after` |
| Cornerstone + global Ctrl+Z | Registering Ctrl+Z without considering Cornerstone's in-app undo | Make hotkey configurable; warn end user; verify with end user before deploy |
| PyInstaller + pywin32 | Building from a venv with both `pywin32` and legacy `pypiwin32` installed | Use only `pywin32==311`; clean venv for builds |
| `Pillow` `ImageTk.PhotoImage` | Not keeping a reference → GC → image vanishes | `label.image = photo` idiom, OR reuse a single PhotoImage with `.paste()` |
| `numpy` + mss | Using `np.frombuffer(shot.raw, ...)` and then slicing BGRA → RGB manually every frame | Use `shot.rgb` if perf is fine; profile before hand-optimizing with numpy |
| `tkinter` Toplevel extended styles | Setting `WS_EX_LAYERED` before the window is mapped | Call `root.update()` once, or withdraw/deiconify, before setting extended styles |
| `tkinter` `overrideredirect(True)` after mapping | Taskbar flashes briefly on launch | Call `overrideredirect(True)` BEFORE the first `deiconify()` / `update()` |

---

## Performance Traps

Patterns that work for small/short usage but fail during a real clinic shift.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Pillow `LANCZOS` resize in main loop | CPU pegged, fps drops to 10–15 | Use `BILINEAR`; reserve LANCZOS for optional "still" mode | Any magnification >= 2× on typical clinic PC |
| Creating new `ImageTk.PhotoImage` per frame | Gradual memory creep (20–100 MB/hour) | Reuse single PhotoImage with `.paste()` | 30+ minutes of continuous use |
| Capturing the entire primary monitor then cropping in Python | Fine for 100 ms, bad for 30 ms | Pass exact region rect to `sct.grab({"left":..., "top":..., "width":..., "height":...})` | First scale-up past 1.5× on a 1080p display |
| `mss.mss()` instantiated in loop | Microsecond-scale but measurable slowdown; possible GDI handle leak | Instantiate once on the capture thread | Sustained long sessions |
| Writing config.json on every `<Motion>` event | Disk IO every few ms, AV conflict | Debounce 500 ms after last change | Interactive drag sessions |
| Writing frame-rate-unthrottled capture loop | CPU at 100%, battery drain (on laptops) | Cap at 30 fps: measure time, sleep remainder | Instantly on any machine |
| SetWindowRgn on every `<Motion>` during drag | GDI handle churn, flicker | Only apply shape on `<Configure>` resize; skip pure moves | After a few minutes of dragging |
| Calling `winfo_x()/winfo_y()/winfo_width()/winfo_height()` inside hot loop | Tk round-trips are cheap but not free | Cache last-known values, update on `<Configure>` | Possibly never visibly; good hygiene though |
| Polling the frame queue at 1 ms via `after(1, ...)` | 100% CPU on a Tk thread that should be idle | Poll at ~16 ms (60 Hz) — plenty for a 30 fps source | Immediately |
| Debug logging to a file on every frame | IO-bound, fps drops | Log at INFO level only during init; DEBUG only when diagnosing | Any production session |
| Un-daemonized hotkey thread | App doesn't exit cleanly on close | `threading.Thread(daemon=True)` | Visible on Task Manager after user closes |

---

## Security Mistakes

Note: this app is local-only, offline, single-user. Network attack surface is nearly zero. But there are still a few non-generic mistakes.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Requesting UAC admin in PyInstaller manifest | Cornerstone rollout team may refuse to install; unnecessary prompts | `uac_admin=False` — `RegisterHotKey` does NOT need admin for Ctrl-based hotkeys |
| Writing config.json to `Program Files\UltimateZoom\` | Needs admin to write; silent failure without admin; config doesn't persist | Store config in `%APPDATA%\UltimateZoom\config.json` OR alongside the .exe in a user-writable location |
| Capturing secondary-display pixels (e.g., a PIN pad on another monitor) | Accidental exposure of sensitive info if user drags bubble across multi-monitor boundary | Document multi-monitor as out of scope (PROJECT.md already does); consider a "stay on primary monitor" constraint |
| Shipping unsigned .exe to a clinic | Windows SmartScreen warns users; IT may block the download | Optional code signing (not strictly required for local copy-deploy, but improves UX); at minimum whitelist the .exe on clinic AV |
| Using `keyboard` library (archived) | Unmaintained code in clinic environment, no CVE fix path | Use `ctypes.RegisterHotKey` directly (already the PROJECT.md recommendation) |
| Logging screen pixel data to disk (even for debug) | Accidental PHI/HIPAA exposure (clinic environment, patient records visible) | NEVER write frame data to disk, even in debug builds. Never. No exceptions. |
| Saving bubble position in a path that includes the user's username in a way that's shared | Leaks username if config.json is exported | Not likely for this app's threat model; mentioned for completeness |
| Leaving `print()` statements that might leak info into a stray console | None practically (GUI build has no console) | Still — `print()` to stdout is harmless but sloppy; use a logger |
| Hardcoding hotkey to Ctrl+Z without confirming with end user | Functional, not security, but: user accidentally loses work when Ctrl+Z fails to undo in Cornerstone | Confirm with end user; make configurable; warn in README |

**IMPORTANT:** The "never log frame data" rule is the single most important security principle for this app. A veterinary clinic has patient records, billing info, and client contact details visible on screen. A debug log of captured frames would be an HIPAA/PHI incident. **Never write captured pixel data to disk, not even behind a debug flag.** Ideally, it should be impossible to do so without modifying the source code — do not add a "save frame" feature for diagnostics.

---

## UX Pitfalls

Common user experience mistakes specific to the vision-impaired-user + touchscreen + clinic-workflow context.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Ctrl+Z hotkey intercepts Cornerstone undo | Breaks muscle-memory workflow; silent data loss | Make hotkey configurable; verify with user before shipping |
| Touch targets < 44×44 px | Finger taps miss buttons on touchscreen | Enforce 44×44 minimum in code (PROJECT.md already specifies this) |
| Small or low-contrast border on the bubble | User with Stargardt's can't see where the bubble is | 3–4 px teal/soft-blue border (PROJECT.md spec); verify on multiple clinic backgrounds including white Cornerstone UI |
| Magnification < 1.5× is "technically supported" | Not visibly useful, wastes a setting | 1.5× floor is correct — don't expose lower |
| No visible feedback when hotkey toggles bubble | User presses Ctrl+Z expecting undo, bubble silently vanishes, user is confused | Add a subtle fade-out or a brief tray-icon flash on toggle so the user confirms intent |
| Tiny close / exit in corner | User accidentally exits during drag | No close button at all — use tray Exit. Dragging should not be able to "flick" the bubble off-screen (clamp to monitor bounds) |
| Hotkey during text entry in Cornerstone | User is typing in a patient record, hits Ctrl+Z expecting undo, bubble toggles instead, they have no idea why | Configurable hotkey + user documentation + optional "modifier lockout" (e.g., don't register Ctrl+Z; require Ctrl+Alt+Z which is never an app undo) |
| Bubble off-screen after monitor disconnect/reconnect | Config restores position that is no longer valid | On startup, validate saved `x,y` against current monitor geometry; if invalid, center on primary |
| No way to restore default size/position | User accidentally resizes to 700×700 and can't find the tiny buttons | Tray menu "Reset to defaults" item |
| Resizing via corner grip competes with drag handle | User accidentally drags when trying to resize | Make the resize grip visually distinct (e.g., diagonal stripes) and physically separate (bottom-right corner only) |
| Zoom buttons adjacent with no gap | Fat-finger touches hit the wrong one | Minimum 8 px gap between [-] and [+]; 44 px minimum touch target (PROJECT.md spec) |
| No tray tooltip | User forgets what the small icon is | Set meaningful tooltip: "Ultimate Zoom — Ctrl+Z to show/hide" |
| Config change applies only after restart | User resizes expectation: instant | All settings should apply live; config persists on debounced timer |
| Hiding the bubble and not making it obvious how to get it back | User panics, force-kills the app | Tray icon + documented hotkey + tray tooltip "Ctrl+Z to toggle" |
| Assuming the user can read a tooltip | Stargardt's = central vision loss; tooltips may not be readable | Tooltips are a bonus, not the primary UX. Use clear large iconography as the primary cue. |

---

## "Looks Done But Isn't" Checklist

Things that appear complete during dev but are missing a critical piece before clinic deployment.

- [ ] **Click-through middle zone:** Works with MOUSE in dev; verify with FINGER on a touchscreen. Not the same code path in Windows 11.
- [ ] **Click-through middle zone:** Verify clicks pass to Cornerstone SPECIFICALLY, not just to Notepad. Cornerstone may use unusual focus/input handling.
- [ ] **WS_EX_NOACTIVATE:** Without this, tapping the bubble momentarily steals focus from Cornerstone — catastrophic for typed input.
- [ ] **DPI awareness:** Works at 100% scale; verify at 125%, 150%, 175%. The clinic PC's scale is unknown — verify with IT before shipping.
- [ ] **PhotoImage memory:** Works for 5 minutes; verify memory is stable over 30+ minutes.
- [ ] **config.json atomic write:** Implemented; verify by killing the process mid-save in a loop and confirming the file is always valid JSON after.
- [ ] **Shape re-application on resize:** Shape updates on first set; verify it updates on user-interactive resize via drag grip.
- [ ] **Hotkey registration failure path:** Assume success during dev; test the failure path (run the app twice) and verify the user sees a visible error.
- [ ] **PyInstaller clean-venv build:** Built in dev venv with 30 extra packages; rebuild from a MINIMAL venv with only `requirements.txt` and verify output size is sane.
- [ ] **PyInstaller on clean VM:** Built and runs on your dev PC; verify on a VM with no Python installed. This is the only way to catch missing hidden imports.
- [ ] **Hidden imports:** `pystray._win32` and `PIL._tkinter_finder` — if you don't list them, you WILL hit them on first clinic install.
- [ ] **WndProc reference:** Stored on `self._wndproc_ref`, not a local. Test by letting the app sit idle with the mouse hovering for 2 minutes — if it crashes, GC got it.
- [ ] **HRGN ownership:** `DeleteObject` NOT called on success path. Test by resizing the window 50 times in a row — if crash, double-free is happening.
- [ ] **Single instance:** Double-click the .exe twice during testing — second instance should NOT launch.
- [ ] **Hotkey unregister on exit:** After app exit, verify the hotkey is free (launch a fresh instance — if it says "already registered," cleanup is broken).
- [ ] **pystray thread marshaling:** Click a tray menu item — if you get `RuntimeError: Calling Tcl from different apartment`, you're missing `root.after(0, ...)`.
- [ ] **overrideredirect + topmost order:** Window is topmost on launch; verify it STAYS topmost after Cornerstone gets focus.
- [ ] **No taskbar entry:** Launch the app; verify (with Task Manager visible) no taskbar button for the bubble.
- [ ] **No Alt+Tab entry:** Launch the app; Alt+Tab; verify the bubble is not in the switcher.
- [ ] **Config restores on launch:** Not just that it SAVES, but that it RESTORES with the exact same position/size/shape/zoom on next launch.
- [ ] **Config off-screen resilience:** Delete primary monitor in display settings (or disconnect cable) between saves and launches; app should recenter, not go invisible off-screen.
- [ ] **Shape click-through:** For non-rectangular shapes (circle/rounded), verify that clicks outside the shape but inside the bounding rect pass through (SetWindowRgn handles this automatically — verify it works).
- [ ] **Resize clamps:** 150×150 minimum, 700×700 maximum (PROJECT.md spec). Try dragging below/above these and verify the clamp.
- [ ] **Zoom range:** 1.5×–6× in 0.25× increments. Click [+] past 6×, click [−] past 1.5× — verify it doesn't go out of range.
- [ ] **Touch targets ≥ 44×44:** Measure the rendered size of every button at the default scale; verify it's >= 44 px.
- [ ] **Frame dropping under load:** Start a CPU-heavy task in the background; verify the bubble's frame queue drops old frames rather than building latency.
- [ ] **Clean shutdown:** Exit via tray; verify in Task Manager that no `python.exe` or `UltimateZoom.exe` process lingers.

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| WS_EX_TRANSPARENT killed buttons (Pitfall 1) | LOW | Remove `WS_EX_TRANSPARENT`; implement `WM_NCHITTEST` subclass. 2-3 hours. |
| WndProc GC crash (Pitfall 2) | LOW | Store `_wndproc_ref` on self. 10 minutes once diagnosed. |
| Touch doesn't pass through (Pitfall 3) | MEDIUM | Add `WS_EX_NOACTIVATE`; verify `WM_NCHITTEST` returns `HTTRANSPARENT`; test on real touch hardware. 2-4 hours. |
| Self-capture loop (Pitfall 4) | LOW | Verify `WS_EX_LAYERED` is still set; trust the BitBlt exclusion. Usually a 5-minute fix. |
| DPI coordinate bug (Pitfall 5) | LOW | Add `SetProcessDpiAwarenessContext(-4)` as first line of main. 1 hour including cross-scale testing. |
| HRGN double-free crash (Pitfall 6) | LOW | Remove `DeleteObject` on success path. 15 minutes. |
| Shape not updating on resize (Pitfall 7) | LOW | Add `<Configure>` binding → `apply_shape`. 30 minutes. |
| pystray thread deadlock (Pitfall 8) | MEDIUM | Refactor: pystray on daemon thread; all Tk access via `root.after(0, ...)`. 2-4 hours if you started single-threaded. |
| Ctrl+Z Cornerstone conflict (Pitfall 9) | HIGH (if discovered post-deploy) | Ship a config.json patch to the clinic; document change; retrain user. Days of lost productivity if it blocks their workflow. |
| Hotkey silent failure (Pitfall 10) | LOW | Add MessageBox on registration failure; add single-instance mutex. 1-2 hours. |
| Missing PyInstaller hidden imports (Pitfall 11) | LOW | Add to `.spec`, rebuild. 15 minutes per missing import, BUT requires a redeploy to the clinic PC. |
| PhotoImage memory leak (Pitfall 12) | MEDIUM | Refactor to `.paste()` pattern; verify memory is stable. 2-4 hours including the 30-min memory test. |
| config.json corruption (Pitfall 13) | LOW (if caught early), HIGH (if deployed) | Implement atomic write; add read-fallback to defaults; ship the fix. Hours + redeploy. |
| Tk "different apartment" from capture thread (Pitfall 14) | MEDIUM | Refactor to queue-based frame marshaling. 2-3 hours. |
| overrideredirect + taskbar/Alt-Tab issues (Pitfall 15) | LOW | Explicit `WS_EX_TOOLWINDOW` via pywin32 after `overrideredirect`. 30 minutes. |

---

## Pitfall-to-Phase Mapping

This is the key input for the roadmap — which phase must address each pitfall.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. WS_EX_TRANSPARENT whole-window | Phase 2 (overlay window) | Drag works + middle click-through works SIMULTANEOUSLY |
| 2. WndProc GC crash | Phase 2 (overlay window) | Idle the app with mouse hover for 2 minutes — no crash |
| 3. Touch vs mouse click-through | Phase 2 + Phase 3 (verified on real touch) | Finger tap on middle zone passes to underlying app |
| 4. mss self-capture | Phase 3 (capture loop) | Save one frame to disk; visually inspect for bubble absence |
| 5. DPI awareness | Phase 1 (scaffolding) — first line of main.py | Tested at 100% / 125% / 150% scale |
| 6. HRGN double-free | Phase 4 (shape masking) | 50 rapid resizes — no crash |
| 7. Shape update on resize | Phase 4 (shape masking) | `<Configure>` binding re-applies shape on size change |
| 8. pystray thread marshaling | Phase 5 (tray icon) | Tray menu items work without "different apartment" error |
| 9. Ctrl+Z Cornerstone conflict | Phase 6 (hotkey) | Hotkey is configurable; end-user confirms before clinic deploy |
| 10. Hotkey registration failure | Phase 6 (hotkey) | Launch app twice — second sees visible error; single-instance mutex prevents it |
| 11. PyInstaller hidden imports | Phase 8 (build & package) | `.exe` runs on a clean VM with no Python |
| 12. PhotoImage memory leak | Phase 3 (capture loop) | Memory stable after 30 minutes continuous use |
| 13. config.json atomic write | Phase 7 (persistence) | Kill mid-save in a loop — file is always valid JSON |
| 14. Capture thread → Tk marshaling | Phase 3 (capture loop) | Queue-based; no `RuntimeError` under load |
| 15. overrideredirect + taskbar | Phase 2 (overlay window) | No taskbar entry, no Alt+Tab entry, stays topmost |

**Phase-level summary:**
- **Phase 1 (scaffolding):** Pitfall 5 (DPI) — set it first thing.
- **Phase 2 (overlay window):** Pitfalls 1, 2, 3 (partial), 15 — all window-styling gotchas.
- **Phase 3 (capture loop):** Pitfalls 3 (verify), 4, 12, 14 — all capture and threading gotchas.
- **Phase 4 (shape masking):** Pitfalls 6, 7 — all SetWindowRgn gotchas.
- **Phase 5 (tray icon):** Pitfall 8 — threading model.
- **Phase 6 (hotkey):** Pitfalls 9, 10 — hotkey and conflict.
- **Phase 7 (persistence):** Pitfall 13 — atomic config writes.
- **Phase 8 (build & package):** Pitfall 11 — PyInstaller hidden imports.

Phases 2, 3, and 6 carry the highest pitfall density and will benefit most from deeper research flags in the roadmap.

---

## Sources

### Microsoft Learn (authoritative, HIGH confidence)

- [SetWindowRgn function (winuser.h)](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowrgn) — HRGN ownership transfer documentation
- [SetWindowLongPtrA function (winuser.h)](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowlongptra) — WndProc subclassing rules
- [Using Window Procedures - Win32 apps](https://learn.microsoft.com/en-us/windows/win32/winmsg/using-window-procedures) — WndProc lifetime and subclassing pitfalls
- [RegisterHotKey function (winuser.h)](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey) — hotkey registration semantics
- [UpdateLayeredWindow function (winuser.h)](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-updatelayeredwindow) — layered window compositing behavior
- [How to stop WS_EX_LAYERED causing mouse clicks to go through (Microsoft Q&A)](https://learn.microsoft.com/en-us/answers/questions/1096479/how-to-stop-ws-ex-layered-causing-mouse-clicks-to) — click-through interaction

### Python / library issue trackers (HIGH confidence)

- [Tkinter Memory Leak updating Label images on Windows (CPython #124364)](https://github.com/python/cpython/issues/124364) — Windows-specific Tk memory leak
- [Issue 45681: tkinter breaks on high resolution screen after SetProcessDPIAware (Python tracker)](https://bugs.python.org/issue45681) — DPI + tkinter interaction
- [Issue 26698: Tk DPI awareness (Python tracker)](https://bugs.python.org/issue26698) — tkinter DPI unawareness
- [SetProcessDpiAwareness issue (BoboTiG/python-mss #184)](https://github.com/BoboTiG/python-mss/issues/184) — mss DPI interaction
- [pystray Icon.run() threading (moses-palmer/pystray #94, #63)](https://github.com/moses-palmer/pystray/issues/94) — pystray threading model
- [pystray usage docs (0.19.5)](https://pystray.readthedocs.io/en/latest/usage.html) — Icon.run() main thread requirement
- [PyInstaller pywin32 hidden imports (pyinstaller #7255, #8543, #4818)](https://github.com/pyinstaller/pyinstaller/issues/7255) — PyInstaller + pywin32 failure modes

### Community references (MEDIUM confidence — verified against authoritative sources above)

- [Transparent Click-thru windows — Sagui Itay's Blog](https://www.saguiitay.com/transparent-click-thru-windows/) — WS_EX_TRANSPARENT + WS_EX_LAYERED pattern
- [Capturing the screen image with BitBlt (Microsoft Learn archive)](https://learn.microsoft.com/en-us/archive/msdn-technet-forums/b2afcb52-431c-4c95-964a-a9698f49b5de) — BitBlt + layered window exclusion on Win8+
- [Layered Windows summary gist (retorillo/3a12e0f7...)](https://gist.github.com/retorillo/3a12e0f7e6ae3d49771f2919608f8498) — layered window behavior on Win10/11
- [Python Tkinter Garbage Collection best practices (iifx.dev)](https://iifx.dev/en/articles/460151305/python-tkinter-garbage-collection-best-practices-for-canvas-images-with-pil) — ImageTk.PhotoImage GC patterns
- [Crash-safe JSON atomic writes (dev.to / constanta)](https://dev.to/constanta/crash-safe-json-at-scale-atomic-writes-recovery-without-a-db-3aic) — atomic write pattern
- [python-atomicwrites (untitaker/python-atomicwrites)](https://github.com/untitaker/python-atomicwrites) — reference implementation
- [How to resolve hotkey conflicts in Windows (Tom's Hardware)](https://www.tomshardware.com/software/windows/how-to-resolve-hotkey-conflicts-in-windows) — hotkey conflict real-world examples
- [Tkinter overrideredirect Windows taskbar issues (copyprogramming.com)](https://copyprogramming.com/howto/tkinter-overridedirect-minimizing-and-windows-task-bar-issues) — overrideredirect + taskbar workarounds
- [mss project on PyPI](https://pypi.org/project/mss/) — mss documentation and version history
- [MSS API docs (python-mss.readthedocs.io)](https://python-mss.readthedocs.io/api.html) — mss usage reference

### PROJECT.md and STACK.md (internal context)

- `.planning/PROJECT.md` — requirements, constraints, and key decisions (Ctrl+Z, WM_NCHITTEST, SetWindowRgn, PyInstaller single-file, config.json location)
- `.planning/research/STACK.md` — stack-specific gotchas already documented in the pipeline, WndProc ref, pystray hidden imports, hotkey thread model

---

*Pitfalls research for: Windows 11 desktop magnifier bubble app (Python + tkinter + pywin32 + mss + pystray)*
*Researched: 2026-04-10*
