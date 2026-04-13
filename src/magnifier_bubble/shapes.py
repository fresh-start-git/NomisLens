"""Shape masking via SetWindowRgn — apply_shape for circle / rounded / rect.

Research Pattern 3 / PITFALLS.md Pitfall 6 "HRGN double-free": after a
SUCCESSFUL SetWindowRgn call the OS takes ownership of the HRGN. The
application MUST NOT delete the region — doing so double-frees and
crashes the process on the next repaint or the next SetWindowRgn call.

On FAILURE (SetWindowRgn returns 0), the OS did NOT take ownership; the
application still owns the HRGN and must release it via GDI DeleteObject
to avoid a GDI leak, then raise an error.

Phase 2 only calls apply_shape once (to install the initial circle).
Phase 4 calls it on every resize and shape-cycle — the 50-cycle and
100-cycle smoke tests in tests/test_shapes_smoke.py ensure the ownership
rule is correct.

Phase 4 Plan 02 HRGN-clipping bug fix (strip-aware region):
When a non-rect shape (circle / rounded) is selected, the circle
inscribed in the bounding rect leaves the four corners OUTSIDE the HRGN.
Windows clips mouse events to the HRGN, so any Canvas item drawn in
those corners becomes invisible AND unclickable. The top drag strip and
bottom control strip extend the FULL WIDTH of the window — their corner
pixels fall inside the clipped-away zone — so the shape button, zoom
buttons, and resize button become unreachable after a single tap that
cycles out of "rect".

Fix: when strip_top / strip_bottom are nonzero, UNION the shape region
with two full-width strip rectangles via CombineRgn(RGN_OR). The
combined region always includes every pixel of both strips plus the
shape-clipped middle, so controls are always hittable regardless of
which shape is active. The middle content zone is still shape-clipped,
preserving the circle / rounded visual.

The intermediate HRGNs created during CombineRgn are owned by the
caller (NOT the OS) — we DeleteObject each one after combining. The
final combined HRGN is what gets passed to SetWindowRgn; on success
the OS takes ownership of the COMBINED region only.

This module is Windows-only at runtime (imports win32gui). Structural
tests run on any platform by inspecting the source without importing
the win32 runtime. DPI awareness is main.py's exclusive job per OVER-05;
this module does not touch the DPI awareness API.
"""
from __future__ import annotations

VALID_SHAPES: tuple[str, ...] = ("circle", "rounded", "rect")
ROUNDED_RADIUS: int = 40  # CreateRoundRectRgn corner radius (STACK.md section 5)

# CombineRgn(dest, src1, src2, mode) — RGN_OR unions the two source regions
# into dest. Value is 2 per win32con (verified against winuser.h RGN_OR).
# Redeclared as a module constant so structural tests can assert it without
# pulling in win32con at module import time.
_RGN_OR: int = 2


def apply_shape(
    hwnd: int,
    w: int,
    h: int,
    shape: str,
    strip_top: int = 0,
    strip_bottom: int = 0,
) -> None:
    """Apply a shape mask to the given HWND via SetWindowRgn.

    Args:
        hwnd: The toplevel HWND (already retrieved via GetParent(winfo_id()))
        w: window width in pixels
        h: window height in pixels
        shape: one of "circle", "rounded", "rect" (see VALID_SHAPES)
        strip_top: height in pixels of the top drag strip that must remain
                   hittable in its full-width rectangle (corners included)
                   regardless of shape. 0 = no top strip union (pure shape).
        strip_bottom: height in pixels of the bottom control strip that
                      must remain hittable in its full-width rectangle.
                      0 = no bottom strip union.

    Raises:
        ValueError: if shape is not in VALID_SHAPES
        OSError: if SetWindowRgn returns 0 (the HRGN is released before raising)

    HRGN ownership rule (Pitfall 6):
        On success: the OS owns the final (possibly combined) HRGN.
                    The caller must NOT release it.
        On failure: we still own the final HRGN and must release it.

    Strip-aware combine rule (Phase 4 bug fix):
        When either strip_top or strip_bottom is nonzero, the function
        builds the shape region AND one/both strip rectangle regions,
        then unions them via CombineRgn(RGN_OR). The intermediate
        regions are OWNED BY US (CombineRgn does NOT transfer ownership
        of its sources) and MUST be released via DeleteObject AFTER the
        combine succeeds. Only the final combined region is passed to
        SetWindowRgn and becomes OS-owned on success.
    """
    if shape not in VALID_SHAPES:
        raise ValueError(
            f"unknown shape {shape!r} — expected one of {VALID_SHAPES}"
        )

    # Import at call time so structural tests can inspect this module
    # without pywin32 being present. The runtime path is Windows-only.
    import win32gui  # type: ignore[import-not-found]

    # Note: pywin32 311 exposes only the *Indirect variants for elliptic and
    # rect regions — the four-int CreateEllipticRgn / CreateRectRgn symbols
    # are not bound in modern pywin32. The Indirect form takes a 4-tuple
    # (left, top, right, bottom) which is equivalent. CreateRoundRectRgn
    # is bound directly with the six-int signature.
    if shape == "circle":
        shape_rgn = win32gui.CreateEllipticRgnIndirect((0, 0, w, h))
    elif shape == "rounded":
        shape_rgn = win32gui.CreateRoundRectRgn(
            0, 0, w, h, ROUNDED_RADIUS, ROUNDED_RADIUS
        )
    else:  # shape == "rect"
        shape_rgn = win32gui.CreateRectRgnIndirect((0, 0, w, h))

    # Build the final region to pass to SetWindowRgn.
    # - Pure shape (no strips): rgn = shape_rgn directly.
    # - Strip-aware: create additional strip rects, CombineRgn into a
    #   destination region, then release the intermediate HRGNs we own.
    if strip_top <= 0 and strip_bottom <= 0:
        rgn = shape_rgn
    else:
        # Destination region; initial rect content doesn't matter since
        # CombineRgn(dest, src1, src2, mode) overwrites it.
        rgn = win32gui.CreateRectRgnIndirect((0, 0, 1, 1))
        # Start with the shape itself (copy into dest via RGN_OR with an
        # empty rect — simpler: OR shape_rgn with itself).
        win32gui.CombineRgn(rgn, shape_rgn, shape_rgn, _RGN_OR)
        # Union in the top strip rectangle if requested.
        if strip_top > 0:
            top_rgn = win32gui.CreateRectRgnIndirect((0, 0, w, strip_top))
            win32gui.CombineRgn(rgn, rgn, top_rgn, _RGN_OR)
            win32gui.DeleteObject(top_rgn)
        # Union in the bottom strip rectangle if requested.
        if strip_bottom > 0:
            bot_rgn = win32gui.CreateRectRgnIndirect(
                (0, h - strip_bottom, w, h)
            )
            win32gui.CombineRgn(rgn, rgn, bot_rgn, _RGN_OR)
            win32gui.DeleteObject(bot_rgn)
        # shape_rgn was copied into `rgn` by the first CombineRgn — we
        # still own shape_rgn (the OS only ever owns the region handed
        # to SetWindowRgn on success). Release it.
        win32gui.DeleteObject(shape_rgn)

    result = win32gui.SetWindowRgn(hwnd, rgn, True)
    if result == 0:
        # Failure — the OS did NOT take ownership, we must clean up.
        win32gui.DeleteObject(rgn)
        raise OSError(
            f"SetWindowRgn failed for shape={shape!r} w={w} h={h} hwnd={hwnd}"
        )
    # Success — the OS owns rgn. Do not release it. Do not touch rgn again.
