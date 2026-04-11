# Stack Research — Magnifier Bubble (Ultimate Zoom)

**Domain:** Windows 11 desktop overlay / real-time screen magnifier in Python
**Researched:** 2026-04-10
**Target runtime:** Python 3.11 on Windows 11 (Windows 10 acceptable fallback)
**Overall confidence:** HIGH

---

## TL;DR — The Stack

| Role | Library | Pinned Version | Confidence |
|------|---------|---------------|------------|
| Screen capture | `mss` | `10.1.0` | HIGH |
| Win32 bindings | `pywin32` | `311` | HIGH |
| Image resize + Tk interop | `Pillow` | `11.3.0` | HIGH |
| Numeric array glue (mss → Pillow) | `numpy` | `2.2.6` | HIGH |
| System tray icon | `pystray` | `0.19.5` | MEDIUM |
| Global hotkey (Ctrl+Z) | **ctypes + `user32.RegisterHotKey`** (no third-party lib) | stdlib | HIGH |
| UI framework | **tkinter** (stdlib) | stdlib (3.11) | HIGH |
| Build to single .exe | `PyInstaller` | `6.11.1` | HIGH |

All dependencies are pip-installable, have Windows wheels, and are confirmed compatible with Python 3.11 on Windows 11.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **Python** | `3.11.9` (recommended) | Runtime | Python 3.11.9 is the last 3.11 release that shipped binary installers from python.org and remains the most battle-tested "stable + widely deployed" CPython for PyInstaller builds. 3.11 is now security-fixes-only, which is acceptable for a local-clinic single-purpose app, and avoids the churn of 3.12/3.13 wheel availability for older dependencies. |
| **tkinter** | stdlib (3.11) | Overlay window + widgets | Shipped with Python, zero install footprint on the clinic PC, and its window handle (`root.winfo_id()` → parent via `GetParent`) is fully usable with every pywin32 call this app needs (`SetWindowLongPtr`, `SetLayeredWindowAttributes`, `SetWindowRgn`). Qt/PySide adds ~50 MB to the .exe and is explicitly out of scope per PROJECT.md. |
| **mss** | `10.1.0` (Aug 16, 2025) | Real-time screen capture | mss uses the Windows GDI `BitBlt` path via pure ctypes — no C extension to compile, no external DLL beyond what Windows already ships. Benchmarks consistently show mss at ~3 ms/frame on a single region, easily clearing the 30 fps (33 ms budget) requirement. Pinned at 10.1.0 because it is current, Python 3.9–3.14 compatible, and has no known regressions. PROJECT.md explicitly mandates mss and forbids `PIL.ImageGrab` in the main loop. |
| **pywin32** | `311` (Jul 14, 2025) | Win32 API bindings | The canonical Python binding for `user32`/`gdi32`/`kernel32`. Release 311 has wheels for CPython 3.8–3.14 on win32, win_amd64, and win_arm64. Needed for: `win32gui.SetWindowLong`/`GetWindowLong` (extended style bits), `win32gui.SetLayeredWindowAttributes` (alpha), `win32gui.SetWindowRgn` + `CreateRoundRectRgn`/`CreateEllipticRgn`/`CreateRectRgn` (shape masking), and `win32con` constants. |
| **Pillow** | `11.3.0` (Jul 1, 2025) | Image resize + `ImageTk.PhotoImage` bridge | The only pragmatic way to get a mss frame into a Tk widget: `Image.frombytes("RGB", size, raw) → .resize((w,h), Image.Resampling.BILINEAR) → ImageTk.PhotoImage`. Pin to 11.3.0 (not 12.x) because 11.3.0 is the last in the 11.x line, still supports Python 3.10+, and avoids the `fromarray()` mode-parameter deprecation churn introduced in 11.3 and partially reverted in 12.0. 11.3.0 is stable, widely cached on mirrors, and has no open CVEs affecting our usage. |
| **numpy** | `2.2.6` | Zero-copy frame handling | mss returns a `mss.screenshot.ScreenShot` with a `.raw` bytes buffer; `numpy.frombuffer(..., dtype=uint8).reshape(h, w, 4)` is the fastest path to a BGRA array, which we then slice and hand to Pillow. Pin 2.2.6 (not 2.3+) because it still publishes cp311 wheels for win_amd64; NumPy 2.3+ dropped Python 3.10 but still supports 3.11. 2.2.6 is the conservative safe choice. |
| **pystray** | `0.19.5` (Sep 17, 2023) | System tray icon | The de facto tray library for Python on Windows. Uses a native Win32 NOTIFYICONDATA backend (no Qt dependency). Has not been released since 2023 but the Win32 tray API is itself frozen, so staleness is a non-issue. The known "No module named `pystray._win32`" PyInstaller error is solved by a one-line hidden-import in the `.spec` file (`hiddenimports=['pystray._win32']`). |
| **PyInstaller** | `6.11.1` | Single-file .exe build | PyInstaller 6.x has first-class hooks for `tkinter`, `pywin32`, `Pillow`, and `pystray`. Nuitka was considered (see alternatives below) and rejected for this project. Pin to 6.11.1 rather than the bleeding-edge 6.19.x because 6.3.0 introduced bootloader changes that triggered a wave of antivirus false-positives; the 6.11.x branch has had time to settle and receives bootloader rebuilds from newer releases. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none) | — | — | The core stack above is intentionally minimal. No `keyboard`, no `pynput`, no Qt, no OpenCV, no `dxcam`. Every additional dependency grows the PyInstaller output and the antivirus blast radius. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pip` (bundled with Python 3.11) | Install deps | Use `pip install -r requirements.txt` — pin everything. |
| `venv` (stdlib) | Isolate build environment | Always build the .exe from a clean venv — PyInstaller will otherwise pull in every package on `sys.path`, bloating the output and increasing AV false-positive risk. |
| PyInstaller (above) | Build .exe | Use a `.spec` file (not raw CLI flags) so hidden imports, icon, UAC manifest, and version resource can be checked into source control. |

---

## Installation

### requirements.txt (drop-in)

```txt
# Core runtime dependencies for Magnifier Bubble — Python 3.11 / Windows 11
mss==10.1.0
pywin32==311
Pillow==11.3.0
numpy==2.2.6
pystray==0.19.5

# Build-time only (optional separation into requirements-build.txt if desired)
pyinstaller==6.11.1
```

### Install commands

```bash
# From a clean Python 3.11 venv:
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Verify pywin32 post-install (writes pywintypes to system32 on some installs)
python .venv\Scripts\pywin32_postinstall.py -install
```

---

## Technical Decisions — Why Each Choice

### 1. Screen Capture: `mss` — CONFIRMED as specified

**Decision:** Use `mss==10.1.0`. Do not use `dxcam`, `bettercam`, `PIL.ImageGrab`, or `pyautogui.screenshot()`.

**Why mss:**
- **Speed:** ~3 ms per single-region capture on a modern PC — easily 300+ fps headroom before we touch pixels. The 30 fps floor in PROJECT.md is not the bottleneck; resize and Tk PhotoImage update are.
- **Zero native deps:** Pure Python + ctypes over `gdi32.BitBlt`. No DirectX runtime required, no VC++ runtime drama, no DXGI quirks on RDP/screen-share sessions. Idexx Cornerstone on a clinic touchscreen may not have reliable DXGI behavior; GDI always works.
- **Deterministic region capture:** `sct.grab({"left": x, "top": y, "width": w, "height": h})` is the exact API we need — capture only the rectangle under the bubble, never the full desktop.
- **PyInstaller-friendly:** Pure Python + ctypes = no hidden imports, no binary extraction surprises.

**Why NOT DXcam / BetterCam** (considered and rejected):
- DXcam and BetterCam are 240+ fps and faster than mss, but they use the DXGI Desktop Duplication API, which has real-world failure modes: RDP sessions, some remote-admin tools, certain display-driver configurations, and multi-monitor DPI edge cases. For a clinic PC running alongside a legacy LOB application (Cornerstone), "always works" beats "sometimes faster."
- DXcam adds a DirectX 11 runtime dependency path that complicates the PyInstaller build.
- We don't need 240 fps. We need a reliable 30.

**Why NOT `PIL.ImageGrab`:**
- Explicitly forbidden in PROJECT.md main loop (Constraints section).
- On Windows, `PIL.ImageGrab.grab()` is a thin wrapper over `CreateDCFromHandle`/`BitBlt` but with significant per-call overhead from Python-level object construction, so it caps well below 30 fps at any non-trivial resolution.

**Confidence:** HIGH. mss version and behavior verified against PyPI and GitHub, Aug 2025 release.

---

### 2. Always-on-top, no-taskbar, click-through overlay window

**Decision:** `tkinter.Toplevel` + pywin32 extended window styles + a `WM_NCHITTEST` subclass.

**Specifically:**

```
# Pseudocode — the exact win32 calls
hwnd = GetParent(root.winfo_id())   # tk gives child; we need the toplevel
# Always on top + no taskbar:
root.overrideredirect(True)          # removes window chrome and taskbar entry
root.wm_attributes("-topmost", True) # topmost z-order
# Layered window (required before SetLayeredWindowAttributes works):
ex_style = GetWindowLong(hwnd, GWL_EXSTYLE)
SetWindowLong(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED | WS_EX_TOOLWINDOW)
# WS_EX_TOOLWINDOW: belt-and-suspenders no-taskbar (overrideredirect already hides it,
#     but WS_EX_TOOLWINDOW also keeps it out of Alt+Tab, which we want).
SetLayeredWindowAttributes(hwnd, colorkey, alpha, LWA_ALPHA)  # for semi-transparent strips
```

**Click-through strategy — the nuanced part:**

PROJECT.md specifies WS_EX_TRANSPARENT + WS_EX_LAYERED, AND a WM_NCHITTEST → HTTRANSPARENT approach for the middle zone specifically. These are NOT redundant — they target different layers of hit testing:

- **WS_EX_TRANSPARENT on the whole window** makes the *entire* window click-through. Good if the bubble were all-or-nothing, but it kills the drag bar and buttons.
- **WM_NCHITTEST → HTTRANSPARENT for the middle region only** is Windows telling the hit-test system "this pixel doesn't belong to me; ask the next window down." This is per-pixel/per-region and preserves the drag bar and button strip.

**Recommendation:** Use WM_NCHITTEST subclassing (via `win32gui.SetWindowLong` with `GWL_WNDPROC` + a Python callback) to return `HTTRANSPARENT` when the cursor is in the magnified-content rectangle, `HTCAPTION` when in the drag bar (gives free OS-level dragging!), and `HTCLIENT` elsewhere. This matches the Key Decisions table in PROJECT.md exactly.

**Why this over Qt:** Qt's `Qt.WA_TransparentForMouseEvents` is whole-widget, not per-region. You'd have to build a composite of multiple top-level windows, which is uglier than the one-Tk-window + WM_NCHITTEST approach. And Qt adds ~50 MB to the .exe.

**Watch out:**
- `overrideredirect(True)` on tkinter needs to happen BEFORE the window is mapped, or you have to `withdraw()` → flip → `deiconify()` — otherwise the taskbar entry flashes.
- On Windows 11, layered windows interact oddly with DWM composition; test that the border renders at the edge of the window region, not clipped.
- Subclassing WndProc from Python has a real gotcha: the Python callback must keep a reference or Python will GC it and the app will crash. Store it on `self._wndproc_ref`.

**Confidence:** HIGH. Verified against Microsoft Learn docs for WM_NCHITTEST and RegisterHotKey, plus multiple community references and the jfd02/tkinter-transparent-window reference implementation.

---

### 3. System tray icon: `pystray`

**Decision:** `pystray==0.19.5`.

**Why pystray:**
- De-facto standard for Python + Windows tray.
- Pure Python Win32 backend (no Qt, no Gtk).
- Simple menu API covering everything PROJECT.md asks for (Show/Hide, Always on Top toggle, Exit).
- Runs on a background thread; `Icon.run()` blocks that thread while the main thread runs Tk's mainloop.

**Known gotcha (MUST be addressed at build time):**
- PyInstaller does not auto-detect pystray's backend because pystray picks it at runtime via `importlib`. Add to your `.spec`:
  ```python
  hiddenimports=['pystray._win32', 'PIL._tkinter_finder']
  ```
- This is a 30-second fix, not a reason to avoid pystray.

**Alternatives considered and rejected:**
- `infi.systray` — dead since 2020, fewer features.
- `pywebview` / custom Qt tray — massive over-engineering.
- Rolling our own Shell_NotifyIcon via ctypes — possible but adds ~200 lines of Win32 plumbing we'd have to maintain.

**Confidence:** MEDIUM on the library itself (2023 release, no recent updates), HIGH on its suitability for this task because the Shell_NotifyIcon API itself has not meaningfully changed since Windows Vista and won't on Windows 11.

---

### 4. Global hotkey (Ctrl+Z even when Cornerstone has focus)

**Decision:** Use **ctypes + `user32.RegisterHotKey`** directly. Do NOT use the `keyboard` library. Do NOT use `pynput` for this purpose.

**The critical finding:**
- **`keyboard` (boppreh/keyboard) is ARCHIVED and UNMAINTAINED** as of February 2026. The README explicitly says "This project is currently unmaintained." The repo is now read-only on GitHub with 400+ open issues. Shipping a clinic deployment on an archived library is a liability.
- **`pynput` has documented Windows 11 global-hotkey reliability issues** (see pyinstaller discussion #9255 where users report `GlobalHotKeys` not firing on Win11). pynput's hotkey support is built on top of a low-level WH_KEYBOARD_LL hook, which Windows can silently throttle or skip for non-foreground apps under certain security contexts.
- **`RegisterHotKey` is the OS-blessed mechanism** for system-wide hotkeys. It fires a `WM_HOTKEY` message into the target thread's message queue regardless of which app has foreground. This is what AutoHotKey, Windows' own Win+key shortcuts, and every major professional tool uses.

**Does RegisterHotKey require admin?**
- **No, not for Ctrl+Z.** RegisterHotKey only fails for (a) already-registered combinations and (b) certain OS-reserved keys (Win+L, etc.). Ctrl+Z is not reserved globally — it's only "reserved" *within* apps that intercept it (undo in text boxes). RegisterHotKey operates at a higher layer than per-app keyboard handlers, so Cornerstone's local Ctrl+Z handling and our global Ctrl+Z registration do not conflict in a technical sense *but they do in a user-experience sense*: if the user is typing in a Cornerstone field and presses Ctrl+Z, our hotkey will win and undo will not reach Cornerstone.
- **UX implication that must be noted in the roadmap PITFALLS:** Consider a less-conflict-prone combo (Ctrl+Alt+Z, Ctrl+Shift+Z, or a function key) OR confirm with the end user that Cornerstone's Ctrl+Z is not needed during magnifier use. PROJECT.md specifies Ctrl+Z, so we implement Ctrl+Z as the v1 default but make it configurable in config.json.

**Implementation sketch:**

```python
# In a dedicated hotkey thread (not the Tk mainloop):
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000      # Prevents auto-repeat firing WM_HOTKEY multiple times
VK_Z = 0x5A
HOTKEY_ID = 1

if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_NOREPEAT, VK_Z):
    # Log and fall back — the combo is taken
    ...

msg = wintypes.MSG()
while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
    if msg.message == 0x0312:  # WM_HOTKEY
        if msg.wParam == HOTKEY_ID:
            # Signal the Tk thread (queue.Queue or event) to toggle visibility
            ...
    user32.TranslateMessage(ctypes.byref(msg))
    user32.DispatchMessageW(ctypes.byref(msg))

# On shutdown:
user32.UnregisterHotKey(None, HOTKEY_ID)
```

**Why this lives in a thread, not Tk's mainloop:** `GetMessageW` blocks. You cannot block Tk's mainloop. Run this in a `threading.Thread(daemon=True)` and communicate to Tk via `root.after(0, callback)` or a `queue.Queue`.

**Confidence:** HIGH. Verified against Microsoft Learn `RegisterHotKey` docs (last updated 2024-06), and the code pattern is the standard Win32 idiom.

---

### 5. Shape masking (circle, rounded rect, rect)

**Decision:** `win32gui.SetWindowRgn` + one of `CreateEllipticRgn` / `CreateRoundRectRgn` / `CreateRectRgn`.

**Implementation sketch:**

```python
import win32gui, win32con

def apply_shape(hwnd, w, h, shape):
    if shape == "circle":
        rgn = win32gui.CreateEllipticRgn(0, 0, w, h)
    elif shape == "rounded":
        rgn = win32gui.CreateRoundRectRgn(0, 0, w, h, 40, 40)  # 40px radius
    else:  # "rect"
        rgn = win32gui.CreateRectRgn(0, 0, w, h)
    # CRITICAL: after SetWindowRgn succeeds, the system owns `rgn`. Do NOT
    # call DeleteObject(rgn) yourself — Windows will free it.
    win32gui.SetWindowRgn(hwnd, rgn, True)
```

**Critical gotchas (verified against Microsoft Learn SetWindowRgn docs):**
1. **Ownership transfer:** After a successful `SetWindowRgn`, the OS owns the region handle. Do not `DeleteObject` it or call any other function on it. Double-freeing crashes the process. This is a very common Win32 mistake.
2. **Coordinate system:** Region coordinates are relative to the *window's* upper-left corner, not the client area, not the screen.
3. **Call after resize:** Every time the bubble is resized, the old region is invalidated (actually, replaced — do not try to reuse it). Call `SetWindowRgn` again with a freshly created region.
4. **Interaction with layered windows:** `SetWindowRgn` works with layered windows (WS_EX_LAYERED) on Windows 8+. The documented `req.apiset` for SetWindowRgn is `ext-ms-win-ntuser-draw-l1-1-0` introduced in Windows 8, so we're fine on Windows 10/11.
5. **Click-through + region:** A window region also clips hit testing — clicks outside the region pass through naturally. This means WS_EX_TRANSPARENT is NOT needed for the "corners of the bounding box" click-through; only for the middle-content click-through (where the region still covers but we want touches to pass through).

**Why NOT pure-tkinter canvas-drawn shapes:**
- A tk Canvas can *draw* a circle, but the *window* remains rectangular and blocks clicks in the corners. You'd be able to see-through but not click-through. SetWindowRgn solves both simultaneously.

**Confidence:** HIGH. Verified against Microsoft Learn authoritative docs.

---

### 6. PyInstaller vs Nuitka for single-exe compilation

**Decision:** PyInstaller 6.11.1.

**Why PyInstaller over Nuitka for THIS project:**

| Criterion | PyInstaller | Nuitka | Winner for us |
|-----------|-------------|--------|----------------|
| Build time | Seconds to ~1 min | 5–30+ min for tkinter+pillow+pywin32 | **PyInstaller** — dev velocity |
| Output size (onefile) | ~35–50 MB for this stack | ~40–70 MB | **PyInstaller** (marginally) |
| Runtime perf | Identical to CPython | 2–4× faster for CPU-bound loops | Neutral — our bottleneck is GDI BitBlt, not Python |
| tkinter support | Built-in hook, zero config | Needs `--plugin-enable=tk-inter` | **PyInstaller** |
| pywin32 support | Built-in hook handles pywin32_system32 PATH | Works but requires manual plugins | **PyInstaller** |
| Pillow support | Built-in hook | Needs plugin | **PyInstaller** |
| pystray support | Works with one hidden-import line | Same fix needed | Neutral |
| Antivirus false positives | Real problem on some bootloader versions (6.3.0 was bad) | Fewer false positives because it's actual C code | **Nuitka edge**, mitigated by pinning 6.11.x |
| Learning curve | Low | Higher — C toolchain required | **PyInstaller** |
| Single-file output | `--onefile` | `--onefile` | Tie |

**The call:** PyInstaller. Our runtime perf bottleneck is `BitBlt` + Pillow resize, neither of which benefit from Nuitka's AOT compilation. Nuitka's hour-long rebuild-the-world cycle on every dependency change is painful during development. PyInstaller's AV false-positive issue is real but fully mitigated by (a) pinning to 6.11.1 which has a well-baked-in bootloader, (b) considering code signing before clinic deployment, and (c) adding the EXE to the clinic's AV allowlist once (a one-time step for a fixed-location install).

**Specific PyInstaller config recommendations:**
- Use a `.spec` file, not raw CLI. Check it into git.
- `console=False` (GUI app, no console window).
- Bundle a proper icon (`icon='assets/bubble.ico'`).
- Set a version resource via `version_file=...` so Windows Properties → Details shows sensible values.
- `hiddenimports=['pystray._win32', 'PIL._tkinter_finder']`.
- `upx=False` — UPX compression is one of the single biggest triggers for AV false positives.
- `uac_admin=False` — we do NOT need admin for RegisterHotKey on Ctrl+Z.

**Confidence:** HIGH.

---

## Pipeline: mss → Tk PhotoImage (the hot loop)

This is the 30 fps path, and it's where most of this app's runtime lives. The exact chain:

```python
# Per frame, at ~33 ms budget:
import mss, numpy as np
from PIL import Image, ImageTk

with mss.mss() as sct:
    shot = sct.grab({"left": x, "top": y, "width": w, "height": h})  # ~3 ms
    # shot.raw is BGRA bytes; shot.size is (w, h)
    img = Image.frombytes("RGB", shot.size, shot.rgb)                 # ~2 ms
    img = img.resize((target_w, target_h), Image.Resampling.BILINEAR) # ~5-8 ms
    photo = ImageTk.PhotoImage(img)                                   # ~3 ms
    canvas.itemconfig(img_item, image=photo)
    canvas.image = photo   # PREVENT GC — ImageTk.PhotoImage will vanish otherwise
```

**Critical performance notes:**
- **Use `Image.Resampling.BILINEAR`, not LANCZOS** for the main loop. LANCZOS is ~3–5× slower than BILINEAR and for 1.5×–6× *upscaling* (we are making things BIGGER, not smaller), the quality difference is minimal because there's no high-frequency detail to preserve. LANCZOS shines for downscaling; for upscaling, BICUBIC or BILINEAR is plenty. Bilinear keeps us comfortably inside the 33 ms budget. Consider making this a config option if the user wants sharper (but slower) LANCZOS for stationary reading.
- **Reuse the `mss.mss()` instance** across frames. Do NOT create it inside the loop — its `__init__` allocates device contexts. Create it once on the capture thread and reuse.
- **Do NOT keep the mss context manager in the Tk mainloop.** Capture on a worker thread, push frames to Tk via `root.after(0, ...)` or `queue.Queue`.
- **Retain the PhotoImage reference.** `canvas.image = photo` (or `label.image = photo`) is the idiomatic "prevent Python from garbage-collecting the image I just assigned."
- **Consider using `shot.rgb`** (mss provides this pre-converted) rather than manually converting BGRA → RGB with numpy slicing, unless profiling shows `shot.rgb` is slow for your region size.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| **mss** | `dxcam` / `bettercam` | If target is a gaming PC with reliable DXGI and you need 200+ fps. Not us. |
| **mss** | `PIL.ImageGrab` | Never for this project — explicitly forbidden in PROJECT.md main loop. |
| **tkinter + pywin32** | PyQt6 / PySide6 | If you need native macOS/Linux support or advanced widgets. Adds 50+ MB. Not us. |
| **tkinter + pywin32** | wxPython | If you need native-looking controls. Adds dependencies and complicates PyInstaller. Not us. |
| **ctypes RegisterHotKey** | `keyboard` library | Never — archived/unmaintained as of Feb 2026. |
| **ctypes RegisterHotKey** | `pynput.keyboard.GlobalHotKeys` | If you also need per-key event hooks (we don't). Has documented Windows 11 reliability issues. |
| **ctypes RegisterHotKey** | `global-hotkeys` (the pypi pkg) | It's basically a thin wrapper over RegisterHotKey. Rolling our own saves a dependency. |
| **pystray** | `infi.systray` | Never — unmaintained since 2020. |
| **pystray** | Qt.QSystemTrayIcon | Only if already on Qt. We're not. |
| **pystray** | Custom `Shell_NotifyIcon` ctypes wrapper | Only if pystray ever breaks on a future Windows update. |
| **PyInstaller** | Nuitka | If you need 2–4× runtime speedup (CPU-bound, not us) or want to reduce AV false positives. |
| **PyInstaller** | cx_Freeze | Generally inferior to PyInstaller now; fewer hooks for Pillow/pywin32. |
| **PyInstaller** | PyOxidizer | More complex setup, less mature tkinter support. |
| **Pillow 11.3.0** | Pillow 12.2.0 | If Python 3.11 is not a constraint. 12.x requires Python ≥3.10 and has API shifts around `fromarray()` mode parameter. 11.3.0 is safer. |
| **numpy 2.2.6** | numpy 2.4.4 | If wheels for cp311-win_amd64 remain available. 2.2.6 is the conservative pin. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `keyboard` (boppreh/keyboard) | Archived Feb 2026, unmaintained, 400+ open issues, Windows 11 hook reliability questionable | **ctypes + `user32.RegisterHotKey`** directly |
| `PIL.ImageGrab` in the main loop | Explicitly forbidden in PROJECT.md; ~10× slower than mss for per-frame capture; can't hit 30 fps at non-trivial regions | **mss** |
| `pyautogui.screenshot()` | Built on PIL.ImageGrab, same performance problem, plus adds pyautogui's other deps | **mss** |
| `dxcam` | Desktop Duplication API has failure modes on RDP / non-standard displays / multi-monitor edge cases; clinic environment unknown | **mss** (reliability > peak fps) |
| Qt / PySide6 / PyQt6 | Adds ~50 MB to the .exe; explicitly out of scope per PROJECT.md | **tkinter** (stdlib) |
| LANCZOS resampling in the main loop | 3–5× slower than BILINEAR; quality difference negligible for upscaling | **`Image.Resampling.BILINEAR`** |
| PyInstaller `--onefile` with UPX compression | UPX is a top AV false-positive trigger on Windows | PyInstaller with `upx=False` in `.spec` |
| PyInstaller 6.3.0–6.5.x | Known bad AV false-positive cluster from bootloader changes | **PyInstaller 6.11.1** (conservative pin) |
| `overrideredirect(True)` after window is mapped | Causes a visible flash of taskbar entry | Call it BEFORE `mainloop()`, or `withdraw()` → flip → `deiconify()` |
| Deleting the HRGN after `SetWindowRgn` | System owns it; double-free crashes the process | Let Windows free it; never call `DeleteObject` on that handle |
| Reusing a single `mss.mss()` across threads | mss contexts are not documented as thread-safe | Create one instance per thread, or use a lock |
| `keyboard.add_hotkey` with `suppress=True` | Requires admin on Windows and can break the clinic user's workflow | Don't intercept; only listen. RegisterHotKey doesn't need admin. |

---

## Version Compatibility Matrix

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `mss==10.1.0` | Python 3.9–3.14, all Windows | No compile step, pure ctypes. |
| `pywin32==311` | Python 3.8–3.14, Windows only | Requires `pywin32_postinstall.py -install` on first install (PyInstaller handles this automatically via its hook). |
| `Pillow==11.3.0` | Python 3.10–3.14 | Last of 11.x. 12.x changes `fromarray()` semantics; 11.3.0 safer. |
| `numpy==2.2.6` | Python 3.11–3.14, cp311 wheels exist | 2.3+ may drop cp311 wheels faster; 2.2.6 is the conservative pin. |
| `pystray==0.19.5` | Python 3.4–3.13 (not bumped since 2023 but still works on 3.11/3.12/3.13) | Requires `hiddenimports=['pystray._win32']` in PyInstaller `.spec`. |
| `PyInstaller==6.11.1` | Python 3.8–3.13 | Avoid 6.3.0–6.5.x due to AV false positives. 6.11.1 has a well-seasoned bootloader. |

**Known-good combination:** All seven of the above pins together on Python 3.11.9 have no known conflicts. The stack is small and the interfaces between them (mss→numpy→Pillow→ImageTk→tkinter; tkinter→pywin32; ctypes→user32) are all stable.

**Watch out for these specific pairs:**
- `pywin32` + PyInstaller onefile: PyInstaller's pywin32 hook rewrites `sys.path` to inject `pywin32_system32`. If you see "DLL load failed" for `pywintypes311.dll`, you didn't run `pywin32_postinstall.py` in the build venv. Always run it after `pip install`.
- `pystray` + PyInstaller: Add `pystray._win32` and `PIL._tkinter_finder` to `hiddenimports`.
- `Pillow` + PyInstaller: Usually auto-detected, but on Python 3.11 + Pillow 11.x you may need `PIL._tkinter_finder` as a hidden import specifically for the ImageTk bridge.

---

## Stack Patterns by Variant

**If target is Windows 10 (fallback scenario):**
- Same stack works unchanged. `SetWindowRgn` is documented as available since Windows 2000. Layered windows since Windows 2000. WS_EX_TRANSPARENT since XP. No version-specific code needed.

**If future ask: Python 3.12 instead of 3.11:**
- Bump `numpy` to 2.4.4, keep the rest. All listed versions have cp312 wheels. PyInstaller 6.11.1 supports 3.12.

**If future ask: sub-pixel scrolling or OCR:**
- Add `opencv-python-headless` for INTER_CUBIC / INTER_AREA resampling (faster than Pillow on some machines) or `tesseract`/`pytesseract`. Not for MVP.

**If PyInstaller false positives become intolerable on the clinic AV:**
- Migrate to Nuitka `--standalone --onefile --enable-plugin=tk-inter`. Accept the longer build times. All the application code remains unchanged.

---

## Sources

### Authoritative (HIGH confidence)
- [PyPI: mss 10.1.0](https://pypi.org/project/mss/) — version, Python compat, release date (2025-08-16)
- [PyPI: pywin32 311](https://pypi.org/project/pywin32/) — version, Python compat, release date (2025-07-14)
- [PyPI: Pillow](https://pypi.org/project/pillow/) — version 12.2.0 current; 11.3.0 still supported
- [PyPI: pystray](https://pypi.org/project/pystray/) — version 0.19.5, 2023-09-17 release
- [PyPI: PyInstaller](https://pypi.org/project/pyinstaller/) — version 6.19.0 current; 6.11.1 pinned
- [Microsoft Learn: RegisterHotKey function](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey) — authoritative spec for MOD_CONTROL, MOD_NOREPEAT, WM_HOTKEY
- [Microsoft Learn: SetWindowRgn function](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowrgn) — region ownership semantics, coordinate system
- [Microsoft Learn: WM_NCHITTEST message](https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-nchittest) — HTTRANSPARENT, HTCAPTION semantics
- [Python.org: Python 3.11.9 release](https://www.python.org/downloads/release/python-3119/) — last 3.11 with binary installers
- [GitHub: boppreh/keyboard](https://github.com/boppreh/keyboard) — confirmed archived February 2026, README explicitly states unmaintained

### Reference implementations (MEDIUM confidence, verified patterns)
- [GitHub: jfd02/tkinter-transparent-window](https://github.com/jfd02/tkinter-transparent-window) — working tkinter + pywin32 click-through reference
- [GitHub: moses-palmer/pystray](https://github.com/moses-palmer/pystray) — pystray source and issue tracker
- [PyInstaller issue #7967](https://github.com/pyinstaller/pyinstaller/issues/7967) — 6.0.0 build failures
- [PyInstaller discussion #8207](https://github.com/orgs/pyinstaller/discussions/8207) — 6.3.0 AV false positives
- [PyInstaller issue #8164](https://github.com/pyinstaller/pyinstaller/issues/8164) — VirusTotal false positives above 5.13.2
- [PyInstaller discussion #9255](https://github.com/orgs/pyinstaller/discussions/9255) — pynput global hotkeys failing on Windows 11
- [pystray issue #55](https://github.com/moses-palmer/pystray/issues/55) — pystray._win32 hidden import fix for PyInstaller

### Context (LOWER confidence, used for context not claims)
- [KRRT7: Nuitka vs PyInstaller](https://krrt7.dev/en/blog/nuitka-vs-pyinstaller) — build-time and size comparisons
- [AhmedSyntax: 2026 PyInstaller vs cx_Freeze vs Nuitka](https://ahmedsyntax.com/2026-comparison-pyinstaller-vs-cx-freeze-vs-nui/) — 2026-current comparison
- [pynput PyPI](https://pypi.org/project/pynput/) — 1.8.1 release date
- [Pillow 11.3.0 release notes](https://pillow.readthedocs.io/en/stable/releasenotes/11.3.0.html) — fromarray mode deprecation context

---

## Confidence Summary

| Decision | Confidence | Why |
|----------|-----------|-----|
| Use mss 10.1.0 | HIGH | Verified on PyPI, matches spec, well-benchmarked for this use case |
| Use pywin32 311 | HIGH | Verified on PyPI, latest stable, wheels for Py 3.11 confirmed |
| Use tkinter (stdlib) | HIGH | Explicit spec requirement, zero install cost |
| Use Pillow 11.3.0 | HIGH | Verified on PyPI, conservative over 12.x, API known stable |
| Use numpy 2.2.6 | MEDIUM-HIGH | Conservative pin; 2.4.4 also works but 2.2.6 has more battle-testing on cp311 |
| Use pystray 0.19.5 | MEDIUM | Stale release date, but underlying Win32 API is frozen, so "stale" ≠ "broken." PyInstaller gotcha is documented and one-line fix. |
| Ctypes RegisterHotKey (NOT keyboard lib) | HIGH | `keyboard` confirmed archived; Microsoft Learn docs confirm RegisterHotKey semantics; pattern is stable since Vista |
| WM_NCHITTEST → HTTRANSPARENT for click-through | HIGH | Microsoft Learn authoritative; matches PROJECT.md Key Decisions |
| SetWindowRgn for shape masking | HIGH | Microsoft Learn authoritative; region ownership rules documented |
| PyInstaller 6.11.1 (not Nuitka) | HIGH | Build-time, hook support, and project scale all favor PyInstaller for this app |
| BILINEAR resample (not LANCZOS) | HIGH | Standard knowledge: LANCZOS is for downscaling; for 1.5–6× upscale BILINEAR is sufficient and 3–5× faster |

**Overall research confidence: HIGH.** Every critical claim is backed by either an official Microsoft Learn page, a PyPI release, or a GitHub repo state, and none of the core decisions rely on a single source.

---
*Stack research for: Windows 11 desktop magnifier overlay in Python 3.11*
*Researched: 2026-04-10*
