"""Runtime smoke tests for DXGICaptureWorker — Windows-only, requires dxcam.

CAPT-02: achieves >= 25 fps (30 fps target; 25 threshold accounts for test overhead).
CAPT-06: hall-of-mirrors defense — WDA_EXCLUDEFROMCAPTURE means the overlay is
         excluded from capture, NOT that frames are blank. Sanity-check that the
         worker returns non-black pixel data.

These tests require a real Windows display and dxcam installed. They are skipped
automatically on non-Windows platforms (CI, Mac, Linux).

Run manually on the development machine to validate capture pipeline:
    python -m pytest tests/test_capture_dxgi_smoke.py -v

NOTE on new_frame_only=True and static screens: DXGICaptureWorker uses
grab(new_frame_only=True) which returns None when the desktop has not changed.
On a fully static screen, this yields very few frames. test_achieves_30fps
synthesizes screen activity by briefly moving the mouse pointer to ensure
the DWM compositor marks frames as "new". This is the correct test because
NomisLens is always used with an active display (Cornerstone, web browser, etc).
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-only dxcam smoke test — requires DXGI display",
)


class _FakeState:
    """Minimal AppState stub returning a 400x400 region at zoom 2.0."""

    def capture_region(self):
        # w=400, h=400, zoom=2.0 -> src_w=200, src_h=200 source rect
        return (100, 100, 400, 400, 2.0)


def _make_worker(frames_list, stop_event):
    """Return a DXGICaptureWorker that appends frames to frames_list."""
    from magnifier_bubble.capture_dxgi import DXGICaptureWorker

    def _on_frame(img):
        frames_list.append(img)
        if len(frames_list) >= 60:
            stop_event.set()

    worker = DXGICaptureWorker(_FakeState(), _on_frame)
    return worker


def _move_mouse_loop(stop_event: threading.Event) -> None:
    """Move mouse back and forth to trigger new frames from DXGI.

    DXGICaptureWorker uses grab(new_frame_only=True) which only returns
    frames when the desktop compositor marks the swapchain as updated.
    On a static screen this rarely triggers. Moving the cursor causes the
    cursor layer to composite, marking the frame as new.
    """
    u32 = ctypes.windll.user32
    pt = ctypes.wintypes.POINT()
    u32.GetCursorPos(ctypes.byref(pt))
    ox, oy = pt.x, pt.y
    dx = 0
    while not stop_event.is_set():
        u32.SetCursorPos(ox + dx, oy)
        dx = 5 if dx == 0 else 0
        stop_event.wait(0.016)  # ~60 moves/sec
    u32.SetCursorPos(ox, oy)  # restore original position


def test_achieves_30fps():
    """CAPT-02: DXGICaptureWorker achieves >= 25 fps over a 5-second window.

    25 fps threshold (not 30) accounts for test environment scheduling overhead.
    The worker targets 30 fps; in a real display session it should comfortably
    exceed 25 fps even under load.

    Mouse movement is used to ensure DXGI marks frames as new (new_frame_only=True
    returns None on a static screen since no swapchain update occurs).
    """
    frames = []
    stop_event = threading.Event()
    worker = _make_worker(frames, stop_event)

    # Start mouse mover to generate screen activity
    mouse_thread = threading.Thread(target=_move_mouse_loop, args=(stop_event,), daemon=True)
    mouse_thread.start()

    worker.start()
    try:
        # Allow up to 5 seconds for 60 frames to arrive (needed for fps calculation)
        stop_event.wait(timeout=5.0)
    finally:
        stop_event.set()  # stop mouse mover too
        worker.stop()
        worker.join(timeout=3.0)

    fps = worker.get_fps()
    assert fps > 25.0, (
        f"CAPT-02: expected >= 25 fps, got {fps:.1f} fps. "
        f"Frames collected: {len(frames)}. "
        "Check dxcam installation and display availability."
    )


def test_no_hall_of_mirrors():
    """CAPT-06: Captured frames contain non-black pixel data.

    WDA_EXCLUDEFROMCAPTURE excludes the overlay window from ALL capture APIs.
    This means the overlay does NOT appear inside its own magnified view (no
    hall of mirrors). However, the capture should still return real screen
    content — not a blank/black frame.

    This test verifies the capture pipeline returns meaningful pixel data.
    A fully-black frame would indicate a capture failure (e.g., wrong region,
    driver issue) rather than correct operation.
    """
    frames = []
    stop_event = threading.Event()

    def _on_first_frame(img):
        frames.append(img)
        stop_event.set()

    from magnifier_bubble.capture_dxgi import DXGICaptureWorker
    worker = DXGICaptureWorker(_FakeState(), _on_first_frame)

    # Move mouse to ensure a frame arrives quickly
    u32 = ctypes.windll.user32
    pt = ctypes.wintypes.POINT()
    u32.GetCursorPos(ctypes.byref(pt))
    ox, oy = pt.x, pt.y

    worker.start()
    try:
        # Nudge mouse to trigger at least one frame
        for _ in range(20):
            if stop_event.is_set():
                break
            u32.SetCursorPos(ox + 5, oy)
            time.sleep(0.05)
            u32.SetCursorPos(ox, oy)
            time.sleep(0.05)
        stop_event.wait(timeout=5.0)
    finally:
        worker.stop()
        worker.join(timeout=3.0)
        u32.SetCursorPos(ox, oy)

    assert len(frames) >= 1, (
        "CAPT-06: No frames captured within 5 seconds. "
        "Check dxcam installation and display availability."
    )

    frame = frames[0]
    # Convert to bytes and check that not all pixels are (0, 0, 0)
    pixel_data = frame.tobytes()
    assert any(b != 0 for b in pixel_data), (
        "CAPT-06: Captured frame is entirely black — capture pipeline may be broken. "
        "If running headless (no display), this test must be skipped manually."
    )
