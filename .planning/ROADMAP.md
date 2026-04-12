# Roadmap: Magnifier Bubble — Ultimate Zoom

## Overview

Ultimate Zoom is a floating, click-through, always-on-top magnifier bubble for a single Stargardt's user operating Idexx Cornerstone on a Windows 11 clinic touchscreen. The journey builds the app bottom-up following Win32 dependency order: DPI-correct foundation first, then the shaped click-through overlay window (the hardest Win32 work), then live capture/rendering, then the user-facing controls that make it usable, then persistence so it survives restart, then the global hotkey and tray integration that let it coexist with Cornerstone, and finally the PyInstaller single-exe build the clinic PC can actually run. Every phase produces something the user can observe on a real screen — no invisible infrastructure phases.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation + DPI** - Project scaffold, AppState container, DPI awareness set as first line of main.py (completed 2026-04-11)
- [x] **Phase 2: Overlay Window** - Shaped, draggable, click-through, non-focus-stealing empty bubble on screen (completed 2026-04-12)
- [ ] **Phase 3: Capture Loop** - Live magnified pixels rendered inside the bubble at 30 fps with no memory leak
- [ ] **Phase 4: Controls, Shape, Resize** - Zoom buttons, shape cycling, resize grip, touch-sized hit targets
- [ ] **Phase 5: Config Persistence** - Position, size, zoom, shape saved to config.json and restored on launch
- [ ] **Phase 6: Global Hotkey** - Ctrl+Z (configurable) toggles bubble visibility even when Cornerstone has focus
- [ ] **Phase 7: System Tray** - Tray icon with Show/Hide, Always-on-Top toggle, and Exit
- [ ] **Phase 8: Build and Package** - Single portable .exe via PyInstaller, README, pushed to GitHub

## Phase Details

### Phase 1: Foundation + DPI
**Goal**: Establish a DPI-correct Python project scaffold with a single source of truth for app state, so every subsequent phase runs on a foundation that captures pixels at the right coordinates on 125%/150% clinic displays.
**Depends on**: Nothing (first phase)
**Requirements**: OVER-05
**Success Criteria** (what must be TRUE):
  1. `python main.py` launches without errors on Windows 11 and exits cleanly
  2. `SetProcessDpiAwarenessContext(-4)` (Per-Monitor-V2) is the first executable line of main.py, before any tkinter/PIL/mss imports
  3. A pinned `requirements.txt` exists and `pip install -r requirements.txt` succeeds in a clean venv
  4. An `AppState` object holds position, size, zoom, shape, and visible fields and is the only place those values are mutated
  5. Running the app on a 150%-scaled display reports logical and physical screen dimensions that match Windows' actual values (verified via a debug print)
**Plans**: 3 plans (3/3 complete)
- [x] 01-PLAN.md — Project scaffold: requirements.txt, pyproject.toml, package+tests skeleton (completed 2026-04-11, see 01-01-SUMMARY.md)
- [x] 02-PLAN.md — TDD AppState container + DPI helper module (completed 2026-04-11, see 01-02-SUMMARY.md)
- [x] 03-PLAN.md — Root main.py shim (OVER-05 first-line DPI) + app.py entry + entry-point tests (completed 2026-04-11, see 01-03-SUMMARY.md)

### Phase 2: Overlay Window
**Goal**: Put a shaped, always-on-top, click-through empty bubble on screen that can be dragged by its top strip and never steals focus from Cornerstone — the hardest Win32 work in the project, delivering the first visible milestone.
**Depends on**: Phase 1
**Requirements**: OVER-01, OVER-02, OVER-03, OVER-04, LAYT-01, LAYT-02, LAYT-03, LAYT-04, LAYT-05, LAYT-06
**Success Criteria** (what must be TRUE):
  1. A borderless, title-bar-less bubble window appears on launch, stays above all other windows, and shows no taskbar entry
  2. Clicking anywhere in the middle content zone passes the click through to the app underneath (verified against Notepad/Cornerstone; window does not consume the click)
  3. Dragging the top strip moves the bubble; dragging inside the middle zone does not move it
  4. Clicking the bubble while Cornerstone has focus does not steal focus from Cornerstone (Cornerstone cursor/typing continues uninterrupted)
  5. The bubble has visible top/bottom semi-transparent dark strips and a 3–4px teal border that are legible against both light and dark backgrounds
  6. WndProc subclassing is installed via `SetWindowLongPtrW` with the callback stored on the instance, and the app runs for at least 5 minutes of interaction without a GC crash
**Plans**: 3 plans
- [ ] 02-01-PLAN.md — winconst.py + hit_test.py (pure-Python foundation; locks string zone contract "drag"/"content"/"control" + Win32 sentinel constants; covers LAYT-01, LAYT-02, LAYT-03)
- [ ] 02-02-PLAN.md — wndproc.py + shapes.py (Windows-only WndProc subclass with keepalive + SetWindowRgn wrapper; 50-message GC smoke test for Pitfall A; 50-cycle HRGN smoke test for Pitfall F; covers OVER-03, LAYT-02, LAYT-03, LAYT-04)
- [ ] 02-03-PLAN.md — BubbleWindow + app.py rewrite + manual checkpoint (wires canonical Pattern 1 constructor ordering, Pattern 2b live-drag workaround, visible strips + teal border, ULTIMATE_ZOOM_SMOKE escape hatch for subprocess tests; ends with 7-check human verification on Windows dev box; covers OVER-01, OVER-02, OVER-03, OVER-04, LAYT-01, LAYT-04, LAYT-05, LAYT-06)

### Phase 3: Capture Loop
**Goal**: Fill the middle zone with live, magnified pixels of whatever is under the bubble at 30 fps minimum, using mss + BILINEAR resampling, without the Windows PhotoImage memory leak.
**Depends on**: Phase 2
**Requirements**: CAPT-01, CAPT-02, CAPT-03, CAPT-04, CAPT-05, CAPT-06
**Success Criteria** (what must be TRUE):
  1. Moving a window under the bubble shows that window's content magnified inside the bubble in real time, at the correct screen coordinates
  2. The capture loop sustains >= 30 fps on a typical clinic PC (measured via frame-time logging over a 60-second window)
  3. The bubble does not show its own content recursively (no "hall of mirrors") when positioned over its previous location
  4. The app's memory footprint is stable (< 5 MB drift) after 10 minutes of continuous capture, proving the single-PhotoImage `paste()` pattern is in place
  5. `grep -r "ImageGrab" src/` returns zero matches in the hot capture path; only `mss` is used
**Plans**: 2 plans
- [ ] 03-01-PLAN.md — Pure-Python capture.py module (CaptureWorker producer thread with mss + BILINEAR + Event.wait pacing + outer reconnect loop) + Wave 0 structural/lint tests in tests/test_capture.py + mss/Pillow wheel verification (CAPT-01, CAPT-02, CAPT-03, CAPT-04)
- [ ] 03-02-PLAN.md — BubbleWindow wiring (_photo/_image_id/_on_frame/start_capture Step 9b) + SetWindowDisplayAffinity Path A (Step 8b) hall-of-mirrors defense + tests/test_capture_smoke.py (Windows-only fps/memory/teal-sampling) + 7-point manual verification checkpoint (CAPT-01, CAPT-02, CAPT-05, CAPT-06)

### Phase 4: Controls, Shape, and Resize
**Goal**: Give the user the on-bubble controls they need to operate the magnifier with fingers on a touchscreen — zoom in/out, cycle shapes, resize — all with touch-safe hit targets and the full specified zoom range.
**Depends on**: Phase 3
**Requirements**: CTRL-01, CTRL-02, CTRL-03, CTRL-04, CTRL-05, CTRL-06, CTRL-07, CTRL-08, CTRL-09
**Success Criteria** (what must be TRUE):
  1. Tapping [+] and [−] on the bottom strip changes the zoom level in 0.25x increments between 1.5x and 6x, with the current zoom value displayed between the buttons
  2. Tapping the shape button (⊙) in the top strip cycles the bubble outline Circle → Rounded Rectangle → Rectangle → Circle via `SetWindowRgn`, and the region handle is not freed manually
  3. Dragging the bottom-right resize button [⤢] and the window corner grip both resize the bubble, clamped to 150×150 min and 700×700 max
  4. Every interactive control (drag grip, shape button, zoom buttons, resize button) measures at least 44×44 pixels and is tappable with a fingertip on the clinic touchscreen
  5. The top strip grip indicator (≡) is visible and the bubble drags smoothly by finger from anywhere on the top strip
**Plans**: TBD

### Phase 5: Config Persistence
**Goal**: Make the bubble remember where it was, how big it was, how zoomed in it was, and what shape it was the last time the user closed it, so every launch picks up exactly where the user left off.
**Depends on**: Phase 4
**Requirements**: PERS-01, PERS-02, PERS-03, PERS-04
**Success Criteria** (what must be TRUE):
  1. After moving, resizing, zooming, and shape-cycling the bubble, a `config.json` file appears in the app's directory containing the new position, size, zoom, and shape
  2. Relaunching the app restores the bubble at exactly the last-used position, size, zoom level, and shape
  3. Rapid consecutive changes (e.g., mashing the + button 10 times in 2 seconds) produce a single debounced write ~500 ms after the last change, not 10 writes
  4. Killing the app mid-change (closing via WM_DELETE_WINDOW) flushes any pending debounced write before exit, and no partially written config.json is observable
  5. Writes use `os.replace()` atomically — pulling the plug or corrupting a write never leaves a broken config.json
**Plans**: TBD

### Phase 6: Global Hotkey
**Goal**: Let the user toggle the bubble visible/hidden with Ctrl+Z (or a configured alternative) from inside Cornerstone without the magnifier ever stealing focus or needing admin rights.
**Depends on**: Phase 5
**Requirements**: HOTK-01, HOTK-02, HOTK-03, HOTK-04, HOTK-05
**Success Criteria** (what must be TRUE):
  1. Pressing the configured hotkey (default Ctrl+Z, confirmed with user vs. Cornerstone undo before clinic deploy) toggles the bubble visible/hidden
  2. The hotkey fires correctly while Cornerstone has focus, proving `RegisterHotKey` is reaching the system-wide level
  3. The hotkey is implemented via `ctypes + user32.RegisterHotKey` on a daemon message-pump thread — no `keyboard` library, no `pynput`
  4. Editing `config.json` to change the hotkey (e.g., to Ctrl+Alt+Z) and relaunching picks up the new binding
  5. If the hotkey is already registered by another app, the app surfaces a graceful message and continues running (does not crash), and on clean exit the hotkey is unregistered
**Plans**: TBD

### Phase 7: System Tray
**Goal**: Give the user a persistent tray icon that lets them show/hide the bubble, toggle always-on-top, and exit the app cleanly — the last user-facing integration before packaging.
**Depends on**: Phase 6
**Requirements**: TRAY-01, TRAY-02, TRAY-03, TRAY-04, TRAY-05
**Success Criteria** (what must be TRUE):
  1. Launching the app shows a custom tray icon in the Windows notification area
  2. The tray right-click menu contains Show/Hide, Always on Top toggle, and Exit, and each item performs the labeled action
  3. Left-clicking the tray icon toggles the bubble's visibility
  4. pystray runs on its own managed thread and every menu callback is marshaled to the Tk main thread via `root.after(0, ...)` — no threading deadlocks after 5 minutes of menu interaction
  5. Exiting via the tray menu calls `icon.stop()` before `root.destroy()`, and the process terminates cleanly (no lingering threads or orphaned tray icons)
**Plans**: TBD

### Phase 8: Build and Package
**Goal**: Produce a single portable .exe the non-technical clinic staff can double-click on a Windows 11 PC with no Python installed, documented in a plain-English README, and published to the project GitHub repo.
**Depends on**: Phase 7
**Requirements**: BULD-01, BULD-02, BULD-03, BULD-04, BULD-05, BULD-06
**Success Criteria** (what must be TRUE):
  1. Running `build.bat` in a clean venv produces a single `.exe` with no external runtime dependencies
  2. The `.spec` file is committed, includes `hiddenimports=['pystray._win32', 'PIL._tkinter_finder', 'win32timezone']`, and sets `upx=False`
  3. The resulting `.exe` launches on a Windows 11 machine with no Python installed and exercises all Phase 1–7 success criteria end-to-end
  4. A `README.md` walks a non-technical user step-by-step through installing Python, installing dependencies, running from source, and running the `.exe`, including an AV allowlist note
  5. The full source tree, `.spec`, `build.bat`, and `README.md` are pushed to `https://github.com/fresh-start-git/Ultimate-Zoom.git`
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation + DPI | 3/3 | Complete | 2026-04-11 |
| 2. Overlay Window | 3/3 | Complete   | 2026-04-12 |
| 3. Capture Loop | 0/2 | Not started | - |
| 4. Controls, Shape, Resize | 0/TBD | Not started | - |
| 5. Config Persistence | 0/TBD | Not started | - |
| 6. Global Hotkey | 0/TBD | Not started | - |
| 7. System Tray | 0/TBD | Not started | - |
| 8. Build and Package | 0/TBD | Not started | - |

## Coverage

**v1 requirements:** 46 total
**Mapped:** 46 / 46
**Orphaned:** 0

| Category | Count | Phase |
|----------|-------|-------|
| OVER | 5 | Phase 1 (OVER-05), Phase 2 (OVER-01..04) |
| CAPT | 6 | Phase 3 |
| LAYT | 6 | Phase 2 |
| CTRL | 9 | Phase 4 |
| HOTK | 5 | Phase 6 |
| TRAY | 5 | Phase 7 |
| PERS | 4 | Phase 5 |
| BULD | 6 | Phase 8 |

## Research Flags

- **Phase 2** needs hardware validation — WM_NCHITTEST touch click-through cannot be fully verified without the actual clinic touchscreen
- **Phase 6** needs user conversation — confirm Ctrl+Z vs. Cornerstone undo conflict before shipping; safer default is Ctrl+Alt+Z
- **Phase 8** needs clinic AV validation — unknown AV product; budget time for allowlisting on target PC

---
*Roadmap created: 2026-04-10*
*Granularity: coarse (8 phases derived from natural Win32 dependency order)*
