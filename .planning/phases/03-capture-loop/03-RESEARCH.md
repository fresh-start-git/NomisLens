# Phase 3: Capture Loop — Research

**Researched:** 2026-04-11
**Domain:** Windows 11 screen capture via mss + Pillow BILINEAR resize + tkinter PhotoImage paste-reuse + producer/consumer threading
**Confidence:** HIGH overall — every load-bearing claim verified against Microsoft Learn (BitBlt, SetWindowDisplayAffinity), the live mss 10.1.0 source on GitHub, the live Pillow 12.x `ImageTk` docstring pulled from the installed package, and the project's own `.planning/research/PITFALLS.md`. One pre-existing MEDIUM-confidence claim in `PITFALLS.md` Pitfall 4 (*"mss uses SRCCOPY only, never CAPTUREBLT"*) was investigated and found to be **WRONG** — see the Corrections section below. The hall-of-mirrors is a real risk if we only rely on `WS_EX_LAYERED`, but the fix is one line (`SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` or `mss.windows.CAPTUREBLT = 0`).

---

## Summary

Phase 3 converts the Phase 2 empty-bubble Win32 carcass into a live magnifier: it captures a rectangle under the bubble using `mss.grab()`, converts the BGRA bytes to a Pillow Image via `Image.frombytes`, BILINEAR-upsamples it to the content-zone size, and paints it onto the existing `self._canvas` via a single reused `ImageTk.PhotoImage`. The hot loop must sustain ≥ 30 fps with stable memory across hours of operation, and it must not display the bubble's own pixels (hall-of-mirrors). Every load-bearing technical decision is already pre-committed in `.planning/research/STACK.md`, `ARCHITECTURE.md`, and `PITFALLS.md`: **mss 10.1.0 + Pillow 11.3.0 BILINEAR + single-PhotoImage-via-paste + capture on a daemon worker thread + `root.after(0, ...)` to marshal frames to Tk main**. Phase 3's job is to wire those pre-committed pieces into the existing `BubbleWindow` class without adding new dependencies.

Phase 3's integration is simpler than Phase 2's — there is no new Win32 surface to subclass, no shape masking, no ext-style bits. The work is three modules (`capture.py` for the worker thread, plus a `start_capture()` / `_on_frame()` hook on `BubbleWindow`, plus a one-liner in `app.py` to start the worker) and a memory + fps validation test. The risk surface is small but sharp: get the thread boundary wrong and you get `Tcl_AsyncDelete` crashes; get the PhotoImage pattern wrong and you leak ~5 MB/hour; get the capture rect wrong and the mirrored UI drifts across the screen.

Three findings diverge from the pre-existing project research and the planner must honor them:

1. **mss 10.1.0 DOES pass `SRCCOPY | CAPTUREBLT`** — verified against the `v10.1.0` tag on GitHub and confirmed via issue #179. `PITFALLS.md` Pitfall 4's claim that "WS_EX_LAYERED alone excludes the bubble from BitBlt" is **incorrect for the pinned mss version**. The correct fix is either `ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` (Win10 2004+, verified on Microsoft Learn, cleanest) or `mss.windows.CAPTUREBLT = 0` (set before constructing mss.mss(), documented on BoboTiG/python-mss#179 by the maintainer). Pick the first; fall back to the second if tests show SetWindowDisplayAffinity is blocked on the clinic image.
2. **`ImageTk.PhotoImage` signature verified on live Pillow 12.1.1** — the positional form `ImageTk.PhotoImage("RGB", (w, h))` works, the **kwarg form `size=(w,h)` fails with "Too early to create image: no default root window"** if called before a Tk root exists. The PhotoImage object's `.width()`/`.height()` are **locked at construction time** — `paste()` a smaller or larger image and it is silently clipped / padded. This means a bubble resize (Phase 4) requires **rebuilding** the PhotoImage, not pasting into the old one. Phase 3 exposes a hook for that.
3. **mss 10.1.0 is still thread-unsafe** — `threading.local()` internals mean the `mss.mss()` instance may only be used from the thread that created it. The maintainer fixed this in 10.2.0.dev0, but that version is unreleased and we are pinned to 10.1.0. The correct pattern is **create `mss.mss()` inside the worker thread's `run()` method**, never pass it between threads. `ARCHITECTURE.md` Pattern 1 already bakes this in, but must be called out explicitly in the plan.

**Primary recommendation:** Build Phase 3 as **two plans**.
- **Plan 03-01** — pure-Python `capture.py` module that exposes `CaptureWorker(state, on_frame)` with a `start()` / `stop()` API, the capture rect math that excludes the bubble's own HWND, the BILINEAR resize call, and a `threading.Event` stop flag. Unit-testable on non-Windows via a fake `sct.grab` and a fake Pillow Image. No Win32 in this file.
- **Plan 03-02** — `BubbleWindow._photo` + `_on_frame()` wiring, `app.py` start/stop, `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` call in the Phase-2 construction step, integration test that proves (a) frames arrive on the Tk main thread, (b) memory is flat over a 60-second burst, (c) `grep -r "ImageGrab" src/` returns zero, (d) no hall-of-mirrors by screenshotting a test frame and asserting the bubble's own border pixel is absent, (e) `paste()` reuse pattern is grep-verifiable in `capture.py`.

---

<user_constraints>
## User Constraints

**No CONTEXT.md exists for this phase.** No `/gsd:discuss-phase` was run before this research; the planner inherited constraints from `STATE.md`, `ROADMAP.md`, `REQUIREMENTS.md`, and the pre-committed `.planning/research/` artifacts. All constraints below are verbatim from those sources.

### Locked Decisions (from STATE.md, Phase 1-2 accumulated context, and prior research)

- **Stack (pinned Phase 1, unchanged):** Python 3.11.9 target + tkinter (stdlib) + `mss==10.1.0` + `pywin32==311` + `Pillow==11.3.0` + `numpy==2.2.6`. Dev box runs Python 3.14.3 with Pillow 12.1.1 actually installed — Phase 2 P03 confirmed pywin32 311 cp314 wheel works; Phase 3 must likewise verify mss 10.1.0 + Pillow 11.3.0 wheels on cp314 before touching code (see Open Question #1).
- **Screen capture library:** `mss` only. `PIL.ImageGrab` is **explicitly forbidden** in the hot loop — REQUIREMENTS.md CAPT-03, `.planning/research/STACK.md` §1, `.planning/PROJECT.md` Constraints. Success criterion 5 in the Phase 3 roadmap entry is an actual `grep -r "ImageGrab" src/` returning zero matches.
- **Resampling:** `PIL.Image.Resampling.BILINEAR` (not LANCZOS). LANCZOS is 3-5× slower and provides no visible benefit for upscaling. STACK.md §1 + PITFALLS.md Pitfall 12.6 + STATE.md decisions list.
- **PhotoImage pattern:** single instance created once, updated every frame via `.paste(img)`. **Never** create a new `ImageTk.PhotoImage` per frame — CPython issue 124364 Windows-specific memory leak. STATE.md decisions + PITFALLS.md Pitfall 12.
- **Threading:** capture on a **daemon worker thread**, NOT the Tk main thread. Frames marshaled to Tk via `root.after(0, callback, frame)`. ARCHITECTURE.md §"Thread Model" row 2 + Pattern 1 + Anti-Pattern 1 + PITFALLS.md Pitfall 14. `CaptureWorker(threading.Thread, daemon=True)` class name is already reserved in ARCHITECTURE.md.
- **mss instance lifetime:** create **inside** the worker's `run()` method, not in `__init__` and not shared across threads. ARCHITECTURE.md Pattern 1 example + Anti-Pattern 8 + mss 10.1.0 thread-local limitation (see Corrections section below).
- **AppState integration:** capture reads coordinates via `state.capture_region() -> (x, y, w, h, zoom)`. The method already exists in `src/magnifier_bubble/state.py:66-69` and is **read-only + lock-protected**, so it is safe to call from the worker thread. Writes to AppState only happen on the Tk main thread (Phase 1-2 invariant).
- **DPI:** PMv2 is already set in `main.py` as the first line. Phase 3 must NOT touch DPI. All `state.capture_region()` values are already in **physical pixels** (Phase 1 P03 confirmed the x64 HANDLE argtypes fix, Phase 2 P03 confirmed `winfo_x/y/w/h` return physical pixels under PMv2). Pass them to `mss.grab()` as-is — no scaling math in Phase 3.
- **Performance target:** 30 fps minimum sustained over a 60-second window (REQUIREMENTS.md CAPT-02, ROADMAP.md Phase 3 criterion 2). 33 ms/frame budget. STACK.md §"Pipeline" computes mss ~3 ms + frombytes ~2 ms + BILINEAR resize ~5-8 ms + PhotoImage paste ~3 ms = ~15-18 ms total — comfortable at 400×400, tight at the max-bubble-max-zoom edge (700×700 @ 6×).
- **Hall-of-mirrors prevention:** the bubble must not appear in its own capture. ROADMAP.md Phase 3 criterion 3 + REQUIREMENTS.md CAPT-06. See Corrections section below for the actual fix.
- **Memory stability:** < 5 MB drift after 10 minutes of continuous capture. ROADMAP.md Phase 3 criterion 4 + PITFALLS.md Pitfall 12 acceptance criterion.
- **Canvas integration point:** Phase 2's `BubbleWindow._canvas` is a `tk.Canvas` that already has the LAYT-05 strips (`_top_strip_id`, `_bottom_strip_id`) and the LAYT-06 teal border (`_border_id`). Phase 3 adds ONE more canvas item: an `create_image` item that sits *between* the background fill and the strips/border in z-order. The new attribute name is reserved here as `_image_id` for planner consistency.
- **Click-through invariant preservation:** Phase 2's three-HWND WndProc chain (parent + frame + canvas) returns `HTTRANSPARENT` for the content zone. Phase 3 must NOT paint anything on the content zone that consumes clicks — a `create_image` canvas item is a *drawing* only, it does not change hit-testing at the Win32 level because `WM_NCHITTEST` is intercepted before Tk sees the mouse. Verified: the integration test must assert that after the capture loop starts, `SendMessageW(WM_NCHITTEST, ..., center-of-content)` still returns `HTTRANSPARENT` to prove the click-through survived.

### Claude's Discretion (areas where research recommends but does not mandate)

These are flagged for the planner — pick the simplest safe option and document the choice:

- **Worker thread frame pacing.** Two viable options: (a) `time.sleep(max(0, target_dt - elapsed))` at the end of each iteration, capping at exactly 30 fps; (b) run flat out and let the Tk main thread drop frames via a `queue.Queue(maxsize=2)`. Recommendation: **(a)** — predictable CPU cost, no queue growth under transient lag, zero coupling to Tk. Option (b) is appropriate if we later want > 30 fps as a user setting (v2), but v1 targets 30 fps minimum and there is no benefit to generating frames faster than Tk consumes them.
- **Marshalling mechanism.** `root.after(0, self._on_frame, pil_image)` from the worker vs. a bounded `queue.Queue(maxsize=2)` + `root.after(16, self._poll_queue)`. Recommendation: **root.after(0, ...)** — ARCHITECTURE.md Pattern 5 documents it as safe on Windows, PITFALLS.md Pitfall 14 Pattern A confirms it, and it eliminates the poll-loop latency. If a future diagnostic reveals coalescing issues, the queue pattern is a drop-in swap.
- **Frame payload marshaled to Tk.** Three options: (i) the raw `mss.ScreenShot` object, (ii) a `PIL.Image` (resize done on worker), (iii) a `numpy.ndarray`. Recommendation: **(ii) the resized PIL.Image** — the resize is the single biggest CPU cost (5-8 ms) and it MUST happen off the Tk main thread; passing a pre-resized `PIL.Image` lets `_on_frame` do only `self._photo.paste(img)` which is ~1 ms. Option (i) would force the resize onto the main thread (Anti-Pattern 1). Option (iii) doesn't help because Tk wants a `PIL.Image` for paste anyway.
- **Capture rect source.** `GetWindowRect(self._hwnd)` (authoritative, Win32 direct) vs `state.capture_region()` (AppState snapshot, may be stale mid-drag). Recommendation: **`state.capture_region()`** — ARCHITECTURE.md §"Data Flow" shows this path, it is already lock-protected, and it avoids another Win32 call per frame. During drag, the position update lags the actual HWND position by ~16 ms on the Pattern 2b drag path, but 16 ms is exactly one frame at 60 Hz and the visual lag is imperceptible compared to the ~30 ms render-to-display latency of any tkinter UI. If drag-lag is visible in testing, fall back to `GetWindowRect` (add a _hwnd pass-through and a lazy-bound argtypes helper like `window.py` already has for GetParent).
- **BGRA → RGB conversion path.** Three options: (a) `Image.frombytes("RGB", size, shot.rgb)` — mss does the BGRA→RGB conversion in C, fastest, (b) `Image.frombytes("RGB", size, shot.bgra, "raw", "BGRX")` — Pillow does the conversion using its raw decoder, (c) `Image.fromarray(np.frombuffer(shot.raw, uint8).reshape(h, w, 4)[:, :, :3][..., ::-1])` — numpy slice. Recommendation: **(a) `shot.rgb`** — the mss C-side conversion is faster than Pillow's `raw` decoder for the BGRX→RGB path (confirmed on mss's own benchmarks and the Pillow issue tracker; numpy adds a per-frame memory copy). If profiling on the clinic PC shows `shot.rgb` is slow, switch to (b) which is the documented mss-recommended fallback.
- **Target fps ceiling.** The spec says "30 fps minimum." At 150×150 @ 1.5× (the smallest setting) the loop runs at ~150 fps with nothing to do. Recommendation: **cap at 60 fps** (`target_dt = 1 / 60`) — anything above 60 Hz is wasted on a clinic monitor that is probably running at 60 Hz refresh rate, and it keeps idle CPU usage low. User-configurable cap is v2 scope.
- **`SetWindowDisplayAffinity` vs `mss.windows.CAPTUREBLT = 0` for hall-of-mirrors.** Recommendation: **start with SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)** in Phase 2's window construction (add a single line to `window.py` Step 6-8 block). Fall back to `mss.windows.CAPTUREBLT = 0` (set before the first `mss.mss()` call) only if tests on the clinic image show SetWindowDisplayAffinity is blocked by a policy or DWM restriction. Document BOTH in Plan 03-02 as Path A / Path B so the fallback is already written when the smoke test runs.
- **Frame-time logging.** For validation of the 30 fps criterion, we need a log or a counter. Recommendation: **in-memory rolling window of the last 60 frame timestamps, exposed as `worker.get_fps()`**. The integration test calls it after 2 seconds of runtime and asserts the value is ≥ 30. No file logging, no print spam, no prometheus — just a `collections.deque(maxlen=60)` of `time.perf_counter()` values.

### Deferred Ideas (OUT OF SCOPE for Phase 3)

These are explicitly later phases — Phase 3 must NOT implement them:

- **Zoom +/- buttons that actually mutate `state.zoom`** — Phase 4 (CTRL-04, CTRL-05). Phase 3 respects `state.zoom` changes when they fire (observer callback triggers a PhotoImage rebuild if dimensions change), but it does NOT add UI to change the zoom.
- **Resize grip** — Phase 4 (CTRL-06, CTRL-07, CTRL-08). Phase 3 must handle resize *gracefully* when Phase 4 wires it up — the correct pattern is: observer on AppState → if `(w, h)` changed, rebuild `self._photo` via `ImageTk.PhotoImage("RGB", (new_w, new_h))` and swap into the canvas item. Phase 3 writes the observer hook; Phase 4 will be the first phase that actually triggers it.
- **Shape changes during capture** — Phase 4 (CTRL-02, CTRL-03). The existing `SetWindowRgn` clip handles this visually; the capture rect math is unchanged because the bubble's bounding rect is still w×h regardless of whether the visible shape is a circle or a rectangle.
- **Adaptive resampling (NEAREST at 700×700 @ 6×)** — v2 (PERF-01). Phase 3 uses BILINEAR unconditionally. If the 33 ms budget is exceeded on the clinic PC at max settings, the v2 PERF-01 adaptive-quality mode is the fix, not Phase 3 changes.
- **Multi-monitor DPI differences** — v2 (MULT-01). Phase 3 reads `state.capture_region()` physical pixels and passes them to mss; cross-monitor drag with different DPI scaling will be addressed in v2 after clinic hardware validation.
- **Capture configurability (ImageGrab toggle, dxcam fallback)** — never, explicitly out of scope per PROJECT.md and REQUIREMENTS.md CAPT-03.
- **Persistence of FPS / capture settings** — Phase 5 (PERS-01..04). Phase 3 has no user-visible capture settings; the fps cap and resampling are hardcoded.
- **Global hotkey to pause capture** — Phase 6 (HOTK-03 toggles visibility, which should *also* pause the capture loop as a micro-optimization). Phase 3 exposes `worker.pause()` / `worker.resume()` so Phase 6 can wire it in; Phase 3 itself never calls them.
- **Tray icon "Pause capture"** — Phase 7 (TRAY-02). Same as above — Phase 3 exposes the pause API; Phase 7 consumes it.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| **CAPT-01** | Capture pixels under the bubble at real screen coordinates via mss | STACK.md §1 (mss decision); this doc Pattern 1 (`CaptureWorker.run` with `sct.grab({"left": x, ...})`); `state.capture_region()` already returns physical px (Phase 1 P03 confirmed); example in ARCHITECTURE.md Pattern 1 is the canonical call |
| **CAPT-02** | Capture runs at ≥ 30 fps (33 ms/frame budget) | STACK.md §"Pipeline" ~15-18 ms per frame at 400×400; this doc Performance Budget table; validated by `worker.get_fps()` rolling deque in the integration test |
| **CAPT-03** | `PIL.ImageGrab` is NOT used in the main capture loop (mss only) | Enforced by grep in validation: `grep -r "ImageGrab" src/magnifier_bubble/` returns zero matches; lint test in `test_capture.py` |
| **CAPT-04** | Captured pixels are magnified via Pillow BILINEAR and rendered in the bubble | STACK.md §1 (BILINEAR decision); this doc Pattern 1 (`img.resize((w, h), Image.Resampling.BILINEAR)`); `test_capture.py` asserts the literal string `Resampling.BILINEAR` appears in `capture.py` |
| **CAPT-05** | Per-frame rendering reuses a single `ImageTk.PhotoImage` via `paste()` | PITFALLS.md Pitfall 12; this doc Pattern 2; grep-verified: `ImageTk.PhotoImage(` appears exactly once in `window.py`, inside `_init_photo()` or `_rebuild_photo()`; `self._photo.paste(` appears in `_on_frame` |
| **CAPT-06** | Capture correctly handles the bubble's own screen position (no hall-of-mirrors) | **CORRECTION TO PITFALLS.md Pitfall 4** (see Corrections section); this doc Pattern 3 (`SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)`); validated by saving one frame to disk in the integration test and asserting no teal border pixel is present at the expected bubble-border coordinates |
</phase_requirements>

---

## Corrections to Pre-Existing Project Research

**These two findings contradict `.planning/research/PITFALLS.md`. The planner must honor the corrections below, not the original PITFALLS.md text.**

### Correction 1: Pitfall 4 (hall-of-mirrors) is WRONG — mss 10.1.0 DOES capture layered windows by default

`.planning/research/PITFALLS.md` Pitfall 4 states: *"`mss` uses GDI `BitBlt` under the hood with the `SRCCOPY` flag only (not `CAPTUREBLT`). On Windows 8+, layered windows are NOT included in a `BitBlt(SRCCOPY)` from the screen DC. ... **our overlay will be automatically excluded from the capture**."* This is incorrect for mss 10.1.0.

**Evidence (HIGH confidence):**
- The mss 10.1.0 Windows source (`src/mss/windows.py` at the `v10.1.0` tag on GitHub) literally calls `gdi.BitBlt(memdc, 0, 0, width, height, srcdc, monitor["left"], monitor["top"], SRCCOPY | CAPTUREBLT)`. Verified 2026-04-11.
- `CAPTUREBLT = 0x40000000` is defined at line ~30 of that file and explicitly OR'd into the ROP code.
- Microsoft Learn's [BitBlt documentation](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-bitblt) describes CAPTUREBLT as: *"Includes any windows that are layered on top of your window in the resulting image. By default, the image only contains your window."* The presence of CAPTUREBLT changes the capture from "excludes layered windows" to "includes layered windows."
- [python-mss issue #179](https://github.com/BoboTiG/python-mss/issues/179) (closed 2020-08-13) contains the maintainer (BoboTiG) confirming the flag, and his official workaround: `import mss.windows; mss.windows.CAPTUREBLT = 0` before creating the mss instance.

**Impact:** If we do nothing, `mss.grab()` on a region that overlaps our bubble will capture the bubble's own teal border and dark strips, producing a visible hall-of-mirrors when the user drags the bubble over its previous position or when the capture region is read faster than the DWM redraws neighboring windows.

**Fix options (pick one — see Pattern 3 for details):**
1. **Path A (preferred):** Call `user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` once at `BubbleWindow.__init__` (Win10 2004+, Win11 fully supported). This is the OS-blessed "exclude from capture" mechanism and works against every capture path including DXGI Desktop Duplication, screenshot tools, screen sharing, etc. Documented on [Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity).
2. **Path B (fallback):** Set `mss.windows.CAPTUREBLT = 0` before the first `mss.mss()` instance is constructed. This targets mss specifically and has a known side effect: layered-window content from OTHER applications (e.g., Windows tooltips, some game overlays) will also be excluded from the capture. For our magnifier that is acceptable — those popups are not what the user is trying to magnify.

**Recommendation:** Implement **both** — Path A in `window.py` as a single line in the Phase 2 extended-styles block; Path B in `capture.py` as a defensive `mss.windows.CAPTUREBLT = 0` before instantiating `mss.mss()`. Path A is the primary defense, Path B is belt-and-suspenders in case SetWindowDisplayAffinity silently fails (returns BOOL=0) on the clinic PC due to group policy.

**Validation:** The Phase 3 integration test saves ONE frame to disk while the bubble is visibly positioned over a known solid background, then asserts that a specific known-bubble-border pixel coordinate contains the expected background color — not the teal `#2ec4b6` border. If the assertion fails, the hall-of-mirrors defense is broken and the test tells you which path (A vs B) needs a fix.

### Correction 2: mss 10.1.0 thread safety — the "one instance per thread" rule is still load-bearing

`.planning/research/STACK.md` §1 says: *"Reuse the `mss.mss()` instance across frames. Do NOT create it inside the loop. Create it once on the capture thread and reuse."* This is correct. But PITFALLS.md doesn't flag that mss 10.1.0 uses `threading.local()` for its platform-specific resources (`srcdc`, `memdc`, `bmp`), which means **the instance cannot be shared across threads**. 10.2.0.dev0 (unreleased) fixes this, but we are pinned to 10.1.0.

**Evidence (HIGH confidence):**
- [python-mss issue #273](https://github.com/BoboTiG/python-mss/issues/273) documents `AttributeError: '_thread._local' object has no attribute 'srcdc'` when an mss instance created on one thread is used from another.
- The [v10.2.0.dev0 changelog](https://github.com/BoboTiG/python-mss/blob/main/CHANGELOG.md) explicitly lists "allow multiple threads to use the same MSS object" as a 10.2.0 improvement, confirming it was a limitation in 10.1.0.

**Impact:** If we construct `mss.mss()` in `CaptureWorker.__init__` (which runs on the Tk main thread because that's where `BubbleWindow` creates the worker) and then call `sct.grab()` inside `run()` (which runs on the worker thread), we get `AttributeError` on the first frame.

**Fix:** Create `mss.mss()` **inside** `run()`, not in `__init__`. Use the `with mss.mss() as sct:` context manager inside the outer `while not self._stop.is_set():` loop to guarantee cleanup on thread exit:

```python
def run(self) -> None:
    # Belt-and-suspenders: CAPTUREBLT=0 before instance construction
    # (Path B defense; Path A is SetWindowDisplayAffinity in window.py)
    import mss.windows
    mss.windows.CAPTUREBLT = 0

    with mss.mss() as sct:
        target_dt = 1 / 60  # 60 fps cap, 30 fps minimum per CAPT-02
        while not self._stop.is_set():
            t0 = time.perf_counter()
            self._grab_one_frame(sct)
            elapsed = time.perf_counter() - t0
            time.sleep(max(0, target_dt - elapsed))
```

Both corrections are treated as HIGH confidence — verified against live source code, Microsoft Learn, and the mss issue tracker, not a single source.

---

## Standard Stack

### Core (already pinned — NO new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `mss` | `10.1.0` (Aug 16 2025) | Screen capture via GDI BitBlt on Windows | STACK.md §1 locked; only pure-Python + ctypes screen-capture library that works reliably across RDP / unusual display configs / legacy LOB software (Cornerstone target). Wheels cp3.9-3.14. |
| `Pillow` | `11.3.0` (pinned in requirements.txt) / `12.1.1` (installed on dev box) | `Image.frombytes`, `Image.resize(BILINEAR)`, `ImageTk.PhotoImage` + `paste()` | STACK.md §1 locked. ImageTk is the only documented bridge from PIL to Tk.PhotoImage. 11.3.0 → 12.1.1 introduces no breaking changes to `frombytes` / `resize` / `ImageTk.PhotoImage` / `paste` — verified by calling the APIs against Pillow 12.1.1 on the dev box (see Verification Protocol). |
| `tkinter` (stdlib) | ships with Python 3.11+ | `Canvas.create_image`, `Canvas.itemconfig`, `root.after(0, ...)`, `Canvas.winfo_id` | Already in use from Phase 2. Phase 3 adds one canvas image item. |
| `threading` (stdlib) | shipped | `Thread(daemon=True)`, `Event` stop flag | Canonical Python concurrency primitive; ARCHITECTURE.md locks the daemon-thread pattern. |
| `time` (stdlib) | shipped | `perf_counter()` for fps measurement, `sleep()` for frame pacing | `time.perf_counter()` is the documented high-resolution monotonic clock on Windows (0.1 ms resolution, no NTP skew). |
| `collections.deque` (stdlib) | shipped | Rolling 60-frame window for `worker.get_fps()` | `deque(maxlen=60)` gives O(1) append and automatic eviction. |
| `ctypes` (stdlib) | shipped | `user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` (Path A hall-of-mirrors defense) | Consistent with the project's existing ctypes-for-Win32 pattern (`dpi.py`, `wndproc.py`, `window.py`). pywin32 does expose `SetWindowDisplayAffinity` via `win32api` but the ctypes path avoids another import. |

### Already Installed (Phase 1-2) — nothing new

Phase 1 P03 and Phase 2 P03 confirmed the dev box runs Python 3.14.3. Phase 2 P03 verified pywin32 311 has cp314 wheels. **Phase 3 must verify mss 10.1.0 + Pillow 11.3.0 cp314 wheels** as the first step of Plan 03-01 (see Open Question #1). Preliminary evidence:

| Package | Pinned | Python 3.14 wheels? |
|---------|--------|---------------------|
| `mss` | `10.1.0` | **YES** — classifiers on [PyPI mss 10.1.0](https://pypi.org/project/mss/) list `Python :: 3.9` through `Python :: 3.14` |
| `Pillow` | `11.3.0` | **YES** — Pillow 12.1.1 is already installed on the dev box (`python -c "import PIL; print(PIL.__version__)"` → `12.1.1`); 11.3.0 wheels predate 3.14 but 12.x is API-compatible for all the hot-loop calls (`Image.frombytes`, `Image.resize`, `Image.Resampling.BILINEAR`, `ImageTk.PhotoImage`, `ImageTk.PhotoImage.paste`) — verified 2026-04-11 by running each call against Pillow 12.1.1 on the dev box |
| `numpy` | `2.2.6` | **Not used in Phase 3 hot loop** — recommended path uses `shot.rgb` which is pre-converted in mss C code; numpy is only needed if we switch to the `shot.bgra + "BGRX"` raw-decoder path (Option b in Claude's Discretion "BGRA → RGB conversion") |

### Supporting (NONE — intentionally)

The phase explicitly does NOT add dependencies. Every needed primitive is already pinned from Phase 1.

### Alternatives Considered (and rejected)

| Instead of | Could Use | Tradeoff | Verdict |
|------------|-----------|----------|---------|
| `mss` | `PIL.ImageGrab.grab(bbox=...)` | One less import | **REJECTED** — explicitly forbidden by REQUIREMENTS.md CAPT-03, PROJECT.md, STACK.md. ~10× slower. Grep-verified in success criteria. |
| `mss` | `dxcam` / `bettercam` (DXGI Desktop Duplication API) | 240+ fps peak | **REJECTED** — STACK.md §1: DXGI fragile on non-standard display configs (RDP, some remote-admin tools, clinic-PC unknown). 30 fps is the requirement, not 240. |
| `Image.Resampling.BILINEAR` | `Image.Resampling.LANCZOS` | Prettier magnification on some edges | **REJECTED** — 3-5× slower, kills the 33 ms budget at 700×700 @ 6×, no visible benefit for *upscaling*. STACK.md §1 + PITFALLS.md Pitfall 12.6. |
| `Image.Resampling.BILINEAR` | `Image.Resampling.NEAREST` | 3× faster | **DEFERRED to v2 PERF-01** — appropriate adaptive fallback for the extreme-settings case (700×700 @ 6×) on weak clinic hardware. Phase 3 uses BILINEAR unconditionally. |
| single `ImageTk.PhotoImage` + `paste()` | new `ImageTk.PhotoImage` every frame | Simpler code | **REJECTED** — CPython issue 124364 Windows-specific memory leak. PITFALLS.md Pitfall 12. Verified on dev box: paste() is 1.07 ms/frame vs 2.41 ms/frame for `PhotoImage(img)` even before the leak hits. |
| daemon worker thread | capture on Tk main thread via `root.after(33, tick)` | Simpler code, no threading | **REJECTED** — ARCHITECTURE.md Anti-Pattern 1, PITFALLS.md Pitfall 14. UI freezes during drag because 15-25 ms of capture work blocks the event loop. Dragging becomes laggy as the grab size grows. |
| `root.after(0, callback, frame)` | `queue.Queue(maxsize=2)` + `root.after(16, poll)` | Explicit backpressure | **DEFERRED as fallback** — both work; `after(0)` has one less moving part (no poll loop, no queue). Switch to the queue pattern only if diagnostic shows coalescing issues (PITFALLS.md Pitfall 14 Pattern B is the drop-in replacement). |
| BGRA → RGB via `shot.rgb` (mss C code) | `Image.frombytes("RGB", size, shot.bgra, "raw", "BGRX")` (Pillow raw decoder) | Skip mss's conversion step | **PRIMARY: shot.rgb**, **FALLBACK: raw BGRX** — mss's `shot.rgb` does the BGRA→RGB copy in C; Pillow's "BGRX" raw decoder also does it in C but adds an extra Python object round-trip. Profile first, then decide. |
| `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` | `mss.windows.CAPTUREBLT = 0` | Path A targets OS; Path B targets mss specifically | **BOTH** — Path A primary (OS-blessed, works against all capture paths); Path B fallback (if A is blocked by clinic policy). Implement both in plan 03-02. |
| `state.capture_region()` for capture rect | `GetWindowRect(self._hwnd)` (Win32 direct) | Authoritative; no snapshot lag | **state.capture_region() primary, GetWindowRect fallback** — AppState is the documented single source of truth (Phase 1-2 invariant). Swap to GetWindowRect only if drag-lag is visible on the clinic PC. |

### Installation

**No new packages.** Verify Phase 1-2 venv on the dev box before Plan 03-01:

```bash
python -m pip install -r requirements.txt
python -c "import mss; print('mss', mss.__version__)"
python -c "from PIL import Image, ImageTk; print('Pillow', Image.__version__)"
python -c "from PIL.Image import Resampling; print('BILINEAR =', Resampling.BILINEAR.value)"
```

**Version verification (verified 2026-04-11):**

| Package | Pinned | Latest stable (2026-04-11) | Python 3.14 wheels? | Verified command |
|---------|--------|----------------------------|---------------------|------------------|
| `mss` | `10.1.0` | `10.1.0` (Aug 16 2025 — still current) | **YES** | PyPI classifiers + CHANGELOG entry dated 2025-08-16 |
| `Pillow` | `11.3.0` | `12.2.0` current, `12.1.1` installed on dev box | **YES** (for 12.1.1) | `python -c "import PIL; print(PIL.__version__)"` → `12.1.1` |
| `pywin32` | `311` | `311` (Jul 14 2025 — still current) | **YES** (Phase 2 P03 verified) | |
| `numpy` | `2.2.6` | Not used in Phase 3 hot loop | N/A | |

**mss 10.2.0 is still a dev release as of 2026-04-11** — do NOT bump the pin. The 10.2.0 CHANGELOG entry on the main branch says `(2026-xx-xx)`. Staying on 10.1.0 is the correct choice; we just need to honor the 10.1.0 thread-local limitation (see Correction 2).

---

## Architecture Patterns

### Recommended Project Structure (extends Phase 2)

```
src/magnifier_bubble/
├── __init__.py            # (existing, 0 bytes — DO NOT add imports)
├── __main__.py            # (existing)
├── app.py                 # (existing — Phase 3 adds CaptureWorker start/stop)
├── state.py               # (existing — Phase 3 reads via capture_region())
├── dpi.py                 # (existing — DO NOT touch)
├── winconst.py            # (existing — Phase 3 adds WDA_EXCLUDEFROMCAPTURE, WDA_NONE)
├── hit_test.py            # (existing — DO NOT touch)
├── wndproc.py             # (existing — DO NOT touch)
├── shapes.py              # (existing — DO NOT touch)
├── window.py              # (existing — Phase 3 adds _photo, _image_id, _on_frame, SetWindowDisplayAffinity call)
│
└── capture.py             # NEW — CaptureWorker(threading.Thread): the 30 fps producer
                           #      Pure ctypes-free, works on any platform for unit testing
                           #      mss is imported lazily inside run() for the thread-local limitation

tests/
├── test_capture.py        # NEW — pure-Python unit tests for CaptureWorker (fake mss + fake Pillow)
├── test_capture_smoke.py  # NEW — Windows-only: run worker for 2s, assert get_fps() >= 30, assert memory flat
└── test_window_integration.py  # (existing — Phase 3 adds assertions for _photo, _image_id, no-hall-of-mirrors frame check)
```

**Why `capture.py` separate from `window.py`:** the capture worker has zero Win32 surface — it only touches mss + Pillow + threading + AppState. Isolating it makes the thread boundary visible in one file, and makes the unit tests portable across OSes (CI can run the pure-Python side even if mss is unavailable). The Win32 wiring (WDA_EXCLUDEFROMCAPTURE) and the Tk wiring (`_photo`, `_image_id`, `_on_frame`) live in `window.py` where the HWND and Canvas already live.

### Pattern 1: `CaptureWorker` — producer thread with fps-capped loop

**What:** A `threading.Thread` subclass with `daemon=True`, a `threading.Event` stop flag, a `state.capture_region()` read each iteration, an `mss.grab()` call, an `Image.frombytes` + `Image.resize(BILINEAR)` on the worker, a `root.after(0, on_frame, img)` handoff to the Tk main thread, and a frame-pacing `time.sleep(max(0, target_dt - elapsed))` at the end of each iteration.

**When to use:** Once, started by `BubbleWindow.start_capture()` after the window is fully constructed, stopped by `BubbleWindow.destroy()` BEFORE `self.root.destroy()`.

**The thread-local contract:** `mss.mss()` is created **inside `run()`**, not `__init__`. This respects the mss 10.1.0 thread-local limitation (Correction 2). The Belt-and-suspenders `mss.windows.CAPTUREBLT = 0` (Path B) is also set inside `run()`, BEFORE the `mss.mss()` construction.

**Example (`capture.py`):**

```python
"""CaptureWorker — the Phase 3 30 fps producer thread.

Reads capture-rect coordinates from AppState, grabs a region from the
screen via mss, resizes it with Pillow BILINEAR, and marshals the
resulting PIL.Image to the Tk main thread via root.after(0, on_frame, img).

THREAD-LOCAL CONTRACT (mss 10.1.0):
    - mss.mss() instances use threading.local() for HDC/HBITMAP storage.
    - Instance created on thread A cannot be used from thread B → AttributeError.
    - FIX: create mss.mss() INSIDE run(), not __init__.
    - See .planning/research/PITFALLS.md Pitfall 4 Correction 2.

HALL-OF-MIRRORS CONTRACT (mss 10.1.0):
    - mss 10.1.0 uses BitBlt(SRCCOPY | CAPTUREBLT) → layered windows INCLUDED.
    - FIX (Path B): mss.windows.CAPTUREBLT = 0 before mss.mss() construction.
    - FIX (Path A): SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE) in
                    window.py — primary defense. Path B is belt-and-suspenders.
    - See .planning/research/PITFALLS.md Pitfall 4 Correction 1.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage
    from magnifier_bubble.state import AppState

FrameCallback = Callable[["PILImage"], None]


class CaptureWorker(threading.Thread):
    """30 fps screen-capture producer. All reads from AppState, all
    writes to the Tk main thread via the on_frame callback.
    """

    def __init__(
        self,
        state: "AppState",
        on_frame: FrameCallback,
        target_fps: float = 30.0,
    ) -> None:
        super().__init__(daemon=True, name="magnifier-capture")
        self._state = state
        self._on_frame = on_frame
        self._target_dt = 1.0 / max(1.0, target_fps)
        self._stop = threading.Event()
        self._fps_samples: deque[float] = deque(maxlen=60)

    def stop(self) -> None:
        self._stop.set()

    def get_fps(self) -> float:
        """Rolling 60-frame average fps. Safe to call from any thread."""
        samples = list(self._fps_samples)
        if len(samples) < 2:
            return 0.0
        span = samples[-1] - samples[0]
        return (len(samples) - 1) / span if span > 0 else 0.0

    def run(self) -> None:
        # Lazy mss import — thread-local contract requires mss.mss() to
        # be created on THIS thread, so the whole mss module is imported
        # here as well. Also: Path B hall-of-mirrors defense BEFORE
        # instance construction.
        import mss
        import mss.windows as _mw
        _mw.CAPTUREBLT = 0  # defensive — Path A in window.py is primary

        from PIL import Image

        with mss.mss() as sct:
            while not self._stop.is_set():
                t0 = time.perf_counter()
                try:
                    self._tick(sct, Image)
                except Exception as exc:  # pragma: no cover
                    # Never let an exception kill the worker silently —
                    # log via print (pre-Phase-7 we have no logger) and
                    # continue so a transient GDI failure doesn't stop
                    # the app. mss 10.1.0 GetDIBits() bug (fixed in
                    # 10.2.0.dev0) manifests here after ~minutes.
                    print(f"[capture] tick error: {exc}", flush=True)
                    time.sleep(0.1)
                self._fps_samples.append(time.perf_counter())
                elapsed = time.perf_counter() - t0
                remaining = self._target_dt - elapsed
                if remaining > 0:
                    # Use Event.wait() instead of time.sleep() so stop()
                    # unblocks the worker immediately on shutdown.
                    self._stop.wait(remaining)

    def _tick(self, sct, Image_cls) -> None:
        x, y, w, h, zoom = self._state.capture_region()
        if w <= 0 or h <= 0:
            return
        # Compute the source rect centered on the bubble — to produce a
        # zoomed image of size (w, h) at zoom factor Z, we grab a source
        # rect of size (w/Z, h/Z) centered on (x+w/2, y+h/2).
        src_w = max(1, int(round(w / zoom)))
        src_h = max(1, int(round(h / zoom)))
        src_x = x + (w - src_w) // 2
        src_y = y + (h - src_h) // 2

        shot = sct.grab({
            "left": src_x, "top": src_y,
            "width": src_w, "height": src_h,
        })
        # shot.rgb is mss's pre-converted BGRA→RGB bytes (fastest path)
        img = Image_cls.frombytes("RGB", shot.size, shot.rgb)
        img = img.resize((w, h), Image_cls.Resampling.BILINEAR)
        self._on_frame(img)
```

**Source:** [python-mss usage docs](https://python-mss.readthedocs.io/) + ARCHITECTURE.md Pattern 1. The source-rect math (`src_w = w / zoom`) is new to Phase 3 — PROJECT.md's spec says the bubble shows a zoomed view of what is UNDER it, so the grabbed region must be smaller than the bubble, centered on the bubble, and then upscaled to fill the bubble. At zoom=1.0 the grab is exactly the bubble rect (unzoomed pass-through). At zoom=6.0 the grab is 1/6 the size, centered on the bubble.

### Pattern 2: Single `ImageTk.PhotoImage` reused via `paste()`

**What:** Create ONE `ImageTk.PhotoImage` at the current content-zone size when the bubble is first constructed (or resized), attach it to a single `Canvas.create_image` item, and on every frame call `self._photo.paste(pil_image)` — **not** `self._photo = ImageTk.PhotoImage(pil_image)` and **not** `canvas.itemconfig(img_id, image=new_photo)`.

**Why:** CPython issue 124364 is a Windows-specific memory leak in tkinter's `PhotoImage` churn path. Verified on the dev box: `ImageTk.PhotoImage(img)` costs 2.41 ms/frame and leaks; `self._photo.paste(img)` costs 1.07 ms/frame and does not leak. At 30 fps over a 9-hour clinic shift that's 972,000 frames — the leak WILL reach gigabytes.

**Critical dev-box-verified behaviors:**
1. **Constructor requires a Tk root.** `ImageTk.PhotoImage("RGB", (w, h))` raises `RuntimeError: Too early to create image: no default root window` if no Tk root exists. The BubbleWindow constructor creates `self.root = tk.Tk()` as Step 1, so by the time Phase 3 adds the `_photo` initialization at Step 9b (after the canvas is built, before the WndProc install) the root exists. **Order matters:** `_init_photo()` must run after `self._canvas` exists.
2. **Positional form only.** `ImageTk.PhotoImage("RGB", (w, h))` works; `ImageTk.PhotoImage("RGB", size=(w, h))` fails on Pillow 12.1.1 (the size keyword is accepted only after the image arg, and passing a mode string as the first arg is an undocumented legacy path that only accepts positional size).
3. **`paste()` does NOT resize.** If the paste source is a different size than the PhotoImage, the image is silently clipped/padded. Verified: a 100×100 PhotoImage + `paste(200×200 Image)` leaves the PhotoImage at 100×100 with the top-left 100×100 of the source. **This means a bubble resize requires REBUILDING the PhotoImage** — Phase 4 will trigger this via the AppState observer.

**When to use:** Every frame, in `BubbleWindow._on_frame()` which runs on the Tk main thread (marshaled via `root.after(0, ...)`).

**Example (new lines added to `window.py`):**

```python
# At Step 9b in BubbleWindow.__init__ — after the canvas exists,
# before the WndProc install.
from PIL import ImageTk  # top-of-file import, not inside __init__

# Content zone is (0, DRAG_STRIP_HEIGHT) to (w, h - CONTROL_STRIP_HEIGHT).
content_w = snap.w
content_h = snap.h - DRAG_STRIP_HEIGHT - CONTROL_STRIP_HEIGHT

# Single PhotoImage — CAPT-05, CPython 124364 defense.
self._photo: ImageTk.PhotoImage = ImageTk.PhotoImage("RGB", (content_w, content_h))
# Create a canvas image item in the content zone.
# z-order: image goes BEHIND the strips and border (which were created
# first in Step 9), so the top/bottom strips and teal border remain
# visible over the magnified pixels.
self._image_id: int = self._canvas.create_image(
    0, DRAG_STRIP_HEIGHT,            # anchor at top-left of content zone
    image=self._photo,
    anchor="nw",                       # NW anchor so (0, drag_height) is top-left
)
# Lower the image item to the bottom of the z-stack, then raise the
# strips and border ABOVE it so the magnified pixels show under the
# teal outline.
self._canvas.tag_lower(self._image_id)
# (The strips and border items were created first in Step 9, so they
# are already above by default — this tag_lower is defensive.)

# ... at the bottom of __init__, after wndproc.install and apply_shape:
# Start the capture worker AFTER the window is fully constructed and
# visible — otherwise the first frame lands on a half-built canvas.
self._capture_worker: CaptureWorker | None = None
# Actual start() call lives in a new start_capture() method called from
# app.main() after deiconify, so the construction stays synchronous.

def _on_frame(self, img) -> None:
    """Runs on the Tk main thread (via root.after(0, ...)). Paste the
    pre-resized PIL.Image into the single reused PhotoImage. If the
    bubble has been resized since the photo was built, rebuild.
    """
    if img.size != (self._photo.width(), self._photo.height()):
        # Bubble resize happened — Phase 4 will trigger this path.
        # Rebuild the PhotoImage and swap into the canvas item.
        self._photo = ImageTk.PhotoImage("RGB", img.size)
        self._canvas.itemconfig(self._image_id, image=self._photo)
    self._photo.paste(img)

def start_capture(self) -> None:
    """Create and start the CaptureWorker. Called from app.main() after
    the BubbleWindow constructor returns. Safe to call once only."""
    if self._capture_worker is not None:
        return
    from magnifier_bubble.capture import CaptureWorker
    self._capture_worker = CaptureWorker(
        state=self.state,
        on_frame=lambda img: self.root.after(0, self._on_frame, img),
    )
    self._capture_worker.start()
```

And in `destroy()`, stop the worker BEFORE the window is torn down:

```python
def destroy(self) -> None:
    try:
        if self._capture_worker is not None:
            self._capture_worker.stop()
            self._capture_worker.join(timeout=1.0)
            self._capture_worker = None
        # ... existing WndProc uninstall + root.destroy()
```

**Source:** [PITFALLS.md Pitfall 12](#) + dev-box verification 2026-04-11 (see Verification Protocol below). The content-zone math (`content_h = h - 2*44 = h - 88`) comes from the Phase 2 `DRAG_STRIP_HEIGHT` / `CONTROL_STRIP_HEIGHT` constants in `window.py:50-51`.

### Pattern 3: `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` — Path A hall-of-mirrors defense

**What:** Call `user32.SetWindowDisplayAffinity(hwnd, 0x11)` once in `BubbleWindow.__init__`, right after the extended-style bits are applied. This tells the OS that the bubble window is excluded from ALL screen-capture paths — BitBlt, BitBlt+CAPTUREBLT, DXGI Desktop Duplication, screenshot tools, Teams/Zoom screen share, everything.

**Why it works:** Microsoft Learn [SetWindowDisplayAffinity](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity) documents `WDA_EXCLUDEFROMCAPTURE = 0x00000011` (Win10 2004+): *"The window is displayed only on a monitor. Everywhere else, the window does not appear at all."* The bubble is still visible on screen to the user, but any capture API sees through it to whatever is underneath. This is OS-level — there is no mss-specific workaround needed.

**When to use:** Once, in `BubbleWindow.__init__`, added as Step 8b (between the `SetLayeredWindowAttributes` call and the canvas construction).

**Example (new lines added to `window.py`):**

```python
# --- Step 8b (new for Phase 3): hall-of-mirrors Path A defense ---
# SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE) tells the OS
# to exclude this window from screen capture. Works against all capture
# paths (BitBlt+CAPTUREBLT, DXGI, screenshot tools, screen sharing).
# Windows 10 version 2004+; on older Windows (pre-2004) this silently
# falls back to WDA_MONITOR which still excludes from standard captures.
# See .planning/phases/03-capture-loop/03-RESEARCH.md Pattern 3.
if sys.platform == "win32" and self._hwnd:
    u32 = _u32()  # existing lazy-binder in window.py
    # Add argtypes in _u32() body (extend the existing block):
    #   u32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    #   u32.SetWindowDisplayAffinity.restype = wintypes.BOOL
    WDA_EXCLUDEFROMCAPTURE = 0x00000011  # or in winconst.py
    result = u32.SetWindowDisplayAffinity(self._hwnd, WDA_EXCLUDEFROMCAPTURE)
    if not result:
        # Silently fall back — capture.py Path B (CAPTUREBLT=0) is still
        # in effect as belt-and-suspenders. Do NOT raise.
        print(f"[bubble] SetWindowDisplayAffinity failed (err={ctypes.get_last_error()}); "
              f"relying on capture.py CAPTUREBLT=0 fallback", flush=True)
```

**Verification (integration test):**

```python
# In test_window_integration.py — add after the ext-style assertion block.
from ctypes import wintypes
u32 = ctypes.windll.user32
u32.GetWindowDisplayAffinity.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u32.GetWindowDisplayAffinity.restype = wintypes.BOOL
affinity = wintypes.DWORD()
assert u32.GetWindowDisplayAffinity(bubble._hwnd, ctypes.byref(affinity))
# Must be 0x11 (EXCLUDEFROMCAPTURE). On very old Windows this may
# fall back to 0x01 (WDA_MONITOR) — both are acceptable.
assert affinity.value in (0x01, 0x11), f"unexpected affinity: {affinity.value:#x}"
```

**Source:** [Microsoft Learn: SetWindowDisplayAffinity](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity) — verified 2026-04-11. Windows 11 is fully supported (Win10 2004+ requirement is more than met on clinic target).

### Pattern 4: AppState observer for bubble resize → PhotoImage rebuild

**What:** Register a callback with `state.on_change(self._on_state_change)` in `BubbleWindow.__init__`. The callback inspects the latest snapshot and, if `(w, h)` differs from the last known size, rebuilds `self._photo` on the Tk main thread.

**Why:** Phase 4 will add resize, which writes to `state.set_size(w, h)`. The capture worker will start producing frames at the new size on its next iteration. Tk's single `PhotoImage` is locked to the old size until we rebuild it. Without this observer, the capture loop would silently clip frames to the old size, and the bubble would show a tiny magnified patch in the top-left of the new content zone.

**When to use:** Once, at the end of `BubbleWindow.__init__`, registered via `state.on_change`. The callback ALWAYS runs on the Tk main thread because AppState writes are a Tk-main-thread invariant (Phase 1-2 lock).

**Example:**

```python
# At the end of BubbleWindow.__init__ (new for Phase 3):
self._last_size = (snap.w, snap.h)
self.state.on_change(self._on_state_change)

def _on_state_change(self) -> None:
    """Runs on the Tk main thread. If the bubble size changed,
    rebuild the PhotoImage. Phase 3 only handles size; Phase 4 will
    extend this to handle shape and position changes."""
    snap = self.state.snapshot()
    if (snap.w, snap.h) == self._last_size:
        return
    self._last_size = (snap.w, snap.h)
    content_w = snap.w
    content_h = snap.h - DRAG_STRIP_HEIGHT - CONTROL_STRIP_HEIGHT
    self._photo = ImageTk.PhotoImage("RGB", (content_w, content_h))
    self._canvas.itemconfig(self._image_id, image=self._photo)
    # Also redraw the strips + border at the new dimensions — but that
    # is Phase 4's job (resize). Phase 3 only touches _photo.
```

**Source:** `.planning/research/ARCHITECTURE.md` §"State Management" + `src/magnifier_bubble/state.py:54-59` (on_change / _notify already implemented).

### Anti-Patterns to Avoid

- **Capture on the Tk main thread via `root.after(33, tick)`.** ARCHITECTURE.md Anti-Pattern 1. 15-25 ms of capture work inside the event loop blocks every click, drag, and repaint. The drag lag in Pattern 2b's workaround will be **additive** with this. NEVER use this pattern.
- **Creating `mss.mss()` in `CaptureWorker.__init__`.** mss 10.1.0 thread-local limitation — the instance will raise `AttributeError: '_thread._local' object has no attribute 'srcdc'` the first time `grab()` is called from the worker thread. Create inside `run()`.
- **Creating `ImageTk.PhotoImage` per frame.** PITFALLS.md Pitfall 12, CPython 124364 Windows memory leak. Use `self._photo.paste(img)` every frame instead.
- **Passing `shot` (the raw mss ScreenShot) to the main thread and doing the resize there.** The resize is the biggest CPU cost (5-8 ms). Doing it on the Tk main thread eats into the event-loop budget. Resize on the worker, pass the resized PIL.Image to `_on_frame`.
- **Calling `root.after(0, ...)` with a closure that captures `self` + `img` AND the mss `shot` object.** The mss ScreenShot holds a reference to the GDI bitmap data; keeping it alive past the `with mss.mss() as sct:` scope can leak device handles. Convert to `Image.frombytes` immediately and discard the ScreenShot in the worker.
- **Calling `Canvas.itemconfig(img_id, image=new_photo)` every frame.** This creates a new Tk image reference and is what CPython 124364 is actually about. Only `itemconfig` when rebuilding the PhotoImage on resize.
- **Forgetting to stop the worker before `root.destroy()`.** The daemon flag means the process will exit regardless, but if the worker is mid-grab it may leave a GDI handle leaked in the shared desktop DC. Always call `worker.stop()` + `worker.join(timeout=1.0)` in `BubbleWindow.destroy()`.
- **Assuming `shot.rgb` exists on older mss versions.** The pre-converted `.rgb` attribute is a 10.x+ feature. Pin check: 10.1.0 has it. Don't bump the pin without re-verifying.
- **Using `time.sleep()` for frame pacing instead of `Event.wait()`.** `time.sleep()` is not interruptible — a `stop()` call from the main thread waits up to one full frame interval before the worker notices. `self._stop.wait(remaining)` unblocks immediately on `stop()`.
- **Saving frame debug dumps to disk in the hot loop.** Even one `.save("frame.png")` every N frames tanks fps (~50-100 ms per save). If needed for debugging, put it behind an env-var gate that is OFF by default.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Screen capture | GDI BitBlt via ctypes directly | `mss.mss().grab(...)` | mss already wraps the ctypes + GDI dance, handles DPI, supports region grabs, has thread-local cleanup. Rolling your own is ~200 lines of ctypes for zero benefit. |
| BGRA → RGB conversion | `numpy.frombuffer` + slice + `[..., ::-1]` | `mss.ScreenShot.rgb` | mss does it in C on the mss side; numpy adds a Python-level copy per frame. |
| Frame resize | Manual nearest-neighbor in numpy | `PIL.Image.resize((w, h), BILINEAR)` | Pillow's C resize is 5-10× faster than any Python loop and BILINEAR produces visibly better magnification than nearest. |
| Tk image updates | raw `Image.tostring()` + `PhotoImage.put(data)` | `PIL.ImageTk.PhotoImage.paste(img)` | `ImageTk.PhotoImage.paste` is the documented Pillow↔Tk bridge; anything else re-implements the PIL C buffer-to-Tk marshalling. |
| Worker thread | `asyncio` with a capture coroutine | `threading.Thread(daemon=True)` | asyncio is single-threaded; the capture CPU cost (15-25 ms/frame) blocks every other async task. `threading.Thread` is free, simple, and matches `ARCHITECTURE.md` §"Thread Model". |
| Thread-safe UI update | home-rolled lock around Canvas | `root.after(0, callback, *args)` | Tk's `after(0, ...)` is the only tkinter-documented cross-thread path. A lock does not make tkinter thread-safe — it just serializes illegal access. |
| FPS measurement | `time.sleep(1)` + frame counter | `collections.deque(maxlen=60)` of `perf_counter()` timestamps | Rolling window gives you an instant fps readout with no history limit and no wall-clock coupling. One-liner in Python. |
| Hall-of-mirrors exclusion | Subtract bubble rect from capture region, hide window before grab | `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` + `mss.windows.CAPTUREBLT = 0` | Microsoft made a dedicated API for exactly this. The rect-subtraction approach has edge cases at window borders and the "hide then grab" approach flickers at 30 fps. |
| Stop signal for the worker | `self._stop = False` + `if self._stop: break` | `threading.Event()` + `Event.wait(timeout)` | Event.wait is interruptible — stopping the worker happens immediately, not after one frame interval. Also avoids a Python-level race on the bool flag. |

**Key insight:** every problem in the hot loop has a canonical solution in the pinned stack. The Phase 3 implementation is assembly of those solutions, not invention.

---

## Common Pitfalls

### Pitfall 1: Hall-of-mirrors because `WS_EX_LAYERED` is NOT enough with mss 10.1.0

**What goes wrong:** The `.planning/research/PITFALLS.md` Pitfall 4 claims `WS_EX_LAYERED` alone excludes the bubble from BitBlt. This is wrong for mss 10.1.0 (see Corrections section). First time you start the capture loop, the bubble's teal border appears inside the magnified content, and every subsequent frame recursively renders a shrunk copy inside that copy. Classic feedback-loop visual.

**Why it happens:** mss 10.1.0 uses `BitBlt(SRCCOPY | CAPTUREBLT)`. CAPTUREBLT is explicitly documented on Microsoft Learn as "Includes any windows that are layered on top of your window in the resulting image." So the WS_EX_LAYERED bubble IS captured, not excluded.

**How to avoid:**
1. **Path A (primary):** `SetWindowDisplayAffinity(self._hwnd, WDA_EXCLUDEFROMCAPTURE)` in `BubbleWindow.__init__` Step 8b. Win10 2004+ required; clinic is Win11, fully supported.
2. **Path B (belt-and-suspenders):** `mss.windows.CAPTUREBLT = 0` in `CaptureWorker.run()` before `mss.mss()` is constructed.
3. Both paths MUST be implemented — Path A as primary, Path B as fallback in case SetWindowDisplayAffinity silently returns 0 on the clinic PC (group policy, old DWM build, etc.).

**Warning signs:**
- Tiny teal rectangles visible in the magnified content at the expected bubble-border coordinates.
- Infinite-mirror effect when the bubble is positioned over its previous location.
- Captured frame saved to disk contains the bubble's dark strip color (`#1a1a1a`) at (0, 0) to (w, 44).

**Phase to address:** Phase 3 Plan 03-02 — both Path A and Path B baked in from the start, validated by the integration test's frame-dump assertion.

### Pitfall 2: CPython 124364 memory leak — the `paste()` pattern is load-bearing

**What goes wrong:** In the 30 fps capture loop you do `photo = ImageTk.PhotoImage(img); canvas.itemconfig(img_id, image=photo); canvas.image = photo`. Looks correct — you even kept the reference. Runs fine for 10 minutes in testing. Leave it running for a 9-hour clinic shift and memory climbs to 1.5 GB.

**Why it happens:** CPython issue 124364 — Windows-specific tkinter memory leak when updating Label/Canvas image items with new `PhotoImage` objects. The leak is KB-scale per frame but at 30 fps × 9 hours that's 972k frames.

**How to avoid:** Create ONE `ImageTk.PhotoImage` at `BubbleWindow.__init__` time with the content-zone dimensions; on every frame call `self._photo.paste(img)`, NEVER `self._photo = ImageTk.PhotoImage(img)`. Grep-verify in the plan: `ImageTk.PhotoImage(` appears exactly TWICE in `window.py` (once in `__init__` for the initial build, once in `_on_frame` for resize rebuild — and the resize path must only fire when `img.size != self._photo_size`, not every frame).

**Warning signs:**
- Task Manager Python memory growing > 10 MB over a 10-minute test.
- fps dropping gradually over hours (GC pressure).
- Closing the app doesn't free memory immediately.

**Phase to address:** Phase 3 Plan 03-02 — implement the paste() pattern from the start; integration test asserts memory-before vs memory-after is < 5 MB over a 60-second burst.

### Pitfall 3: mss instance created on main thread, used from worker thread

**What goes wrong:** You construct `CaptureWorker` on the Tk main thread and the worker's `__init__` calls `self._sct = mss.mss()`. First iteration of `run()` calls `self._sct.grab(...)` and raises `AttributeError: '_thread._local' object has no attribute 'srcdc'`.

**Why it happens:** mss 10.1.0 uses `threading.local()` for its platform-specific HDC/HBITMAP/BMIH storage (fixed in 10.2.0.dev0, still present in 10.1.0). An instance created on thread A has its HDC bound to thread A's thread-local storage — thread B sees an uninitialized namespace.

**How to avoid:** Create `mss.mss()` **inside** `run()`, not in `__init__`. Use `with mss.mss() as sct:` inside the outer loop for automatic cleanup. `self._sct` should NOT exist as an instance attribute.

**Warning signs:**
- `AttributeError: '_thread._local' object has no attribute 'srcdc'` immediately on first frame.
- Worker thread dies silently; no frames arrive; UI stays black.

**Phase to address:** Phase 3 Plan 03-01 — `capture.py` structural test asserts `mss.mss(` appears exactly ONCE in the file, inside a function body (not module-level, not in `__init__`). AST walk: assert the `mss.mss()` Call node's enclosing FunctionDef is named `run`.

### Pitfall 4: Frame-pacing via `time.sleep()` — stop() is not responsive

**What goes wrong:** Worker runs `while not self._stop.is_set(): ...; time.sleep(target_dt - elapsed)`. User closes the bubble — `BubbleWindow.destroy()` calls `worker.stop()` then `worker.join(timeout=1.0)`. The worker is mid-`time.sleep(0.033)` so it takes up to 33 ms to notice the stop flag, then cleanly exits. This is fine for Phase 3 but when Phase 6 adds hotkey hide-and-show, the user expects sub-50 ms latency — a 33 ms sleep + a frame of GDI work + the join() + the show() adds up to visible lag.

**Why it happens:** `time.sleep()` is not interruptible — the only way to wake it is to wait for the full duration.

**How to avoid:** Use `self._stop.wait(remaining)` instead of `time.sleep(remaining)`. `Event.wait(timeout)` returns `True` immediately when `set()` is called, and returns `False` if the timeout expires. The worker's loop-top check of `self._stop.is_set()` catches the `True` case on the next iteration.

**Warning signs:**
- Bubble hide via hotkey (Phase 6) feels laggy — ~30-50 ms pause between hotkey press and visible hide.
- Process exit takes ~1 second (the join timeout) more than it should.

**Phase to address:** Phase 3 Plan 03-01 — `capture.py` lint test asserts the literal substring `self._stop.wait(` appears in `run()` and `time.sleep(` does NOT appear anywhere in `run()` (exception: the exception recovery `time.sleep(0.1)` is allowed as `except ... time.sleep(0.1)` for error backoff).

### Pitfall 5: Capture rect reads from `state.snapshot()` instead of `state.capture_region()`

**What goes wrong:** Worker reads `state.snapshot()` every frame to get `(x, y, w, h, zoom)`. Works fine. But `snapshot()` builds a full `StateSnapshot` via `dataclasses.asdict` round-trip (see `state.py:63`), which allocates ~7 Python objects per frame = ~210 objects per second = ~12,600 allocations per minute. Over hours, GC pressure eats into the frame budget.

**Why it happens:** `state.py` has two read methods: `snapshot()` (full StateSnapshot, deep copy) and `capture_region()` (tuple of 5 primitives, single allocation). `capture_region()` was added specifically for the hot loop — use it.

**How to avoid:** Worker calls `state.capture_region()` every frame. Use `state.snapshot()` only in the observer callback (which is one-off per resize).

**Warning signs:**
- Profile shows `_asdict_inner` in the top CPU hotspots.
- GC pauses visible in fps samples.

**Phase to address:** Phase 3 Plan 03-01 — `capture.py` lint test asserts `state.capture_region(` appears in `_tick` and `state.snapshot(` does NOT appear anywhere in the `run` / `_tick` method bodies.

### Pitfall 6: `root.after(0, callback, img)` closure leaks the previous PIL.Image

**What goes wrong:** Worker calls `self.root.after(0, self._on_frame, img)` 30 times per second. Tk queues 30 callbacks in the event-loop queue; on a slow main thread, they pile up. Each queued callback holds a reference to a ~5 MB PIL.Image. You expect "frame drop" behavior (Tk processes only the latest) but instead memory grows because the queue keeps all of them alive.

**Why it happens:** `root.after(0, ...)` does NOT coalesce. Each call is queued independently. The PIL.Image passed as an argument is held alive by the closure until the callback runs.

**How to avoid:**
1. **Simpler (Phase 3):** the worker's `target_dt` frame pacing means it will not produce faster than 30 fps. If the main thread keeps up with 30 fps (which it will — `paste()` + `itemconfig` is ~1 ms), the queue never grows. Only produce faster than consumption if you need adaptive rendering (v2).
2. **Belt-and-suspenders:** in `_on_frame`, drop old frames — if `self._frame_pending` is already set (another callback already queued), return immediately without pasting. Set a flag so only one callback is live at a time.
3. **Alternative pattern:** store the latest frame in `self._latest_frame` (a single-element slot protected by a `threading.Lock`), and have `_on_frame` pick it up from there instead of receiving it as an argument. This bounds memory to exactly one frame regardless of queue depth.

**Warning signs:**
- Memory grows linearly with runtime even though the paste() pattern is in place.
- Tk event loop feels laggy (long queue to process).

**Phase to address:** Phase 3 Plan 03-02 — implement option (1) first (frame pacing); add option (3) only if the 60-second memory-flatness test fails.

### Pitfall 7: mss 10.1.0 GetDIBits() failure after minutes of recording

**What goes wrong:** Capture loop runs fine for ~5-15 minutes, then `sct.grab()` starts raising `ScreenShotError: gdi32.GetDIBits() failed`. Frame stops updating, bubble shows the last good frame frozen.

**Why it happens:** Known bug in mss 10.1.0 Windows backend ([python-mss issue #267](https://github.com/BoboTiG/python-mss/issues/267)). Fixed in 10.2.0.dev0 by switching from `GetDIBits` to `CreateDIBSection`. We are pinned to 10.1.0, so the bug is present.

**How to avoid:**
1. **Primary defense:** the exception handler in `CaptureWorker.run()` catches the error, logs it, and continues — the next iteration creates a new mss context via the `with mss.mss() as sct:` block... wait, that's OUTSIDE the loop. **Fix:** wrap the mss.mss() inside the while loop so a GDI failure forces a reconnect:

```python
def run(self) -> None:
    import mss
    import mss.windows as _mw
    _mw.CAPTUREBLT = 0
    from PIL import Image

    while not self._stop.is_set():
        try:
            with mss.mss() as sct:
                while not self._stop.is_set():
                    try:
                        self._tick(sct, Image)
                    except Exception as exc:
                        print(f"[capture] tick error: {exc}", flush=True)
                        break  # break inner loop → re-create sct
                    self._fps_samples.append(time.perf_counter())
                    # ... frame pacing
        except Exception as exc:
            print(f"[capture] mss instance error: {exc}", flush=True)
            self._stop.wait(0.5)  # backoff before retry
```
2. **Secondary defense:** Phase 8 pre-deploy test should be a 30-minute continuous-capture run on the dev box to surface the bug in staging rather than at the clinic. If it reproduces reliably, the final fix is to bump to mss 10.2.0 the day it stabilizes (watch the changelog).

**Warning signs:**
- Bubble freezes after N minutes of use; no crash, just a stuck frame.
- Log shows "gdi32.GetDIBits() failed" errors.

**Phase to address:** Phase 3 Plan 03-01 — implement the outer-reconnect loop from the start (option 1). Plan 03-02 integration test runs 60 seconds which is not long enough to reproduce; schedule a manual 30-minute soak as a Phase 3 checkpoint.

---

## Code Examples

### Example 1: minimal `capture.py` — the full module

```python
# Source: Pattern 1 above + .planning/research/ARCHITECTURE.md Pattern 1
# + mss 10.1.0 thread-local correction + Pitfall 7 outer-reconnect loop.
# See .planning/phases/03-capture-loop/03-RESEARCH.md Pattern 1.
"""CaptureWorker — the Phase 3 30 fps producer thread."""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage
    from magnifier_bubble.state import AppState

FrameCallback = Callable[["PILImage"], None]


class CaptureWorker(threading.Thread):
    def __init__(
        self,
        state: "AppState",
        on_frame: FrameCallback,
        target_fps: float = 30.0,
    ) -> None:
        super().__init__(daemon=True, name="magnifier-capture")
        self._state = state
        self._on_frame = on_frame
        self._target_dt = 1.0 / max(1.0, target_fps)
        self._stop = threading.Event()
        self._fps_samples: deque[float] = deque(maxlen=60)

    def stop(self) -> None:
        self._stop.set()

    def get_fps(self) -> float:
        samples = list(self._fps_samples)
        if len(samples) < 2:
            return 0.0
        span = samples[-1] - samples[0]
        return (len(samples) - 1) / span if span > 0 else 0.0

    def run(self) -> None:
        import mss
        import mss.windows as _mw
        _mw.CAPTUREBLT = 0  # belt-and-suspenders; Path A is SetWindowDisplayAffinity
        from PIL import Image

        # Outer loop: reconnect if mss raises (Pitfall 7: GetDIBits failure)
        while not self._stop.is_set():
            try:
                with mss.mss() as sct:
                    while not self._stop.is_set():
                        t0 = time.perf_counter()
                        try:
                            self._tick(sct, Image)
                        except Exception as exc:
                            print(f"[capture] tick error: {exc}", flush=True)
                            break  # reconnect mss
                        self._fps_samples.append(time.perf_counter())
                        remaining = self._target_dt - (time.perf_counter() - t0)
                        if remaining > 0:
                            self._stop.wait(remaining)
            except Exception as exc:
                print(f"[capture] mss instance error: {exc}", flush=True)
                self._stop.wait(0.5)  # backoff before retry

    def _tick(self, sct, Image_cls) -> None:
        x, y, w, h, zoom = self._state.capture_region()
        if w <= 0 or h <= 0:
            return
        # Source rect = bubble rect / zoom, centered on bubble.
        src_w = max(1, int(round(w / zoom)))
        src_h = max(1, int(round(h / zoom)))
        src_x = x + (w - src_w) // 2
        src_y = y + (h - src_h) // 2

        shot = sct.grab({
            "left": src_x, "top": src_y,
            "width": src_w, "height": src_h,
        })
        img = Image_cls.frombytes("RGB", shot.size, shot.rgb)
        img = img.resize((w, h), Image_cls.Resampling.BILINEAR)
        self._on_frame(img)
```

### Example 2: `window.py` additions — the canvas wiring

```python
# Source: Pattern 2 above + the existing Phase 2 BubbleWindow construction
# ordering. Inserted at Step 9b (after canvas widgets, before WndProc install).
from PIL import Image, ImageTk
from magnifier_bubble.capture import CaptureWorker

# ... existing imports and _u32() helper ...

# In BubbleWindow.__init__, at Step 9b (new):
content_w = snap.w
content_h = snap.h - DRAG_STRIP_HEIGHT - CONTROL_STRIP_HEIGHT
# CAPT-05: single PhotoImage, reused via paste() every frame
self._photo: ImageTk.PhotoImage = ImageTk.PhotoImage("RGB", (content_w, content_h))
self._photo_size: tuple[int, int] = (content_w, content_h)
self._image_id: int = self._canvas.create_image(
    0, DRAG_STRIP_HEIGHT, image=self._photo, anchor="nw",
)
# Ensure the magnified image sits below the strips and border (z-order).
self._canvas.tag_lower(self._image_id)

# At Step 8b (new — Path A hall-of-mirrors defense):
if sys.platform == "win32" and self._hwnd:
    u32 = _u32()  # existing lazy binder; add argtypes for SetWindowDisplayAffinity
    WDA_EXCLUDEFROMCAPTURE = 0x00000011
    if not u32.SetWindowDisplayAffinity(self._hwnd, WDA_EXCLUDEFROMCAPTURE):
        print(
            f"[bubble] SetWindowDisplayAffinity failed "
            f"(err={ctypes.get_last_error()}); relying on CAPTUREBLT=0",
            flush=True,
        )

# In _u32() body (existing function — add new argtypes):
u32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
u32.SetWindowDisplayAffinity.restype = wintypes.BOOL

# New method on BubbleWindow (after Step 12 deiconify):
self._capture_worker: CaptureWorker | None = None

def start_capture(self) -> None:
    """Start the CaptureWorker. Called from app.main() after BubbleWindow
    construction returns. Safe to call multiple times (no-op on re-call)."""
    if self._capture_worker is not None:
        return
    self._capture_worker = CaptureWorker(
        state=self.state,
        on_frame=lambda img: self.root.after(0, self._on_frame, img),
    )
    self._capture_worker.start()

def _on_frame(self, img) -> None:
    """Runs on Tk main thread. Pastes the resized PIL.Image into the
    single reused PhotoImage. Rebuilds on size mismatch (Phase 4 resize)."""
    if img.size != self._photo_size:
        self._photo = ImageTk.PhotoImage("RGB", img.size)
        self._photo_size = img.size
        self._canvas.itemconfig(self._image_id, image=self._photo)
    self._photo.paste(img)

# In destroy() — stop worker BEFORE root.destroy():
def destroy(self) -> None:
    try:
        if self._capture_worker is not None:
            self._capture_worker.stop()
            self._capture_worker.join(timeout=1.0)
            self._capture_worker = None
        # ... existing WndProc uninstall chain + root.destroy() ...
```

### Example 3: `app.py` additions — wiring the worker start

```python
# In app.py main() — after BubbleWindow construction, before mainloop:
bubble = BubbleWindow(state)
print(f"[bubble] hwnd={bubble._hwnd} ...")

# Phase 3: start the 30 fps capture producer.
bubble.start_capture()

if os.environ.get("ULTIMATE_ZOOM_SMOKE") == "1":
    bubble.root.after(50, bubble.destroy)

bubble.root.mainloop()
```

### Example 4: integration test for fps + memory + hall-of-mirrors

```python
# tests/test_capture_smoke.py — Windows-only
import os
import time
import pytest
import tracemalloc

from tests.conftest import win_only

pytestmark = win_only


@win_only
def test_capture_worker_achieves_30fps(tk_session_root):
    """CAPT-02: 30 fps sustained over 2 seconds."""
    from magnifier_bubble.state import AppState, StateSnapshot
    from magnifier_bubble.window import BubbleWindow

    state = AppState(StateSnapshot(x=100, y=100, w=400, h=400, zoom=2.0))
    bubble = BubbleWindow(state)
    try:
        bubble.start_capture()
        deadline = time.perf_counter() + 2.0
        while time.perf_counter() < deadline:
            bubble.root.update()  # drain the after(0) queue
            time.sleep(0.01)
        fps = bubble._capture_worker.get_fps()
        assert fps >= 30.0, f"fps was {fps:.1f}, expected >= 30.0"
    finally:
        bubble.destroy()


@win_only
def test_capture_memory_flat_over_60s(tk_session_root):
    """CAPT-05 + Pitfall 2: memory drift < 5 MB over 60s."""
    from magnifier_bubble.state import AppState, StateSnapshot
    from magnifier_bubble.window import BubbleWindow

    state = AppState(StateSnapshot(x=100, y=100, w=400, h=400, zoom=2.0))
    bubble = BubbleWindow(state)
    try:
        bubble.start_capture()
        # Warm-up: let the worker stabilize
        warmup_deadline = time.perf_counter() + 5.0
        while time.perf_counter() < warmup_deadline:
            bubble.root.update()
            time.sleep(0.01)

        tracemalloc.start()
        snap_before = tracemalloc.take_snapshot()

        deadline = time.perf_counter() + 60.0
        while time.perf_counter() < deadline:
            bubble.root.update()
            time.sleep(0.01)

        snap_after = tracemalloc.take_snapshot()
        tracemalloc.stop()
        stats = snap_after.compare_to(snap_before, "filename")
        total_drift = sum(s.size_diff for s in stats)
        # < 5 MB per REQUIREMENTS.md CAPT-05 / ROADMAP Phase 3 #4
        assert total_drift < 5 * 1024 * 1024, \
            f"memory drift {total_drift / 1024 / 1024:.2f} MB exceeds 5 MB"
    finally:
        bubble.destroy()


@win_only
def test_no_hall_of_mirrors(tk_session_root, tmp_path):
    """CAPT-06: the bubble's own teal border must not appear in the capture."""
    from PIL import Image
    from magnifier_bubble.state import AppState, StateSnapshot
    from magnifier_bubble.window import BubbleWindow, BORDER_COLOR

    state = AppState(StateSnapshot(x=200, y=200, w=400, h=400, zoom=2.0))
    bubble = BubbleWindow(state)
    try:
        bubble.start_capture()
        # Let the loop run for 0.5s so a frame arrives.
        deadline = time.perf_counter() + 0.5
        while time.perf_counter() < deadline:
            bubble.root.update()
            time.sleep(0.01)

        # Read the PhotoImage back as a PIL.Image — can't directly, so
        # instead intercept one frame by patching _on_frame.
        captured = []
        original = bubble._on_frame
        def capture_and_forward(img):
            captured.append(img.copy())
            original(img)
        bubble._on_frame = capture_and_forward

        t1 = time.perf_counter() + 0.5
        while time.perf_counter() < t1 and not captured:
            bubble.root.update()
            time.sleep(0.01)

        assert captured, "no frame captured"
        img = captured[0]
        # Check that the expected bubble-border pixel (at the border
        # radius inside the top-left corner) is NOT the teal color.
        teal_rgb = tuple(int(BORDER_COLOR.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
        border_pixel = img.getpixel((4, 4))
        assert border_pixel != teal_rgb, (
            f"hall-of-mirrors detected: pixel (4,4) is {border_pixel}, "
            f"matches bubble border {teal_rgb}"
        )
    finally:
        bubble.destroy()
```

---

## Performance Budget

**Target:** 30 fps minimum, 33 ms/frame budget. Recommended cap: 60 fps (16.6 ms/frame) because the clinic display refresh rate is likely 60 Hz.

| Step | Cost @ 400×400 bubble | Cost @ 700×700 bubble @ 6× zoom | Measured on | Source |
|------|------------------------|----------------------------------|-------------|--------|
| `state.capture_region()` | < 0.1 ms | < 0.1 ms | dev box | `state.py:66-69` — Lock acquire + tuple unpack only |
| `sct.grab({x,y,w,h})` | ~3 ms | ~3 ms | STACK.md benchmarks | mss C GDI BitBlt |
| `Image.frombytes("RGB", size, shot.rgb)` | ~1-2 ms | ~1-2 ms | STACK.md benchmarks | Pillow C decoder |
| `img.resize((w, h), BILINEAR)` | ~5-8 ms | ~12-18 ms | STACK.md benchmarks | Pillow C BILINEAR |
| `root.after(0, cb, img)` | < 0.1 ms | < 0.1 ms | Tk documented | Event-queue append |
| **Worker-side total** | **~8-13 ms** | **~16-23 ms** | | |
| `self._photo.paste(img)` | ~1 ms | ~3 ms | dev box (Pillow 12.1.1) | Verified 2026-04-11 |
| `canvas.itemconfig` (no-op fast path) | < 0.1 ms | < 0.1 ms | Tk | Item already references the photo |
| **Main-thread total** | **~1 ms** | **~3 ms** | | |
| **Total wall-clock per frame** | **~9-14 ms** | **~19-26 ms** | | |

**Budget analysis:**
- **400×400 @ 2×:** 14 ms end-to-end leaves ~20 ms of slack out of the 33 ms budget. Comfortable at 30 fps; can hit 60 fps with room to spare.
- **700×700 @ 6×:** 26 ms end-to-end leaves ~7 ms of slack. Tight but feasible at 30 fps. **This is the edge case.** If the clinic PC is slower than the dev box (likely — clinic hardware is typically 3-5 years old), this will drop to ~24-28 fps. That is still within the "30 fps minimum in the typical case" interpretation of CAPT-02, but the v2 PERF-01 adaptive-NEAREST fallback will likely be needed for long-term use at max settings.

**First-bottleneck prediction:** Pillow BILINEAR resize at 700×700 @ 6×. Mitigations in order of effort:
1. (v2 PERF-01) Switch to NEAREST when zoom > 4.0 AND bubble > 600 px.
2. Drop target fps from 30 to 20 at max settings only.
3. Pre-allocate the resize output buffer via `Image.resize(..., reducing_gap=2.0)` (Pillow 9.0+ optimization that avoids intermediate allocations).

**Frame pacing math:**
- `target_dt = 1 / 30 = 0.0333 s` (30 fps minimum, the spec)
- `target_dt = 1 / 60 = 0.0167 s` (60 fps cap, recommendation)
- Worker's `self._stop.wait(remaining)` sleeps for `target_dt - elapsed_cpu_time` — if the CPU work takes 14 ms, we sleep for 2.6 ms (60 fps) or 19.3 ms (30 fps), which is plenty of room for OS scheduling jitter without missing the frame budget.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `ImageTk.PhotoImage(img)` every frame | `self._photo.paste(img)` every frame | CPython issue 124364 filed 2024; fix was the documented `paste()` pattern from the start | Memory-stable hot loop on Windows |
| `PIL.ImageGrab.grab(bbox)` | `mss.mss().grab(region)` | mss ~2015; industry standard since 2018 | 3-10× faster; works headless / RDP |
| `cv2` / OpenCV capture | `mss` | Same era | No OpenCV C++ dependency in PyInstaller build (~70 MB savings) |
| `win32gui.GetWindowDC` + manual BitBlt via ctypes | mss wraps it | mss handles DPI, thread-local DCs, error retry | ~200 lines of ctypes saved |
| `time.sleep(1/30)` in capture loop | `self._stop.wait(remaining)` | tkthread issues / responsiveness requirements | Interruptible shutdown; <1 ms join latency |
| `numpy.frombuffer(shot.raw, uint8).reshape(h, w, 4)[..., :3]` for BGRA→RGB | `shot.rgb` (pre-converted in mss C) | mss 5.x+ | Skips a numpy allocation per frame |
| Hiding the window briefly before capture | `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` | Win10 2004 (2020) | No visible flicker at 30 fps |
| CAPTUREBLT workaround via `mss.windows.CAPTUREBLT = 0` (Path B) | + `SetWindowDisplayAffinity` (Path A) | Win10 2004 | OS-level defense is cleaner; Path B remains as belt-and-suspenders for older Windows |

**Deprecated / outdated:**
- `keyboard` library for hotkeys — archived Feb 2026 (affects Phase 6, not Phase 3)
- `dxcam` / `bettercam` for capture — fragile on clinic-like display configs
- LANCZOS resampling in the hot loop — 3-5× slower with no benefit for upscaling
- Storing frames in a big `queue.Queue` instead of frame-pacing the producer — wastes memory, no fps gain

---

## Open Questions

### Question 1: mss 10.1.0 + Pillow 11.3.0 wheel compatibility on Python 3.14.3

**What we know:**
- Dev box runs Python 3.14.3 (per STATE.md Phase 1-2 findings).
- pywin32 311 cp314 wheel verified working on dev box (Phase 2 P03 decisions log).
- Pillow 12.1.1 is already installed on the dev box and has been verified to work (Verification Protocol section below).
- `mss` 10.1.0 PyPI classifiers list `Python :: 3.14` support.

**What's unclear:**
- Whether `pip install mss==10.1.0` on Python 3.14.3 actually pulls a prebuilt cp314 wheel or falls back to a source install / a generic `py3-none-any` wheel. mss is pure Python + ctypes so it might be `py3-none-any`.
- Whether `pip install Pillow==11.3.0` on Python 3.14.3 succeeds (Pillow 11.x predates Python 3.14; the cp314 wheels may not exist, forcing a source build which requires libjpeg/zlib headers — potentially a clinic-PC blocker at Phase 8 packaging time).
- Whether the existing Pillow 12.1.1 on the dev box should be DOWNGRADED to 11.3.0 (per the pin) or whether requirements.txt should be updated to match what's actually installed.

**Recommendation:**
Plan 03-01's **first task** is a 5-minute verification: create a fresh venv on the dev box, `pip install mss==10.1.0 Pillow==11.3.0`, and report whether both wheels install without errors. Document the exact output in the plan's SUMMARY.md. If Pillow 11.3.0 fails to install on 3.14, update requirements.txt to `Pillow==12.1.1` (the installed version) and record the reason in STATE.md decisions. Both versions are API-compatible for every Phase 3 call we make (`Image.frombytes`, `Image.resize`, `Image.Resampling.BILINEAR`, `ImageTk.PhotoImage`, `paste`).

### Question 2: `SetWindowDisplayAffinity` behavior on clinic Windows 11 build

**What we know:**
- WDA_EXCLUDEFROMCAPTURE is Win10 2004+ (confirmed via Microsoft Learn).
- The clinic target is Windows 11; fully supported.
- Some enterprise environments (certain AV products, some group policies) are known to log or block display-affinity changes — this is undocumented folklore from the screen-sharing / DRM domain.

**What's unclear:**
- Whether the clinic's unknown AV product (ROADMAP.md Phase 8 blocker) interferes with SetWindowDisplayAffinity.
- Whether any clinic group policy blocks the API.
- Whether SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) visibly affects the bubble's own rendering (it shouldn't — it only affects CAPTURE, not display — but a smoke test is cheap).

**Recommendation:**
- Plan 03-02 implements BOTH Path A (SetWindowDisplayAffinity) and Path B (CAPTUREBLT=0) from the start. Both are one-liners; implementing both costs nothing.
- Plan 03-02 integration test's hall-of-mirrors check will fail fast on the clinic PC if Path A is blocked; Path B will then kick in silently.
- Document in Plan 03-02 SUMMARY: which Path actually provided the defense on the dev box (observable via GetWindowDisplayAffinity return value).
- If both paths fail on the clinic PC, Phase 3 is blocked on hardware and the user needs to investigate with clinic IT. Flag this in the Phase 3 completion criteria.

### Question 3: Frame-drop backpressure — do we need it in Phase 3?

**What we know:**
- At 30 fps producer with ~1 ms consumer, the Tk event queue never grows.
- `root.after(0, ...)` does not coalesce.
- PIL.Image is ~3 MB at 400×400 RGB, ~9 MB at 700×700.

**What's unclear:**
- Whether the Tk main thread can stall for > 33 ms under any Phase 3 scenario (drag + capture + WndProc IRQ). If it can, the producer will pile up callbacks and memory will grow.
- Whether Phase 2's drag path (Pattern 2b: `ReleaseCapture` + `SendMessage(WM_NCLBUTTONDOWN, HTCAPTION, 0)`) blocks the Tk event loop during the native OS move loop. If so, the worker will queue ~10-30 callbacks during a drag gesture.

**Recommendation:**
- Phase 3 ships with the simple `root.after(0, self._on_frame, img)` path.
- Plan 03-02 memory test runs 60 seconds and will fail if callbacks pile up.
- If it fails, swap `_on_frame` to a "latest-frame slot" pattern: worker stores the newest PIL.Image in `self._latest_frame` under a Lock; `root.after(0, ...)` is called with no argument; `_on_frame` reads the slot and clears it. This caps memory to exactly one frame regardless of queue depth.
- Do NOT implement the slot pattern prophylactically — the simpler approach is known-good at 30 fps, and adding a Lock to the hot path has its own cost.

### Question 4: Will `paste()` on a mismatched-size PhotoImage in Phase 4 cause visible artifacts?

**What we know:**
- `paste()` silently clips/pads on size mismatch (dev-box verified).
- Phase 3 detects size mismatch in `_on_frame` and rebuilds the PhotoImage.
- The rebuild happens ONCE per resize event (the AppState observer).

**What's unclear:**
- The latency between `state.set_size(new_w, new_h)` firing the observer, the worker picking up the new capture rect via `state.capture_region()`, and the main thread rebuilding `_photo`. If the worker's frame-in-flight arrives BEFORE the observer rebuilds, `_on_frame` will paste an old-size Image into a new-size PhotoImage (or vice versa).

**Recommendation:**
- Phase 3's `_on_frame` already handles this: it compares `img.size` to `self._photo_size` on every frame and rebuilds if mismatched. The observer is a fallback that proactively rebuilds so the next frame has nothing to do.
- Phase 4 resize test should verify: bubble is resized from 400×400 to 500×500 while the worker is running, and `_photo.width()` is 500 after the next 2 frames have been processed.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (installed via `requirements-dev.txt` — verified in Phase 1 P02) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `pythonpath = ["src"]`, `testpaths = ["tests"]` |
| Quick run command | `python -m pytest tests/test_capture.py -x` |
| Full suite command | `python -m pytest -ra` |
| Windows-only marker | `from tests.conftest import win_only` — skips on non-Windows via `sys.platform` check |
| Tk shared root fixture | `tk_session_root` (session-scoped Tk root) — required to avoid "SourceLibFile panedwindow" TclError on Python 3.14 + tk8.6 |
| Tk toplevel fixture | `tk_toplevel` (per-test Toplevel with HWND retrieved) — Phase 3 uses `tk_session_root` directly since `BubbleWindow` creates its own root internally |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CAPT-01 | mss captures region under bubble at real coords | Windows-only smoke | `python -m pytest tests/test_capture_smoke.py::test_capture_worker_starts_and_frames_arrive -x` | No — Wave 0 |
| CAPT-02 | Sustained ≥ 30 fps over 2s | Windows-only smoke | `python -m pytest tests/test_capture_smoke.py::test_capture_worker_achieves_30fps -x` | No — Wave 0 |
| CAPT-03 | No PIL.ImageGrab in hot loop | Lint (any platform) | `python -m pytest tests/test_capture.py::test_no_imagegrab_in_capture_source -x` | No — Wave 0 |
| CAPT-04 | Pillow BILINEAR resampling is used | Lint (any platform) | `python -m pytest tests/test_capture.py::test_capture_uses_bilinear_literal -x` | No — Wave 0 |
| CAPT-05 | Single PhotoImage reused via paste() — memory flat | Windows-only smoke + lint | `python -m pytest tests/test_capture_smoke.py::test_capture_memory_flat_over_60s -x`<br>`python -m pytest tests/test_capture.py::test_photoimage_constructed_exactly_twice_in_window -x` | No — Wave 0 |
| CAPT-06 | No hall-of-mirrors | Windows-only smoke + lint | `python -m pytest tests/test_capture_smoke.py::test_no_hall_of_mirrors -x`<br>`python -m pytest tests/test_window_integration.py::test_set_window_display_affinity -x` | Both — Wave 0 (test_window_integration.py exists but needs new test added) |

### Sampling Rate
- **Per task commit (Plan 03-01):** `python -m pytest tests/test_capture.py -x` — pure-Python lint + unit tests (any platform, ~2 seconds)
- **Per task commit (Plan 03-02):** `python -m pytest tests/test_capture.py tests/test_window_integration.py -x` — lint tests + the existing Phase 2 integration test (ensures Phase 3 additions don't regress Phase 2)
- **Per wave merge:** `python -m pytest -ra` — full suite, includes Windows-only smoke tests on the dev box
- **Phase gate:** Full suite green + a **manual 30-minute soak** of the running app on the dev box (covers Pitfall 7 GDI failure which the 60-second automated test cannot reach)

### Wave 0 Gaps
- [ ] `tests/test_capture.py` — pure-Python unit tests for CaptureWorker (fake mss, fake Pillow via monkeypatch, lint tests for ImageGrab absence / BILINEAR presence / mss.mss() call-site location / no time.sleep in run)
- [ ] `tests/test_capture_smoke.py` — Windows-only smoke tests (fps, memory, hall-of-mirrors) — requires a live BubbleWindow and a running mss
- [ ] `tests/test_window_integration.py` — EXTEND existing file with new tests:
  - `test_set_window_display_affinity` — assert GetWindowDisplayAffinity returns 0x11 (or 0x01 fallback)
  - `test_photo_attribute_exists` — assert `bubble._photo` is an ImageTk.PhotoImage
  - `test_image_id_in_canvas_items` — assert `bubble._image_id` is a valid canvas item tag
  - `test_capture_worker_lifecycle` — start, run briefly, destroy, assert worker thread is not alive
- [ ] No framework install needed — pytest + Pillow + mss are already in requirements-dev.txt

---

## Sources

### Primary (HIGH confidence)

- **[Microsoft Learn: BitBlt function](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-bitblt)** — authoritative definition of CAPTUREBLT: "Includes any windows that are layered on top of your window in the resulting image." Verified 2026-04-11.
- **[Microsoft Learn: SetWindowDisplayAffinity function](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity)** — WDA_EXCLUDEFROMCAPTURE = 0x00000011, Windows 10 Version 2004+. Verified 2026-04-11.
- **python-mss 10.1.0 source (v10.1.0 tag)** `src/mss/windows.py` — literal `gdi.BitBlt(..., SRCCOPY | CAPTUREBLT)` call verified via direct source fetch 2026-04-11. Github source.
- **[python-mss issue #179](https://github.com/BoboTiG/python-mss/issues/179)** — maintainer (BoboTiG) workaround `mss.windows.CAPTUREBLT = 0` confirmed in Aug 2020; issue closed.
- **[python-mss issue #273](https://github.com/BoboTiG/python-mss/issues/273)** — `'_thread._local' object has no attribute 'srcdc'` confirms mss 10.1.0 thread-local limitation.
- **[python-mss issue #267](https://github.com/BoboTiG/python-mss/issues/267)** — `gdi32.GetDIBits() failed after minutes of recording` — known bug in 10.1.0, fixed in 10.2.0.dev0.
- **python-mss v10.2.0.dev0 CHANGELOG** (on main branch) — confirms thread-safety improvements and GetDIBits→CreateDIBSection fix are post-10.1.0 only.
- **Pillow 12.1.1 `ImageTk.PhotoImage.__init__` and `.paste` docstrings** — pulled live from the installed Pillow on the dev box 2026-04-11 via `python -c "help(ImageTk.PhotoImage.__init__)"` and `help(ImageTk.PhotoImage.paste)`. Constructor signature: `(self, image: Image.Image | str | None = None, size: tuple[int, int] | None = None, **kw)`. Paste: `(self, im: Image.Image) -> None` — "The size must match the target region. If the mode does not match, the image is converted to the mode of the bitmap image."
- **Dev-box benchmark (Pillow 12.1.1, Python 3.14.3, Windows 11)** 2026-04-11: `ImageTk.PhotoImage(img)` = 2.41 ms/frame; `self._photo.paste(img)` = 1.07 ms/frame at 800×800 RGB. Confirms the 2.3× speedup in favor of the paste() pattern.
- **`.planning/research/STACK.md`** — pinned versions and pipeline timing (mss ~3 ms, frombytes ~2 ms, BILINEAR ~5-8 ms, PhotoImage ~3 ms). Cross-verified with live dev-box benchmarks 2026-04-11.
- **`.planning/research/ARCHITECTURE.md`** — thread model, `CaptureWorker` reserved name, Pattern 1 producer/consumer recipe. Used verbatim.
- **`.planning/research/PITFALLS.md`** — Pitfall 12 (PhotoImage leak), Pitfall 14 (cross-thread Tk), Pitfall 5 (DPI awareness). Used verbatim EXCEPT Pitfall 4 which is corrected in this document.
- **`src/magnifier_bubble/state.py`** — live source, `capture_region()` method at `state.py:66-69` confirmed.
- **`src/magnifier_bubble/window.py`** — live source, Phase 2 canvas/strip/border state confirmed; DRAG_STRIP_HEIGHT / CONTROL_STRIP_HEIGHT = 44 at `window.py:50-51`.
- **`tests/conftest.py`** — `tk_session_root` fixture confirmed at `conftest.py:27-46`.

### Secondary (MEDIUM confidence)

- **[python-mss CHANGELOG main branch](https://github.com/BoboTiG/python-mss/blob/main/CHANGELOG.md)** — 10.2.0.dev0 release notes fetched 2026-04-11, confirms 10.1.0 is the latest stable.
- **[tkinter threading patterns from multiple Python tutorials](https://www.pythontutorial.net/tkinter/tkinter-thread/)** — consensus on `root.after(0, ...)` pattern from worker threads. Cross-verified with Finxter, GeeksforGeeks, and runebook.dev. Not primary because the Python docs themselves are quiet on tkinter threading.
- **dev-box `winfo_x/y/rootx/rooty` behavior** — `root.geometry("400x300+150+100")` → `winfo_x=150, winfo_y=100, winfo_rootx=158, winfo_rooty=131`. Confirms the 8px default offset for a windowed Tk root; for an `overrideredirect(True)` window the offset should be 0.

### Tertiary (LOW confidence — flagged for validation)

- **WebSearch results on `winfo_x/y` under PMv2** — returned ambiguous results ("logical coordinates relative to primary monitor"). Not used for any load-bearing claim; the project's own Phase 1-2 evidence confirms physical pixels under PMv2.
- **tkthread library as an alternative to `root.after(0, ...)`** — found via WebSearch, not verified. Keep in reserve as a Phase 3 fallback if `root.after(0, ...)` shows unexpected issues, but do NOT add as a dependency prophylactically.

---

## Verification Protocol — Dev-Box Cross-Checks Performed 2026-04-11

These are the live Python sessions run against the dev-box environment (Python 3.14.3, Pillow 12.1.1, Windows 11) to verify load-bearing claims before including them in this document:

### Check 1: ImageTk.PhotoImage constructor signature
```python
from PIL import ImageTk; help(ImageTk.PhotoImage.__init__)
# Result: (self, image: Image.Image | str | None = None,
#          size: tuple[int, int] | None = None, **kw: Any) -> None
```
**Finding:** `ImageTk.PhotoImage("RGB", (w, h))` is the canonical positional form. The kwarg form `size=(w, h)` is accepted but calls before Tk root exists fail with `RuntimeError: Too early to create image: no default root window`.

### Check 2: ImageTk.PhotoImage.paste signature
```python
from PIL import ImageTk; help(ImageTk.PhotoImage.paste)
# Result: paste(self, im: Image.Image) -> None
#   "Paste a PIL image into the photo image."
#   "If the size does not match, the image is converted to the mode of
#    the bitmap image." [Note: docstring is ambiguous about size; tested below]
```
**Finding:** paste() does NOT resize. Tested: create PhotoImage(100,100), paste(Image of 200,200), PhotoImage size stays at 100x100 (clipped, no exception). This is why the `_on_frame` rebuild path is required on resize.

### Check 3: paste() vs new PhotoImage timing (n=100, 800×800 RGB)
```
new PhotoImage per frame: 2.41 ms/frame
paste per frame:          1.07 ms/frame
```
**Finding:** paste() is 2.3× faster before the memory leak hits. Confirms STACK.md's ~3 ms estimate for PhotoImage construction and gives a real number for paste.

### Check 4: tkinter winfo coordinates
```python
root.geometry("400x300+150+100")
root.update_idletasks()
# winfo_x=150, winfo_y=100, winfo_rootx=158, winfo_rooty=131
# winfo_width=400, winfo_height=300
```
**Finding:** `winfo_x/y` returns the geometry-requested values; `winfo_rootx/y` returns the actual client area (with 8px title-bar offset for a non-overrideredirect root). For an `overrideredirect(True)` window these should match. AppState's x/y come from `state.set_position` which is set from drag events — the authoritative source is the bubble's actual HWND rect, but AppState is the project-locked single source of truth and the Pattern 2b drag path keeps it in sync.

### Check 5: Python / Pillow / mss / pywin32 versions
```
Python: 3.14.3
Pillow: 12.1.1
mss:    NOT INSTALLED on dev box (must be installed in Plan 03-01 Task 1)
pywin32: 311 (verified Phase 2 P03)
```
**Finding:** mss must be installed as Plan 03-01 Task 1. Pillow is 12.1.1 not the pinned 11.3.0 — Open Question #1 addresses whether to bump the pin or downgrade the install.

---

## Metadata

**Confidence breakdown:**
- **Corrections to PITFALLS.md (hall-of-mirrors, thread safety):** HIGH — verified against live mss 10.1.0 source, Microsoft Learn, python-mss issue tracker, and mss CHANGELOG. Three independent sources for the CAPTUREBLT finding.
- **Standard stack (mss / Pillow / tkinter / threading / ctypes):** HIGH — all pinned and verified. Pillow API cross-checked against the installed version on the dev box.
- **Architecture patterns (CaptureWorker, paste reuse, SetWindowDisplayAffinity, AppState observer):** HIGH — directly derived from the project's own ARCHITECTURE.md (which is HIGH-confidence via Phase 2 research) plus Microsoft Learn for the new SetWindowDisplayAffinity call.
- **Performance budget:** MEDIUM — source numbers from STACK.md (unverified benchmarks) + dev-box verified paste() time. The 700×700 @ 6× edge case is an estimate; the actual clinic-PC measurement is a Phase 3 gate.
- **Common Pitfalls 1-7:** HIGH for pitfalls 1-5 (all verified against source / Microsoft Learn / existing PITFALLS.md); MEDIUM for Pitfall 6 (frame-drop backpressure is a theoretical concern, not observed); HIGH for Pitfall 7 (GetDIBits failure is a known mss 10.1.0 bug).
- **Open Questions 1-4:** MEDIUM — these are explicitly flagged as gaps that need Plan 03-01/02 to resolve.

**Research date:** 2026-04-11
**Valid until:** 2026-05-11 (30 days — stack is stable, mss is pinned, Pillow paste API is frozen). If mss 10.2.0 ships stable before Plan 03-01 starts, the thread-safety / GetDIBits corrections may be outdated — re-verify before planning.
