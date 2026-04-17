# Phase 7: DXGI Capture + Transparent Input — Research

**Researched:** 2026-04-17
**Domain:** dxcam (DXGI Desktop Duplication), WS_EX_TRANSPARENT zone management, window.py surgery
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Capture Engine:**
- Replace Magnification API (`_mag_init`, `_mag_tick`, `_hwnd_mag`, `magnification.dll`) with DXGI Desktop Duplication via the `dxcam` Python library (v0.3.0 already installed)
- Replace mss fallback path (`CaptureWorker`, `capture.py`, `_frame_queue`, `_poll_frame_queue`) — there is ONE capture path after this phase, not two
- dxcam captures the full DWM-composited frame; we crop to the source rect and resize with BILINEAR before writing to the canvas PhotoImage
- Hall-of-mirrors: `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` already set in Phase 2 continues to exclude the overlay — no additional work needed
- Target frame rate: 30 fps
- New module: `src/magnifier_bubble/capture_dxgi.py` — producer thread pattern identical to current `capture.py` but using dxcam

**Input Architecture:**
- Content zone: set `WS_EX_TRANSPARENT` on parent overlay HWND so mouse and touch fall through to underlying app
- Drag strip (top 44 px) and control strip (bottom 44 px): NOT transparent — overlay intercepts input normally
- Zone transitions tracked by a 50 ms polling timer (`_zone_transparency_poll`) on the Tk main thread using `GetCursorPos()` + window rect comparison
- `WS_EX_TRANSPARENT` added/removed via `SetWindowLongW(hwnd, GWL_EXSTYLE, ...)`

**Removed Code:**
- `src/magnifier_bubble/capture.py` — deleted (replaced entirely)
- `inject_click`, `inject_right_click` — deleted from clickthru.py
- `send_rclick_at` — deleted from clickthru.py (or kept if needed elsewhere)
- `_on_canvas_rclick` handler — deleted from window.py
- `_poll_menu_restore` method — deleted from window.py
- `_active_menu_hwnd`, `_active_menu_cls`, `_active_menu_skip_zorder` attributes — deleted
- `_mag_init`, `_mag_tick`, `_hwnd_mag`, `_mag_dll` — deleted from window.py
- All Z-order manipulation — deleted

**Kept Code:**
- `send_lclick_at`, `send_click_at`, `send_hover_at` — keep in clickthru.py (not called from window.py content zone)
- `wndproc.py` install/install_child/uninstall — unchanged
- Drag bar manual geometry drag — unchanged
- Control strip button handlers — unchanged
- `_dbg` / `_DEBUG_LOG` in clickthru.py — keep but disable before shipping

**Dependencies:**
- Add `dxcam==0.3.0` to `requirements.txt` and `requirements-dev.txt`
- Add `dxcam` hidden import to `naomi_zoom.spec` PyInstaller spec
- `comtypes` (dxcam dependency) also needs adding to spec hidden imports

**WS_EX_TRANSPARENT Behavior Contract:**
- When set: WindowFromPoint skips the overlay HWND; all mouse/touch events go to the topmost non-transparent window
- When not set: overlay intercepts events normally (drag and controls work)
- `WS_EX_TRANSPARENT` must NOT be set during drag or control interaction

**Debug Logging:**
- Disable `_DEBUG_LOG` in clickthru.py (`= None`) before shipping

### Claude's Discretion
(No explicit discretion areas defined in CONTEXT.md)

### Deferred Ideas (OUT OF SCOPE)
- WH_MOUSE_LL hook for right-click interception — not needed
- `send_lclick_at` / `send_click_at` callers removed from window.py but functions kept
- Multi-monitor DXGI output selection — deferred to Phase 9
- Touch-specific WM_POINTER handling — physical touch falls through WS_EX_TRANSPARENT naturally
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CAPT-01 | App captures screen pixels directly beneath the bubble at real screen coordinates | dxcam grab(region=...) uses physical pixel coordinates identical to mss; confirmed via empirical test |
| CAPT-02 | Capture runs at 30 fps minimum | dxcam uses Windows high-resolution timer internally; 30 fps easily achievable; CPU overhead measured lower than mss |
| CAPT-03 | PIL.ImageGrab is NOT used in the main capture loop | dxcam returns numpy array; PIL.Image.fromarray() used for conversion; ImageGrab not involved |
| CAPT-04 | Captured pixels magnified using Pillow BILINEAR resampling | img.resize((w, h), PIL.Image.BILINEAR) — same as current mss path |
| CAPT-05 | Per-frame rendering reuses single ImageTk.PhotoImage via paste() | Same single-PhotoImage paste() pattern; no change to _on_frame() |
| CAPT-06 | No hall-of-mirrors; overlay excluded from capture | WDA_EXCLUDEFROMCAPTURE already set in Phase 2 init; applies to DXGI capture path automatically |
| CTRL-01 | Top drag bar has grip indicator and is draggable | Unchanged; drag continues to intercept via WS_EX_TRANSPARENT removal from content zone + WndProc HTCAPTION for drag zone |
</phase_requirements>

---

## Summary

Phase 7 replaces two major systems in window.py: (1) the capture pipeline (Magnification API → dxcam DXGI), and (2) the click routing system (inject_click + _poll_menu_restore → WS_EX_TRANSPARENT content zone). Both changes reduce code volume and eliminate failure modes, making this primarily a deletion + replacement phase.

The dxcam library (0.3.0, already installed) provides DXGI Desktop Duplication through a clean Python API. It is confirmed to work from a worker thread, returns frames as numpy uint8 arrays in the requested color format, and handles its own frame deduplication (returning `None` when the screen has not changed). The processor backend must be `"numpy"` (not the default `"cv2"`) because opencv is not installed in this project's venv.

The WS_EX_TRANSPARENT approach for input pass-through is architecturally cleaner than click injection: the OS handles all input routing at the hardware level, no coordinate mapping is needed for user input, and right-clicks automatically open menus via physical input rather than synthetic PostMessageW. The 50 ms polling timer is sufficient granularity for human interaction (no zone transition in normal use crosses 50 ms without the cursor being inside the zone for at least one poll cycle).

**Primary recommendation:** Implement `capture_dxgi.py` as a near-copy of `capture.py` with dxcam substituted for mss, then surgically remove the entire Magnification API path and click injection infrastructure from `window.py`. The zone transparency poll is the only new mechanism added to window.py.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dxcam | 0.3.0 | DXGI Desktop Duplication frame capture | Already installed; DWM-level capture sees all composited windows including menus above our overlay |
| comtypes | 1.4.16 | COM interop used internally by dxcam | dxcam's direct dependency; no app code needed |
| numpy | 2.2.6 | Frame buffer array returned by dxcam | Already in requirements.txt; dxcam requires it |
| Pillow | 12.1.1 | BILINEAR resize + PhotoImage paste | Already in requirements.txt; unchanged from Phase 3 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dxcam processor "numpy" backend | built-in | Color conversion via Cython kernels | Always — cv2 not installed in this venv |
| ctypes.windll.user32 | stdlib | GetCursorPos, GetWindowLongW, SetWindowLongW | Zone transparency poll on Tk main thread |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| dxcam processor_backend="numpy" | processor_backend="cv2" | cv2 (opencv) is NOT installed in the venv; "numpy" uses compiled Cython kernels and works without cv2 |
| dxcam grab(new_frame_only=True) | grab(new_frame_only=False) | Default True returns None on duplicate frames (correct for us — skip that tick); False reuses last frame (wastes CPU) |
| 50 ms polling timer | WH_MOUSE_LL hook | Hook requires SetWindowsHookEx and a message pump; poll is simpler and sufficient for human-speed zone transitions |

**Installation — no installation needed, already present:**
```bash
# dxcam 0.3.0 already in .venv
# Add to requirements.txt:
# dxcam==0.3.0
```

**Version verification (confirmed 2026-04-17):**
```
dxcam: 0.3.0  (pip show dxcam)
comtypes: 1.4.16  (pip show comtypes)
numpy: 2.2.6  (pip show numpy)
```

---

## Architecture Patterns

### Recommended Project Structure
```
src/magnifier_bubble/
├── capture_dxgi.py     # NEW — replaces capture.py; DXGICaptureWorker
├── capture.py          # DELETE — CaptureWorker (mss) no longer needed
├── window.py           # MODIFIED — remove Mag API, remove inject, add zone poll
├── clickthru.py        # MODIFIED — remove inject_click, inject_right_click, send_rclick_at
├── winconst.py         # UNCHANGED (WS_EX_TRANSPARENT constant already there)
├── wndproc.py          # UNCHANGED
└── (all other files)   # UNCHANGED
```

### Pattern 1: DXGICaptureWorker (mirrors CaptureWorker structure)

**What:** Worker thread that calls `dxcam.create()` inside `run()` (thread-local constraint), grabs frames in a loop, converts to PIL.Image, puts on frame queue.

**When to use:** Always — this is the only capture path after Phase 7.

**Critical detail:** `dxcam.create()` is a singleton factory (one instance per device/output/backend tuple). Calling it on the worker thread ensures the DXCamera object is created on the same thread that calls `grab()`. In practice dxcam's grab() does NOT have a strict thread-local constraint like mss, but following the same create-in-run() pattern is safer and consistent with existing project convention.

**Color format:** Use `output_color="RGB"` and `processor_backend="numpy"`. The numpy backend uses compiled Cython kernels (_numpy_kernels.pyd) for BGRA→RGB conversion without requiring opencv. Frame returned as numpy uint8 array shape (H, W, 3). Convert with `PIL.Image.fromarray(frame)` directly — no channel slicing needed.

**Source confirmed:** Empirical test on this machine, 2026-04-17.

```python
# In capture_dxgi.py
class DXGICaptureWorker(threading.Thread):
    def run(self) -> None:
        import dxcam
        from PIL import Image

        camera = dxcam.create(output_color="RGB", processor_backend="numpy")
        import ctypes
        _winmm = ctypes.windll.winmm
        _winmm.timeBeginPeriod(1)
        try:
            while not self._stop.is_set():
                t0 = time.perf_counter()
                x, y, w, h, zoom = self._state.capture_region()
                if w <= 0 or h <= 0:
                    self._stop.wait(self._target_dt)
                    continue
                src_w = max(1, int(round(w / zoom)))
                src_h = max(1, int(round(h / zoom)))
                src_x = x + (w - src_w) // 2
                src_y = y + (h - src_h) // 2
                # region=(left, top, right, bottom) in physical screen pixels
                frame = camera.grab(
                    region=(src_x, src_y, src_x + src_w, src_y + src_h),
                    new_frame_only=True,
                )
                if frame is None:
                    # No new frame since last grab (screen unchanged) — skip
                    remaining = self._target_dt - (time.perf_counter() - t0)
                    if remaining > 0:
                        self._stop.wait(remaining)
                    continue
                img = Image.fromarray(frame)   # frame is already RGB (H, W, 3)
                img = img.resize((w, h), Image.BILINEAR)
                self._on_frame(img)
                self._fps_samples.append(time.perf_counter())
                remaining = self._target_dt - (time.perf_counter() - t0)
                if remaining > 0:
                    self._stop.wait(remaining)
        finally:
            _winmm.timeEndPeriod(1)
            camera.release()
```

### Pattern 2: Zone Transparency Poll

**What:** A 50 ms repeating `root.after()` timer on the Tk main thread that reads cursor position, computes which zone the cursor is in, and sets/clears `WS_EX_TRANSPARENT` on `self._hwnd`.

**When to use:** Started once at end of `__init__` (after `deiconify()`). Must be cancellable in `destroy()`.

**Source:** Verbatim from CONTEXT.md specifics section (verified against project's winconst.py constants).

```python
def _zone_transparency_poll(self) -> None:
    """50 ms timer: set WS_EX_TRANSPARENT when cursor is in content zone,
    clear it when cursor is in drag/control strip or outside overlay.
    Runs on Tk main thread only — safe to call SetWindowLongW."""
    if sys.platform != "win32" or not self._hwnd:
        return
    u32 = ctypes.windll.user32
    pt = ctypes.wintypes.POINT()
    u32.GetCursorPos(ctypes.byref(pt))
    wx = self.root.winfo_x()
    wy = self.root.winfo_y()
    ww = self.root.winfo_width()
    wh = self.root.winfo_height()
    cx = pt.x - wx
    cy = pt.y - wy
    in_overlay = 0 <= cx < ww and 0 <= cy < wh
    in_content = in_overlay and DRAG_STRIP_HEIGHT <= cy < (wh - CONTROL_STRIP_HEIGHT)
    cur_ex = u32.GetWindowLongW(self._hwnd, wc.GWL_EXSTYLE)
    has_t = bool(cur_ex & wc.WS_EX_TRANSPARENT)
    if in_content and not has_t:
        u32.SetWindowLongW(self._hwnd, wc.GWL_EXSTYLE, cur_ex | wc.WS_EX_TRANSPARENT)
    elif not in_content and has_t:
        u32.SetWindowLongW(self._hwnd, wc.GWL_EXSTYLE, cur_ex & ~wc.WS_EX_TRANSPARENT)
    self._zone_poll_id = self.root.after(50, self._zone_transparency_poll)
```

**Cancellation in destroy():** Store the `root.after()` return value in `self._zone_poll_id`. In `destroy()`, before `root.destroy()`:
```python
if self._zone_poll_id is not None:
    self.root.after_cancel(self._zone_poll_id)
    self._zone_poll_id = None
# Also: clear WS_EX_TRANSPARENT before destroy so WM_DELETE_WINDOW is delivered
if sys.platform == "win32" and self._hwnd:
    cur = u32.GetWindowLongW(self._hwnd, wc.GWL_EXSTYLE)
    u32.SetWindowLongW(self._hwnd, wc.GWL_EXSTYLE, cur & ~wc.WS_EX_TRANSPARENT)
```

### Pattern 3: start_capture() Simplification

**What:** `start_capture()` in window.py is simplified to one path — DXGICaptureWorker. The entire Magnification API branch (`if sys.platform == "win32" and self._mag_init()`) is removed.

```python
def start_capture(self) -> None:
    if self._capture_worker is not None:
        return
    from magnifier_bubble.capture_dxgi import DXGICaptureWorker
    self._capture_worker = DXGICaptureWorker(
        state=self.state,
        on_frame=self._frame_queue.put,
    )
    self._capture_worker.start()
    self._poll_frame_queue()
```

### Pattern 4: WndProc Interaction with WS_EX_TRANSPARENT

**What:** When `WS_EX_TRANSPARENT` is set on `self._hwnd`, `WindowFromPoint` skips the overlay entirely — the WndProc is not called for mouse events in the content zone. This means `WM_NCHITTEST` is NOT delivered to the canvas or any child HWND when the cursor is in a transparent region.

**Implication:** The existing WndProc chain (parent + Tk frame + canvas) continues to work correctly:
- Content zone: `WS_EX_TRANSPARENT` set → OS skips overlay → WndProc not called → click goes to window below. No change needed to wndproc.py.
- Drag zone: `WS_EX_TRANSPARENT` cleared → WndProc called → HTCAPTION returned → drag works.
- Control zone: `WS_EX_TRANSPARENT` cleared → WndProc called → HTCLIENT returned → Tk bindings fire.

**No changes to wndproc.py are needed.** The content zone WM_NCHITTEST → HTCLIENT path (which was wired for inject_click) is now dead code but harmless — it will only fire in the narrow window between a cursor entering content zone and the 50 ms poll setting TRANSPARENT.

### Anti-Patterns to Avoid

- **Creating dxcam camera on main thread then using from worker:** The singleton factory returns the same instance, but DXGI COM state is initialized on the calling thread. Always call `dxcam.create()` inside `run()`.
- **Using processor_backend="cv2" without installing opencv:** Will raise `ModuleNotFoundError: No module named 'cv2'` at first grab. Use `"numpy"` — the Cython .pyd is pre-compiled in the package wheel.
- **Pushing None to frame_queue:** dxcam returns `None` when no new frame is available (frame deduplication). Must check `if frame is None: continue` before converting to PIL.Image.
- **Leaving WS_EX_TRANSPARENT set on destroy:** If the window is destroyed with TRANSPARENT set, `WM_DELETE_WINDOW` may not be delivered to the Tk event loop. Clear TRANSPARENT before `root.destroy()`.
- **Cancelling _zone_poll_id after root.destroy():** `root.after_cancel()` requires a live root. Cancel in `destroy()` BEFORE `root.destroy()`, in the same position as config_writer.flush_pending() — at the top of the try block.
- **Using grab(new_frame_only=False) in the hot loop:** Returns the last frame even when screen is unchanged; wastes CPU converting and resizing identical data. Use `new_frame_only=True` (the default) and skip on None.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DXGI Desktop Duplication | Raw ctypes DXGI COM calls | dxcam 0.3.0 | 500+ lines of COM plumbing; dxcam handles duplicate frame detection, surface staging, GPU → CPU copy, output recovery |
| Frame deduplication | Compare pixel buffers | dxcam grab(new_frame_only=True) | Built into dxcam; returns None when presenter hasn't updated the swapchain |
| High-resolution capture timer | WinMM timeBeginPeriod in our loop | dxcam.start(target_fps=30) internal timer | dxcam.start() uses CreateWaitableTimerExW with high-resolution flag; however we use poll-mode grab() in our worker, so we keep our own timeBeginPeriod(1) |
| BGRA→RGB conversion | numpy slicing `frame[:,:,:3][...,::-1]` | `output_color="RGB"` in dxcam.create() | dxcam applies Cython kernels for color conversion in-GPU-copy path |
| Input pass-through routing | PostMessageW + Z-order walk | WS_EX_TRANSPARENT | OS handles all routing at hardware input level; correct for all input types including touch |

**Key insight:** The dxcam "numpy" backend with `output_color="RGB"` eliminates ALL manual color channel manipulation. The frame arrives as a correctly-ordered RGB uint8 numpy array (H, W, 3) that can be passed directly to `PIL.Image.fromarray(frame)`.

---

## Common Pitfalls

### Pitfall 1: dxcam Singleton Factory — "Already exists" Warning
**What goes wrong:** Calling `dxcam.create()` a second time for the same device/output/backend returns the existing released instance (if not GC'd) or warns "DXCamera instance already exists" and returns the old live instance.
**Why it happens:** `DXFactory` uses a `WeakValueDictionary` keyed by `(device_idx, output_idx, backend)`. If the old camera is still referenced, a new one is not created.
**How to avoid:** Always call `camera.release()` in the `finally:` block of `DXGICaptureWorker.run()`. After release, `camera.is_released == True` and the factory will recreate on the next `dxcam.create()` call (e.g., on worker thread restart after an error).
**Warning signs:** `[WARNING] DXCamera instance already exists...` in log output.

### Pitfall 2: cv2 Processor Default — ModuleNotFoundError
**What goes wrong:** `dxcam.create()` defaults to `processor_backend="cv2"`. First `grab()` call fails with `ModuleNotFoundError: No module named 'cv2'`.
**Why it happens:** opencv-python is not in this project's requirements.txt and not installed in the venv.
**How to avoid:** Always pass `processor_backend="numpy"` explicitly. The numpy backend uses `_numpy_kernels.cp311-win_amd64.pyd` (Cython extension, pre-compiled, in the dxcam wheel) and does not require cv2.
**Warning signs:** `ModuleNotFoundError` on first frame grab.

### Pitfall 3: WS_EX_TRANSPARENT + WM_DELETE_WINDOW Not Delivered
**What goes wrong:** User closes window (clicks X button in top strip). The WM_DELETE_WINDOW protocol message is not received by Tk. App appears frozen.
**Why it happens:** The close button is in the drag strip, which should have TRANSPARENT cleared. If the poll timer has a bug and leaves TRANSPARENT set, the close button click falls through to the underlying app.
**How to avoid:** In `destroy()`, explicitly clear `WS_EX_TRANSPARENT` before `root.destroy()`. The zone poll's `elif not in_content and has_t: clear` branch handles normal cases, but the explicit clear in `destroy()` is a belt-and-suspenders safety.
**Warning signs:** App can't be closed via the X button; close button click goes to app underneath.

### Pitfall 4: Zone Poll After root.destroy()
**What goes wrong:** `root.after()` callback fires after `root.destroy()` → TclError: "can't invoke after command: application has been destroyed".
**Why it happens:** The zone poll reschedules itself every 50 ms via `self.root.after(50, self._zone_transparency_poll)`. If `destroy()` doesn't cancel this chain, the last scheduled callback fires after `root.destroy()`.
**How to avoid:** Store the after-ID in `self._zone_poll_id`. In `destroy()`, call `self.root.after_cancel(self._zone_poll_id)` BEFORE `root.destroy()`. This is the same pattern as `_poll_frame_queue` (though current code does NOT store its after-ID — a pre-existing issue). Phase 7 must store `_zone_poll_id`.
**Warning signs:** TclError on teardown involving "after".

### Pitfall 5: _poll_frame_queue After-ID Not Cancelled
**What goes wrong:** (Pre-existing) `_poll_frame_queue` also reschedules itself every 16 ms but the after-ID is not stored or cancelled in `destroy()`. Phase 7 is a good time to fix this.
**How to avoid:** Store `self._poll_frame_queue_id = self.root.after(16, self._poll_frame_queue)` and cancel in `destroy()`. Add alongside `_zone_poll_id` cancellation.
**Warning signs:** TclError on teardown.

### Pitfall 6: _on_canvas_press Still References _active_menu_hwnd
**What goes wrong:** After deleting `_active_menu_hwnd` attribute, any remaining reference in `_on_canvas_press` raises `AttributeError`.
**Why it happens:** `window.py` has extensive click injection logic in `_on_canvas_press` that checks `self._active_menu_hwnd`, imports from clickthru, calls `inject_click`, `inject_touch_at`, etc. All of this must be removed as part of the Phase 7 cleanup.
**How to avoid:** `_on_canvas_press` should be simplified to ONLY handle button dispatch + drag start. The content-zone click injection block (everything from `if ( self._click_injection_enabled ...` to the end of the function) is entirely deleted.
**Warning signs:** `AttributeError: 'BubbleWindow' object has no attribute '_active_menu_hwnd'`.

### Pitfall 7: dxcam grab() Region Coordinates vs. Physical Pixels
**What goes wrong:** Capture region is offset or wrong size, causing the magnified view to show the wrong part of the screen.
**Why it happens:** mss used a dict `{"left": x, "top": y, "width": w, "height": h}`. dxcam uses `(left, top, right, bottom)` — a 4-tuple with the BOTTOM-RIGHT corner, not width/height.
**How to avoid:** `region=(src_x, src_y, src_x + src_w, src_y + src_h)` — always compute the right/bottom by adding the width/height. Empirically verified: region `(100, 100, 500, 400)` returns frame shape `(300, 400, 3)` as expected (height=300, width=400).
**Warning signs:** Capture region is double-sized or offset by the source dimensions.

### Pitfall 8: Intel GPU — dxcam device_idx=0
**What goes wrong:** On a system with both Intel iGPU and discrete GPU, `device_idx=0` may select the Intel adapter, which may have performance or compatibility issues with DXGI Desktop Duplication.
**Why it happens:** DXGI adapter enumeration order varies. Some systems list Intel as adapter 0.
**Assessment (MEDIUM confidence — clinic hardware unknown):** The dev machine has NVIDIA RTX 4060 Ti as the only device (`Device[0]`). The clinic PC (touchscreen) likely has Intel integrated graphics only. DXGI Desktop Duplication is supported on Intel integrated graphics on Windows 8+ — no known blocking issues for basic capture. dxcam's `device_idx=0` defaults to the first adapter returned by `IDXGIFactory::EnumAdapters`.
**How to avoid:** Use `dxcam.create(device_idx=0)` (the default). Add a try/except around `dxcam.create()` in `run()` so a hardware failure is logged and the thread exits gracefully rather than crashing.
**Warning signs:** `Exception in DXGICaptureWorker` in output; no frames displayed.

### Pitfall 9: _click_injection_enabled Flag Becomes Dead Code
**What goes wrong:** `BubbleWindow.__init__` still accepts `click_injection_enabled` parameter; `app.py` still passes it; `--no-click-injection` CLI flag is still parsed.
**Why it happens:** These were wired in Phase 4 to support the click injection architecture, which is now deleted.
**How to avoid:** Remove the `click_injection_enabled` parameter from `BubbleWindow.__init__`, the `self._click_injection_enabled` attribute, the `argparse` flag in `app.py`, and the `--no-click-injection` CLI documentation. Phase 7 must clean up this dead code or tests that assert on these will break (e.g., `test_app_parses_no_click_injection_flag` in `test_clickthru.py`).
**Warning signs:** Stale tests in `test_clickthru.py` that assert on the `--no-click-injection` flag.

---

## Code Examples

Verified patterns from official sources / empirical testing:

### dxcam.create() with numpy backend (empirically verified 2026-04-17)
```python
# Source: empirical test on this machine
import dxcam
# MUST specify processor_backend="numpy" — cv2 not installed
camera = dxcam.create(output_color="RGB", processor_backend="numpy")
# Returns numpy uint8 array (H, W, 3) or None if no new frame
frame = camera.grab(region=(left, top, right, bottom), new_frame_only=True)
if frame is not None:
    from PIL import Image
    img = Image.fromarray(frame)  # No channel manipulation needed — already RGB
camera.release()
```

### Region coordinate format (empirically verified)
```python
# Source: empirical test — region=(100, 100, 500, 400) returned shape (300, 400, 3)
# dxcam region = (left, top, right, bottom) — NOT (left, top, width, height)
src_w = max(1, int(round(w / zoom)))
src_h = max(1, int(round(h / zoom)))
src_x = x + (w - src_w) // 2
src_y = y + (h - src_h) // 2
frame = camera.grab(region=(src_x, src_y, src_x + src_w, src_y + src_h))
```

### Worker thread safety (empirically verified 2026-04-17)
```python
# Source: empirical test — grab() called from threading.Thread succeeds
# dxcam.create() and grab() both work correctly from a non-main thread
# Confirmed: 5/5 grabs returned correct (400, 300) shaped frames from worker thread
def run(self):
    camera = dxcam.create(output_color="RGB", processor_backend="numpy")
    # ... loop calling camera.grab() from this thread ...
    camera.release()
```

### WS_EX_TRANSPARENT zone poll (from CONTEXT.md, consistent with existing window.py pattern)
```python
# Source: CONTEXT.md specifics + existing clickthru.py WS_EX_TRANSPARENT pattern
def _zone_transparency_poll(self) -> None:
    u32 = ctypes.windll.user32
    pt = ctypes.wintypes.POINT()
    u32.GetCursorPos(ctypes.byref(pt))
    wx, wy = self.root.winfo_x(), self.root.winfo_y()
    ww, wh = self.root.winfo_width(), self.root.winfo_height()
    cx, cy = pt.x - wx, pt.y - wy
    in_content = (0 <= cx < ww and 0 <= cy < wh
                  and DRAG_STRIP_HEIGHT <= cy < (wh - CONTROL_STRIP_HEIGHT))
    cur_ex = u32.GetWindowLongW(self._hwnd, wc.GWL_EXSTYLE)
    has_t = bool(cur_ex & wc.WS_EX_TRANSPARENT)
    if in_content and not has_t:
        u32.SetWindowLongW(self._hwnd, wc.GWL_EXSTYLE, cur_ex | wc.WS_EX_TRANSPARENT)
    elif not in_content and has_t:
        u32.SetWindowLongW(self._hwnd, wc.GWL_EXSTYLE, cur_ex & ~wc.WS_EX_TRANSPARENT)
    self._zone_poll_id = self.root.after(50, self._zone_transparency_poll)
```

### destroy() teardown additions
```python
def destroy(self) -> None:
    try:
        # 0. Cancel zone poll BEFORE anything else (needs live root)
        if self._zone_poll_id is not None:
            try:
                self.root.after_cancel(self._zone_poll_id)
            except Exception:
                pass
            self._zone_poll_id = None
        # 0b. Clear WS_EX_TRANSPARENT so WM_DELETE_WINDOW is delivered
        if sys.platform == "win32" and self._hwnd:
            u32 = ctypes.windll.user32
            cur = u32.GetWindowLongW(self._hwnd, wc.GWL_EXSTYLE)
            u32.SetWindowLongW(self._hwnd, wc.GWL_EXSTYLE, cur & ~wc.WS_EX_TRANSPARENT)
        # 1. config_writer.flush_pending() ...
        # 2. hotkey_manager.stop() ...
        # 3. capture_worker.stop() / join() ...
        # (NO Magnification API cleanup — _mag_dll is deleted)
        # 4. WndProc uninstall ...
    finally:
        self.root.destroy()
```

### PyInstaller spec additions
```python
# In naomi_zoom.spec hiddenimports=[...], ADD:
'dxcam',
'dxcam.dxcam',
'dxcam._libs',
'dxcam._libs.d3d11',
'dxcam._libs.dxgi',
'dxcam._libs.user32',
'dxcam.core',
'dxcam.core.backend',
'dxcam.core.capture_loop',
'dxcam.core.capture_runtime',
'dxcam.core.device',
'dxcam.core.display_recovery',
'dxcam.core.duplicator',
'dxcam.core.dxgi_duplicator',
'dxcam.core.dxgi_errors',
'dxcam.core.output',
'dxcam.core.output_recovery',
'dxcam.core.stagesurf',
'dxcam.processor',
'dxcam.processor.base',
'dxcam.processor.numpy_processor',
'dxcam.processor.cv2_processor',   # imported by numpy_processor for fallback
'dxcam.types',
'dxcam.util',
'dxcam.util.io',
'dxcam.util.timer',
'comtypes',
'comtypes.client',
```

**Note:** `dxcam.processor._numpy_kernels` is a .pyd file — PyInstaller includes .pyd extensions automatically as binaries, not as Python modules. Do NOT add it to hiddenimports.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| mss + PostMessageW click injection | dxcam + WS_EX_TRANSPARENT | Phase 7 | Eliminates 300+ lines of Z-order, menu detection, and click routing code |
| Magnification API (DWM child window) | DXGI Desktop Duplication (dxcam) | Phase 7 | Captures the full composited desktop frame including menus at any Z-order |
| _poll_menu_restore 50ms poll | _zone_transparency_poll 50ms poll | Phase 7 | Same polling cadence, but simpler purpose: just track cursor zone |
| inject_click PostMessageW | Physical mouse input (falls through WS_EX_TRANSPARENT) | Phase 7 | No coordinate mapping, no window class detection, no Chrome/WinUI3 special cases |

**Deprecated/outdated after Phase 7:**
- `capture.py` (CaptureWorker): deleted entirely; replaced by `capture_dxgi.py`
- `magnification.dll` usage: removed; no longer needed
- `_active_menu_hwnd` pattern: concept eliminated; WS_EX_TRANSPARENT handles all input routing
- `--no-click-injection` CLI flag: removed (click injection no longer exists)
- `_click_injection_enabled` attribute: removed

---

## Open Questions

1. **Intel iGPU on clinic touchscreen — dxcam device_idx=0**
   - What we know: DXGI Desktop Duplication is supported on Intel integrated graphics on Windows 8+. dxcam 0.3.0 has been tested on NVIDIA RTX 4060 Ti (dev machine). The clinic PC hardware is unknown.
   - What's unclear: Whether the Intel iGPU (if it is the only adapter) causes any issues with dxcam output recovery or the DXGI duplicator initialization.
   - Recommendation: Wrap `dxcam.create()` in try/except inside `run()`. If it fails, log clearly and let the thread exit cleanly. Document in verification checklist as CHECK 1.

2. **_numpy_kernels.pyd inclusion in PyInstaller exe**
   - What we know: `_numpy_kernels.cp311-win_amd64.pyd` is a compiled Cython extension. PyInstaller should include .pyd files as binaries automatically when the package is collected.
   - What's unclear: Whether PyInstaller 6.11.1 correctly collects the dxcam .pyd without an explicit `collect_data` directive.
   - Recommendation: Test the built exe on Phase 9 verification. If `ModuleNotFoundError: _numpy_kernels` occurs at runtime, add `datas=[('.venv/Lib/site-packages/dxcam/processor/_numpy_kernels.cp311-win_amd64.pyd', 'dxcam/processor')]` to the spec. This is a Phase 9 concern, not Phase 7.

3. **comtypes logging noise on first import**
   - What we know: dxcam.__init__ calls `_configure_comtypes_logging()` which sets comtypes loggers to INFO level. Without this, comtypes emits debug-level COM Release messages per frame.
   - What's unclear: Whether importing dxcam on the worker thread (inside `run()`) re-runs `_configure_comtypes_logging()` or whether it was already run at module import time.
   - Recommendation: `import dxcam` inside `run()` is a first-import if the module hasn't been imported yet. The factory initialization (`__factory = DXFactory()`) runs at module import time. This is fine — the singleton is created once and reused. No action needed.

4. **test_clickthru.py stale assertions after code removal**
   - What we know: `tests/test_clickthru.py` contains 14+ tests that assert on `inject_click` signatures, `_on_canvas_press` routing, `--no-click-injection` flag, etc. Most of these will fail after Phase 7 deletes the injected code.
   - What's unclear: Whether these tests should be deleted, updated, or replaced.
   - Recommendation: Phase 7 Plan 1 (Wave 0) should audit `test_clickthru.py` and mark obsolete tests for deletion/replacement. `test_capture.py` tests for CaptureWorker (mss) will also need replacement with `test_capture_dxgi.py` tests.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (pyproject.toml pytest.ini_options) |
| Config file | `pyproject.toml` |
| Quick run command | `python -m pytest tests/test_capture_dxgi.py tests/test_clickthru.py tests/test_window_phase4.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CAPT-01 | dxcam captures at correct physical pixel coordinates | unit (structural) | `pytest tests/test_capture_dxgi.py::test_region_coordinates_use_right_bottom -x` | Wave 0 |
| CAPT-02 | DXGICaptureWorker achieves 30 fps | smoke (Windows-only) | `pytest tests/test_capture_dxgi_smoke.py::test_achieves_30fps -x` | Wave 0 |
| CAPT-03 | PIL.ImageGrab not used in capture_dxgi.py | unit (AST lint) | `pytest tests/test_capture_dxgi.py::test_no_imagegrab -x` | Wave 0 |
| CAPT-04 | Pillow BILINEAR resampling used | unit (source lint) | `pytest tests/test_capture_dxgi.py::test_uses_bilinear -x` | Wave 0 |
| CAPT-05 | Single PhotoImage reused via paste() | unit (existing) | `pytest tests/test_window_integration.py -x -q` | existing |
| CAPT-06 | No hall-of-mirrors | smoke (Windows-only) | `pytest tests/test_capture_dxgi_smoke.py::test_no_hall_of_mirrors -x` | Wave 0 |
| CTRL-01 | Drag bar draggable after transparent zone install | manual | N/A — manual verification CHECK 5 | manual |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_capture_dxgi.py tests/test_clickthru.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_capture_dxgi.py` — structural + source lint tests for DXGICaptureWorker (mirrors test_capture.py structure; covers CAPT-01, CAPT-03, CAPT-04)
- [ ] `tests/test_capture_dxgi_smoke.py` — Windows-only fps/memory/hall-of-mirrors smoke tests (covers CAPT-02, CAPT-06)
- [ ] Audit + update `tests/test_clickthru.py` — delete tests for inject_click, inject_right_click, send_rclick_at, --no-click-injection, _active_menu_hwnd; add structural tests for remaining kept functions (send_lclick_at, send_click_at, send_hover_at)
- [ ] Audit + update `tests/test_capture.py` — tests reference CaptureWorker in capture.py which will be deleted; these tests must either be deleted or migrated to test_capture_dxgi.py
- [ ] Audit `tests/test_window_phase4.py` — tests for _on_canvas_press content-zone injection path (inject_click, _active_menu_hwnd) must be removed; zone poll tests must be added

---

## Sources

### Primary (HIGH confidence)
- Empirical testing on this machine (2026-04-17) — dxcam 0.3.0 API, color format, thread safety, region coordinates
- dxcam source code in `.venv/Lib/site-packages/dxcam/` — DXFactory singleton, DXCamera.grab() contract, NumpyProcessor behavior
- Project source files — window.py, capture.py, clickthru.py, winconst.py, wndproc.py (read directly)
- CONTEXT.md decisions — locked implementation decisions (verbatim)

### Secondary (MEDIUM confidence)
- dxcam PyPI page: https://pypi.org/project/dxcam/ — version and dependency confirmation
- CLAUDE.md pitfalls log — pitfalls 1-15 verified against source code

### Tertiary (LOW confidence)
- Intel integrated graphics DXGI Desktop Duplication compatibility — general Windows documentation knowledge; clinic hardware not tested
- PyInstaller .pyd collection behavior — known PyInstaller behavior; specific dxcam .pyd collection not empirically tested

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — dxcam 0.3.0 empirically verified; comtypes/numpy versions confirmed from pip show
- Architecture: HIGH — patterns derived from source code reading + empirical API tests + CONTEXT.md locked decisions
- Pitfalls: HIGH — most pitfalls derived from direct code reading (AttributeError on _active_menu_hwnd, WS_EX_TRANSPARENT on destroy, etc.); Intel GPU pitfall is MEDIUM (unverified on clinic hardware)
- PyInstaller hidden imports: MEDIUM — list derived from pkgutil.walk_packages; actual bundling behavior not tested

**Research date:** 2026-04-17
**Valid until:** 2026-06-17 (dxcam 0.3.0 is a pinned dependency; stable)

---

## RESEARCH COMPLETE

**Phase:** 7 - DXGI Capture + Transparent Input
**Confidence:** HIGH

### Key Findings
- dxcam 0.3.0 is already installed, confirmed working from worker thread, region format is `(left, top, right, bottom)`, output format with `output_color="RGB"` is numpy uint8 (H, W, 3) ready for `PIL.Image.fromarray(frame)` — no channel manipulation needed
- `processor_backend="numpy"` is REQUIRED (not the default "cv2") because opencv is not installed in this venv; the Cython `_numpy_kernels.pyd` handles color conversion
- The WS_EX_TRANSPARENT zone poll pattern is a clean replacement for all click injection machinery; WM_DELETE_WINDOW delivery requires clearing TRANSPARENT before `root.destroy()`
- Phase 7 is primarily a deletion phase: window.py loses ~400 lines (Mag API, inject paths, _poll_menu_restore), clickthru.py loses inject_click + inject_right_click + send_rclick_at, capture.py is deleted entirely
- `_zone_poll_id` must be stored and cancelled in `destroy()` before `root.destroy()` — same pattern needed for `_poll_frame_queue_id` (a pre-existing gap)
- PyInstaller spec needs dxcam and all its submodules as hiddenimports; `comtypes` also needed; `_numpy_kernels.pyd` is collected as a binary automatically

### File Created
`.planning/phases/07-dxgi-capture-transparent-input/07-RESEARCH.md`

### Confidence Assessment
| Area | Level | Reason |
|------|-------|--------|
| Standard stack | HIGH | Empirically tested dxcam API on this machine |
| Architecture | HIGH | Direct source code + CONTEXT.md locked decisions |
| Pitfalls | HIGH | Most derived from actual code reading; Intel GPU is MEDIUM |
| PyInstaller imports | MEDIUM | List from pkgutil; bundling not empirically tested |

### Open Questions
1. Intel iGPU on clinic touchscreen — wrap `dxcam.create()` in try/except; verify in Phase 7 CHECK 1
2. PyInstaller .pyd collection — validate in Phase 9; fallback is explicit spec datas entry
3. Stale test_clickthru.py and test_capture.py tests — audit in Wave 0 plan

### Ready for Planning
Research complete. Planner can now create PLAN.md files.
