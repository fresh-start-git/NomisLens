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

REGION FORMAT: dxcam uses (left, top, right, bottom) — NOT (left, top,
width, height).  Compute: region=(src_x, src_y, src_x+src_w, src_y+src_h).

FRAME DEDUPLICATION: grab(new_frame_only=True) returns None when the
desktop has not changed.  Do NOT push None to the frame queue.

CLEANUP: camera.release() MUST be called in the finally block so the
dxcam DXFactory WeakValueDictionary releases the singleton reference.
Without this, the next dxcam.create() call may reuse a released instance
and log a "[WARNING] DXCamera instance already exists" message.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage
    from magnifier_bubble.state import AppState

FrameCallback = Callable[["PILImage"], None]


class DXGICaptureWorker(threading.Thread):
    """30 fps DXGI Desktop Duplication capture producer thread."""

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
        import ctypes
        from PIL import Image

        _winmm = ctypes.windll.winmm  # type: ignore[attr-defined]
        _winmm.timeBeginPeriod(1)

        camera = None
        try:
            import dxcam
            try:
                camera = dxcam.create(
                    output_color="RGB",
                    processor_backend="numpy",
                )
            except Exception as exc:
                print(f"[dxcam] create failed: {exc}", flush=True)
                return

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
                # region format: (left, top, right, bottom) — NOT width/height
                frame = camera.grab(
                    region=(src_x, src_y, src_x + src_w, src_y + src_h),
                    new_frame_only=self._new_frame_only,
                )
                if frame is None:
                    # No new frame (screen unchanged) — skip this tick
                    remaining = self._target_dt - (time.perf_counter() - t0)
                    if remaining > 0:
                        self._stop_ev.wait(remaining)
                    continue
                # frame is already RGB (H, W, 3) — fromarray works directly
                img = Image.fromarray(frame)
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
