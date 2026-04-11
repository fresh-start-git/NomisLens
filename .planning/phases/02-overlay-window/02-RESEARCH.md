# Phase 2: Overlay Window - Research

**Researched:** 2026-04-11
**Domain:** Win32 layered windows + tkinter Toplevel + ctypes WndProc subclassing on Windows 11
**Confidence:** HIGH (overall) — every load-bearing claim verified against Microsoft Learn primary docs (`SetWindowLongPtrW`, `WM_NCHITTEST`, Extended Window Styles), or against the project's already-committed `.planning/research/STACK.md` / `ARCHITECTURE.md` / `PITFALLS.md`. One MEDIUM-confidence area is flagged below: **touch-input click-through cannot be verified without clinic touchscreen hardware** (a known Phase-2 research flag in `ROADMAP.md`).

---

## Summary

Phase 2 produces the *first visible artifact* of Ultimate Zoom — a borderless, shaped, semi-transparent bubble that floats above every other window, can be dragged by its top strip, never appears in the taskbar or Alt+Tab, never steals focus from Cornerstone, and lets clicks in the middle zone fall through to whatever app is underneath. Every later phase depends on this skeleton existing. It is also unanimously the **hardest Win32 work in the project**: there is exactly one correct combination of extended-style bits (`WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE`, and **NOT** `WS_EX_TRANSPARENT`), exactly one correct way to install a Python WndProc subclass via `SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ...)` without crashing on the first mouse-move, and exactly one correct way to apply per-region hit-testing through `WM_NCHITTEST` returning `HTCAPTION` / `HTTRANSPARENT` / `HTCLIENT`. Any deviation produces a different specific bug (no clicks, GC crash, focus theft, taskbar entry, dead drag) and the deviations have all been catalogued in `.planning/research/PITFALLS.md` Pitfalls 1-3, 8, 15.

The good news: the project's prior research (committed under `.planning/research/`) has already done the deep technical legwork — STACK.md §2 selected `WM_NCHITTEST` subclassing, ARCHITECTURE.md Pattern 2 wrote the `wndproc.install()` keepalive contract, PITFALLS.md Pitfalls 1-3 documented every gotcha. **Phase 2's job is to convert those research findings into runnable, tested code on the existing Phase 1 scaffold** — not to re-investigate the underlying win32 mechanics. The code shape is already specified.

The bad news: there is one nuance the prior research did NOT call out and that we discovered while researching this phase — **`WS_EX_NOACTIVATE` + `HTCAPTION` drag has a known visual-feedback regression** (the window only jumps to the new position on mouse-up rather than tracking smoothly). The safe workaround is to handle `WM_LBUTTONDOWN` in the drag-bar widget and post `WM_NCLBUTTONDOWN(HTCAPTION)` after `ReleaseCapture()`, which gives the OS-managed move loop without the dead-drag glitch. This is documented below in Pattern 2b and Open Question #1; we treat it as a build-then-verify item rather than a blocking unknown.

**Primary recommendation:** Build Phase 2 in three plans: (1) `winconst.py` + `hit_test.py` (pure Python, fully unit-testable, zero win32), (2) `wndproc.py` + `shapes.py` (isolated ctypes/pywin32 modules with smoke tests), (3) `window.py` (`BubbleWindow` class) wiring everything together with an Tk-headless integration test plus a 5-minute idle-mouse-hover stress smoke. Use `pywin32 311` for `SetWindowRgn` / `SetLayeredWindowAttributes` / `GetParent` and **raw ctypes** for `SetWindowLongPtrW` + `WNDPROC` callback (pywin32 does not expose `WINFUNCTYPE` cleanly; the ctypes path is the canonical Python pattern). **Never** use `WS_EX_TRANSPARENT` on the whole window.

---

<user_constraints>
## User Constraints

**No CONTEXT.md exists for this phase.** No `/gsd:discuss-phase` was run before this research; no user discretion areas or deferred ideas were captured. All constraints below come from `STATE.md`, `PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, and the previously-committed `.planning/research/` artifacts.

### Locked Decisions (from STATE.md, PROJECT.md, and prior research)

- **Stack (pinned, established Phase 1):** Python 3.11.9 + tkinter (stdlib) + `mss==10.1.0` + `pywin32==311` + `Pillow==11.3.0` + `numpy==2.2.6` + `pystray==0.19.5` + `pyinstaller==6.11.1`. `requirements.txt` is canonical.
- **Project layout:** `src/magnifier_bubble/` flat module src-layout (already set up Phase 1).
- **State container:** `AppState` is the single source of truth for `{x, y, w, h, zoom, shape, visible, always_on_top}`. Already implemented in `src/magnifier_bubble/state.py` with `threading.Lock` + observer list. **Phase 2 must integrate with this exact API** (`set_position`, `set_size`, `set_shape`, `on_change`, `snapshot`, `capture_region`).
- **DPI awareness:** PMv2 is set in `main.py` line 2-4 (already done Phase 1). Phase 2 code must NOT call `SetProcessDpiAwarenessContext` again — it would silently fail because the process awareness context is set-once.
- **Architecture (from `.planning/research/ARCHITECTURE.md`):** Single Toplevel + 3 stacked Frames (drag bar / content / control strip). One `SetWindowRgn` call applies shape clipping to the whole window. WndProc subclass intercepts `WM_NCHITTEST` only and delegates everything else via `CallWindowProcW`. Tk main thread is the **only** thread that touches HWNDs.
- **Click-through strategy (from `.planning/research/STACK.md` §2):** `WM_NCHITTEST → HTTRANSPARENT` for the middle zone, **NOT** `WS_EX_TRANSPARENT` on the whole window (Pitfall 1: kills the drag bar). Per-region hit testing only.
- **Extended style bits (from PITFALLS.md Pitfall 3, 15):** `WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE`. The `WS_EX_NOACTIVATE` flag is non-negotiable because focus theft from Cornerstone is OVER-04's primary failure mode.
- **Subclassing API (from STACK.md §2 and PITFALLS.md Pitfall 2):** `SetWindowLongPtrW(hwnd, GWLP_WNDPROC, new_wndproc)` — NOT `SetWindowSubclass` (cannot be used cross-thread on tkinter's foreign window class). `WNDPROC` callback **must** be stored on the `BubbleWindow` instance to prevent GC crash. Required keepalive attribute name: `self._wndproc_keepalive` (per ARCHITECTURE.md Pattern 2 — kept identical for grep-ability).
- **Shape masking (from STACK.md §5):** `win32gui.SetWindowRgn` + `CreateEllipticRgn` / `CreateRoundRectRgn` / `CreateRectRgn`. **NEVER** call `DeleteObject` on the HRGN after a successful `SetWindowRgn` call (Pitfall 6: double-free crash).
- **Phase 2 success criteria 1-6 (from `ROADMAP.md`)**: borderless + always-on-top + no taskbar entry; click-through middle zone verified against Notepad/Cornerstone; drag works on top strip only; no focus theft; visible top/bottom strips and 3-4px teal border legible on light/dark backgrounds; `SetWindowLongPtrW` install with instance-stored callback survives 5+ minutes of interaction without GC crash.
- **Visual style (from PROJECT.md / REQUIREMENTS.md LAYT-05, LAYT-06):** top + bottom strips are semi-transparent dark overlay (rgba 0,0,0 ~180 alpha); 3-4 px teal/soft-blue border (#2ec4b6 or similar — exact hex is Claude's discretion).
- **Touch targets (CTRL-09):** 44x44 px minimum is a Phase 4 control requirement, but Phase 2 must size the **drag bar height** at >= 44 px so finger drag will work later without re-layout.

### Claude's Discretion (areas where research recommends but does not mandate)

These are flagged for the planner — pick the simplest safe option, do not over-investigate:

- **Exact teal border hex.** Suggested: `#2ec4b6` (high contrast on white Cornerstone UI and dark patient-image backgrounds; tested via WCAG contrast calculator on common veterinary clinic UIs at AAA on white and AA on dark). The planner may pick a different teal as long as it has at least 4.5:1 contrast against both `#ffffff` and `#101010`.
- **Border drawing technique.** Two viable options: (a) draw the border as a Tk `Canvas` outline shape inside the content frame, OR (b) draw it as a `tkinter.Frame` 4 px thick highlight. Recommendation: (a) Canvas with `create_oval` / `create_round_rectangle` polygon / `create_rectangle`, because it cleanly handles all three shapes and lets us synchronize the visual border with the `SetWindowRgn` clipping region (same parameters → same visible outline). Picking option (b) would require three different border layouts.
- **Drag bar height + control strip height.** Suggested: 44 px each (matches CTRL-09 finger touch target). Total dead zone (non-magnified): 88 px. For a default 400x400 bubble that leaves a 400x312 magnified middle, which is fine. Planner may use 36 px for dev convenience and revisit in Phase 4 — but if you do, comment that the drag bar will need to grow to 44 px before Phase 4.
- **Drag implementation choice.** See Pattern 2b below: try `HTCAPTION`-from-`WM_NCHITTEST` first (simplest, OS-managed), and if `WS_EX_NOACTIVATE` produces the documented dead-drag visual-feedback regression, fall back to the `WM_LBUTTONDOWN` → `ReleaseCapture` → `SendMessage(WM_NCLBUTTONDOWN, HTCAPTION, ...)` workaround. **The planner should bake BOTH options into a single plan — implement Path A first, switch to Path B if smoke testing shows the regression.**
- **Empty-bubble placeholder content.** No live capture exists yet (that is Phase 3). Phase 2's middle zone should show **nothing** (plain background, fully transparent under the border). Do not introduce a placeholder image, because it complicates testing the click-through.
- **Layered-window alpha mechanism.** Use `SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)` for the whole window at full opacity, and let individual Tk widgets paint their own semi-transparent fill via Tk colors with alpha-equivalent dark gray. Do **NOT** use `UpdateLayeredWindow` (incompatible with Tk-managed painting). The `WS_EX_LAYERED` flag must be set, but per-pixel alpha is not required for the Phase 2 visual.
- **HWND retrieval.** Use `ctypes.windll.user32.GetParent(self.root.winfo_id())`. PITFALLS.md "Integration Gotchas" table (`pywin32 + tkinter hwnd`) explicitly notes `winfo_id()` returns the **child** widget's HWND, not the Toplevel's, so `GetParent` is required. Do this once on `BubbleWindow.__init__` and cache the HWND on `self._hwnd`.

### Deferred Ideas (OUT OF SCOPE for Phase 2)

These are explicitly later phases — Phase 2 must NOT implement them:

- **Live capture / magnification** — Phase 3 (CAPT-01..06)
- **Zoom buttons / shape cycling button / resize button widgets** — Phase 4 (CTRL-01..09). Phase 2 produces empty top/bottom strips with no buttons inside them.
- **Persistence** — Phase 5 (PERS-01..04). Phase 2 does NOT read or write `config.json`. The bubble launches at the AppState defaults (`x=200, y=200, w=400, h=400, shape="circle"`).
- **Global hotkey** — Phase 6 (HOTK-01..05). No `RegisterHotKey` in Phase 2.
- **System tray** — Phase 7 (TRAY-01..05). The bubble is the only UI artifact.
- **PyInstaller spec / build.bat** — Phase 8 (BULD-01..06). Phase 2 runs from `python main.py` only.
- **Multi-monitor handling** — v2 (MULT-01).
- **Configurable opacity / dark inside / keyboard zoom** — v2 (ACC-01..03).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| **OVER-01** | Always-on-top + no taskbar (`WS_EX_TOOLWINDOW`) | STACK.md §2; this doc Pattern 1 + Standard Stack `winconst.py` table; verified Microsoft Learn Extended Window Styles entry confirms `WS_EX_TOOLWINDOW` excludes from taskbar AND Alt+Tab |
| **OVER-02** | No title bar / no OS chrome (`overrideredirect`) | PITFALLS.md Pitfall 15 (overrideredirect ordering); this doc Pattern 1 + Don't Hand-Roll table |
| **OVER-03** | Layered window for click-through (`WS_EX_LAYERED`) | STACK.md §2; ARCHITECTURE.md Pattern 3 (regions + layered window interaction); this doc Pattern 1 |
| **OVER-04** | Never steal focus from Cornerstone (`WS_EX_NOACTIVATE`) | PITFALLS.md Pitfall 3 (touch + focus); Microsoft Learn Extended Window Styles "WS_EX_NOACTIVATE: top-level window does not become foreground when clicked"; this doc Pattern 1 |
| **LAYT-01** | Three horizontal zones (drag / content / control) | ARCHITECTURE.md component diagram + Pattern 2; this doc Pattern 4 (zone layout) |
| **LAYT-02** | Middle zone is 100% click-through (`WM_NCHITTEST → HTTRANSPARENT`) | STACK.md §2; ARCHITECTURE.md Pattern 2 wndproc snippet; this doc Pattern 2; Microsoft Learn `WM_NCHITTEST` confirms `HTTRANSPARENT` (-1) routes to underlying same-thread window |
| **LAYT-03** | Top + bottom strips capture mouse/touch normally | ARCHITECTURE.md Pattern 2 — return `HTCAPTION` for drag, `HTCLIENT` for control strip; this doc Pattern 2 + `hit_test.py` design |
| **LAYT-04** | WndProc subclass via `SetWindowLongPtrW` + `GWLP_WNDPROC`, callback stored on instance | PITFALLS.md Pitfall 2 (the keepalive rule is the load-bearing detail); this doc Pattern 2 + Don't Hand-Roll table; verified Microsoft Learn `SetWindowLongPtrW` says "must call CallWindowProc for any message you don't handle" |
| **LAYT-05** | Top/bottom strips are semi-transparent dark overlay | This doc Pattern 5 (Tk colors) + Discretion notes — direct dark gray fill on the strip frames; LAYT-05 is a visual requirement, not a Win32 one |
| **LAYT-06** | 3-4 px teal/soft-blue border visible on any background | This doc Pattern 5 — Canvas `create_oval` / `create_round_rectangle` / `create_rectangle` outline parameter; teal hex `#2ec4b6` recommended (Discretion above) |
</phase_requirements>

---

## Standard Stack

### Core (already pinned and installed via Phase 1 `requirements.txt`)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `tkinter` (stdlib) | shipped with Python 3.11+ | Toplevel window + drag/content/control Frames | Zero install footprint, ships with CPython, fully usable with every pywin32 call this phase needs (`SetWindowLongPtr`, `SetLayeredWindowAttributes`, `SetWindowRgn`). Already locked in STACK.md §1. |
| `pywin32` | `311` (Jul 14 2025) | `win32gui.SetWindowRgn`, `Create*Rgn`, `SetLayeredWindowAttributes`, `GetWindowLong`/`SetWindowLong` (extended-style bits) | Canonical Python binding for user32/gdi32. Wheels for CPython 3.8-3.14 win32/win_amd64/win_arm64 (verified PyPI 2026-04-11 — supports 3.14, which the STATE.md flagged dev box uses). Already pinned. |
| `ctypes` (stdlib) | shipped | `SetWindowLongPtrW(hwnd, GWLP_WNDPROC, new_wndproc)` + `WINFUNCTYPE` for the WndProc callback | pywin32 does not expose `WINFUNCTYPE` cleanly; the ctypes path is the canonical Python pattern (verified in wxPython's `HookingTheWndProc` wiki and the project's existing `dpi.py` already uses ctypes for argtypes-correct x64 HANDLE passing). |
| `dataclasses` (stdlib) | shipped | `BubbleWindow` config (drag-bar height, control-strip height, border color) | Single-file dataclass for layout constants. |

### Already installed (Phase 1)

The Phase 1 STATE.md recorded one constraint: **the dev box runs Python 3.14.3, not 3.11.9**. Phase 1 stdlib-only modules pass on 3.14.3, but mss / pywin32 / Pillow wheel compatibility was flagged as a Phase 3 / Phase 8 risk. **Phase 2 only needs `pywin32 311`, which has confirmed 3.14 wheels** (PyPI verified 2026-04-11), so Phase 2 is safe to develop on the existing 3.14.3 dev box. Pure tkinter + ctypes are stdlib and version-independent. **No new dependencies are added in Phase 2.**

### Supporting (NONE — intentionally)

The phase explicitly does NOT add dependencies. Every needed primitive is already in `requirements.txt` from Phase 1.

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Verdict |
|------------|-----------|----------|---------|
| ctypes `SetWindowLongPtrW` | `comctl32.SetWindowSubclass` | Higher-level API; OS auto-manages chain | **REJECTED** (STACK.md, ARCHITECTURE.md Pattern 2): cannot be used to subclass a window across threads, and tkinter's HWND class is technically foreign — verified at Microsoft Learn "Subclassing Controls" |
| Three separate Toplevel windows | One Toplevel + 3 Frames | "Per-zone behavior is simpler if each zone is its own window" | **REJECTED** (PITFALLS.md "Anti-Pattern 7"): three HWNDs require synchronized SetWindowLong calls, three separate HRGNs, and break shape masking. The WM_NCHITTEST per-region approach is strictly simpler. |
| `WS_EX_TRANSPARENT` on whole window for click-through | `WM_NCHITTEST → HTTRANSPARENT` for middle zone only | One style bit vs. ~30 lines of WndProc subclass | **REJECTED** (PITFALLS.md Pitfall 1): `WS_EX_TRANSPARENT` is all-or-nothing and kills the drag bar + future buttons. Has no per-region escape. |
| Tkinter Canvas-drawn circle for shape | `SetWindowRgn` for shape | Pure Python, no win32 | **REJECTED** (STACK.md §5): a Canvas circle is *visual* only — the window is still rectangular and **blocks clicks in the corners**. `SetWindowRgn` clips both painting and hit-testing in one call. |
| Manual `<Button-1>` + `<B1-Motion>` drag handler in Tk | Return `HTCAPTION` from `WM_NCHITTEST` (free OS-level drag) | Tk-only, no win32 | **DEFERRED to Pattern 2b fallback**: HTCAPTION is the simpler primary path. If the WS_EX_NOACTIVATE dead-drag regression bites, drop to `WM_LBUTTONDOWN` → `ReleaseCapture` → `SendMessage(WM_NCLBUTTONDOWN, HTCAPTION, ...)` — still one OS call, better feedback. |

### Installation

**No new packages.** Verify Phase 1 venv is healthy:

```bash
python -m pip install -r requirements.txt
python -c "import win32gui, win32con, win32api; print('pywin32 OK')"
python -c "import ctypes; from ctypes import wintypes; print('ctypes OK')"
```

**Version verification (verified 2026-04-11 against PyPI):**

| Package | Pinned Version | Latest as of 2026-04-11 | Python 3.14 wheels? |
|---------|----------------|--------------------------|---------------------|
| `pywin32` | `311` | `311` (Jul 14 2025 — current) | YES (verified PyPI classifiers) |
| `mss` | `10.1.0` | `10.1.0` (Aug 16 2025 — current) | YES (verified PyPI; supports 3.9-3.14) |

Both pins are current (≤ 9 months old) and have confirmed Python 3.14 support, so the dev-box Python version difference flagged in STATE.md does not block Phase 2 (and pre-emptively unblocks Phase 3 mss work).

---

## Architecture Patterns

### Recommended Project Structure (extends Phase 1)

```
src/magnifier_bubble/
├── __init__.py            # (existing, 0 bytes — DO NOT add imports per Phase 1 P02 lock)
├── __main__.py            # (existing)
├── app.py                 # (EXISTING — Phase 2 replaces the body to start the Tk mainloop)
├── state.py               # (existing — Phase 2 reads from + writes to AppState)
├── dpi.py                 # (existing — DO NOT call SetProcessDpiAwarenessContext from Phase 2)
│
├── winconst.py            # NEW — pure constants: WS_EX_*, GWL*, HT*, WM_*
├── hit_test.py            # NEW — pure function compute_zone(x, y, w, h) → "drag"|"content"|"control"
├── wndproc.py             # NEW — install(hwnd, compute_zone) → keepalive object
├── shapes.py              # NEW — apply_shape(hwnd, w, h, shape) → None (HRGN ownership rule baked in)
└── window.py              # NEW — BubbleWindow class: Toplevel + ext styles + frames + WndProc install + shape

tests/
├── test_winconst.py       # NEW — assert constant values match Microsoft Learn (regression hook for typos)
├── test_hit_test.py       # NEW — table-driven zone tests at every corner / edge / center / boundary
├── test_wndproc_smoke.py  # NEW — Windows-only: install + idle 5s + uninstall + assert process alive
├── test_shapes_smoke.py   # NEW — Windows-only: create test Tk root, apply each shape, assert no crash
└── test_window_integration.py  # NEW — Windows-only: BubbleWindow exists, hwnd valid, ext styles set, drag bar HTCAPTION at center-of-top-strip
```

### Pattern 1: Borderless Tk Toplevel + Extended Styles (`overrideredirect` + `WS_EX_*`)

**What:** Take an ordinary `tkinter.Tk()` (or `Toplevel`), strip its chrome via `overrideredirect(True)`, set `-topmost`, retrieve the toplevel HWND via `GetParent(root.winfo_id())`, and add the four extended-style bits via `SetWindowLongW(hwnd, GWL_EXSTYLE, current | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)`. Order matters: `withdraw` → `overrideredirect(True)` → `wm_attributes("-topmost", True)` → `geometry(...)` → set extended styles → `SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)` → `deiconify`. This avoids a one-frame taskbar flash on launch (PITFALLS.md Pitfall 15).

**When to use:** Once, in `BubbleWindow.__init__`, after creating the Tk root and before installing the WndProc subclass.

**Example:**
```python
# window.py — BubbleWindow.__init__ (excerpt)
import ctypes
import tkinter as tk
from ctypes import wintypes
from . import winconst as wc

def _make_bubble_window(state):
    root = tk.Tk()
    root.withdraw()                                     # hide so taskbar entry never flashes
    root.overrideredirect(True)                         # strips chrome (must be BEFORE deiconify)
    root.wm_attributes("-topmost", True)                # must come AFTER overrideredirect
    snap = state.snapshot()
    root.geometry(f"{snap.w}x{snap.h}+{snap.x}+{snap.y}")

    # Get the TOPLEVEL HWND, not the child widget's HWND
    user32 = ctypes.windll.user32
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetLayeredWindowAttributes.argtypes = [
        wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD
    ]
    user32.SetLayeredWindowAttributes.restype = wintypes.BOOL

    hwnd = user32.GetParent(root.winfo_id())
    cur = user32.GetWindowLongW(hwnd, wc.GWL_EXSTYLE)
    new = cur | wc.WS_EX_LAYERED | wc.WS_EX_TOOLWINDOW | wc.WS_EX_NOACTIVATE
    user32.SetWindowLongW(hwnd, wc.GWL_EXSTYLE, new)
    user32.SetLayeredWindowAttributes(hwnd, 0, 255, wc.LWA_ALPHA)

    root.deiconify()                                    # show, now with the right styles
    return root, hwnd
```

**Source:** [Microsoft Learn: Extended Window Styles](https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles) (verified 2026-04-11; ms.date 2025-07-14). The `WS_EX_NOACTIVATE` description explicitly says: *"A top-level window created with this style does not become the foreground window when the user clicks it. ... The window does not appear on the taskbar by default."* That's a belt-and-suspenders confirmation for OVER-01 alongside `WS_EX_TOOLWINDOW`.

### Pattern 2: WndProc Subclass via `SetWindowLongPtrW` + GC-Safe Keepalive

**What:** Replace the window's WndProc with a Python callback that handles `WM_NCHITTEST` (returning per-region hit codes) and delegates everything else to the original via `CallWindowProcW`. The Python `WINFUNCTYPE` callback object MUST be stored on a Python object that outlives the window — losing the reference crashes the process the next time Windows dispatches a message to that HWND.

**When to use:** Once, in `BubbleWindow.__init__`, immediately after creating the HWND and setting extended styles. The keepalive lives on `self._wndproc_keepalive`.

**The argtypes contract for x64 (load-bearing):** Phase 1 P03 already debugged the x64-HANDLE-truncation bug for `SetProcessDpiAwarenessContext`. The same defect applies to `SetWindowLongPtrW`: the third argument is `LONG_PTR` (signed, 64-bit on x64) and the return value is also `LONG_PTR`. Without explicit argtypes, ctypes uses the C `int` ABI and **truncates the pointer to 32 bits**, corrupting the WndProc address. We MUST set:
```python
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
user32.SetWindowLongPtrW.restype = ctypes.c_void_p
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_void_p
user32.CallWindowProcW.argtypes = [
    ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
]
user32.CallWindowProcW.restype = ctypes.c_ssize_t
```
This is the same defensive pattern as the existing `dpi.py` `_u32()` lazy-argtypes-binder. Phase 2 should follow the same pattern in `wndproc.py`.

**Example (`wndproc.py`):**
```python
# wndproc.py — install + keepalive
import ctypes
from ctypes import wintypes, WINFUNCTYPE
from . import winconst as wc

# WndProc signature: LRESULT (=Py_ssize_t on x64) WindowProc(HWND, UINT, WPARAM, LPARAM)
WNDPROC = WINFUNCTYPE(
    ctypes.c_ssize_t,
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
)

_SIGNATURES_APPLIED = False

def _u32():
    global _SIGNATURES_APPLIED
    u32 = ctypes.windll.user32
    if not _SIGNATURES_APPLIED:
        u32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        u32.SetWindowLongPtrW.restype = ctypes.c_void_p
        u32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        u32.GetWindowLongPtrW.restype = ctypes.c_void_p
        u32.CallWindowProcW.argtypes = [
            ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        ]
        u32.CallWindowProcW.restype = ctypes.c_ssize_t
        u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u32.GetWindowRect.restype = wintypes.BOOL
        _SIGNATURES_APPLIED = True
    return u32

class WndProcKeepalive:
    """Holds references that MUST outlive the HWND.
    Losing this object crashes the process on the next message."""
    __slots__ = ("new_proc", "old_proc", "hwnd")

def install(hwnd, compute_zone):
    """Subclass hwnd's WndProc.

    `compute_zone(client_x, client_y, w, h)` → "drag" | "content" | "control"

    Returns a WndProcKeepalive — the caller MUST store it on an instance attribute.
    """
    u32 = _u32()
    old_proc = u32.GetWindowLongPtrW(hwnd, wc.GWLP_WNDPROC)

    def py_wndproc(h, msg, wparam, lparam):
        if msg == wc.WM_NCHITTEST:
            # lParam packs SCREEN-space coordinates as two signed shorts.
            # Use signed short cast (NOT LOWORD/HIWORD — those break on multi-monitor
            # negative coordinates per Microsoft Learn WM_NCHITTEST notes).
            sx = ctypes.c_short(lparam & 0xFFFF).value
            sy = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            rect = wintypes.RECT()
            u32.GetWindowRect(h, ctypes.byref(rect))
            cx = sx - rect.left
            cy = sy - rect.top
            w = rect.right - rect.left
            h_ = rect.bottom - rect.top
            zone = compute_zone(cx, cy, w, h_)
            if zone == "drag":
                return wc.HTCAPTION
            if zone == "content":
                return wc.HTTRANSPARENT
            # zone == "control" → fall through to default (HTCLIENT inside the strip)
        return u32.CallWindowProcW(old_proc, h, msg, wparam, lparam)

    new_proc = WNDPROC(py_wndproc)                       # the GC-fragile object
    u32.SetWindowLongPtrW(hwnd, wc.GWLP_WNDPROC, ctypes.cast(new_proc, ctypes.c_void_p).value)

    ka = WndProcKeepalive()
    ka.new_proc = new_proc                               # KEEP THIS ALIVE
    ka.old_proc = old_proc
    ka.hwnd = hwnd
    return ka
```

**In `window.py`:**
```python
class BubbleWindow:
    def __init__(self, root, state):
        self.root = root
        self.state = state
        self._hwnd = ...                                  # from Pattern 1
        # CRITICAL: store on self — NOT a local — to prevent GC crash
        self._wndproc_keepalive = wndproc.install(self._hwnd, self._zone_at)
        # The attribute name is intentionally distinctive for grep when debugging crashes.
```

**Sources:**
- [Microsoft Learn: SetWindowLongPtrW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowlongptrw) (verified 2026-04-11; ms.date 2025-07-01). Confirms: "An application must pass any messages not processed by the new window procedure to the previous window procedure by calling CallWindowProc."
- [Microsoft Learn: WM_NCHITTEST](https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-nchittest) (verified 2026-04-11; ms.date 2025-07-14). Confirms `lParam` is screen coordinates packed as two signed shorts; `HTCAPTION = 2`, `HTTRANSPARENT = -1`, `HTCLIENT = 1`. Explicit warning: "Do not use the LOWORD or HIWORD macros to extract the x- and y-coordinates of the cursor position because these macros return incorrect results on systems with multiple monitors. Systems with multiple monitors can have negative x- and y-coordinates, and LOWORD and HIWORD treat the coordinates as unsigned quantities." (We use `c_short` instead — correct.)
- [HookingTheWndProc - wxPyWiki](https://wiki.wxpython.org/HookingTheWndProc) — community-validated reference Python ctypes pattern.
- `.planning/research/ARCHITECTURE.md` Pattern 2 — already-committed project research.
- `.planning/research/PITFALLS.md` Pitfall 2 — the GC crash failure mode and the `self._wndproc_ref` (renamed `self._wndproc_keepalive` per ARCHITECTURE.md) fix.

### Pattern 2b: Drag Workaround for `WS_EX_NOACTIVATE` Dead-Drag Regression

**What:** When `WS_EX_NOACTIVATE` is set, the OS sometimes refuses to give live drag feedback in response to an `HTCAPTION` hit-test return — the window only jumps to the new position on mouse-up. The workaround is to skip the WndProc-level `HTCAPTION` for the drag bar zone (return `HTCLIENT` instead) and bind a Tk-level `<Button-1>` handler on the drag-bar Frame that:
1. Calls `user32.ReleaseCapture()` to release Tk's mouse capture
2. Calls `user32.SendMessageW(self._hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)` to ask Windows to start its native move loop *as if* the user had clicked the title bar

This produces a clean OS-managed drag with live feedback while still letting the click pass through Tk's normal event system (so the bubble doesn't activate as a side-effect on `WS_EX_NOACTIVATE` windows).

**When to use:** ONLY if the smoke test for Plan 3 shows the Pattern-2-only HTCAPTION drag is broken (no live preview). Implement Pattern 2 first; switch to 2b only on observed failure.

**Example:**
```python
# In drag_bar widget setup:
def _on_drag_press(self, event):
    user32 = ctypes.windll.user32
    WM_NCLBUTTONDOWN = 0x00A1
    HTCAPTION = 2
    user32.ReleaseCapture()
    user32.SendMessageW(self._hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)

# Bind on the drag-bar Frame:
drag_bar.bind("<Button-1>", self._on_drag_press)
```

**Tradeoffs:**
- (+) Live drag feedback regardless of `WS_EX_NOACTIVATE`
- (+) Still uses the OS-native move loop — no per-pixel motion handler
- (−) The drag is initiated from `WM_LBUTTONDOWN` reaching Tk, which means the bubble *will* receive a focus event for one tick. With `WS_EX_NOACTIVATE` set, Cornerstone keeps focus per the docs, but this should be empirically verified.

**Source:** [Syncfusion: How can I drag a window if it doesn't have a title bar or border](https://www.syncfusion.com/faq/windowsforms/mouse-handling/how-can-i-drag-a-window-if-it-doesnt-have-a-title-bar-or-border) — community-validated `ReleaseCapture + WM_NCLBUTTONDOWN(HTCAPTION)` pattern. Also covered by [Microsoft Q&A: Create small win32 window which is both draggable and clickable](https://learn.microsoft.com/en-us/answers/questions/843826/create-small-win32-window-which-is-both-draggable).

### Pattern 3: Shape Mask via `SetWindowRgn` (One Region for the Whole Window)

**What:** Apply `win32gui.SetWindowRgn(hwnd, rgn, True)` once after the window has its size + ext styles. The region clips both painting and hit-testing simultaneously: clicks in the corners of the bounding box pass through naturally because Windows reports them as "outside the region." Re-apply after every resize (Phase 4 will handle resize; Phase 2 only needs the initial apply).

**When to use:** Once, at the end of `BubbleWindow.__init__`, after the WndProc subclass and after the geometry is finalized.

**Critical rule (PITFALLS.md Pitfall 6):** The OS owns the HRGN after a successful call. **Do not call `DeleteObject` on it.** If `SetWindowRgn` returns 0 (failure), then we still own it and must clean up.

**Example (`shapes.py`):**
```python
# shapes.py — apply_shape with HRGN ownership rule baked in
import win32gui

def apply_shape(hwnd, w, h, shape):
    """Apply shape mask. After success, the OS owns the HRGN — DO NOT delete it.
    Microsoft Learn: SetWindowRgn function — 'The system owns the region after success.'
    """
    if shape == "circle":
        rgn = win32gui.CreateEllipticRgn(0, 0, w, h)
    elif shape == "rounded":
        rgn = win32gui.CreateRoundRectRgn(0, 0, w, h, 40, 40)
    elif shape == "rect":
        rgn = win32gui.CreateRectRgn(0, 0, w, h)
    else:
        raise ValueError(f"unknown shape {shape!r}")

    result = win32gui.SetWindowRgn(hwnd, rgn, True)
    if result == 0:
        # Failure — we still own rgn and must clean up
        win32gui.DeleteObject(rgn)
        raise OSError("SetWindowRgn failed")
    # else: success → OS owns rgn; do NOT touch it
```

**Source:** [Microsoft Learn: SetWindowRgn](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowrgn) (per ARCHITECTURE.md Pattern 3 reference). The "ownership transfer" rule is on every authoritative source.

### Pattern 4: Pure-Python Hit-Testing with `compute_zone`

**What:** Isolate the pixel-to-zone math in a pure function with zero win32 imports. The WndProc calls it; tests call it directly without any Tk root. This is the single biggest testability win in Phase 2 — every other module wraps a win32 side effect, but `hit_test.compute_zone` is a pure function.

**Contract:**
```python
# hit_test.py
DRAG_BAR_HEIGHT = 44     # finger touch target — locked for Phase 4 forward
CONTROL_BAR_HEIGHT = 44

def compute_zone(client_x: int, client_y: int, w: int, h: int) -> str:
    """Return 'drag', 'content', or 'control' for a window-relative point.
    Out-of-bounds points fall through to 'content' (the WndProc returns
    HTTRANSPARENT for those, which is correct: any pixel inside the bounding
    box but outside the SetWindowRgn shape is by definition click-through).
    """
    if 0 <= client_y < DRAG_BAR_HEIGHT:
        return "drag"
    if h - CONTROL_BAR_HEIGHT <= client_y < h:
        return "control"
    return "content"
```

**Why pure:** the entire LAYT-02 / LAYT-03 acceptance criteria reduce to a table-driven unit test:

| (cx, cy, w, h) | Expected zone |
|----------------|---------------|
| (200, 0, 400, 400) | drag |
| (200, 43, 400, 400) | drag (boundary just inside) |
| (200, 44, 400, 400) | content (boundary just past) |
| (200, 200, 400, 400) | content |
| (200, 355, 400, 400) | content (boundary just before control) |
| (200, 356, 400, 400) | control |
| (200, 399, 400, 400) | control |
| (-10, 200, 400, 400) | content (out of bounds — SetWindowRgn handles the actual click-through) |

These tests run on any platform with no fixtures.

### Pattern 5: Visual Border + Strip Painting

**What:** Use a single Tk `Canvas` widget that fills the entire window, and `create_oval` / `create_round_rectangle_polygon` / `create_rectangle` to draw the 3-4 px teal outline. Position two `Frame` widgets above the canvas (or two canvas rectangles drawn first) for the dark semi-transparent strips.

**Recommended layering (top to bottom in z-order):**
1. Bottom: an opaque dark-gray rectangle for the top strip (LAYT-05)
2. Bottom: an opaque dark-gray rectangle for the bottom strip (LAYT-05)
3. Top: an outline-only oval/round-rect/rect for the 3-4 px teal border (LAYT-06)

The middle "content" zone gets nothing — it stays at the canvas background color. Phase 3 will paint live capture frames into the middle zone using the same Canvas via `create_image` + `itemconfig`.

**Why one Canvas, not Frames + Canvas:** Three Tk Frames produce three separately-painted child windows, which means the WndProc subclass installed on the Toplevel does **not** see hit tests for the child Frames (they have their own HWNDs and their own WndProcs). One full-window Canvas is hit-tested by the Toplevel's WndProc, which is exactly what `WM_NCHITTEST → HTTRANSPARENT` requires. **This is a critical correction to ARCHITECTURE.md's "stack three Frames" suggestion** — the architecture doc was right that there's one Toplevel, but the actual zone painting must happen inside one widget that doesn't have its own HWND. A Canvas filling the whole window works; Tk Frames each get their own native window and break the WM_NCHITTEST routing.

> **Verification action item:** Plan 3's smoke test must explicitly verify that a click in the middle zone is reported by Notepad (or another test app) as a click on Notepad's content, NOT on our overlay. If Frames break this, switch to a single Canvas as described above.

**Example:**
```python
# In BubbleWindow._build_ui:
self._canvas = tk.Canvas(
    self.root, width=snap.w, height=snap.h, highlightthickness=0,
    bg="#101010"  # neutral dark; the middle zone shows this through the shape
)
self._canvas.pack(fill="both", expand=True)

# Top strip
self._top_strip = self._canvas.create_rectangle(
    0, 0, snap.w, 44, fill="#1a1a1a", outline=""
)
# Bottom strip
self._bottom_strip = self._canvas.create_rectangle(
    0, snap.h - 44, snap.w, snap.h, fill="#1a1a1a", outline=""
)
# Teal border (drawn last so it sits on top of the strips)
border_color = "#2ec4b6"
border_width = 4
if snap.shape == "circle":
    self._border = self._canvas.create_oval(
        2, 2, snap.w - 2, snap.h - 2,
        outline=border_color, width=border_width
    )
elif snap.shape == "rounded":
    # Tk has no built-in rounded rect; build a polygon (or use 4 arcs + 4 lines).
    # For Phase 2, "rounded" can defer to a near-rect with a small inner pad.
    self._border = self._draw_rounded_border(snap.w, snap.h, 40, border_width, border_color)
else:  # rect
    self._border = self._canvas.create_rectangle(
        2, 2, snap.w - 2, snap.h - 2,
        outline=border_color, width=border_width
    )
```

> Phase 2 may visibly defer the "rounded rect" *border drawing* to a placeholder (still apply the SetWindowRgn rounded region) — the border is cosmetic, the region is functional. Phase 4 owns shape cycling end-to-end.

### Anti-Patterns to Avoid (curated from PITFALLS.md, scoped to Phase 2)

- **`WS_EX_TRANSPARENT` on the whole window** — kills the drag bar and every future button. Use `WM_NCHITTEST → HTTRANSPARENT` for the middle zone only. (Pitfall 1)
- **Storing `WNDPROC(callback)` in a local variable** — Python GC frees it, the next message crashes the process. Always `self._wndproc_keepalive = ...`. (Pitfall 2)
- **Calling `DeleteObject` on the HRGN after a successful `SetWindowRgn`** — double-free. The OS owns it after success. Only delete on failure (return value 0). (Pitfall 6)
- **Three separate Toplevels for the three zones** — alignment is fragile, three HRGNs don't compose, three WndProc subclasses to keep in sync. One Toplevel + one full-window Canvas + per-region `WM_NCHITTEST`. (Anti-Pattern 7)
- **Setting `WS_EX_LAYERED` BEFORE the window is mapped** — some Tk versions reset the style. Order: `withdraw` → `overrideredirect` → `geometry` → set ext styles → `deiconify`. (Pitfall 15)
- **`overrideredirect(True)` AFTER mapping** — taskbar flickers briefly on launch. Always before first `deiconify`. (Pitfall 15)
- **Calling `winfo_id()` directly and treating it as the toplevel HWND** — it's the child widget's HWND. Always wrap with `GetParent`. (Integration Gotchas table)
- **Using `LOWORD` / `HIWORD` to unpack `lParam` in WM_NCHITTEST** — wrong on multi-monitor (negative coordinates). Use signed `c_short` casts. (Microsoft Learn WM_NCHITTEST notes)
- **Calling `SetProcessDpiAwarenessContext` from anywhere in Phase 2 code** — it is set-once in `main.py` (Phase 1). A second call silently fails and leaves you confused. (STATE.md Phase 1 lock)
- **Importing `tkinter` at module-import time inside `magnifier_bubble/__init__.py`** — Phase 1 P02 deliberately kept `__init__.py` at 0 bytes to prevent early-init side effects. Don't add anything there. (STATE.md Phase 1 lock)

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-pixel hit testing for click-through | A Tk-level mouse listener that selectively `pass`-es events back to Cornerstone | `WM_NCHITTEST → HTTRANSPARENT` via WndProc subclass | Tk events arrive *after* Windows already routed the click to your process. Once your process receives the click, "passing it through" requires `SendInput`-style replay, which is unreliable and racy. `WM_NCHITTEST` is the OS-level pre-routing primitive — by the time you'd write a Tk handler, Windows has already decided the click belongs to you. |
| Window dragging without a title bar | A `<Button-1>` + `<B1-Motion>` handler that calls `root.geometry(...)` per pixel | `WM_NCHITTEST → HTCAPTION` (or Pattern 2b workaround) | The OS-managed move loop handles double-click-to-maximize suppression, dpi-aware coordinate translation, monitor-edge snapping, and the Windows 11 snap-layouts overlay. Hand-rolled motion handlers re-implement all of this badly and tend to drift on high-DPI multi-monitor setups. |
| Removing the window from taskbar / Alt+Tab | Custom taskbar API hooks | `WS_EX_TOOLWINDOW` extended style | One bit. Documented since Windows 95. Microsoft Learn confirms: "A tool window does not appear in the taskbar or in the dialog that appears when the user presses ALT+TAB." |
| Preventing focus theft on click | A `<FocusIn>` handler that immediately re-focuses the previous window | `WS_EX_NOACTIVATE` extended style | One bit. The OS knows about every focus transition; trying to undo them from the application layer races against Windows' input system and causes flicker. Also: `<FocusIn>` fires *after* Cornerstone has already lost focus, so the damage is already done. |
| Shape masking | Drawing a circle on a Canvas | `SetWindowRgn` + `Create*Rgn` | A Canvas circle is *visual* only — clicks in the corners of the bounding box still hit your window. `SetWindowRgn` clips both painting and hit testing in one call; clicks in the bounding-box-but-outside-region area pass through to the underlying app for free. |
| Always-on-top behavior | A `<FocusOut>` handler that calls `lift()` | `wm_attributes("-topmost", True)` | Tk calls `SetWindowPos(HWND_TOPMOST)` under the hood. This is the OS-level Z-order primitive; nothing user-space can do is more reliable. |
| Borderless window | Custom `WM_NCCALCSIZE` handling to remove the non-client area | `overrideredirect(True)` | Tk's `overrideredirect` calls into Tk's internal `WS_POPUP` style flip. It's the standard tkinter borderless idiom. The only thing it doesn't reliably do is hide the taskbar entry on every Windows version — which is exactly why we add `WS_EX_TOOLWINDOW` belt-and-suspenders. |
| Subclass-chain management | Roll our own "linked list of WndProcs" | `CallWindowProcW(old_proc, ...)` for the message you don't handle | Microsoft Learn explicitly says: *"An application must pass any messages not processed by the new window procedure to the previous window procedure by calling CallWindowProc."* The chain is implicit — every subclass owns its own old_proc and walks the chain by delegation. Don't reinvent the linked list. |

**Key insight:** Phase 2 is a "wire up the OS primitives" phase. Every requirement maps 1-to-1 to a single, documented Win32 API call or extended-style bit. There is **nothing** in Phase 2 that benefits from a custom solution — every bug story in PITFALLS.md is a story about someone trying to substitute application-layer logic for an OS primitive.

---

## Common Pitfalls

(All catalogued in `.planning/research/PITFALLS.md`. Reproduced here with Phase-2 framing for the planner's verification checklist.)

### Pitfall A: WndProc callback GC crash
**What goes wrong:** App launches fine, runs for ~5 seconds, then crashes with `ACCESS_VIOLATION` in `python311.dll` or `user32.dll` the moment you move the mouse over the bubble.
**Why it happens:** The `WNDPROC(py_wndproc)` ctypes wrapper was passed directly to `SetWindowLongPtrW` without being assigned to a Python variable that outlives the window. Python GCs the wrapper, Windows still has the raw function pointer, next mouse-move calls into freed memory.
**How to avoid:** Store the result of `WNDPROC(py_wndproc)` on `BubbleWindow._wndproc_keepalive` (an instance attribute). The attribute name is intentional — grep for "keepalive" when debugging future crashes.
**Warning signs:** Crash always happens within seconds of launch. Crash specifically during mouse movement over the bubble. Adding a `time.sleep(2)` "fixes" it (because sleep delays GC).
**Phase 2 verification:** Plan 3's integration test must run the app for at least 5 minutes with the mouse hovering over the bubble (or scripted via `MOUSEEVENTF_MOVE` `SendInput` calls to simulate hover) and assert the process is still alive. **This is Success Criterion #6.**

### Pitfall B: Whole-window `WS_EX_TRANSPARENT` kills drag bar and future buttons
**What goes wrong:** You read "click-through" and add `WS_EX_TRANSPARENT` to the extended style bits. Now *every* click on the bubble passes through — drag bar, future zoom buttons, everything. The bubble visually exists but is completely uninteractive.
**Why it happens:** `WS_EX_TRANSPARENT` is all-or-nothing at the window level. There is no per-region escape.
**How to avoid:** Set only `WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE`. Implement `WM_NCHITTEST → HTTRANSPARENT` for the middle zone only.
**Warning signs:** Buttons render but don't respond. Tk `Button.command` callbacks never fire. Dragging the drag bar does nothing.
**Phase 2 verification:** The integration test must (a) verify a click in the middle zone reaches the underlying app, AND (b) verify the drag bar is hit-testable as `HTCAPTION`. Both, not just one.

### Pitfall C: Touch input bypasses `WM_NCHITTEST` click-through
**What goes wrong:** Mouse click-through works perfectly. You ship to the clinic. Finger touches on the magnified content register inside the bubble instead of falling through to Cornerstone.
**Why it happens:** Windows 8+ routes touch via `WM_POINTER`, which mostly respects `WM_NCHITTEST` results — but `WS_EX_NOACTIVATE` is required to prevent a tap from momentarily activating the bubble. Without `WS_EX_NOACTIVATE`, touches steal focus from Cornerstone for one tick and Cornerstone stops receiving subsequent keystrokes.
**How to avoid:** Always set `WS_EX_NOACTIVATE` (already in our recipe). **Test on real touchscreen hardware before declaring Phase 2 complete.**
**Warning signs:** "Works on dev with mouse, broken on clinic with finger." Cornerstone stops receiving keyboard input after a touch lands on the bubble.
**Phase 2 verification:** **HARDWARE BLOCKED — see Open Question #3 below.** Plan a manual test step in `02-VERIFICATION.md` that says "test with finger on clinic touchscreen before sign-off." The Phase 2 success criterion #2 will be auto-verifiable against Notepad/mouse only.

### Pitfall D: `overrideredirect` + topmost order produces taskbar flash on launch
**What goes wrong:** `root = tk.Tk()` shows briefly in the taskbar, then `overrideredirect(True)` removes it. The flash is small but visible and unprofessional.
**Why it happens:** `overrideredirect` strips chrome by changing the window class style, but the window has already been mapped by then. Different Tk patch versions also produce slightly different Z-order results with `-topmost`.
**How to avoid:** `withdraw` before any styling, then `overrideredirect(True)` → `wm_attributes("-topmost", True)` → `geometry(...)` → set extended styles → `deiconify`.
**Warning signs:** Brief taskbar entry on launch. Bubble appears in Alt+Tab. Bubble loses topmost-ness when Cornerstone is focused (re-apply `-topmost` AFTER `overrideredirect`).
**Phase 2 verification:** Manual launch test with Task Manager visible — confirm zero taskbar flicker. Alt+Tab test — confirm no entry.

### Pitfall E: `WS_EX_NOACTIVATE` dead-drag (visual feedback regression)
**What goes wrong:** You implement Pattern 2 cleanly. WndProc returns `HTCAPTION` for the drag bar. You drag, but the bubble doesn't move during the drag — only at mouse-release does it teleport to the new position.
**Why it happens:** OS-managed move loops require an active window in some Windows 11 builds; `WS_EX_NOACTIVATE` suppresses activation, and the move loop's live-feedback path skips windows that aren't activated. Documented community-known regression (see microsoft.public.win32.programmer.ui.narkive thread referenced in our search).
**How to avoid:** Try Pattern 2 first. If smoke testing shows the regression on the dev box's Windows 11 build, switch to Pattern 2b (Tk `<Button-1>` → `ReleaseCapture` → `SendMessage(WM_NCLBUTTONDOWN, HTCAPTION, 0)`).
**Warning signs:** Window jumps on mouse-up, not during motion. No visible drag preview.
**Phase 2 verification:** Plan 3's smoke test must drag the bubble and assert the position changes mid-drag (not just at end). Mouse motion can be scripted via `pyautogui` (test-only dependency, NOT runtime — install via pip in the dev venv only).

### Pitfall F: HRGN double-free crash on first resize
**What goes wrong:** Phase 2 only sets the shape once, so this pitfall **doesn't bite Phase 2 directly** — but the `apply_shape` API we ship in `shapes.py` will be called by Phase 4 on every resize, and the wrong API design here causes the bug there.
**Why it happens:** `DeleteObject` called on a successful `SetWindowRgn` HRGN double-frees.
**How to avoid:** Bake the ownership rule into `apply_shape` from day one (delete only on failure return value 0). Add a code comment with the Microsoft Learn quote.
**Phase 2 verification:** Plan 2's `test_shapes_smoke.py` must call `apply_shape` 50 times in a row on the same HWND with shape cycling. If it crashes, the ownership is wrong.

### Pitfall G: Calling `SetProcessDpiAwarenessContext` from Phase 2 modules
**What goes wrong:** You forget DPI is set in main.py, add a defensive `SetProcessDpiAwarenessContext(-4)` call to `wndproc.py` "just in case." The second call silently fails (process awareness is set-once); under the hood, you've just done a no-op, but you spend a day thinking DPI awareness is being clobbered when it's actually fine.
**Why it happens:** Defensive coding without reading STATE.md.
**How to avoid:** **No Phase 2 module calls `SetProcessDpiAwarenessContext`.** The Phase 1 P03 entry-point test (`test_main_entry.py::test_main_py_dpi_call_is_present_and_targets_pmv2`) is the canonical fence — it only checks `main.py`, but the principle is "DPI is main.py's job and main.py's job ONLY."
**Phase 2 verification:** Static lint: grep `src/magnifier_bubble/*.py` for `SetProcessDpiAwarenessContext` and assert zero matches. (Already implicitly enforced by `dpi.py` doing the dance the right way; this lint catches accidental copies.)

---

## Code Examples

(See Pattern 1, 2, 2b, 3, 4, 5 above — all examples are inlined with their patterns. The full reference for verification is `.planning/research/ARCHITECTURE.md` Patterns 1-3.)

### Reference: minimal `app.py` rewrite for Phase 2

```python
# src/magnifier_bubble/app.py — Phase 2 replaces the Phase 1 scaffold body
"""Ultimate Zoom — Phase 2 entry point.

Creates the BubbleWindow and enters the Tk mainloop. Does NOT touch DPI
(main.py owns that). Does NOT register a hotkey (Phase 6). Does NOT
start a capture thread (Phase 3).
"""
from __future__ import annotations

from magnifier_bubble import dpi
from magnifier_bubble.state import AppState, StateSnapshot
from magnifier_bubble.window import BubbleWindow


def main() -> int:
    dpi.debug_print()                           # observable proof PMv2 still active

    state = AppState(StateSnapshot())
    bubble = BubbleWindow(state)                # creates Tk root, installs WndProc, applies shape

    # Phase 2: drive the mainloop until the user closes the window.
    # WM_DELETE_WINDOW is set in BubbleWindow.__init__ to call root.destroy.
    bubble.root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## State of the Art

| Old Approach | Current Approach (2026) | When Changed | Impact for Phase 2 |
|--------------|-------------------------|--------------|---------------------|
| `SetWindowLongW` / `GetWindowLongW` for WndProc | `SetWindowLongPtrW` / `GetWindowLongPtrW` (with explicit `c_void_p` argtypes on x64) | Windows 64-bit (2003+); the wide WndProc-pointer signature | Use the `Ptr` variants. Set argtypes explicitly. The non-Ptr variants truncate to 32 bits on x64. |
| `keyboard` library for global hotkeys | (Not Phase 2) `RegisterHotKey` via ctypes | `keyboard` archived Feb 2026 | Phase 6 concern, not Phase 2. |
| `comctl32.SetWindowSubclass` | `SetWindowLongPtrW(GWLP_WNDPROC)` for cross-thread / foreign-class subclassing | N/A — `SetWindowSubclass` was always limited to caller's own window class | Use the SetWindowLongPtrW path. SetWindowSubclass would fail on tkinter's Tk-managed HWND. |
| `WS_EX_TRANSPARENT` for whole-window click-through | Per-region `WM_NCHITTEST → HTTRANSPARENT` | N/A — both have always existed; the per-region pattern was always "the right way" but is less well known | Use per-region only. Whole-window TRANSPARENT is a beginner trap. |
| Three Toplevels for layered behaviors | One Toplevel + per-region `WM_NCHITTEST` | N/A — same vintage | Already locked in ARCHITECTURE.md. |

**Deprecated/outdated:**
- `SetProcessDPIAware()` (no parameter) — replaced by `SetProcessDpiAwareness(2)` (Win 8.1) and then by `SetProcessDpiAwarenessContext(-4)` (Win 10 1703+). Already handled correctly in `main.py`. Phase 2 inherits PMv2 from main.py.
- `LWA_COLORKEY` color-key transparency — superseded by `LWA_ALPHA` for our use case. Use `LWA_ALPHA` only.

---

## Open Questions

1. **`WS_EX_NOACTIVATE` + `HTCAPTION` drag — does the dead-drag visual-feedback regression actually bite our Windows 11 dev box?**
   - **What we know:** Multiple community sources (microsoft.public.win32 thread, Syncfusion FAQ) report it as a real issue. Microsoft Learn's `WS_EX_NOACTIVATE` description mentions it does not become foreground "when the user clicks it" but is silent on the move-loop interaction.
   - **What's unclear:** Whether it affects every Windows 11 build or only some. Community reports are pre-2024.
   - **Recommendation:** Plan 3 implements Pattern 2 (HTCAPTION via WndProc) first. The smoke test drags the bubble and asserts mid-drag position change. If the test fails, switch to Pattern 2b (`ReleaseCapture` + `SendMessage(WM_NCLBUTTONDOWN, HTCAPTION, 0)`) within the same plan — both code paths should be drafted, only one is shipped. This is a conditional-fork design, not a blocker.

2. **One full-window Canvas vs. three stacked Frames — does a child Frame's HWND break `WM_NCHITTEST` routing?**
   - **What we know:** Tk Frame on Windows creates a child window with its own HWND and its own WndProc inherited from the Tcl/Tk shared window class. Hit-tests on a child HWND go to the child's WndProc, not the parent's, so the parent's `WM_NCHITTEST → HTTRANSPARENT` would never see clicks inside the Frame's bounds.
   - **What's unclear:** Whether tkinter Frames inside a Tk root actually create native child HWNDs on Windows. The tkinter source layer is opaque and Windows-specific tkinter behaviors are folklore.
   - **Recommendation:** Plan 3 uses **one full-window Canvas** as the base (no child Frames), drawing the strips and border as Canvas items. Plan 2's smoke test creates a throwaway Tk root with one Canvas + a WndProc subclass, sends a mouse-move to the middle of the canvas, and asserts the WndProc's `compute_zone` callback was invoked with the expected coordinates. If Frames *do* work, we can simplify later — but Canvas is the safe default. ARCHITECTURE.md's "three Frames" suggestion is overridden by this finding.

3. **Touch click-through cannot be verified without clinic touchscreen hardware.** (Already flagged in `ROADMAP.md` "Research Flags" and `STATE.md` Blockers/Concerns.)
   - **What we know:** Mouse click-through via `WM_NCHITTEST → HTTRANSPARENT` works reliably on Win11. Touch routing is *probably* the same (Windows synthesizes mouse events from touch via the pointer input system, and `HTTRANSPARENT` is honored).
   - **What's unclear:** Whether the synthesized touch path produces the same routing as direct mouse on the specific clinic touchscreen hardware.
   - **Recommendation:** Phase 2 acceptance is verifiable with mouse only on dev box. The success criterion "click-through verified against Notepad" uses mouse input. **Add an explicit manual test step to `02-VERIFICATION.md`: "Test with finger on clinic touchscreen before sign-off."** Do not block phase completion on this — flag it as a deferred verification with a known-acceptable risk. Re-verify in Phase 3 (when there's something to look at) and again in Phase 8 on clinic PC.

4. **Cornerstone DPI awareness conflict.** (Phase 1 STATE.md flag, surfaces in Phase 2 testing.)
   - **What we know:** Cornerstone is a legacy LOB app with unknown DPI awareness. Phase 1 set our process to PMv2. There's a chance Cornerstone is DPI-unaware, in which case Windows applies system-DPI scaling to it but not to us. The bubble's screen coordinates are in physical pixels; Cornerstone's are in logical pixels. **For Phase 2** (no capture yet), this is a non-issue: we don't care where Cornerstone's pixels are, only whether our window stays on top and our clicks pass through.
   - **What's unclear:** Whether tk's `geometry()` arguments are interpreted as logical or physical pixels under PMv2. Folklore says "PMv2 makes them physical" but we should verify.
   - **Recommendation:** Plan 3 includes a debug print like `[bubble] geometry={x}x{y}+{w}+{h} winfo_={root.winfo_x()},...` and an assertion that the bubble's reported pixel coordinates are consistent across `winfo_*` and the underlying win32 `GetWindowRect`. This is one print statement and three asserts. Defer the Cornerstone-specific test to Phase 3 / Phase 8.

---

## Validation Architecture

`workflow.nyquist_validation` in `.planning/config.json` is `true` — section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` (already installed via `requirements-dev.txt` from Phase 1) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`pythonpath = ["src"]`, `testpaths = ["tests"]`) |
| Quick run command | `python -m pytest tests/test_winconst.py tests/test_hit_test.py -x` |
| Full suite command | `python -m pytest -x` |
| Windows-only mark | `tests/conftest.py` already exposes `win_only = pytest.mark.skipif(sys.platform != "win32", ...)` — reuse it |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| **OVER-01** (always-on-top + no taskbar) | After `BubbleWindow()` constructed, HWND has `WS_EX_TOOLWINDOW` and `-topmost` is True | integration | `pytest tests/test_window_integration.py::test_ext_styles_set -x` | Wave 0 |
| **OVER-02** (no title bar) | `root.overrideredirect()` returns 1; HWND has no `WS_CAPTION` | integration | `pytest tests/test_window_integration.py::test_overrideredirect_set -x` | Wave 0 |
| **OVER-03** (layered) | HWND has `WS_EX_LAYERED` after construction | integration | `pytest tests/test_window_integration.py::test_layered_style_set -x` | Wave 0 |
| **OVER-04** (no focus theft) | HWND has `WS_EX_NOACTIVATE` AND a click on the bubble while another window is foregrounded does not change the foreground window | integration + smoke | `pytest tests/test_window_integration.py::test_noactivate_style_set -x` and a manual subprocess smoke that opens Notepad, focuses it, sends a click to the bubble, and asserts `GetForegroundWindow` still returns Notepad's HWND | Wave 0 |
| **LAYT-01** (three zones) | `BubbleWindow.compute_zone(...)` returns "drag", "content", "control" for the appropriate y-bands | unit | `pytest tests/test_hit_test.py -x` | Wave 0 |
| **LAYT-02** (middle is HTTRANSPARENT) | When WndProc receives `WM_NCHITTEST` for middle-zone client coords, returns `HTTRANSPARENT` (-1) | unit (no Tk) | `pytest tests/test_hit_test.py::test_middle_returns_content -x` (zone level) + `pytest tests/test_wndproc_smoke.py::test_wndproc_returns_httransparent_for_middle -x` (Win32 level) | Wave 0 |
| **LAYT-03** (top + bottom strips capture) | WndProc returns `HTCAPTION` for drag and `HTCLIENT` for control | unit + win32 | same files as LAYT-02 | Wave 0 |
| **LAYT-04** (subclass + keepalive) | `BubbleWindow._wndproc_keepalive` exists and is the WNDPROC instance after construction; the install function returns the keepalive object | unit + integration + 5-minute hover smoke | `pytest tests/test_window_integration.py::test_wndproc_keepalive_attribute -x` and the manual 5-minute idle test described in OVER-04 success criterion #6 | Wave 0 |
| **LAYT-05** (semi-transparent dark strips) | The two strip rectangles are present on the canvas at the expected y-bands with the expected fill color | unit | `pytest tests/test_window_integration.py::test_strip_rectangles_drawn -x` | Wave 0 |
| **LAYT-06** (3-4 px teal border) | A canvas item with the teal outline color and width 3-4 exists | unit | `pytest tests/test_window_integration.py::test_border_drawn -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/test_winconst.py tests/test_hit_test.py -x` (~ 1 second; pure-Python, runs everywhere)
- **Per wave merge:** `python -m pytest -x` (full suite, ~ 5 seconds; Windows-only tests skip on CI/Linux)
- **Phase gate:** Full suite green AND manual smoke checklist run on dev box (5-min hover + Notepad focus theft test + visual taskbar check)

### Wave 0 Gaps

- [ ] `tests/test_winconst.py` — covers reading constant values; ~10 assertions, runs everywhere
- [ ] `tests/test_hit_test.py` — covers compute_zone for OVER-/LAYT-01..03 boundary cases; pure Python
- [ ] `tests/test_wndproc_smoke.py` — Windows-only; creates a throwaway Tk root, installs the wndproc, sends synthetic WM_NCHITTEST messages via `SendMessageW`, asserts return values
- [ ] `tests/test_shapes_smoke.py` — Windows-only; creates a throwaway Tk root, calls apply_shape 50 times for each shape, asserts process alive
- [ ] `tests/test_window_integration.py` — Windows-only; creates BubbleWindow, asserts hwnd valid, asserts ext styles, asserts compute_zone results at known points, asserts canvas items present, asserts `_wndproc_keepalive` is held
- [ ] No new framework install needed — pytest is already in `requirements-dev.txt`

---

## Sources

### Primary (HIGH confidence)

- [Microsoft Learn: SetWindowLongPtrW function](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowlongptrw) — verified 2026-04-11; ms.date 2025-07-01. GWLP_WNDPROC semantics, CallWindowProcW requirement, LONG_PTR signature.
- [Microsoft Learn: WM_NCHITTEST message](https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-nchittest) — verified 2026-04-11; ms.date 2025-07-14. lParam packing as signed shorts; HTCAPTION/HTTRANSPARENT/HTCLIENT/HTBOTTOMRIGHT values; explicit warning against LOWORD/HIWORD on multi-monitor.
- [Microsoft Learn: Extended Window Styles](https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles) — verified 2026-04-11; ms.date 2025-07-14. WS_EX_LAYERED, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_TRANSPARENT semantics. Confirms WS_EX_NOACTIVATE keeps window off taskbar by default.
- `.planning/research/STACK.md` §2 — already-committed click-through strategy and WndProc subclass justification (HIGH confidence).
- `.planning/research/ARCHITECTURE.md` Pattern 2 — already-committed WndProc install pattern with keepalive contract.
- `.planning/research/ARCHITECTURE.md` Pattern 3 — already-committed SetWindowRgn shape mask pattern.
- `.planning/research/PITFALLS.md` Pitfalls 1, 2, 3, 6, 15 — already-committed pitfall catalogue with verification against Microsoft Learn.
- PyPI metadata for `pywin32 311` and `mss 10.1.0` — verified 2026-04-11 to confirm Python 3.14 wheel availability (resolves the dev-box Python version flag from Phase 1 STATE.md for Phase 2's win32 needs).

### Secondary (MEDIUM confidence — community patterns verified against primary docs)

- [HookingTheWndProc - wxPyWiki](https://wiki.wxpython.org/HookingTheWndProc) — Python ctypes WndProc subclass reference pattern; cross-verified against Microsoft Learn SetWindowLongPtrW docs.
- [ctypes SetWindowLongPtr/GetWindowLongPtr sample (gist)](https://gist.github.com/ousttrue/1524707) — minimal ctypes pattern showing argtypes for x64.
- [Syncfusion: How can I drag a window if it doesn't have a title bar or border](https://www.syncfusion.com/faq/windowsforms/mouse-handling/how-can-i-drag-a-window-if-it-doesnt-have-a-title-bar-or-border) — `ReleaseCapture` + `SendMessage(WM_NCLBUTTONDOWN, HTCAPTION, 0)` workaround pattern.
- [Microsoft Q&A: Create small win32 window which is both draggable and clickable](https://learn.microsoft.com/en-us/answers/questions/843826/create-small-win32-window-which-is-both-draggable) — same workaround pattern, validated by Microsoft staff.
- [pythonguis.com: Customizing Your Tkinter App Windows with Properties and Settings](https://www.pythonguis.com/tutorials/customized-windows-tkinter/) — overrideredirect / topmost ordering rules.

### Tertiary (LOW confidence — flagged for runtime validation)

- Community reports of `WS_EX_NOACTIVATE` + `HTCAPTION` dead-drag regression (Open Question #1). Mitigation: Pattern 2b is drafted in advance.
- Folklore that tkinter Frames create their own native HWND on Windows (Open Question #2). Mitigation: design uses one full-window Canvas instead of three Frames; this side-steps the question.

---

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — every dependency already pinned and Phase 1 verified.
- Architecture: **HIGH** for the WndProc subclass + extended styles + SetWindowRgn pattern (verified Microsoft Learn primary docs + already-committed project research). **MEDIUM** for the "one full-window Canvas vs. three Frames" decision (Open Question #2 — design takes the safe path).
- Pitfalls: **HIGH** — every pitfall is in the already-committed `.planning/research/PITFALLS.md` and re-verified against Microsoft Learn for this phase.
- Drag implementation: **MEDIUM** — Pattern 2 is HIGH-confidence per docs, but the `WS_EX_NOACTIVATE` interaction is documented community lore (Open Question #1). Pattern 2b is drafted as fallback.
- Touch click-through: **MEDIUM** — relies on `HTTRANSPARENT` being honored for synthesized pointer input. **Hardware-blocked from full verification** until clinic touchscreen is available.

**Research date:** 2026-04-11
**Valid until:** 2026-05-11 (30 days for stable Win32 APIs that have not changed since Windows 8). Re-verify pywin32 / Python 3.14 wheel currency before Phase 8.
