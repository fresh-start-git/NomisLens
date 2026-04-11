# Phase 1: Foundation + DPI - Research

**Researched:** 2026-04-11
**Domain:** Windows DPI awareness + Python project scaffold + dataclass state container
**Confidence:** HIGH

---

## Summary

Phase 1 is deceptively simple on the surface — scaffold a Python project, pin requirements, and create an AppState container — but has one load-bearing detail: **`SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)` must be the first executable statement of `main.py`, before any module that might set DPI awareness on its own (mss, PIL.ImageGrab, pyautogui, tkinter.Tk).** Miss this and every downstream phase silently breaks on 125%/150% clinic displays: mss captures the wrong pixels, the bubble's on-screen position drifts from the capture region, and the app ships "works on dev / broken at clinic."

Microsoft Learn is explicit that **the DPI awareness mode of a process cannot be changed after it has been set once** (either by manifest or by API). Some Python packages (`mouseinfo`, `pyautogui`, `pyscreeze`, and — crucially — **`mss` itself on `MSSImplWindows.__init__()`**) call `SetProcessDpiAwareness(2)` = Per-Monitor (V1), which is a *weaker* level than V2. If `mss.mss()` is instantiated before we set PMv2, we are permanently locked to V1 and lose the V2-only goodies (child HWND DPI-change notifications, non-client area scaling, proper WM_DPICHANGED routing). So the order of operations in `main.py` is non-negotiable: `ctypes` first, `SetProcessDpiAwarenessContext(-4)` first, then everything else.

**Primary recommendation:** Write `main.py` with a 6-line header (ctypes import → `SetProcessDpiAwarenessContext(-4)` with graceful fallback ladder → then imports). Parallel-belt-and-braces by also embedding a `<dpiAwareness>PerMonitorV2</dpiAwareness>` manifest in the PyInstaller spec (Phase 8, but documented here). Build a `src/magnifier_bubble/` src-layout package. Implement `AppState` as a `@dataclass` with a `threading.Lock` and a simple observer list — no heavyweight state libraries. Pin everything exactly in `requirements.txt`.

---

<user_constraints>
## User Constraints

No CONTEXT.md exists for this phase (research is running standalone or via plan-phase without a prior discuss-phase). Constraints below are lifted from `STATE.md`, `PROJECT.md`, and the research summary already committed under `.planning/research/`.

### Locked Decisions (from STATE.md and prior research)

- **Stack (pinned):** Python 3.11.9 + tkinter (stdlib) + `mss 10.1.0` + `pywin32 311` + `Pillow 11.3.0` + `numpy 2.2.6` + `pystray 0.19.5` + `pyinstaller 6.11.1`
- **DPI API:** `ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)` (Per-Monitor-V2) called BEFORE importing tkinter / mss / Pillow
- **Project layout:** `src/magnifier_bubble/` (src-layout, flat module structure)
- **State container name:** `AppState` — single source of truth for `{x, y, w, h, zoom, shape, visible}` (and `always_on_top` per ARCHITECTURE.md)
- **Resampling (downstream):** Pillow BILINEAR (not LANCZOS) — 3-5x faster
- **PhotoImage pattern (downstream):** single reused instance via `.paste()` — CPython issue 124364
- **Hotkey (downstream):** ctypes + user32.RegisterHotKey (not `keyboard`, not `pynput`)

### Claude's Discretion (this phase)

- **Test framework:** pytest vs stdlib unittest — both acceptable; recommend pytest (see Validation Architecture)
- **Dataclass vs plain class for AppState:** recommend `@dataclass` for the value fields + a wrapper with lock + observers
- **`main.py` at repo root vs `src/magnifier_bubble/__main__.py`:** recommend both (thin `main.py` shim at root for `python main.py` ergonomics, plus `__main__.py` for `python -m magnifier_bubble`)
- **requirements.txt location and split:** recommend single `requirements.txt` at repo root (no split into runtime/dev yet — keep Phase 1 minimal; PyInstaller pin lives here too since README instructs users to install from same file)
- **Logging strategy for the DPI debug print:** plain `print()` to stderr is fine for Phase 1 acceptance; `logging` module can be adopted later
- **venv vs pipx:** venv (project-local, matches clinic deployment flow)

### Deferred Ideas (OUT OF SCOPE for Phase 1)

- BubbleWindow / Toplevel creation (Phase 2)
- WS_EX_LAYERED / WS_EX_TOOLWINDOW / overrideredirect (Phase 2)
- WndProc subclassing (Phase 2)
- mss screen capture loop (Phase 3)
- Zoom controls, shape cycling, resize (Phase 4)
- config.json persistence (Phase 5) — AppState has the fields but no save/load yet
- Global hotkey, system tray (Phases 6, 7)
- PyInstaller spec / manifest / build.bat (Phase 8) — but we note the manifest dpiAwareness entry as a Phase 8 belt-and-braces
- Multi-monitor scaling edge cases (v2, MULT-01)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **OVER-05** | DPI awareness set as first line of main.py (`SetProcessDpiAwarenessContext` Per-Monitor-V2) before any imports | `## Standard Stack → DPI API`, `## Architecture Patterns → Pattern 1 (DPI-First main.py)`, `## Code Examples → main.py header`, `## Common Pitfalls → Pitfall 1 (late DPI awareness)`, `## Don't Hand-Roll → DPI detection loop` |

**Coverage:** 1/1 phase requirements explicitly addressed. All five Phase 1 success criteria from ROADMAP.md map to sections below:

| Success Criterion | Research Section |
|---|---|
| 1. `python main.py` launches & exits cleanly | `## Architecture Patterns → Recommended Project Structure`, `## Code Examples → main.py stub` |
| 2. `SetProcessDpiAwarenessContext(-4)` is first executable line | `## Standard Stack → DPI API`, `## Code Examples → main.py header` |
| 3. Pinned `requirements.txt` installs in clean venv | `## Standard Stack → Installation`, `## Code Examples → requirements.txt` |
| 4. `AppState` holds `{position, size, zoom, shape, visible}` and is the sole mutator | `## Architecture Patterns → Pattern 2 (Single Source of Truth)`, `## Code Examples → state.py` |
| 5. 150% display reports correct logical & physical dimensions | `## Code Examples → DPI debug print`, `## Common Pitfalls → Pitfall 3 (verifying without a 150% display)` |
</phase_requirements>

---

## Standard Stack

### Core (pinned — required by OVER-05 and downstream phases)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | **3.11.9** | Runtime | Last 3.11 with a security-fix cadence acceptable for a local clinic app; most battle-tested CPython for PyInstaller; 3.11.9 ships Tcl/Tk ≥ 8.6.12 which contains the fix for [bugs.python.org/issue45681](https://bugs.python.org/issue45681) (ttk widgets shrinking on hover under DPI awareness). **Do NOT jump to 3.12/3.13 until PyInstaller wheel story matures for all deps.** |
| `ctypes` | stdlib | `SetProcessDpiAwarenessContext`, `GetDpiForMonitor`, `GetScaleFactorForMonitor` | The only dependency-free path to the DPI API in Phase 1; pywin32 is available but pywin32 doesn't expose `SetProcessDpiAwarenessContext` directly, and using ctypes here keeps Phase 1 truly "first executable line" — no heavy imports. |
| `dataclasses` | stdlib | `AppState` value fields | Built-in since 3.7; zero install. |
| `threading` | stdlib | `threading.Lock` around AppState mutations | Needed to satisfy the "capture worker reads while Tk main mutates" pattern documented in ARCHITECTURE.md. |

### Supporting (installed in Phase 1, used in downstream phases)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `mss` | `10.1.0` (2025-08-16) | Screen capture via BitBlt + EnumDisplayMonitors | Phase 3 (Capture Loop). **Install in Phase 1** so `requirements.txt` is complete and the import order can be validated now. |
| `pywin32` | `311` (2025-07-14) | `win32gui.SetWindowLongPtrW`, `SetLayeredWindowAttributes`, `SetWindowRgn`, `CreateEllipticRgn` | Phases 2, 4. Install now. |
| `Pillow` | `11.3.0` | Image resize, ImageTk.PhotoImage | Phase 3. Install now. |
| `numpy` | `2.2.6` | Zero-copy mss → Pillow glue via `frombuffer` | Phase 3. Install now. |
| `pystray` | `0.19.5` | System tray icon | Phase 7. Install now. |
| `pyinstaller` | `6.11.1` | Build to single .exe | Phase 8. **Install now** — clinic deployment README walks the user through one `pip install -r requirements.txt`, not two. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)` | `ctypes.windll.shcore.SetProcessDpiAwareness(2)` (Per-Monitor V1) | V1 is weaker: no child HWND DPI notifications, no automatic non-client scaling, no menu scaling. **Only use as a fallback ladder if V2 is unavailable (Windows < 10 1703).** |
| DPI via ctypes at runtime | DPI via PyInstaller manifest `<dpiAwareness>PerMonitorV2</dpiAwareness>` | Manifest is the Microsoft-preferred approach but runs at OS load time, before Python starts. We use **both**: ctypes for development (`python main.py`) and manifest for the .exe (Phase 8). Belt and braces. |
| `@dataclass` AppState | Plain class with `__init__` | Dataclass is shorter, auto-generates `__eq__`/`__repr__`, and plays well with `asdict()` for the Phase 5 config snapshot. No downside. |
| pinned `requirements.txt` via `pip freeze` | Hand-pinned with package comments | `pip freeze` snapshots the dev environment including transitive deps (numpy → nothing, but Pillow may pull platform-specific wheels). **Recommendation: hand-pin top-level only** (7 lines, one per deliberate choice) — transitive deps resolve on target. `pip freeze` is reproducibility-maximalist but adds churn on every minor numpy patch. |
| Python 3.12 / 3.13 | Python 3.11.9 | 3.12+ has faster subinterpreters and better typing, but 3.11 is what STACK.md validated for PyInstaller 6.11.1 + mss 10.1.0 + pywin32 311 wheel triple-compatibility. Don't bump mid-build. |

### Installation

```bash
# From a clean Python 3.11.9 venv on Windows 11
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# One-time pywin32 postinstall (writes pywintypesXXX.dll into system32 on some installs;
# harmless if already done)
python .venv\Scripts\pywin32_postinstall.py -install
```

### Version Verification (2026-04-11)

Queried PyPI directly — every pinned version is still published and downloadable as of 2026-04-11:

| Package | Pin | Latest on PyPI (2026-04-11) | Verdict |
|---|---|---|---|
| `mss` | 10.1.0 | 10.1.0 (2025-08-16) | **Current** — no newer release |
| `pywin32` | 311 | 311 (2025-07-14) | **Current** — no newer release |
| `Pillow` | 11.3.0 | 12.2.0 | **Safe pin** — 11.3.0 still published; 12.x is newer but we don't need it |
| `numpy` | 2.2.6 | 2.4.4 | **Safe pin** — 2.2.6 still ships cp311 wheels for win_amd64 |
| `pystray` | 0.19.5 | 0.19.5 | **Current** — no release since 2023; Win32 tray API is frozen so staleness is fine |
| `pyinstaller` | 6.11.1 | 6.19.0 (2026-02-14) | **Deliberate back-pin** — 6.11.1 (Nov 2024) is the stable post-AV-cluster baseline per STACK.md; do not bump without re-validating AV behavior |
| Python | 3.11.9 | 3.11.9 is still available from python.org | **Current for 3.11 branch** |

**Verification method:** `pip index versions <package>` and `WebFetch https://pypi.org/project/<package>/`.

---

## Architecture Patterns

### Recommended Project Structure

From `.planning/research/ARCHITECTURE.md` — committed. Phase 1 creates the skeleton; most files are empty or stubs.

```
Ultimate-Zoom/
├── main.py                       # Thin shim → magnifier_bubble.app.main()
├── requirements.txt              # Pinned runtime + build deps
├── .gitignore                    # .venv/, __pycache__/, config.json, dist/, build/
├── src/
│   └── magnifier_bubble/
│       ├── __init__.py           # empty
│       ├── __main__.py           # delegates to app.main() for python -m
│       ├── app.py                # main() entry point (Phase 1: just prints and exits)
│       ├── state.py              # AppState (PHASE 1 DELIVERABLE)
│       ├── winconst.py           # winconst stubs (will grow in Phase 2)
│       ├── dpi.py                # DPI init + debug helpers (PHASE 1 DELIVERABLE)
│       └── (window.py, wndproc.py, hit_test.py, shapes.py, capture.py,
│           hotkey.py, tray.py, config.py, widgets/, ... added in later phases)
├── tests/                        # pytest — created in Phase 1 for validation
│   ├── __init__.py
│   ├── conftest.py               # empty for now
│   ├── test_state.py             # unit tests for AppState
│   └── test_dpi.py               # unit tests + smoke test for dpi.py
└── .planning/                    # (already present)
```

**Phase 1 rationale:**
- `main.py` at repo root is **the literal file named in OVER-05 and every success criterion**. Keeping it as a 3-line shim that calls into `src/magnifier_bubble/app.py` means the "first executable line of main.py" criterion is satisfied by that shim and the bulk of code lives in a proper importable package.
- `src/` layout prevents PyInstaller shadow-import bugs (Phase 8 concern, worth front-loading).
- `tests/` is sibling to `src/` so `pytest` Just Works with no config.

### Pattern 1: DPI-First `main.py` Header

**What:** `main.py` is a 6-line file. Line 1 is `import ctypes`. Line 2 is the DPI call with a fallback ladder. Line 3-4 is the fallback chain. Only after those lines does anything else import.

**When to use:** Always, in every Python entry point that uses tkinter, mss, or any screen-coordinate API on Windows. This is not a "best practice"; it is load-bearing for OVER-05 correctness.

**Why `main.py` and not `app.py`:** Because mss, Pillow, tkinter, and even `magnifier_bubble.app` itself all trigger imports that may touch DPI state. The DPI call has to happen **before** any `import magnifier_bubble.*`. Therefore the entry point must be a bare script, not a package import. A thin shim at repo root satisfies OVER-05 without polluting the package.

**Example:**
```python
# main.py — ENTIRE FILE, no module docstring at top (see note below)
import ctypes
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
except (AttributeError, OSError):
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor V1 (Win 8.1+)
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()        # System-aware (legacy)

from magnifier_bubble.app import main
main()
```

**Important nuance about "first executable line":** A module docstring (`"""..."""` at the very top of the file) is a *string literal expression* that Python evaluates as part of module load but does not execute any user code from. It is acceptable to have a docstring before `import ctypes` — it does not count as "executable" in the sense OVER-05 means. **However**, to remove all ambiguity during verification, put the DPI call before the docstring, or omit the docstring from `main.py` and put it on `magnifier_bubble.app.main()` instead. Recommendation: **no docstring on `main.py`; `import ctypes` is literally line 1**.

### Pattern 2: Single Source of Truth AppState

**What:** `AppState` is the one place every other module reads and writes `(x, y, w, h, zoom, shape, visible, always_on_top)`. Use `@dataclass` for the field definitions and wrap with a class that owns a `threading.Lock` and an observers list.

**When to use:** Every setter that changes a value the user would persist across restarts (Phase 5), or that another thread reads (Phase 3 capture), or that another thread would want to trigger (Phase 6 hotkey toggling visible). Phase 1 builds the container; downstream phases subscribe.

**Why not `pydantic.BaseModel` or `attrs`:** Both are better for JSON serialization but pull in a full installed dependency. `dataclasses.asdict()` (Phase 5) gives us the same snapshot API for free. Zero new deps = lower PyInstaller .exe size = less AV surface.

**Thread-safety model:** "Writes from Tk main thread only; worker threads read under the same lock, or route mutations back via `root.after(0, ...)`." This is enforced at the architecture-invariant level (ARCHITECTURE.md lists it as an explicit invariant), not at the AppState API level, because runtime thread-identity assertions in Python are noisy.

**Example** (see `## Code Examples → state.py` below).

### Pattern 3: DPI Verification Module

**What:** A small `dpi.py` module that exposes:
- `init() -> None` — idempotent (re)assertion of the DPI context, raising if the process is already locked to a weaker level
- `report() -> dict` — returns `{monitor_count, awareness_context_value, logical_size, physical_size, scale_factor}` for the debug print that satisfies Phase 1 Success Criterion #5

**Why a separate module:** Because the debug print and the smoke test and the `main.py` header all need to reference the same DPI constants. Keeping them in `magnifier_bubble/dpi.py` gives one import surface; `main.py` still has to do its own `ctypes` call because of the import-order constraint, but everything else (debug print, tests) uses `dpi.report()`.

**Caveat:** `dpi.init()` from inside a package module **will not satisfy OVER-05** — the spec says the call must be in `main.py`. `dpi.init()` is a *safety net* that raises if somehow the module is imported without main.py first (e.g., pytest direct import). It is NOT the primary DPI call.

### Anti-Patterns to Avoid

- **Module docstring on `main.py`** — creates ambiguity about "first executable line"; an auditor looking at line 1 should see `import ctypes`, not `"""Ultimate Zoom — entry point"""`.
- **`from magnifier_bubble import *` at the top of `main.py`** — kills any chance of DPI being first; `magnifier_bubble` transitively imports tkinter.
- **Catching `Exception`** on the DPI call — we catch `(AttributeError, OSError)` specifically. A bare `except:` hides genuine programmer errors and makes the fallback ladder silently degrade.
- **Setting DPI awareness twice** — Microsoft Learn explicitly: *"Once API awareness is set for an app, any future calls to this API will fail."* The fallback ladder uses exception flow, not "try multiple, keep the best," because the second call will always return `ERROR_ACCESS_DENIED` and corrupt the fallback logic.
- **Creating a global `mss.mss()` at module scope** — if `src/magnifier_bubble/__init__.py` accidentally imports `mss`, `mss.mss()` may be constructed during package init, which calls `SetProcessDpiAwareness(2)` (V1). Then the `main.py` ctypes call on V2 will fail silently because V1 got there first. **Rule:** `__init__.py` stays empty; mss is only imported inside `capture.py` (Phase 3).
- **Using `os.environ["PYTHONDONTWRITEBYTECODE"]` or any envvar hack** — unnecessary here; just don't do it.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Detecting DPI scale per monitor | Custom EnumDisplayMonitors + GetDeviceCaps loop | `ctypes.windll.user32.GetDpiForMonitor(hmon, 0, ...)` / `GetDpiForWindow(hwnd)` | Microsoft-authored; handles every edge case of mixed-DPI setups; widely documented on Microsoft Learn. Rolling your own EnumDisplayMonitors loop is a classic "works on dev laptop, breaks on clinic" pit. |
| Setting DPI awareness level | Copy-pasted `if windows_version >= 10:` detection | Try/except ladder on `SetProcessDpiAwarenessContext` → `SetProcessDpiAwareness` → `SetProcessDPIAware` | Version detection is fragile (Win11 reports as Win10 via many APIs). Try/except is Pythonic, exception-driven, and matches Microsoft's own fallback guidance. |
| Pinned requirements parsing | Writing a `setup.py install_requires=[...]` | Plain `requirements.txt` with `pkg==ver` lines | `install_requires` is for libraries we publish. This is an application. `requirements.txt` + `pip install -r` is what the clinic README says to run; don't add a second source of truth. |
| Thread-safe state container | `queue.Queue` + custom message protocol | `threading.Lock` around an `@dataclass` | Queue is overkill for "write from Tk main, read from capture worker." A Lock has zero ceremony, is the idiom ARCHITECTURE.md already committed to, and won't bite us in Phase 5 config snapshots. |
| JSON config schema validation | Hand-rolled try/except/KeyError chain | `@dataclass` + `dataclasses.asdict()` + `cls(**data_dict)` for load | Phase 5 concern, but Phase 1 AppState design enables it for free if we use dataclass. Don't build a schema library. |
| Observer / pub-sub | Blinker, PyDispatch, RxPy | A plain Python `list[Callable]` on AppState, called synchronously in the setter | The app has 3-4 observers total (BubbleWindow, ConfigStore, maybe TrayService `checked` helper). A list of callables is 8 lines and zero dependencies. |

**Key insight:** Phase 1 is the phase where "just install the library" is most tempting and most wrong. Every dep we add here gets pulled into Phase 8's PyInstaller analysis, bloats the .exe, and adds AV-scan surface. The entire Phase 1 code should be ~200 LOC using nothing but `ctypes`, `dataclasses`, `threading`, and the typing module.

---

## Common Pitfalls

### Pitfall 1: Late DPI Awareness (the entire reason OVER-05 exists)

**What goes wrong:** `SetProcessDpiAwarenessContext(-4)` runs after some other module has already set the process to V1 or System-aware. Microsoft Learn: `ERROR_ACCESS_DENIED` returned; the process is now permanently locked to the weaker level. Downstream: mss captures with logical coordinates, the bubble's `winfo_x/y` doesn't match the capture region, everything visible is offset by 25% (at 125% scaling) or 50% (at 150%).

**Why it happens:**
1. `mss.mss()` in its `__init__` on Windows calls `SetProcessDpiAwareness(2)` = V1. If mss is imported and instantiated before `main.py`'s ctypes call, we lose.
2. `pyautogui`, `mouseinfo`, `pyscreeze` call `SetProcessDpiAware()` = legacy System-aware at import time. None are dependencies of this project, but any one imported transitively (e.g., from a stray `import pyautogui` left over from an experiment) would wreck DPI state.
3. `tkinter.Tk()` does NOT set DPI awareness on Windows (tkinter inherits whatever the process has), but it DOES read the scaling factor once at creation and cache it. So Tk must also be created after the DPI call — which happens naturally in our architecture since `tk.Tk()` lives in Phase 2's `window.py`.
4. PyInstaller embeds a manifest by default; if that manifest has a DPI awareness setting different from what our ctypes call attempts, the .exe's at-OS-load behavior wins. Phase 8 fixes this in the spec.

**How to avoid:**
- `import ctypes` is literally line 1 of `main.py`. `SetProcessDpiAwarenessContext` is line 2.
- `src/magnifier_bubble/__init__.py` is empty — it imports nothing.
- No module under `magnifier_bubble/` imports `mss` at module level; `import mss` happens inside `CaptureWorker.run()` (Phase 3) or inside the `with mss.mss() as sct:` block.
- Add a Phase 1 unit test that does `import main; import magnifier_bubble; <assert process DPI context == -4>`.
- Do NOT embed a docstring at the top of `main.py` to eliminate any auditor ambiguity.

**Warning signs at runtime:**
- `GetLastError() == 5 (ERROR_ACCESS_DENIED)` return from the DPI call.
- `GetDpiForSystem()` returning 96 on a machine the user clearly has set to 125%/150%.
- The debug print in `main()` reports logical size `1920×1080` when Windows Settings says `3840×2160 @ 200%`.

**How to verify:** `ctypes.windll.user32.GetThreadDpiAwarenessContext()` returns a `DPI_AWARENESS_CONTEXT` handle. Compare against `-4`:
```python
ctx = ctypes.windll.user32.GetThreadDpiAwarenessContext()
# ctx is a handle (ssize_t); on Win10+ the sentinel values are -1 .. -5
# Bitwise compare via AreDpiAwarenessContextsEqual
eq = ctypes.windll.user32.AreDpiAwarenessContextsEqual(ctx, -4)
```
Use `AreDpiAwarenessContextsEqual` — pointer identity is unreliable because Windows can return different wrapper handles for the same logical context.

### Pitfall 2: Python 3.11 shipped Tk with an old DPI bug

**What goes wrong:** On very early 3.11.x releases, ttk widgets (Checkbutton especially) rendered at normal size but shrank dramatically on hover when the process was DPI-aware. Described in [bugs.python.org/issue45681](https://bugs.python.org/issue45681).

**Why it happens:** Tk 8.6.10 had a bug in ttk theme scaling under DPI awareness. Fixed in Tk 8.6.11. Python 3.11.0 shipped Tk 8.6.12; **3.11.9 (April 2024) ships Tk 8.6.13** — bug is resolved. But if a user is running an early 3.11.0/3.11.1 install, they may hit it.

**How to avoid:**
- Pin **Python 3.11.9** in README; do not accept "I have Python 3.11" from the user.
- Runtime check in `main.py` or early in `app.main()`: `if tkinter.TkVersion < 8.6 or sys.version_info < (3, 11, 9): warn()` — belt and braces.

**Warning signs:** ttk.Checkbutton (which we may not even use, but any ttk widget) rendering tiny on hover; labels reflowing on mouse enter.

**Verify:** Python 3.14 (what is currently installed on the dev machine) ships Tk 8.6.15, confirmed clean. Phase 1 pins 3.11.9 for deployment but dev work can happen on 3.14 and target 3.11.9.

### Pitfall 3: Verifying DPI correctness without a physical 150% display

**What goes wrong:** Phase 1 Success Criterion #5 says "running on a 150%-scaled display reports logical and physical dimensions that match." Most developers don't have a 150% monitor handy. Temptation: skip the check, "I'll test it before shipping." Reality: you ship broken.

**How to avoid:**
1. **Change the scaling slider on your primary monitor.** Windows 11 Settings → System → Display → Scale. 150% is listed by default at 1080p. Do this once during verification, then revert.
2. **Debug print strategy** (below) reports physical, logical, and ratio together — any mismatch is visible in a single line without a monitor swap.
3. **Unit test with a mock**: mock `ctypes.windll.user32.GetSystemMetrics(SM_CXSCREEN)` to return `2880` and `ctypes.windll.shcore.GetScaleFactorForMonitor` to return `150`; assert the debug print format and the logical→physical conversion math.
4. **Verify in a VM**: Windows 11 in Hyper-V or VirtualBox lets you set guest DPI scaling independently of host. Not required for Phase 1 but valuable before shipping.
5. **Automated runtime check** (script-level, not unit test): `ctypes.windll.user32.GetDpiForSystem()` returns 96 at 100%, 120 at 125%, 144 at 150%, 168 at 175%. Log it. If it's not 96/120/144/168, log WARN.

**The debug print that satisfies Criterion #5:**
```python
# After main() sets DPI and before mainloop:
import ctypes
u32 = ctypes.windll.user32
shcore = ctypes.windll.shcore

SM_CXSCREEN, SM_CYSCREEN = 0, 1
logical_w = u32.GetSystemMetrics(SM_CXSCREEN)   # primary monitor logical px
logical_h = u32.GetSystemMetrics(SM_CYSCREEN)
dpi = u32.GetDpiForSystem()                      # 96 @ 100%, 144 @ 150%
scale_pct = dpi * 100 // 96

# Physical size via the ForDpi variant (which ignores thread DPI virtualization):
physical_w = u32.GetSystemMetricsForDpi(SM_CXSCREEN, dpi)
physical_h = u32.GetSystemMetricsForDpi(SM_CYSCREEN, dpi)

print(f"[dpi] logical={logical_w}x{logical_h} physical={physical_w}x{physical_h} "
      f"dpi={dpi} scale={scale_pct}%")
```

Under PMv2, `GetSystemMetrics(SM_CXSCREEN)` already returns physical pixels for the primary display (because the thread context is V2). The `ForDpi` variant is still useful as a consistency check. On a correctly-configured V2 process at 150% scaling, both values should equal the physical resolution reported by Windows Settings (e.g., `1920×1080` for a physical 1920×1080 panel, not `1280×720` which is what a DPI-unaware process would see).

### Pitfall 4: `requirements.txt` install fails in clean venv

**What goes wrong:** Developer installs packages interactively, never validates a fresh-venv install, ships `requirements.txt` with a missing dep or a version that has no wheel for the target Python.

**How to avoid:**
- Phase 1 acceptance **must** include `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt` in a fresh directory.
- Every pinned version above has been verified on PyPI as of 2026-04-11 (see Version Verification table).
- **numpy 2.2.6 caveat:** ships cp311 wheels for win_amd64 — verified. numpy 2.3+ has not dropped 3.11 yet, so bumping is safe in principle, but conservative pin wins.
- **pywin32 311 post-install:** `.venv\Scripts\pywin32_postinstall.py -install` is usually harmless but some setups need it. Include in README.

### Pitfall 5: `main.py` import path confusion with src-layout

**What goes wrong:** `main.py` at repo root does `from magnifier_bubble.app import main`, but `magnifier_bubble` lives under `src/`. Python doesn't find it.

**Why it happens:** src-layout requires either an editable install (`pip install -e .`) or `sys.path.insert(0, 'src')` in `main.py`, or running via `python -m magnifier_bubble` with the venv on `src`. The third option requires a `pyproject.toml` and a proper install.

**How to avoid (Phase 1 choice):**
- **Option A (recommended for Phase 1):** `sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))` in `main.py`, right after the DPI ctypes calls. Ugly but zero build infrastructure.
- **Option B:** Add a minimal `pyproject.toml` with `[project] name=magnifier_bubble` and run `pip install -e .` in the venv. Cleaner but adds a build tool requirement.
- **Option C:** Flatten — put `magnifier_bubble/` at repo root, skip `src/`. Loses src-layout PyInstaller-safety benefits.

**Recommendation:** **Option A for Phase 1, migrate to Option B in Phase 8** (PyInstaller works best against an installed package). Document the sys.path hack with a TODO comment.

### Pitfall 6: Observer called from the wrong thread

**What goes wrong:** A Phase 5 ConfigStore subscribes to AppState via `state.on_change(cb)`. Phase 6 Hotkey thread calls `state.set_visible(False)` directly. Observer fires on the hotkey thread, ConfigStore touches `root.after`, tkinter crashes with "main thread is not in main loop".

**How to avoid in Phase 1:**
- Document in `state.py` docstring: *"All writes must come from the Tk main thread. Worker threads route writes via `root.after(0, state.setter, ...)`."*
- Observers fire synchronously in the thread that called the setter. Correct architecture is enforced by architecture invariants (ARCHITECTURE.md §845-856), not by AppState API.
- **Alternative considered and rejected:** thread-identity assertion inside setters (`assert threading.current_thread() is self._main_thread`). This is nice to have but needs the main thread's identity captured in `AppState.__init__`, which means AppState must be constructed on the main thread. Fine for us, but adds a runtime check that's only useful during development. **Recommendation: add the assertion as a debug-mode-only check** (`if __debug__:`) so it disappears in `-O` builds.

---

## Code Examples

Verified patterns combining the research sources (Microsoft Learn, ARCHITECTURE.md, PITFALLS.md) with version-current practice.

### `main.py` — ENTIRE FILE

```python
# Source: MS Learn SetProcessDpiAwarenessContext + PITFALLS.md Pitfall 5
import ctypes
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)  # PMv2
except (AttributeError, OSError):
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)      # PMv1 (Win 8.1+)
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()           # System-aware (legacy)

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from magnifier_bubble.app import main
main()
```

Exactly 12 lines. `import ctypes` is line 1. The DPI call is line 2. This satisfies OVER-05 literally.

### `requirements.txt`

```txt
# Ultimate Zoom — pinned deps for Python 3.11.9 on Windows 11
# Installed by: pip install -r requirements.txt
mss==10.1.0
pywin32==311
Pillow==11.3.0
numpy==2.2.6
pystray==0.19.5

# Build tool — used only by Phase 8 build.bat, but pinned here
# so the single-install workflow in README.md is one command.
pyinstaller==6.11.1
```

### `src/magnifier_bubble/state.py` — AppState

```python
# Source: ARCHITECTURE.md §Components (state.py row) + §Invariants §845-856
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from threading import Lock
from typing import Callable

Shape = str  # "circle" | "rounded" | "rect" — stringly-typed for JSON-compat; could be Enum

@dataclass
class StateSnapshot:
    """Immutable-by-convention value snapshot of AppState."""
    x: int = 200
    y: int = 200
    w: int = 400
    h: int = 400
    zoom: float = 2.0
    shape: Shape = "circle"
    visible: bool = True
    always_on_top: bool = True


class AppState:
    """Single source of truth for app state.

    INVARIANT: All writes must come from the Tk main thread.
    Worker threads mutate via `root.after(0, state.set_*)`.
    Readers may call from any thread (lock-protected).
    """

    def __init__(self, initial: StateSnapshot | None = None) -> None:
        self._lock = Lock()
        self._snap = initial or StateSnapshot()
        self._observers: list[Callable[[], None]] = []

    # --- observer registration ---
    def on_change(self, cb: Callable[[], None]) -> None:
        self._observers.append(cb)

    def _notify(self) -> None:
        for cb in list(self._observers):  # copy in case observer unsubscribes
            cb()

    # --- snapshot / capture-region helpers (thread-safe reads) ---
    def snapshot(self) -> StateSnapshot:
        with self._lock:
            return StateSnapshot(**asdict(self._snap))

    def capture_region(self) -> tuple[int, int, int, int, float]:
        """Used by CaptureWorker (Phase 3). Returns (x, y, w, h, zoom)."""
        with self._lock:
            s = self._snap
            return (s.x, s.y, s.w, s.h, s.zoom)

    # --- writers (call from Tk main thread only) ---
    def set_position(self, x: int, y: int) -> None:
        with self._lock:
            self._snap.x, self._snap.y = x, y
        self._notify()

    def set_size(self, w: int, h: int) -> None:
        with self._lock:
            self._snap.w, self._snap.h = w, h
        self._notify()

    def set_zoom(self, zoom: float) -> None:
        # clamp 1.5..6.0 in 0.25 steps — see CTRL-05
        zoom = max(1.5, min(6.0, round(zoom * 4) / 4))
        with self._lock:
            self._snap.zoom = zoom
        self._notify()

    def set_shape(self, shape: Shape) -> None:
        if shape not in ("circle", "rounded", "rect"):
            raise ValueError(f"invalid shape: {shape!r}")
        with self._lock:
            self._snap.shape = shape
        self._notify()

    def set_visible(self, visible: bool) -> None:
        with self._lock:
            self._snap.visible = visible
        self._notify()

    def toggle_visible(self) -> None:
        with self._lock:
            self._snap.visible = not self._snap.visible
        self._notify()

    def toggle_aot(self) -> None:
        with self._lock:
            self._snap.always_on_top = not self._snap.always_on_top
        self._notify()
```

### `src/magnifier_bubble/dpi.py` — DPI helpers + debug print

```python
# Source: MS Learn GetDpiForSystem / GetSystemMetricsForDpi + PITFALLS.md Pitfall 5
from __future__ import annotations
import ctypes
from ctypes import wintypes
from typing import TypedDict

_u32 = ctypes.windll.user32
_shcore = ctypes.windll.shcore

# sentinel handles from windef.h
DPI_AWARENESS_CONTEXT_UNAWARE = -1
DPI_AWARENESS_CONTEXT_SYSTEM_AWARE = -2
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE = -3
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
DPI_AWARENESS_CONTEXT_UNAWARE_GDISCALED = -5

SM_CXSCREEN, SM_CYSCREEN = 0, 1
USER_DEFAULT_SCREEN_DPI = 96


class DpiReport(TypedDict):
    logical_w: int
    logical_h: int
    physical_w: int
    physical_h: int
    dpi: int
    scale_pct: int
    context_is_pmv2: bool


def is_pmv2_active() -> bool:
    """Returns True iff the calling thread's DPI context equals PMv2."""
    try:
        cur = _u32.GetThreadDpiAwarenessContext()
        return bool(_u32.AreDpiAwarenessContextsEqual(
            cur, DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        ))
    except (AttributeError, OSError):
        return False


def report() -> DpiReport:
    """Collects a cross-check of logical and physical primary-monitor dimensions.

    Under a PMv2 process, logical and physical should agree. Divergence signals
    that PMv2 failed to take effect (check main.py DPI call order).
    """
    logical_w = _u32.GetSystemMetrics(SM_CXSCREEN)
    logical_h = _u32.GetSystemMetrics(SM_CYSCREEN)
    dpi = _u32.GetDpiForSystem()
    physical_w = _u32.GetSystemMetricsForDpi(SM_CXSCREEN, dpi)
    physical_h = _u32.GetSystemMetricsForDpi(SM_CYSCREEN, dpi)
    return {
        "logical_w": logical_w,
        "logical_h": logical_h,
        "physical_w": physical_w,
        "physical_h": physical_h,
        "dpi": dpi,
        "scale_pct": dpi * 100 // USER_DEFAULT_SCREEN_DPI,
        "context_is_pmv2": is_pmv2_active(),
    }


def debug_print() -> None:
    r = report()
    print(
        f"[dpi] pmv2={r['context_is_pmv2']} "
        f"dpi={r['dpi']} scale={r['scale_pct']}% "
        f"logical={r['logical_w']}x{r['logical_h']} "
        f"physical={r['physical_w']}x{r['physical_h']}"
    )
```

### `src/magnifier_bubble/app.py` — Phase 1 entry

```python
# Source: ARCHITECTURE.md §Startup Flow (Phase 1 subset — no Tk yet)
from __future__ import annotations

from magnifier_bubble import dpi
from magnifier_bubble.state import AppState, StateSnapshot


def main() -> int:
    # Criterion 5: report logical & physical dimensions.
    dpi.debug_print()

    # Criterion 4: construct the single source of truth.
    state = AppState(StateSnapshot())

    # Phase 1 smoke: mutate and snapshot to prove the container round-trips.
    state.set_position(300, 400)
    snap = state.snapshot()
    print(f"[state] snapshot after set_position(300,400): {snap}")

    # Phase 1 is scaffolding only — no Tk mainloop yet. Exit cleanly.
    print("[app] phase 1 scaffold OK; exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### `src/magnifier_bubble/__main__.py`

```python
# Enables `python -m magnifier_bubble` as an alternate entry.
from magnifier_bubble.app import main
raise SystemExit(main())
```

### `tests/test_state.py` (pytest)

```python
# Source: Phase 1 Validation Architecture
from magnifier_bubble.state import AppState, StateSnapshot


def test_default_snapshot():
    s = AppState()
    snap = s.snapshot()
    assert snap.x == 200 and snap.y == 200
    assert snap.w == 400 and snap.h == 400
    assert snap.zoom == 2.0
    assert snap.shape == "circle"
    assert snap.visible is True


def test_set_position_fires_observer():
    s = AppState()
    calls = []
    s.on_change(lambda: calls.append(s.snapshot()))
    s.set_position(123, 456)
    assert len(calls) == 1
    assert calls[0].x == 123 and calls[0].y == 456


def test_zoom_clamps_to_range():
    s = AppState()
    s.set_zoom(10.0)
    assert s.snapshot().zoom == 6.0
    s.set_zoom(0.1)
    assert s.snapshot().zoom == 1.5


def test_zoom_snaps_to_quarter_steps():
    s = AppState()
    s.set_zoom(2.37)
    assert s.snapshot().zoom == 2.25  # round(2.37*4)/4 == 9/4
    s.set_zoom(2.49)
    assert s.snapshot().zoom == 2.5


def test_invalid_shape_raises():
    s = AppState()
    try:
        s.set_shape("triangle")
    except ValueError:
        return
    assert False, "expected ValueError"


def test_capture_region_is_tuple():
    s = AppState()
    s.set_position(50, 60)
    s.set_size(300, 200)
    s.set_zoom(3.0)
    assert s.capture_region() == (50, 60, 300, 200, 3.0)


def test_toggle_visible():
    s = AppState()
    s.set_visible(True)
    s.toggle_visible()
    assert s.snapshot().visible is False
    s.toggle_visible()
    assert s.snapshot().visible is True
```

### `tests/test_dpi.py` (pytest, Windows-only)

```python
# Source: PITFALLS.md Pitfall 5 + MS Learn DPI API
import sys
import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")


def test_dpi_report_has_required_keys():
    from magnifier_bubble import dpi
    r = dpi.report()
    for k in ("logical_w", "logical_h", "physical_w", "physical_h",
              "dpi", "scale_pct", "context_is_pmv2"):
        assert k in r


def test_dpi_positive_dimensions():
    from magnifier_bubble import dpi
    r = dpi.report()
    assert r["logical_w"] > 0
    assert r["logical_h"] > 0
    assert r["dpi"] >= 96


def test_scale_pct_matches_dpi():
    from magnifier_bubble import dpi
    r = dpi.report()
    assert r["scale_pct"] == r["dpi"] * 100 // 96


def test_is_pmv2_active_after_main_py_initialization():
    """If main.py was run as entry point (pytest isn't), this may fail — that's OK.
    The test documents the expected post-init state. Skip if not set."""
    from magnifier_bubble import dpi
    r = dpi.report()
    if not r["context_is_pmv2"]:
        pytest.skip("process DPI context is not PMv2 "
                    "(expected when running via pytest; check main.py when running via `python main.py`)")
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `SetProcessDPIAware()` (legacy, system-aware only) | `SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)` | Windows 10 1703 (Creators Update), April 2017 | V2 gets child-HWND DPI notifications, automatic NC area scaling, comctl32 theme scaling. V1 and legacy modes do not. |
| `SetProcessDpiAwareness(2)` (shcore, Win 8.1) | `SetProcessDpiAwarenessContext(-4)` (user32, Win 10 1703+) | Windows 10 1703 | shcore.SetProcessDpiAwareness is still supported but can't express PMv2. |
| DPI awareness via API call | DPI awareness via application manifest | Microsoft recommendation, explicit on MS Learn | Manifest fires at OS load, before Python starts. **We use both**: ctypes for `python main.py` dev, manifest for Phase 8 .exe. |
| `GetSystemMetrics(SM_CXSCREEN)` with DPI virtualization | `GetSystemMetricsForDpi(SM_CXSCREEN, dpi)` | Windows 10 1607 | Per-DPI variants bypass thread-context virtualization. Under PMv2, `GetSystemMetrics` already returns physical pixels for the primary monitor, but `ForDpi` is explicit. |
| `keyboard` library for global hotkey | `ctypes + user32.RegisterHotKey` | keyboard library archived Feb 2026 (STATE.md) | Phase 6 concern, but Phase 1 requirements.txt does NOT include the `keyboard` library (never did). |
| Pillow LANCZOS for upscale | Pillow BILINEAR for upscale | Always (this isn't new; LANCZOS was always for downscale) | Phase 3 concern; Phase 1 installs Pillow without touching resampling. |

**Deprecated / outdated approaches we are NOT using:**
- `SetProcessDPIAware()` as the only DPI call (System-aware only; insufficient)
- `SetProcessDpiAwareness(2)` as the only DPI call (V1 only; lacks V2 features)
- `dpi.SetProcessDpiAwareness()` from any 3rd-party DPI library (unnecessary abstraction)
- `pyautogui.size()` (imports pyautogui which sets System-aware at import — corrupts DPI state)
- `pywin32.win32api.GetSystemMetrics` at module-import time (same risk as above if pywin32 is touched before the ctypes DPI call)

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | **pytest** (latest — not pinned) |
| Config file | `pyproject.toml` with `[tool.pytest.ini_options] pythonpath = ["src"]` OR `conftest.py` with `sys.path` insertion. Recommend `pyproject.toml`. |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

**Note:** pytest is NOT in `requirements.txt` because it is a dev-only dependency and adding it bloats PyInstaller analysis. Add to a separate `requirements-dev.txt` (Phase 1 deliverable) that is installed on the developer machine but NOT on the clinic PC.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|---|
| OVER-05 | DPI Per-Monitor-V2 is set before imports | smoke (integration) | `python main.py && echo OK` + verify `[dpi] pmv2=True` in stdout | Wave 0 (new) |
| OVER-05 | `SetProcessDpiAwarenessContext(-4)` is line 2 of main.py | lint (static) | `python -c "import ast; mod = ast.parse(open('main.py').read()); assert mod.body[0].value.func.attr == 'SetProcessDpiAwarenessContext' if isinstance(mod.body[0], ast.Expr) else True"` (or simpler: `grep -n 'SetProcessDpiAwarenessContext' main.py` returns line 3 or earlier) | Wave 0 (new) |
| OVER-05 | AppState round-trips a set → snapshot | unit | `python -m pytest tests/test_state.py -x` | Wave 0 (new) |
| OVER-05 | `dpi.report()` returns matching logical/physical dims under PMv2 | unit | `python -m pytest tests/test_dpi.py -x` | Wave 0 (new) |
| Success #1 | `python main.py` exits 0 | smoke | `python main.py; echo $?` (expect 0) | Wave 0 (new) |
| Success #3 | Clean venv install succeeds | integration | `python -m venv /tmp/fresh && /tmp/fresh/Scripts/python -m pip install -r requirements.txt` | Wave 0 (new) |
| Success #5 | Debug print on 150% display matches Windows values | manual + runtime log | Change Windows scaling slider to 150%, run `python main.py`, verify `[dpi] scale=150% physical=<expected>` | manual-only (hardware) |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/ -x -q` (~ 2 seconds)
- **Per wave merge:** `python -m pytest tests/ -v` + `python main.py` smoke + fresh-venv install check
- **Phase gate:** Full suite green; manual 150% scale verification on at least one Windows 11 machine before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `requirements-dev.txt` — add `pytest>=8.0` (not pinned for dev tooling)
- [ ] `pyproject.toml` — minimal, adds `[tool.pytest.ini_options] pythonpath = ["src"]` so pytest can import `magnifier_bubble.*`
- [ ] `tests/__init__.py` — empty marker
- [ ] `tests/conftest.py` — empty for now; reserved for shared fixtures in later phases
- [ ] `tests/test_state.py` — unit tests for AppState (see Code Examples)
- [ ] `tests/test_dpi.py` — unit tests for dpi module
- [ ] Framework install: `pip install pytest` in dev venv (NOT in `requirements.txt`)

---

## Open Questions

### 1. Should `main.py` install the PyInstaller manifest equivalent now, or defer to Phase 8?

- **What we know:** Microsoft Learn prefers manifest over API call; our ctypes approach works for `python main.py` but NOT for the future `.exe` if the PyInstaller-embedded manifest disagrees.
- **What's unclear:** Does PyInstaller 6.11.1 default to a manifest with `<dpiAware>true/pm</dpiAware>` (System-aware) that would silently downgrade us?
- **Recommendation:** Phase 1 uses the ctypes approach exclusively. Phase 8 spec file adds `<dpiAwareness>PerMonitorV2</dpiAwareness>` and `manifest=` entry. Flag in Phase 8 research to re-verify PyInstaller 6.11.1's default manifest behavior.

### 2. Does Cornerstone's presence on the PATH affect DPI awareness of our process?

- **What we know:** STATE.md Blockers/Concerns lists "Cornerstone (legacy LOB) may conflict with Per-Monitor-V2 DPI awareness — needs empirical test."
- **What's unclear:** Cornerstone is a separate process, so its manifest shouldn't affect ours. But if Cornerstone's process hosts a DLL we load via COM, shared DPI state could bite. Unlikely in Phase 1 (we don't touch Cornerstone until Phase 6 hotkey).
- **Recommendation:** Phase 1 proceeds with PMv2. If Phase 6 or Phase 8 testing on the clinic PC shows DPI drift when Cornerstone is running, fall back to PMv1 and document.

### 3. Should AppState use `threading.RLock` instead of `Lock`?

- **What we know:** Lock is sufficient if no setter calls another setter under the same lock. Our design has setters that each acquire the lock once and release before calling `_notify()`.
- **What's unclear:** If a future observer re-enters the lock (e.g., "on change, read snapshot, decide whether to adjust another field"), Lock will deadlock.
- **Recommendation:** Use plain `Lock` for Phase 1. If Phase 5 ConfigStore or Phase 6 HotkeyService induce reentrance, swap to `RLock`. Document in `state.py` docstring: *"If you need re-entrant locking, this is the line to change."*

### 4. Where exactly does "first executable line" start counting — after a docstring?

- **What we know:** Python's module loader evaluates a docstring at the top of a file as part of `ast.Module.body[0]` (an `Expr` with a `Constant` value). It is *evaluated* but has no side effects.
- **What's unclear:** OVER-05 says "first executable line." A strict reader might say a docstring is not "executable" (it's just a literal), so `import ctypes` can go on line 2. A paranoid auditor might argue any bytecode-generating statement counts.
- **Recommendation:** Zero ambiguity wins. `main.py` has no docstring. Line 1 is `import ctypes`. Line 2 is the DPI call. All documentation lives in `src/magnifier_bubble/app.py` and module docstrings there.

### 5. Should we support DPI-unaware fallback for Windows 7?

- **What we know:** Requirements say Windows 11 primary, Windows 10 fallback acceptable. Windows 7 is not mentioned.
- **What's unclear:** Is there a clinic PC running Windows 7 somewhere?
- **Recommendation:** Fallback ladder in `main.py` already handles the Windows 7 case (falls through to `SetProcessDPIAware()`). No code needed beyond the try/except chain we already have.

---

## Sources

### Primary (HIGH confidence)

- [Microsoft Learn — SetProcessDpiAwarenessContext](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setprocessdpiawarenesscontext) — authoritative on the API signature, the "set once per process" rule, `ERROR_ACCESS_DENIED` on second call, and the recommendation to use manifest over API. Confirmed 2026-04-11, last updated 2025-07-01.
- [Microsoft Learn — DPI_AWARENESS_CONTEXT](https://learn.microsoft.com/en-us/windows/win32/hidpi/dpi-awareness-context) — sentinel handle values: PMv2 is `-4`, PMv1 is `-3`, System-Aware is `-2`, Unaware is `-1`, Unaware-GDI-Scaled is `-5`. Last updated 2025-07-14.
- [Microsoft Learn — High DPI Desktop Application Development](https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-desktop-application-development-on-windows) — explains PMv2 behavior: child HWND notifications, NC area scaling, virtualization, forced process-wide awareness resets. Last updated 2025-07-14.
- [PyPI — mss 10.1.0](https://pypi.org/project/mss/) — released 2025-08-16, supports Python 3.9–3.14, uses BitBlt + EnumDisplayMonitors on Windows.
- [PyPI — PyInstaller release history](https://pypi.org/project/pyinstaller/#history) — confirmed 6.11.1 still available (Nov 2024); latest is 6.19.0 (Feb 2026).
- [.planning/research/ARCHITECTURE.md](C:\Users\Jsupport\OneDrive - Ackley Athletics LLC\JB\Naomi Zoom\.planning\research\ARCHITECTURE.md) (committed 2026-04-10) — Component table, project layout, invariants, startup flow, all patterns used.
- [.planning/research/STACK.md](C:\Users\Jsupport\OneDrive - Ackley Athletics LLC\JB\Naomi Zoom\.planning\research\STACK.md) — pinned versions and rationale.
- [.planning/research/PITFALLS.md](C:\Users\Jsupport\OneDrive - Ackley Athletics LLC\JB\Naomi Zoom\.planning\research\PITFALLS.md) — Pitfall 5 DPI unawareness; detailed warning signs and fallback code.
- [.planning/research/SUMMARY.md](C:\Users\Jsupport\OneDrive - Ackley Athletics LLC\JB\Naomi Zoom\.planning\research\SUMMARY.md) — top-5 pitfall ranking lists DPI as #2.
- Local verification via `pip index versions <pkg>` on 2026-04-11 — mss 10.1.0, pywin32 311, Pillow 11.3.0 available, numpy 2.2.6 available, pystray 0.19.5 current, pyinstaller 6.11.1 back-pinned deliberately.

### Secondary (MEDIUM confidence)

- [GitHub — python-mss issue #184](https://github.com/BoboTiG/python-mss/issues/184) — documents mss's own `SetProcessDpiAwareness(2)` call inside `MSSImplWindows.__init__`; confirms the fix is "import mss first OR set DPI yourself before importing mss." Cross-verified with a direct read of `python-mss/src/mss/windows.py` on GitHub (2026-04-11).
- [bugs.python.org issue 45681](https://bugs.python.org/issue45681) — tkinter ttk widgets shrink on hover under DPI awareness; fixed in Tk 8.6.11; Python 3.11.9 ships Tk 8.6.13 (verified via GitHub cpython/issues/116145 context).
- [GitHub — CPython issue 116145](https://github.com/python/cpython/issues/116145) — installer Tcl/Tk version tracking; confirms 3.12+ moved to 8.6.14 in 2024; 3.11 branch at 8.6.13.
- Direct tk patchlevel check on dev machine: `tkinter.Tk().tk.call('info', 'patchlevel')` returned `8.6.15` on Python 3.14.3. Confirms tk 8.6.11+ DPI fix is present in modern Pythons.

### Tertiary (LOW confidence — flagged for validation)

- [copyprogramming.com 2026 Python Screenshot Shortcut guide](https://copyprogramming.com/howto/fastest-way-to-take-a-screenshot-with-python-on-windows) — minor corroborating source for mss performance. Not load-bearing; PITFALLS.md already covered this authoritatively.
- [TkDocs install tutorial](https://tkdocs.com/tutorial/install.html) — generic Tk install reference; mentions 8.6 bundling. Not required for Phase 1 decisions.
- General WebSearch responses about `winfo_x/y` returning physical pixels under PMv2 — **FLAGGED**: consistent across sources but no single authoritative citation. Phase 1 should empirically verify with the debug print at 150% scaling before trusting this for Phase 3 capture math.

---

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — every version verified on PyPI 2026-04-11; stack decisions inherited from committed research
- Architecture: **HIGH** — inherited from committed ARCHITECTURE.md which is marked HIGH confidence
- DPI API details: **HIGH** — Microsoft Learn is authoritative
- Pitfalls: **HIGH** — inherited from committed PITFALLS.md plus direct MS Learn verification
- AppState design: **HIGH** — dataclass + lock + observers is idiomatic Python and matches ARCHITECTURE.md component spec
- Phase 1 test scaffold (pytest): **MEDIUM** — pytest is a reasonable default but no CLAUDE.md or existing test config dictates it. Could switch to unittest without cost.
- "winfo_x/y under PMv2 returns physical pixels": **MEDIUM** — asserted in PITFALLS.md and corroborated by multiple web sources but not verified with an official Tcl/Tk doc. Verify empirically in Phase 1 via the debug print.
- PyInstaller 6.11.1 back-pin AV-cluster rationale: **MEDIUM** — STATE.md asserts it; not re-verified in this research pass. Not Phase 1 load-bearing.

**Research date:** 2026-04-11
**Valid until:** ~2026-05-11 (30 days — stable domain; DPI API hasn't changed since Windows 10 1703; only major invalidator would be a Python 3.11.10 release or mss 11.0 with different DPI semantics)
