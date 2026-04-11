"""DPI helpers for Ultimate Zoom.

This module is SAFE to import from anywhere — it does NOT call
SetProcessDpiAwarenessContext at import time. That call lives in
main.py (the first executable line), where it must be in order to
satisfy OVER-05 before any tkinter/mss/PIL import.

Exports:
    DPI_AWARENESS_CONTEXT_*      sentinel handle values (-1..-5)
    is_pmv2_active()             bool — is the current thread's DPI context PMv2?
    report()                     DpiReport — full logical/physical/scale cross-check
    debug_print()                print one line to stdout summarizing report()

Per-Monitor-V2 debugging (Phase 1 Success Criterion #5):
    On a 150%-scaled display, `debug_print()` should print a line like:
        [dpi] pmv2=True dpi=144 scale=150% logical=1920x1080 physical=1920x1080
    Under PMv2, logical and physical agree (both are physical pixels).
    Under V1 or System-aware, logical may equal physical * (96/dpi) and
    this mismatch is the smoking gun that DPI init failed.
"""
from __future__ import annotations

import ctypes
import sys
from typing import TypedDict

# Sentinel DPI_AWARENESS_CONTEXT handles from Windows <windef.h>.
# These are *negative integers* on the wire, interpreted as handles.
DPI_AWARENESS_CONTEXT_UNAWARE = -1
DPI_AWARENESS_CONTEXT_SYSTEM_AWARE = -2
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE = -3
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
DPI_AWARENESS_CONTEXT_UNAWARE_GDISCALED = -5

# GetSystemMetrics indices
SM_CXSCREEN = 0
SM_CYSCREEN = 1

USER_DEFAULT_SCREEN_DPI = 96


class DpiReport(TypedDict):
    logical_w: int
    logical_h: int
    physical_w: int
    physical_h: int
    dpi: int
    scale_pct: int
    context_is_pmv2: bool


def _u32():
    """Lazy access to user32 — avoids any side effects at module import.

    On non-Windows, ctypes.windll does not exist and accessing it would
    raise AttributeError. All callers of _u32() guard with sys.platform.
    """
    return ctypes.windll.user32  # type: ignore[attr-defined]


def is_pmv2_active() -> bool:
    """Returns True iff the calling thread's DPI context equals PMv2.

    Uses AreDpiAwarenessContextsEqual (not pointer identity) because
    Windows may return different handle wrappers for the same context.
    """
    if sys.platform != "win32":
        return False
    try:
        u32 = _u32()
        cur = u32.GetThreadDpiAwarenessContext()
        # AreDpiAwarenessContextsEqual takes two handles; we cast -4 to handle.
        return bool(u32.AreDpiAwarenessContextsEqual(
            cur, DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        ))
    except (AttributeError, OSError):
        return False


def report() -> DpiReport:
    """Collect logical + physical + DPI + scale_pct + PMv2 flag.

    Windows-only. Raises on non-Windows (callers should guard).
    """
    u32 = _u32()
    logical_w = int(u32.GetSystemMetrics(SM_CXSCREEN))
    logical_h = int(u32.GetSystemMetrics(SM_CYSCREEN))
    dpi_val = int(u32.GetDpiForSystem())
    physical_w = int(u32.GetSystemMetricsForDpi(SM_CXSCREEN, dpi_val))
    physical_h = int(u32.GetSystemMetricsForDpi(SM_CYSCREEN, dpi_val))
    return DpiReport(
        logical_w=logical_w,
        logical_h=logical_h,
        physical_w=physical_w,
        physical_h=physical_h,
        dpi=dpi_val,
        scale_pct=dpi_val * 100 // USER_DEFAULT_SCREEN_DPI,
        context_is_pmv2=is_pmv2_active(),
    )


def debug_print() -> None:
    """Print one line summarizing the DPI report.

    Satisfies Phase 1 Success Criterion #5 as an observable proof that
    PMv2 is active on the running display. Compare the printed physical
    dimensions against Windows Settings > Display to validate 150% scale.
    """
    r = report()
    print(
        f"[dpi] pmv2={r['context_is_pmv2']} "
        f"dpi={r['dpi']} scale={r['scale_pct']}% "
        f"logical={r['logical_w']}x{r['logical_h']} "
        f"physical={r['physical_w']}x{r['physical_h']}"
    )
