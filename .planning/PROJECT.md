# Magnifier Bubble — Ultimate Zoom

## What This Is

A Windows 11 desktop magnifier bubble application written in Python 3.11+. It captures screen pixels directly beneath the overlay window and displays them magnified in real time inside a floating, always-on-top bubble. Designed for a user with Stargardt's disease at a medical clinic who uses a touchscreen, running alongside Idexx Cornerstone veterinary software without interfering with it.

## Core Value

Clicks and touches pass through the magnified content area to whatever app is underneath — the bubble enhances vision without blocking the workflow.

## Requirements

### Validated

- [x] requirements.txt with pinned versions — *Validated in Phase 1: Foundation + DPI*
- [x] DPI-correct foundation: `SetProcessDpiAwarenessContext(-4)` as first executable line of main.py — *Validated in Phase 1: Foundation + DPI*
- [x] AppState container as single source of truth for position, size, zoom, shape, visible — *Validated in Phase 1: Foundation + DPI*

### Active

- [ ] Always-on-top floating overlay with no taskbar presence
- [ ] Real-time screen capture (mss) of pixels beneath the bubble at 30fps minimum
- [ ] Full click-through on the magnified content zone (WS_EX_TRANSPARENT + WS_EX_LAYERED)
- [ ] Three-zone layout: drag handle top, magnified content middle, zoom controls bottom
- [ ] Top drag bar: draggable, grip indicator (≡), shape-cycle button (⊙)
- [ ] Middle zone: shows magnified capture, zero UI chrome, 100% click-through
- [ ] Bottom strip: [−] / [+] zoom buttons, zoom level display, resize button [⤢]
- [ ] Zoom range 1.5x–6x in 0.25x increments
- [ ] Shape cycling: Circle → Rounded Rectangle → Rectangle → (repeat)
- [ ] Resize via drag handle (bottom-right) and corner grip; min 150×150, max 700×700
- [ ] All touch targets ≥ 44×44px
- [ ] Teal/soft-blue border (3–4px) visible on any background
- [ ] Semi-transparent dark strips for top/bottom controls
- [ ] Ctrl+Z global hotkey toggles bubble visible/hidden (works even when Cornerstone has focus)
- [ ] System tray icon with Show/Hide, Always on Top toggle, Exit
- [ ] Persist config (position, size, zoom, shape) to config.json on every change; restore on launch
- [ ] requirements.txt with pinned versions
- [ ] PyInstaller build.bat → single .exe, no Python install required on clinic PC
- [ ] README.md with plain-English setup for non-technical users
- [ ] Push code to GitHub repo: fresh-start-git/Ultimate-Zoom

### Out of Scope

- Linux / macOS support — Windows 11 only (clinic environment)
- Any UI framework other than tkinter/pywin32 — keep dependencies minimal and pip-installable
- Network features — fully local, offline app
- Multi-monitor advanced scaling edge cases — single primary display focus

## Context

- Target user has Stargardt's disease (central vision loss), relies on peripheral vision, needs real-time content magnification without losing ability to interact with underlying apps
- Running at a medical clinic alongside Idexx Cornerstone (veterinary practice management software) on a touchscreen PC
- Must not steal focus from Cornerstone or intercept touches in the content area
- Deployment target is a clinic PC — no Python install available; must ship as a compiled .exe
- GitHub repo for the project: https://github.com/fresh-start-git/Ultimate-Zoom.git

## Constraints

- **Tech Stack**: Python 3.11+, mss (screen capture), pywin32 (Windows API), tkinter (UI), pystray (tray), keyboard or ctypes (global hotkey), PyInstaller (build)
- **Performance**: 30fps minimum in the magnification loop; mss only — no PIL.ImageGrab in the main loop
- **Accessibility**: All touch targets ≥ 44×44px for finger use on clinic touchscreen
- **Deployment**: Single .exe via PyInstaller — no external dependencies at runtime
- **Compatibility**: Windows 11 (primary); Windows 10 fallback acceptable

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| mss for screen capture | Faster than PIL.ImageGrab; PIL explicitly excluded by spec | — Pending |
| WM_NCHITTEST → HTTRANSPARENT for middle zone | More precise than whole-window transparency; preserves dragging on handle bar | — Pending |
| SetWindowRgn for shape masking | Simplest cross-Python approach for circle/rounded-rect/rect clipping | — Pending |
| PyInstaller single-file .exe | Clinic PC has no Python; one-click deploy needed | — Pending |
| config.json in app directory | Predictable location, easy for non-technical staff to find/reset | — Pending |

---
*Last updated: 2026-04-11 — Phase 1 (Foundation + DPI) complete*
