# Research Summary: Magnifier Bubble — Ultimate Zoom

**Synthesized from:** STACK.md · FEATURES.md · ARCHITECTURE.md · PITFALLS.md
**Date:** 2026-04-10
**Confidence:** HIGH

---

## Executive Summary

Ultimate Zoom is a floating, always-on-top, click-through screen magnification bubble for a single user with Stargardt's disease operating Idexx Cornerstone on a clinic touchscreen. The core insight: this app is a **prosthetic overlay, not a workspace**. Every major commercial magnifier (ZoomText, SuperNova, Windows Magnifier) optimizes for "the magnifier is the primary interface." This app optimizes for "Cornerstone is the interface; the bubble must never interfere with it." That reframing makes click-through, non-focus-stealing, and always-on-top non-negotiable — and makes full-screen magnification, follow-focus tracking, and modal dialogs active anti-features.

---

## Stack

**Recommended:** Python 3.11.9 + tkinter (stdlib) + mss 10.1.0 + pywin32 311 + Pillow 11.3.0 + pystray 0.19.5 + PyInstaller 6.11.1

```
mss==10.1.0
pywin32==311
Pillow==11.3.0
numpy==2.2.6
pystray==0.19.5
pyinstaller==6.11.1
```

**Key stack decisions:**
- `mss` → GDI BitBlt, ~3 ms/frame, zero native dependencies, no DXGI fragility
- `keyboard` library → **ARCHIVED Feb 2026** — use `ctypes + user32.RegisterHotKey` directly
- `pynput` → documented Win11 global hotkey reliability issues — rejected
- PyInstaller 6.11.1 (NOT 6.3–6.5.x — AV false-positive cluster in those versions); UPX disabled
- Pillow BILINEAR resampling (NOT LANCZOS) — 3–5× faster for upscaling, hits 30 fps budget
- Hot loop budget: mss ~3 ms + frombytes ~2 ms + BILINEAR resize ~5–8 ms + PhotoImage paste ~3 ms = ~15–18 ms (33 ms budget at 30 fps)

---

## Features

**Table stakes (must ship or users reject):**
- Real-time magnified capture, click-through middle zone, always-on-top + no focus steal
- Three-zone layout (drag bar / content / controls), drag to move, resize grip
- Zoom 1.5x–6x in 0.25x steps, visible zoom level display
- Shape cycling: Circle → Rounded Rectangle → Rectangle
- Ctrl+Z global toggle (configurable), system tray (Show/Hide/Exit)
- Config persistence (position, size, zoom, shape), single .exe deploy, README

**Differentiators (why this beats commercial tools for this user):**
- Shape cycling accommodates Preferred Retinal Locus (PRL) variation in Stargardt's eccentric viewing
- Fine 0.25x zoom steps (competitors use 0.5x–1x jumps)
- Zero-chrome content area — no overlay inside the magnified view
- Stationary bubble (not mouse-follow) — stable reference point for eccentric viewers
- Configurable hotkey (Ctrl+Z is a clinic default, but must be changeable)

**Anti-features (explicitly excluded):**
- Full-screen / panning magnification modes — destroys peripheral context Stargardt's users rely on
- Follow-cursor/focus tracking — disorienting for eccentric viewers
- Color inversion / filter overlays — not needed, adds complexity
- OCR / TTS integration — out of scope, different tool
- Auto-hide on inactivity — must stay visible when user needs it

---

## Architecture

**Thread model (4 threads):**
1. **Tk main thread** — all UI and win32 HWND calls; sole owner of tkinter
2. **Capture worker** (daemon) — mss → Pillow → root.after() → Tk
3. **Hotkey thread** (daemon) — Win32 message pump for WM_HOTKEY only
4. **pystray thread** (managed) — tray icon; all callbacks marshaled via root.after()

**Single source of truth:** `AppState` (position, size, zoom, shape, visible) — all mutations via Tk main thread.

**Build order (linearizable):**
1. `winconst` + `hit_test` (pure constants/logic, testable)
2. `AppState` (state container)
3. `shapes` + `wndproc` subclassing
4. `BubbleWindow` ← first visible milestone (shaped, draggable, empty bubble)
5. `CaptureWorker` ← second visible milestone (live magnified pixels)
6. `widgets` (zoom buttons, shape button, resize grip)
7. `ConfigStore` (debounced atomic writes)
8. `HotkeyService` + `TrayService` (parallelizable)
9. PyInstaller spec + `build.bat`

**PyInstaller spec must include:**
```python
hiddenimports=['pystray._win32', 'PIL._tkinter_finder', 'win32timezone']
upx=False  # top AV false-positive cause
uac_admin=False  # RegisterHotKey Ctrl+Z does not need admin
```
Run `pywin32_postinstall.py -install` in build venv BEFORE invoking PyInstaller.

---

## Top 5 Pitfalls

| # | Pitfall | Fix | Phase |
|---|---------|-----|-------|
| 1 | **WndProc callback GC crash** — Python GCs the ctypes callback, next message = crash | Store `self._wndproc_ref = WNDPROC(callback)` on instance | Phase 2 |
| 2 | **DPI unawareness** — mss captures wrong region at 125%/150% scaling | `SetProcessDpiAwarenessContext(-4)` as first line of main.py, before any imports | Phase 1 |
| 3 | **PhotoImage per-frame memory leak** (CPython issue 124364, Windows-specific) | Reuse a single `ImageTk.PhotoImage`; call `.paste()` each frame | Phase 3 |
| 4 | **pystray threading deadlock** — `icon.run()` blocks main thread; menu callbacks touch Tk | `icon.run_detached()` or daemon thread; all menu callbacks via `root.after(0, ...)` | Phase 7 |
| 5 | **Ctrl+Z pre-empts Cornerstone undo** — `RegisterHotKey` wins before the focused app | Make hotkey configurable in config.json; confirm choice with user before clinic deploy | Phase 6 |

**mss self-capture is NOT a risk** — `WS_EX_LAYERED` windows are excluded from BitBlt by default on Windows 8+.

**SetWindowRgn HRGN ownership** — Windows owns the region handle after a successful call; never free it manually (double-free crash).

---

## Roadmap Implications

**8 phases, coarse granularity:**

| Phase | Name | Key Deliverable | Risk |
|-------|------|-----------------|------|
| 1 | Foundation + DPI | Scaffold, AppState, DPI line 1 | Low |
| 2 | Overlay Window | Shaped, draggable, click-through empty bubble | **HIGH** — hardest Win32 work |
| 3 | Capture Loop | Live magnified pixels at 30 fps, memory-stable | Medium |
| 4 | Shape + Resize | Shape cycling, resize grip, zoom controls | Medium |
| 5 | Config Persistence | config.json atomic debounced save/restore | Low |
| 6 | Global Hotkey | RegisterHotKey daemon, configurable, end-user confirmed | Medium |
| 7 | System Tray | pystray + show/hide toggle | Low |
| 8 | Build + Package | Single .exe, build.bat, README | Medium |

**Research flags:**
- **Phase 2** needs hardware validation — WM_NCHITTEST touch click-through cannot be verified without actual touchscreen
- **Phase 8** needs clinic AV validation — unknown AV product; budget time for allowlisting

**Standard patterns (no additional research needed):** Phases 1, 3, 5, 6, 7

---

## Open Questions (carry into phase planning)

1. **Ctrl+Z vs. Cornerstone undo** — requires user conversation before Phase 6 ships; default to `Ctrl+Alt+Z` as safer alternative
2. **Touchscreen hardware access** — Phase 2 acceptance criteria must include real finger-input test
3. **Clinic AV software** — unknown; test .exe on actual clinic PC before handoff
4. **Cornerstone DPI awareness** — legacy LOB app may conflict with Per-Monitor-V2; needs empirical testing
5. **config.json write location** — app directory works unless clinic IT locks the folder; have `%LOCALAPPDATA%` fallback ready
