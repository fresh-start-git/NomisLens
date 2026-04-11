"""Pure-Python hit-test for the bubble window's three horizontal zones.

LAYT-01: the bubble has three zones — drag bar (top), magnified content
(middle), control strip (bottom).
LAYT-02: the content zone is 100% click-through (the WndProc returns
HTTRANSPARENT from winconst.py when this function returns "content").
LAYT-03: the drag and control zones capture mouse/touch normally
(HTCAPTION for drag, HTCLIENT for control, via the WndProc in Plan 02).

This module is pure Python — it has ZERO win32 / tkinter / pywin32 /
mss / PIL imports. That is deliberate: the zone math is fully unit-
testable on any platform, and the Win32 wiring (WM_NCHITTEST -> HT*)
lives in wndproc.py (Plan 02) which translates the string return value
to the appropriate HT* constant.

Touch-target note (CTRL-09): the 44 px heights are the finger touch
target from REQUIREMENTS.md CTRL-09. They are locked here so Phase 4's
controls can place 44x44 buttons inside the strips without re-layout.
"""
from __future__ import annotations

# Finger touch target heights (locked for Phase 2+; CTRL-09).
DRAG_BAR_HEIGHT: int = 44
CONTROL_BAR_HEIGHT: int = 44


def compute_zone(client_x: int, client_y: int, w: int, h: int) -> str:
    """Return 'drag', 'content', or 'control' for a window-relative point.

    Args:
        client_x: x coordinate relative to the window's top-left (0 at left edge).
        client_y: y coordinate relative to the window's top-left (0 at top edge).
        w: total window width in pixels.
        h: total window height in pixels.

    Returns:
        "drag"    if client_y is in [0, DRAG_BAR_HEIGHT) — drag bar band
        "control" if client_y is in [h - CONTROL_BAR_HEIGHT, h) — control strip band
        "content" otherwise (middle band AND all out-of-bounds points)

    Overlap rule: when h < DRAG_BAR_HEIGHT + CONTROL_BAR_HEIGHT (tiny windows),
    the drag band is tested first and wins over the control band for the
    overlapping rows. The content zone may be empty in that case.

    Out-of-bounds rule: points with client_x or client_y outside [0, w) or
    [0, h) return "content" so the WndProc returns HTTRANSPARENT — clicks
    in the SetWindowRgn-clipped corners pass through to the app below.
    """
    if 0 <= client_y < DRAG_BAR_HEIGHT:
        return "drag"
    if h - CONTROL_BAR_HEIGHT <= client_y < h:
        return "control"
    return "content"
