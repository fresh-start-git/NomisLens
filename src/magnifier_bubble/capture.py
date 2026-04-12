"""CaptureWorker — the Phase 3 30 fps producer thread.

Reads capture-rect coordinates from AppState, grabs a region from
the screen via mss, resizes it with Pillow BILINEAR, and marshals
the resulting PIL.Image to the Tk main thread via
root.after(0, on_frame, img).

THREAD-LOCAL CONTRACT (mss 10.1.0):
    - mss.mss() instances use threading.local() for HDC/HBITMAP.
    - Instance created on thread A cannot be used from thread B.
    - FIX: create mss.mss() INSIDE run(), not __init__.
    - See .planning/phases/03-capture-loop/03-RESEARCH.md
      Correction 2.

HALL-OF-MIRRORS CONTRACT (mss 10.1.0):
    - mss 10.1.0 uses BitBlt(SRCCOPY | CAPTUREBLT) so layered
      windows ARE included. CAPTUREBLT=0 is Path B defense.
    - Path A (SetWindowDisplayAffinity) lives in window.py,
      added in Plan 03-02.
    - See 03-RESEARCH.md Correction 1.
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


class CaptureWorker(threading.Thread):
    """30 fps screen-capture producer thread."""

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
        """Signal the worker to exit its frame loop."""
        self._stop.set()

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
        """Main loop: lazy-import mss + Pillow, then capture in a loop.

        Uses an outer reconnect loop (Pitfall 7) around mss.mss()
        and an inner frame loop with Event.wait-based pacing (Pitfall 4).
        """
        # Lazy imports -- thread-local contract requires mss.mss() to
        # be created on THIS thread, so the whole mss module is also
        # imported here. Path B hall-of-mirrors defense goes BEFORE
        # mss.mss() construction.
        import mss
        import mss.windows as _mw
        _mw.CAPTUREBLT = 0
        from PIL import Image

        # Outer loop: reconnect mss on GDI failure (Pitfall 7 --
        # mss 10.1.0 GetDIBits() fails after minutes of recording).
        while not self._stop.is_set():
            try:
                with mss.mss() as sct:
                    while not self._stop.is_set():
                        t0 = time.perf_counter()
                        try:
                            self._tick(sct, Image)
                        except Exception as exc:
                            print(
                                f"[capture] tick error: {exc}",
                                flush=True,
                            )
                            break  # reconnect mss
                        self._fps_samples.append(time.perf_counter())
                        remaining = self._target_dt - (
                            time.perf_counter() - t0
                        )
                        if remaining > 0:
                            self._stop.wait(remaining)
            except Exception as exc:
                print(
                    f"[capture] mss instance error: {exc}",
                    flush=True,
                )
                self._stop.wait(0.5)  # backoff before retry

    def _tick(self, sct, Image_cls) -> None:
        """Grab one frame, resize with BILINEAR, invoke callback."""
        x, y, w, h, zoom = self._state.capture_region()
        if w <= 0 or h <= 0:
            return
        # Source rect = bubble rect / zoom, centered on bubble.
        # At zoom=1.0 the grab equals the bubble rect (pass-through);
        # at zoom=6.0 the grab is 1/6 the size, centered.
        src_w = max(1, int(round(w / zoom)))
        src_h = max(1, int(round(h / zoom)))
        src_x = x + (w - src_w) // 2
        src_y = y + (h - src_h) // 2

        shot = sct.grab({
            "left": src_x, "top": src_y,
            "width": src_w, "height": src_h,
        })
        # shot.rgb is mss's pre-converted BGRA->RGB bytes (fastest path)
        img = Image_cls.frombytes("RGB", shot.size, shot.rgb)
        img = img.resize((w, h), Image_cls.Resampling.BILINEAR)
        self._on_frame(img)
