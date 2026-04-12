# Requirements: Magnifier Bubble — Ultimate Zoom

**Defined:** 2026-04-10
**Core Value:** Clicks and touches pass through the magnified content area to whatever app is underneath — the bubble enhances vision without blocking the workflow.

## v1 Requirements

### Overlay Window

- [x] **OVER-01**: App window is always-on-top and has no taskbar presence (WS_EX_TOOLWINDOW)
- [x] **OVER-02**: Window has no title bar or standard OS chrome (overrideredirect)
- [x] **OVER-03**: Window is a layered window (WS_EX_LAYERED) to enable per-pixel transparency and click-through
- [x] **OVER-04**: Window never steals focus from Cornerstone or any other app (WS_EX_NOACTIVATE)
- [x] **OVER-05**: DPI awareness set as first line of main.py (SetProcessDpiAwarenessContext Per-Monitor-V2) before any imports

### Capture

- [ ] **CAPT-01**: App captures screen pixels directly beneath the bubble at real screen coordinates using mss
- [ ] **CAPT-02**: Capture runs at 30 fps minimum (33 ms/frame budget)
- [ ] **CAPT-03**: PIL.ImageGrab is NOT used in the main capture loop (mss only)
- [ ] **CAPT-04**: Captured pixels are magnified using Pillow BILINEAR resampling and rendered inside the bubble
- [ ] **CAPT-05**: Per-frame rendering reuses a single ImageTk.PhotoImage via paste() to avoid Windows memory leak (CPython issue 124364)
- [ ] **CAPT-06**: Capture correctly handles the bubble's own screen position (no hall-of-mirrors; WS_EX_LAYERED excludes the window from BitBlt by default)

### Layout

- [x] **LAYT-01**: Window has three horizontal zones: drag handle (top), magnified content (middle), controls (bottom)
- [x] **LAYT-02**: Middle content zone is 100% click-through — all mouse and touch input passes through to underlying app (WM_NCHITTEST → HTTRANSPARENT for middle zone)
- [x] **LAYT-03**: Top drag bar and bottom control strip capture mouse/touch input normally
- [x] **LAYT-04**: WndProc subclassed via SetWindowLongPtrW + GWLP_WNDPROC; callback stored on instance to prevent GC crash
- [x] **LAYT-05**: Top and bottom strips are semi-transparent dark overlay (rgba 0,0,0 ~180 alpha)
- [x] **LAYT-06**: Teal/soft-blue border (3–4px) visible around the bubble on any background

### Controls

- [ ] **CTRL-01**: Top drag bar has a grip indicator (≡ three horizontal lines) and is draggable by finger or mouse to reposition the bubble anywhere on screen
- [ ] **CTRL-02**: Top drag bar has a shape-cycle button (⊙) that cycles Circle → Rounded Rectangle → Rectangle → Circle
- [ ] **CTRL-03**: Shape masking applied via SetWindowRgn; HRGN not freed after successful call (Windows owns it)
- [ ] **CTRL-04**: Bottom strip has [−] and [+] zoom buttons with current zoom level displayed between them
- [ ] **CTRL-05**: Zoom range is 1.5x to 6x in 0.25x increments
- [ ] **CTRL-06**: Bottom strip has a resize button [⤢] in the bottom-right that allows drag-to-resize
- [ ] **CTRL-07**: Window corner grip (bottom-right of whole window) provides secondary resize via drag
- [ ] **CTRL-08**: Minimum window size 150×150px; maximum 700×700px
- [ ] **CTRL-09**: All touch targets are minimum 44×44px for finger use on clinic touchscreen

### Hotkey

- [ ] **HOTK-01**: Ctrl+Z registered as a global system-wide hotkey via ctypes + user32.RegisterHotKey (no keyboard library)
- [ ] **HOTK-02**: Hotkey works even when Cornerstone or any other app has focus
- [ ] **HOTK-03**: Hotkey toggles the bubble visible/hidden
- [ ] **HOTK-04**: Hotkey is configurable in config.json (default: Ctrl+Z; safer alternative Ctrl+Alt+Z available if Cornerstone undo conflict confirmed)
- [ ] **HOTK-05**: Hotkey is registered/unregistered cleanly on app start/exit; graceful failure message if already registered

### Tray

- [ ] **TRAY-01**: App launches to system tray with a custom tray icon
- [ ] **TRAY-02**: Tray menu includes: Show/Hide, Always on Top toggle, Exit
- [ ] **TRAY-03**: Clicking the tray icon toggles bubble visibility
- [ ] **TRAY-04**: pystray runs on its own managed thread; all menu callbacks marshaled to Tk main thread via root.after(0, ...)
- [ ] **TRAY-05**: icon.stop() called before root.destroy() on exit

### Persistence

- [ ] **PERS-01**: config.json saved in the same directory as the app executable
- [ ] **PERS-02**: Config is written on every change (position, size, zoom level, shape) using debounce (500 ms) and atomic os.replace()
- [ ] **PERS-03**: On launch, app restores last known position, size, zoom level, and shape from config.json
- [ ] **PERS-04**: Config write pending at shutdown is flushed before exit (WM_DELETE_WINDOW handler)

### Build and Deployment

- [ ] **BULD-01**: requirements.txt with pinned versions provided
- [ ] **BULD-02**: PyInstaller .spec file checked into repo; includes hiddenimports=['pystray._win32', 'PIL._tkinter_finder', 'win32timezone'] and upx=False
- [ ] **BULD-03**: build.bat script compiles app to a single portable .exe with no external dependencies
- [ ] **BULD-04**: Output .exe runs on clinic PC without Python installed
- [ ] **BULD-05**: README.md with plain-English step-by-step setup for a non-technical user (how to install Python, install dependencies, run from source, and run the .exe)
- [ ] **BULD-06**: Code pushed to GitHub repo: https://github.com/fresh-start-git/Ultimate-Zoom.git

## v2 Requirements

### Accessibility Enhancements

- **ACC-01**: Configurable bubble opacity (for users who find the overlay visually intrusive)
- **ACC-02**: Dark-background-inside-bubble option (for photophobia sensitivity)
- **ACC-03**: Keyboard-accessible zoom controls (arrow keys when bubble focused)

### Multi-Monitor

- **MULT-01**: Correct capture region handling when bubble is dragged to a secondary monitor with different DPI scaling

### Performance

- **PERF-01**: Adaptive resampling (NEAREST at extreme settings 700×700@6×) for weak clinic hardware

## Out of Scope

| Feature | Reason |
|---------|--------|
| Linux / macOS support | Windows 11 clinic environment only |
| Full-screen magnification mode | Destroys peripheral context Stargardt's users rely on for eccentric viewing |
| Follow-cursor / focus tracking | Disorienting for eccentric viewers; Cornerstone must stay primary |
| Color inversion / filter overlays | Not needed; adds complexity |
| OCR / TTS integration | Different tool category |
| Auto-hide on inactivity | Must stay visible when user needs it |
| OAuth / network features | Fully local, offline app |
| Windows Graphics Capture API (DXGI) | DXcam/BetterCam fragile on non-standard clinic display configs; mss covers the use case |
| Code signing | Out of scope; deployment README will include AV allowlist step |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| OVER-01 | Phase 2 | Complete |
| OVER-02 | Phase 2 | Complete |
| OVER-03 | Phase 2 | Complete |
| OVER-04 | Phase 2 | Complete |
| OVER-05 | Phase 1 | Complete |
| CAPT-01 | Phase 3 | Pending |
| CAPT-02 | Phase 3 | Pending |
| CAPT-03 | Phase 3 | Pending |
| CAPT-04 | Phase 3 | Pending |
| CAPT-05 | Phase 3 | Pending |
| CAPT-06 | Phase 3 | Pending |
| LAYT-01 | Phase 2 | Complete |
| LAYT-02 | Phase 2 | Complete |
| LAYT-03 | Phase 2 | Complete |
| LAYT-04 | Phase 2 | Complete |
| LAYT-05 | Phase 2 | Complete |
| LAYT-06 | Phase 2 | Complete |
| CTRL-01 | Phase 4 | Pending |
| CTRL-02 | Phase 4 | Pending |
| CTRL-03 | Phase 4 | Pending |
| CTRL-04 | Phase 4 | Pending |
| CTRL-05 | Phase 4 | Pending |
| CTRL-06 | Phase 4 | Pending |
| CTRL-07 | Phase 4 | Pending |
| CTRL-08 | Phase 4 | Pending |
| CTRL-09 | Phase 4 | Pending |
| HOTK-01 | Phase 6 | Pending |
| HOTK-02 | Phase 6 | Pending |
| HOTK-03 | Phase 6 | Pending |
| HOTK-04 | Phase 6 | Pending |
| HOTK-05 | Phase 6 | Pending |
| TRAY-01 | Phase 7 | Pending |
| TRAY-02 | Phase 7 | Pending |
| TRAY-03 | Phase 7 | Pending |
| TRAY-04 | Phase 7 | Pending |
| TRAY-05 | Phase 7 | Pending |
| PERS-01 | Phase 5 | Pending |
| PERS-02 | Phase 5 | Pending |
| PERS-03 | Phase 5 | Pending |
| PERS-04 | Phase 5 | Pending |
| BULD-01 | Phase 8 | Pending |
| BULD-02 | Phase 8 | Pending |
| BULD-03 | Phase 8 | Pending |
| BULD-04 | Phase 8 | Pending |
| BULD-05 | Phase 8 | Pending |
| BULD-06 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 46 total
- Mapped to phases: 46
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-10*
*Last updated: 2026-04-10 after initial definition*
