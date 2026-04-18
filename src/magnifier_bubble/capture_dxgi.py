"""DXGICaptureWorker — Phase 7 replacement for CaptureWorker (mss).

Uses dxcam (DXGI Desktop Duplication) instead of mss.  DWM-level capture
sees ALL composited windows including context menus above the overlay —
the core advantage over mss BitBlt which misses layered/popup windows.

THREAD CONSTRAINT: dxcam.create() MUST be called inside run() on the
worker thread.  Same pattern as capture.py mss thread-local contract.

COLOR FORMAT: output_color="RGB" with processor_backend="numpy" produces
numpy uint8 (H, W, 3) RGB arrays.  PIL.Image.fromarray(frame) works
directly — no channel manipulation needed.  The opencv processor backend
is NOT installed in this venv and must NOT be referenced.

REGION FORMAT: dxcam uses per-output (left, top, right, bottom) coordinates.
Each dxcam output represents one physical monitor.  Region coordinates are
relative to that output's top-left corner — NOT absolute virtual-screen
coordinates.  On single-monitor systems output 0 starts at (0, 0) so virtual
and per-output coordinates are identical.  On multi-monitor systems, region
coordinates must be offset by subtracting the monitor's virtual-screen origin.

FRAME DEDUPLICATION: grab(new_frame_only=True) returns None when the
desktop has not changed.  Do NOT push None to the frame queue.

MULTI-MONITOR: The worker detects which physical monitor contains the source
region center on every frame.  When the bubble crosses a monitor boundary the
old camera is released and a new one is created for the new output_idx.
Monitor enumeration order (EnumDisplayMonitors) matches dxcam output_idx order.

CLEANUP: camera.release() MUST be called in the finally block so the
dxcam DXFactory WeakValueDictionary releases the singleton reference.
Without this, the next dxcam.create() call may reuse a released instance
and log a "[WARNING] DXCamera instance already exists" message.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
import time
from collections import deque
from typing import Callable, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage
    from magnifier_bubble.state import AppState

FrameCallback = Callable[["PILImage"], None]


# ---------------------------------------------------------------------------
# Monitor enumeration helpers (Windows-only; no-op stubs on other platforms)
# ---------------------------------------------------------------------------

class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", ctypes.wintypes.RECT),
        ("rcWork", ctypes.wintypes.RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


def _enumerate_monitors() -> List[Tuple[int, int, int, int]]:
    """Return list of (left, top, right, bottom) for each monitor.

    Enumeration order matches dxcam's output_idx assignment — both use the
    same underlying Windows monitor enumeration path (EnumDisplayMonitors
    and IDXGIAdapter::EnumOutputs follow the same device order on single-GPU
    systems with the primary GPU at adapter index 0).
    """
    import sys
    if sys.platform != "win32":
        return [(0, 0, 1920, 1080)]

    monitors: List[Tuple[int, int, int, int]] = []

    _MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.wintypes.RECT),
        ctypes.c_long,
    )

    def _cb(hmon: int, hdc: int, rect_ptr, data: int) -> bool:  # type: ignore[override]
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(info))  # type: ignore[attr-defined]
        r = info.rcMonitor
        monitors.append((r.left, r.top, r.right, r.bottom))
        return True

    ctypes.windll.user32.EnumDisplayMonitors(  # type: ignore[attr-defined]
        None, None, _MONITORENUMPROC(_cb), 0
    )
    if not monitors:
        monitors = [(0, 0, 1920, 1080)]
    return monitors


def _output_for_center(
    cx: int, cy: int, monitors: List[Tuple[int, int, int, int]]
) -> Tuple[int, int, int]:
    """Return (output_idx, mon_left, mon_top) for the monitor containing (cx, cy).

    Falls back to output 0 if the point is outside all known monitors
    (e.g., bubble partially off-screen or monitors not yet re-enumerated).
    """
    for i, (left, top, right, bottom) in enumerate(monitors):
        if left <= cx < right and top <= cy < bottom:
            return i, left, top
    return 0, monitors[0][0], monitors[0][1]


# ---------------------------------------------------------------------------
# DXGICaptureWorker
# ---------------------------------------------------------------------------

class DXGICaptureWorker(threading.Thread):
    """30 fps DXGI Desktop Duplication capture producer thread.

    Multi-monitor aware: automatically switches dxcam output when the bubble
    crosses a monitor boundary.  Region coordinates are translated from
    virtual-screen space to per-output space before each grab.
    """

    def __init__(
        self,
        state: "AppState",
        on_frame: FrameCallback,
        target_fps: float = 30.0,
        new_frame_only: bool = True,
    ) -> None:
        super().__init__(daemon=True, name="magnifier-dxgi-capture")
        self._state = state
        self._on_frame = on_frame
        self._target_dt = 1.0 / max(1.0, target_fps * 1.05)
        self._new_frame_only = new_frame_only
        # NOTE: named _stop_ev (not _stop) to avoid shadowing threading.Thread._stop()
        # which is called internally by join().  Shadowing it converts _stop() calls
        # into Event method calls, raising TypeError: 'Event' object is not callable.
        self._stop_ev = threading.Event()
        self._fps_samples: deque[float] = deque(maxlen=60)

    def stop(self) -> None:
        """Signal the worker to exit its frame loop."""
        self._stop_ev.set()

    def get_fps(self) -> float:
        """Return the rolling 60-frame average FPS, or 0.0 if < 2 samples."""
        samples = list(self._fps_samples)
        if len(samples) < 2:
            return 0.0
        span = samples[-1] - samples[0]
        if span <= 0:
            return 0.0
        return (len(samples) - 1) / span

    def run(self) -> None:
        """Main loop: create dxcam camera on this thread, then capture frames."""
        import ctypes as _ctypes
        from PIL import Image

        _winmm = _ctypes.windll.winmm  # type: ignore[attr-defined]
        _winmm.timeBeginPeriod(1)

        camera = None
        current_output_idx = -1  # force camera creation on first iteration
        mon_left = 0
        mon_top = 0

        try:
            import dxcam

            # Enumerate monitors once at thread start.  If the display
            # configuration changes while running the user must restart.
            monitors = _enumerate_monitors()

            while not self._stop_ev.is_set():
                t0 = time.perf_counter()
                x, y, w, h, zoom = self._state.capture_region()
                if w <= 0 or h <= 0:
                    self._stop_ev.wait(self._target_dt)
                    continue

                src_w = max(1, int(round(w / zoom)))
                src_h = max(1, int(round(h / zoom)))
                src_x = x + (w - src_w) // 2
                src_y = y + (h - src_h) // 2

                # Determine which monitor contains the center of the source rect.
                cx = src_x + src_w // 2
                cy = src_y + src_h // 2
                output_idx, mon_left, mon_top = _output_for_center(cx, cy, monitors)

                # Switch cameras when the bubble crosses a monitor boundary.
                if output_idx != current_output_idx:
                    if camera is not None:
                        try:
                            camera.release()
                        except Exception:
                            pass
                        camera = None
                    try:
                        camera = dxcam.create(
                            output_idx=output_idx,
                            output_color="RGB",
                            processor_backend="numpy",
                        )
                        current_output_idx = output_idx
                    except Exception as exc:
                        # Output index may not exist (e.g., 2-monitor system
                        # with only output 0 and 1).  Fall back to primary.
                        print(f"[dxcam] create(output_idx={output_idx}) failed: {exc}", flush=True)
                        if output_idx != 0:
                            try:
                                camera = dxcam.create(
                                    output_idx=0,
                                    output_color="RGB",
                                    processor_backend="numpy",
                                )
                                current_output_idx = 0
                                mon_left, mon_top = monitors[0][0], monitors[0][1]
                            except Exception as exc2:
                                print(f"[dxcam] create(output_idx=0) also failed: {exc2}", flush=True)
                                self._stop_ev.wait(1.0)
                                continue
                        else:
                            self._stop_ev.wait(1.0)
                            continue

                # Translate virtual-screen coordinates to per-output coordinates.
                # dxcam region is relative to the output's top-left corner.
                adj_x = src_x - mon_left
                adj_y = src_y - mon_top

                # Clamp region to valid per-output bounds (0,0)..(mon_w,mon_h).
                # The overlay can extend past a screen edge; an out-of-bounds
                # grab raises an exception that kills the worker thread (freeze).
                mon_w = monitors[output_idx][2] - monitors[output_idx][0]
                mon_h = monitors[output_idx][3] - monitors[output_idx][1]
                r_left = max(0, adj_x)
                r_top = max(0, adj_y)
                r_right = min(mon_w, adj_x + src_w)
                r_bottom = min(mon_h, adj_y + src_h)

                if r_left >= r_right or r_top >= r_bottom:
                    # Entire source region is off-screen — skip frame
                    remaining = self._target_dt - (time.perf_counter() - t0)
                    if remaining > 0:
                        self._stop_ev.wait(remaining)
                    continue

                try:
                    frame = camera.grab(
                        region=(r_left, r_top, r_right, r_bottom),
                        new_frame_only=self._new_frame_only,
                    )
                except Exception as exc:
                    print(f"[dxcam] grab error: {exc}", flush=True)
                    remaining = self._target_dt - (time.perf_counter() - t0)
                    if remaining > 0:
                        self._stop_ev.wait(remaining)
                    continue

                if frame is None:
                    # No new frame (screen unchanged) — skip this tick
                    remaining = self._target_dt - (time.perf_counter() - t0)
                    if remaining > 0:
                        self._stop_ev.wait(remaining)
                    continue

                # frame is already RGB (H, W, 3) — fromarray works directly
                img = Image.fromarray(frame)

                # If the region was clamped (overlay partially off-screen), embed
                # the grabbed pixels in a black src-sized canvas so the resize is
                # not distorted — off-screen pixels appear black.
                if r_left != adj_x or r_top != adj_y or r_right != adj_x + src_w or r_bottom != adj_y + src_h:
                    canvas_img = Image.new("RGB", (src_w, src_h), (0, 0, 0))
                    canvas_img.paste(img, (r_left - adj_x, r_top - adj_y))
                    img = canvas_img

                img = img.resize((w, h), Image.BILINEAR)
                self._on_frame(img)
                self._fps_samples.append(time.perf_counter())
                remaining = self._target_dt - (time.perf_counter() - t0)
                if remaining > 0:
                    self._stop_ev.wait(remaining)
        finally:
            _winmm.timeEndPeriod(1)
            if camera is not None:
                try:
                    camera.release()
                except Exception:
                    pass
