"""Shape masking via SetWindowRgn — apply_shape for circle / rounded / rect.

Research Pattern 3 / PITFALLS.md Pitfall 6 "HRGN double-free": after a
SUCCESSFUL SetWindowRgn call the OS takes ownership of the HRGN. The
application MUST NOT delete the region — doing so double-frees and
crashes the process on the next repaint or the next SetWindowRgn call.

On FAILURE (SetWindowRgn returns 0), the OS did NOT take ownership; the
application still owns the HRGN and must release it via GDI DeleteObject
to avoid a GDI leak, then raise an error.

Phase 2 only calls apply_shape once (to install the initial circle).
Phase 4 will call it on every resize and shape-cycle — the 50-cycle
smoke test in this plan ensures the ownership rule is correct NOW,
before Phase 4 has to debug it.

This module is Windows-only at runtime (imports win32gui). Structural
tests run on any platform by inspecting the source without importing
the win32 runtime. DPI awareness is main.py's exclusive job per OVER-05;
this module does not touch the DPI awareness API.
"""
from __future__ import annotations

VALID_SHAPES: tuple[str, ...] = ("circle", "rounded", "rect")
ROUNDED_RADIUS: int = 40  # CreateRoundRectRgn corner radius (STACK.md section 5)


def apply_shape(hwnd: int, w: int, h: int, shape: str) -> None:
    """Apply a shape mask to the given HWND via SetWindowRgn.

    Args:
        hwnd: The toplevel HWND (already retrieved via GetParent(winfo_id()))
        w: window width in pixels
        h: window height in pixels
        shape: one of "circle", "rounded", "rect" (see VALID_SHAPES)

    Raises:
        ValueError: if shape is not in VALID_SHAPES
        OSError: if SetWindowRgn returns 0 (the HRGN is released before raising)

    HRGN ownership rule (Pitfall 6):
        On success: the OS owns the HRGN. The caller must NOT release it.
        On failure: we still own the HRGN and must release it.
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
        rgn = win32gui.CreateEllipticRgnIndirect((0, 0, w, h))
    elif shape == "rounded":
        rgn = win32gui.CreateRoundRectRgn(0, 0, w, h, ROUNDED_RADIUS, ROUNDED_RADIUS)
    else:  # shape == "rect"
        rgn = win32gui.CreateRectRgnIndirect((0, 0, w, h))

    result = win32gui.SetWindowRgn(hwnd, rgn, True)
    if result == 0:
        # Failure — the OS did NOT take ownership, we must clean up.
        win32gui.DeleteObject(rgn)
        raise OSError(
            f"SetWindowRgn failed for shape={shape!r} w={w} h={h} hwnd={hwnd}"
        )
    # Success — the OS owns rgn. Do not release it. Do not touch rgn again.
