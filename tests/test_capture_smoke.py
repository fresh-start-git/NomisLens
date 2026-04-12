"""Phase 3 capture-loop smoke tests -- Windows-only.

Runs the full pipeline:
  BubbleWindow __init__ -> start_capture -> worker.run() -> mss.grab
  -> BILINEAR resize -> root.after(0, _on_frame, img) -> _photo.paste

Verifies CAPT-02 (>= 30 fps over 2s), CAPT-05 (< 5 MB drift over 60s),
CAPT-06 (no hall-of-mirrors in a captured frame).

These tests require a live display and will not run on headless CI.

NOTE: These tests use root.mainloop() with scheduled quit() calls
rather than root.update() loops because Tk's root.after() from a
background thread requires the Tcl main loop to be running. The
root.update() approach leaves gaps where the main loop is inactive,
causing "main thread is not in main loop" errors from the capture
worker's root.after(0, ...) callback.
"""
from __future__ import annotations

import sys
import time
import pathlib
import pytest
import tracemalloc

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-only -- requires live display + mss + pywin32"
)


def _make_bubble(w: int = 400, h: int = 400, zoom: float = 2.0):
    """Construct a BubbleWindow at a known geometry for a test.
    Caller is responsible for calling bubble.destroy() in a finally."""
    from magnifier_bubble.state import AppState, StateSnapshot
    from magnifier_bubble.window import BubbleWindow
    state = AppState(StateSnapshot(x=200, y=200, w=w, h=h, zoom=zoom))
    return BubbleWindow(state)


def _run_for(bubble, duration_s: float) -> None:
    """Run the Tk main loop for approximately duration_s seconds.

    Uses root.after() to schedule a quit, then runs mainloop().
    This keeps the Tcl event loop active so root.after() calls from
    background threads (the capture worker) are properly processed.
    """
    bubble.root.after(int(duration_s * 1000), bubble.root.quit)
    bubble.root.mainloop()


def test_capture_worker_starts_and_frames_arrive():
    """CAPT-01: start_capture triggers at least one frame."""
    bubble = _make_bubble()
    frames_received = []

    # Wrap the original _on_frame to spy on calls
    _orig_on_frame = bubble._on_frame

    def spy(img):
        frames_received.append(img.size)
        _orig_on_frame(img)

    bubble._on_frame = spy
    try:
        bubble.start_capture()
        _run_for(bubble, 1.0)
        assert frames_received, (
            "no frames arrived within 1s of start_capture"
        )
        assert all(
            sz[0] > 0 and sz[1] > 0 for sz in frames_received
        ), "frames have zero dimensions"
    finally:
        bubble.destroy()


def test_capture_worker_achieves_30fps():
    """CAPT-02: sustained >= 30 fps over 2 seconds."""
    bubble = _make_bubble(w=400, h=400, zoom=2.0)
    try:
        bubble.start_capture()
        _run_for(bubble, 2.0)
        assert bubble._capture_worker is not None
        fps = bubble._capture_worker.get_fps()
        assert fps >= 30.0, (
            f"CAPT-02 FAILED: fps was {fps:.1f}, expected >= 30.0"
        )
    finally:
        bubble.destroy()


def test_capture_memory_flat_over_60s():
    """CAPT-05 Pitfall 12: memory drift < 5 MB over 60 seconds."""
    bubble = _make_bubble(w=400, h=400, zoom=2.0)
    try:
        bubble.start_capture()
        # Warm-up: let mss + PhotoImage allocate steady-state memory
        _run_for(bubble, 5.0)

        tracemalloc.start()
        snap_before = tracemalloc.take_snapshot()

        _run_for(bubble, 60.0)

        snap_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snap_after.compare_to(snap_before, "filename")
        total_drift = sum(s.size_diff for s in stats)
        # < 5 MB per REQUIREMENTS.md CAPT-05 / ROADMAP Phase 3 #4
        assert total_drift < 5 * 1024 * 1024, (
            f"CAPT-05 FAILED: memory drift "
            f"{total_drift / 1024 / 1024:.2f} MB exceeds 5 MB"
        )
    finally:
        bubble.destroy()


def test_no_hall_of_mirrors():
    """CAPT-06: the bubble's own teal border must not appear in
    a captured frame (SetWindowDisplayAffinity + CAPTUREBLT=0)."""
    from magnifier_bubble.window import BORDER_COLOR
    bubble = _make_bubble(w=400, h=400, zoom=2.0)
    captured = []
    _orig_on_frame = bubble._on_frame

    def spy(img):
        if not captured:
            captured.append(img.copy())
        _orig_on_frame(img)

    bubble._on_frame = spy
    try:
        bubble.start_capture()
        _run_for(bubble, 1.0)
        assert captured, "no frame captured in 1s"
        img = captured[0]
        # teal_rgb = (46, 196, 182)  -- #2ec4b6 decoded
        teal_rgb = tuple(
            int(BORDER_COLOR.lstrip("#")[i:i + 2], 16)
            for i in (0, 2, 4)
        )
        assert teal_rgb == (46, 196, 182), (
            f"BORDER_COLOR decoded to {teal_rgb}, "
            f"expected (46, 196, 182)"
        )
        # Sample a 10x10 grid across the image; none should equal
        # the exact teal. If the bubble were leaking into its own
        # capture, the top/bottom rows would be full of teal pixels
        # (the border runs around the whole bubble).
        w_img, h_img = img.size
        teal_hits = 0
        for gx in range(10):
            for gy in range(10):
                px = img.getpixel((
                    gx * (w_img - 1) // 9,
                    gy * (h_img - 1) // 9,
                ))
                if px[:3] == teal_rgb:
                    teal_hits += 1
        assert teal_hits == 0, (
            f"CAPT-06 FAILED: {teal_hits}/100 sampled pixels "
            f"match bubble teal border -- hall-of-mirrors detected"
        )
    finally:
        bubble.destroy()
