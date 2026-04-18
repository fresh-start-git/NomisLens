"""Click-through input helpers — Phase 7 reduced version.

Phase 4 inject_click and inject_right_click are deleted (Phase 7 uses
WS_EX_TRANSPARENT content zone for natural input pass-through instead).
send_rclick_at is deleted (right-clicks fall through WS_EX_TRANSPARENT naturally).

Remaining functions (kept for potential future use or edge cases):
  send_lclick_at — atomic left-click at screen coords via SendInput
  send_lclick_here — left-click at current cursor position via SendInput
  send_click_at — left-click at screen coords (3-event: MOVE+DOWN+UP)
  send_hover_at — mouse MOVE only, no click (WinUI3 hover-arm)
  inject_touch_at — WinUI3-compatible touch tap via InjectTouchInput

DEBUG: _DEBUG_LOG is None (production mode). Set to a file path to enable.
"""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
# NOTE: os/time kept for _dbg; set _DEBUG_LOG to a path to re-enable logging.

from magnifier_bubble import winconst as wc

_SIGNATURES_APPLIED = False

# Debug log — set to a file path to enable, None to disable.
_DEBUG_LOG = None


def _dbg(msg: str) -> None:
    """Append a timestamped line to the debug log. Never raises."""
    if not _DEBUG_LOG:
        return
    try:
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass

# ---- SendInput structures (used by send_hover_at / send_click_at) ----
# These are defined at module level so they're only built once.

class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          ctypes.c_long),
        ("dy",          ctypes.c_long),
        ("mouseData",   ctypes.c_ulong),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("_u",)
    _fields_ = [("type", ctypes.c_ulong), ("_u", _INPUT_UNION)]


_INPUT_MOUSE           = 0
_MOUSEEVENTF_MOVE      = 0x0001
_MOUSEEVENTF_LEFTDOWN  = 0x0002
_MOUSEEVENTF_LEFTUP    = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP   = 0x0010
_MOUSEEVENTF_ABSOLUTE    = 0x8000
_MOUSEEVENTF_VIRTUALDESK = 0x4000

# ---- InjectTouchInput structures (used by inject_touch_at) ----
# POINTER_INFO / POINTER_TOUCH_INFO layout verified against winuser.h for x64.
# Field order and sizes must match exactly; ctypes inserts natural alignment
# padding, matching the C compiler's output.

class _POINTER_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerType",            ctypes.c_uint32),   # POINTER_INPUT_TYPE
        ("pointerId",              ctypes.c_uint32),
        ("frameId",                ctypes.c_uint32),
        ("pointerFlags",           ctypes.c_uint32),   # POINTER_FLAGS
        ("sourceDevice",           ctypes.c_void_p),   # HANDLE
        ("hwndTarget",             ctypes.c_void_p),   # HWND
        ("ptPixelLocation",        wintypes.POINT),
        ("ptHimetricLocation",     wintypes.POINT),
        ("ptPixelLocationRaw",     wintypes.POINT),
        ("ptHimetricLocationRaw",  wintypes.POINT),
        ("dwTime",                 ctypes.c_uint32),
        ("historyCount",           ctypes.c_uint32),
        ("InputData",              ctypes.c_int32),
        ("dwKeyStates",            ctypes.c_uint32),
        ("PerformanceCount",       ctypes.c_uint64),   # aligned to 8
        ("ButtonChangeType",       ctypes.c_int32),    # POINTER_BUTTON_CHANGE_TYPE enum
    ]


class _POINTER_TOUCH_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerInfo",   _POINTER_INFO),
        ("touchFlags",    ctypes.c_uint32),
        ("touchMask",     ctypes.c_uint32),
        ("rcContact",     wintypes.RECT),
        ("rcContactRaw",  wintypes.RECT),
        ("orientation",   ctypes.c_uint32),
        ("pressure",      ctypes.c_uint32),
    ]


_TOUCH_INITED = False


def _u32():
    """Lazy bind user32 functions used by inject_click.

    Mirrors the pattern in wndproc.py._u32 and dpi.py._u32. On first use,
    applies argtypes/restype so x64 Python passes HWND values at full
    pointer width. After the first call the global sentinel short-
    circuits further re-binds.
    """
    global _SIGNATURES_APPLIED
    u32 = ctypes.windll.user32  # type: ignore[attr-defined]
    if not _SIGNATURES_APPLIED:
        u32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        u32.GetWindow.restype = wintypes.HWND
        u32.IsWindowVisible.argtypes = [wintypes.HWND]
        u32.IsWindowVisible.restype = wintypes.BOOL
        u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u32.GetWindowTextW.restype = ctypes.c_int
        u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u32.GetClassNameW.restype = ctypes.c_int
        u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u32.GetWindowRect.restype = wintypes.BOOL
        u32.ChildWindowFromPointEx.argtypes = [
            wintypes.HWND, wintypes.POINT, wintypes.UINT,
        ]
        u32.ChildWindowFromPointEx.restype = wintypes.HWND
        u32.ScreenToClient.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.POINT),
        ]
        u32.ScreenToClient.restype = wintypes.BOOL
        u32.PostMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        u32.PostMessageW.restype = wintypes.BOOL
        u32.SetForegroundWindow.argtypes = [wintypes.HWND]
        u32.SetForegroundWindow.restype = wintypes.BOOL
        u32.FindWindowExW.argtypes = [
            wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
        ]
        u32.FindWindowExW.restype = wintypes.HWND
        _SIGNATURES_APPLIED = True
    return u32



def inject_touch_at(screen_x: int, screen_y: int) -> bool:
    """Inject a WinUI3-compatible touch tap via InjectTouchInput.

    Caller MUST hide the overlay first (SW_HIDE) so the tap reaches the
    window below, not our own bubble.  The overlay returns HTCLIENT for the
    content zone (HTTRANSPARENT was removed — it broke cross-process routing),
    so a visible overlay would absorb the touch event.

    Returns True if both InjectTouchInput calls succeeded, False otherwise.
    On non-touch hardware InjectTouchInput fails with ERROR_INVALID_PARAMETER
    (0x57); callers should fall back to the two-phase SendInput path.
    """
    global _TOUCH_INITED
    try:
        u32 = ctypes.windll.user32  # type: ignore[attr-defined]
        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        if not _TOUCH_INITED:
            u32.InitializeTouchInjection.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
            u32.InitializeTouchInjection.restype  = wintypes.BOOL
            # TOUCH_FEEDBACK_DEFAULT=1, TOUCH_FEEDBACK_INDIRECT=2, TOUCH_FEEDBACK_NONE=3
            ok = u32.InitializeTouchInjection(1, 3)  # maxCount=1, TOUCH_FEEDBACK_NONE=3
            if not ok:
                return False
            _TOUCH_INITED = True
        u32.InjectTouchInput.argtypes = [
            ctypes.c_uint32, ctypes.POINTER(_POINTER_TOUCH_INFO),
        ]
        u32.InjectTouchInput.restype = wintypes.BOOL

        # Use field-by-field assignment; whole-structure assignment of nested
        # ctypes objects can silently mis-copy on some Python builds.
        PT_TOUCH               = 0x00000002
        # NOTE: POINTER_FLAG_NEW omitted — it marks "first arrival" and some OS
        # builds validate it strictly against touch-device state, triggering
        # ERROR_INVALID_PARAMETER.  INRANGE+INCONTACT+PRIMARY+DOWN is the
        # minimal valid tap-down sequence per winuser.h documentation.
        POINTER_FLAG_INRANGE   = 0x00000002
        POINTER_FLAG_INCONTACT = 0x00000004
        POINTER_FLAG_PRIMARY   = 0x00002000
        POINTER_FLAG_DOWN      = 0x00010000
        POINTER_FLAG_UP        = 0x00040000
        # touchMask=0 → no optional rcContact/orientation/pressure fields;
        # avoids INVALID_PARAMETER from mis-sized or out-of-range rect values.

        def _make(flags: int, btn: int) -> _POINTER_TOUCH_INFO:
            c = _POINTER_TOUCH_INFO()   # zero-initialised by ctypes
            c.pointerInfo.pointerType                = PT_TOUCH
            c.pointerInfo.pointerId                  = 0
            c.pointerInfo.historyCount               = 1   # required: ≥1 per MSDN
            c.pointerInfo.pointerFlags               = flags
            c.pointerInfo.ptPixelLocation.x          = screen_x
            c.pointerInfo.ptPixelLocation.y          = screen_y
            c.pointerInfo.ptHimetricLocation.x       = screen_x
            c.pointerInfo.ptHimetricLocation.y       = screen_y
            c.pointerInfo.ptPixelLocationRaw.x       = screen_x
            c.pointerInfo.ptPixelLocationRaw.y       = screen_y
            c.pointerInfo.ptHimetricLocationRaw.x    = screen_x
            c.pointerInfo.ptHimetricLocationRaw.y    = screen_y
            c.pointerInfo.ButtonChangeType           = btn
            c.touchMask                              = 0  # no optional fields
            return c

        # DOWN: pointer first touches digitizer (INCONTACT=touching, DOWN=transition).
        # UP:   pointer lifts off — only POINTER_FLAG_UP is required.
        down_flags = (POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT |
                      POINTER_FLAG_PRIMARY | POINTER_FLAG_DOWN)
        up_flags   = POINTER_FLAG_UP

        c_down = _make(down_flags, 1)   # ButtonChangeType 1 = POINTER_CHANGE_FIRSTBUTTON_DOWN
        c_up   = _make(up_flags,   2)   # ButtonChangeType 2 = POINTER_CHANGE_FIRSTBUTTON_UP

        r1 = u32.InjectTouchInput(1, ctypes.byref(c_down))
        r2 = u32.InjectTouchInput(1, ctypes.byref(c_up))
        return bool(r1 and r2)
    except Exception:
        return False


def send_hover_at(screen_x: int, screen_y: int) -> None:
    """Inject a mouse-move (hover) event at (screen_x, screen_y) without
    clicking.  Used as Phase-1 of the two-phase WinUI3 click: WinUI3
    BreadcrumbBar items arm themselves on PointerEntered (hover) and only
    respond to PointerPressed once in the armed state.  Sending the move
    first — then the click 150 ms later — gives the XAML host time to fire
    PointerEntered before we send the down/up pair.

    Caller MUST hide the overlay (SW_HIDE) before calling so the move event
    hits the target window, not our bubble.

    Never raises.
    """
    try:
        u32 = ctypes.windll.user32  # type: ignore[attr-defined]
        u32.SetCursorPos(screen_x, screen_y)
        u32.GetSystemMetrics.argtypes = [ctypes.c_int]
        u32.GetSystemMetrics.restype  = ctypes.c_int
        vx = u32.GetSystemMetrics(76)
        vy = u32.GetSystemMetrics(77)
        vw = u32.GetSystemMetrics(78)
        vh = u32.GetSystemMetrics(79)
        norm_x = round((screen_x - vx) * 65536 / vw)
        norm_y = round((screen_y - vy) * 65536 / vh)

        move = _INPUT()
        move.type = _INPUT_MOUSE
        move.mi.dx = norm_x
        move.mi.dy = norm_y
        move.mi.dwFlags = _MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE | _MOUSEEVENTF_VIRTUALDESK

        u32.SendInput(1, ctypes.byref(move), ctypes.sizeof(_INPUT))
    except Exception:
        pass


def send_click_at(screen_x: int, screen_y: int) -> None:
    """Move the cursor to (screen_x, screen_y) and inject a left click via
    SendInput (hardware-level).

    Caller MUST ensure our overlay is not the topmost window at
    (screen_x, screen_y) before calling — e.g. by hiding the overlay
    first with ShowWindow(SW_HIDE).  SendInput routes to whatever window
    is topmost at the cursor position, exactly like a real mouse click.

    Never raises — errors are silently swallowed so the caller's hide/show
    sequence always completes.
    """
    try:
        u32 = ctypes.windll.user32  # type: ignore[attr-defined]
        u32.SetCursorPos(screen_x, screen_y)
        u32.GetSystemMetrics.argtypes = [ctypes.c_int]
        u32.GetSystemMetrics.restype = ctypes.c_int

        # Use MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK so the click
        # position is embedded directly in the input event — correct for
        # multi-monitor setups where the virtual desktop spans beyond the
        # primary screen.  GetSystemMetrics(SM_*VIRTUALSCREEN) gives the
        # full virtual desktop rect; normalize to 0-65535 for the API.
        vx = u32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
        vy = u32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
        vw = u32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
        vh = u32.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN
        norm_x = round((screen_x - vx) * 65536 / vw)
        norm_y = round((screen_y - vy) * 65536 / vh)

        move = _INPUT()
        move.type = _INPUT_MOUSE
        move.mi.dx = norm_x
        move.mi.dy = norm_y
        move.mi.dwFlags = _MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE | _MOUSEEVENTF_VIRTUALDESK

        down = _INPUT()
        down.type = _INPUT_MOUSE
        down.mi.dwFlags = _MOUSEEVENTF_LEFTDOWN

        up = _INPUT()
        up.type = _INPUT_MOUSE
        up.mi.dwFlags = _MOUSEEVENTF_LEFTUP

        buf = (_INPUT * 3)(move, down, up)
        u32.SendInput(3, buf, ctypes.sizeof(_INPUT))
    except Exception:
        pass



def send_lclick_at(screen_x: int, screen_y: int) -> None:
    """Move cursor to (screen_x, screen_y), inject a left-click, then restore
    the cursor to its original position — all in one atomic SendInput batch so
    the visible cursor jump is imperceptible (sub-frame).

    Mirrors send_rclick_at exactly, but with LEFTDOWN + LEFTUP.  Caller MUST
    add WS_EX_TRANSPARENT to the overlay before calling so the injected events
    reach the window below (e.g. a #32768 context menu).

    Never raises.
    """
    try:
        u32 = ctypes.windll.user32  # type: ignore[attr-defined]
        cur_pt = wintypes.POINT()
        u32.GetCursorPos(ctypes.byref(cur_pt))

        u32.GetSystemMetrics.argtypes = [ctypes.c_int]
        u32.GetSystemMetrics.restype = ctypes.c_int
        vx = u32.GetSystemMetrics(76)
        vy = u32.GetSystemMetrics(77)
        vw = u32.GetSystemMetrics(78)
        vh = u32.GetSystemMetrics(79)

        def _norm(px: int, py: int):
            return (
                round((px - vx) * 65536 / vw),
                round((py - vy) * 65536 / vh),
            )

        tgt_nx, tgt_ny = _norm(screen_x, screen_y)
        orig_nx, orig_ny = _norm(cur_pt.x, cur_pt.y)

        move = _INPUT()
        move.type = _INPUT_MOUSE
        move.mi.dx = tgt_nx
        move.mi.dy = tgt_ny
        move.mi.dwFlags = _MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE | _MOUSEEVENTF_VIRTUALDESK

        down = _INPUT()
        down.type = _INPUT_MOUSE
        down.mi.dwFlags = _MOUSEEVENTF_LEFTDOWN

        up = _INPUT()
        up.type = _INPUT_MOUSE
        up.mi.dwFlags = _MOUSEEVENTF_LEFTUP

        restore = _INPUT()
        restore.type = _INPUT_MOUSE
        restore.mi.dx = orig_nx
        restore.mi.dy = orig_ny
        restore.mi.dwFlags = _MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE | _MOUSEEVENTF_VIRTUALDESK

        _dbg(f"send_lclick_at target=({screen_x},{screen_y}) orig=({cur_pt.x},{cur_pt.y})")
        buf = (_INPUT * 4)(move, down, up, restore)
        u32.SendInput(4, buf, ctypes.sizeof(_INPUT))
    except Exception as _e:
        _dbg(f"send_lclick_at exception: {_e}")


def send_lclick_here() -> None:
    """Inject a left-click at the CURRENT cursor position — no SetCursorPos,
    no coordinate mapping, no cursor jump.

    Used when the overlay has WS_EX_TRANSPARENT set so the OS routes the
    synthetic LEFTDOWN + LEFTUP past the overlay to whatever window is below
    at the current cursor coordinates (e.g. the desktop to dismiss a shell
    context menu).

    Caller MUST call ReleaseCapture() and set WS_EX_TRANSPARENT on the
    overlay HWND before calling, so the events reach the window below.

    Never raises.
    """
    try:
        u32 = ctypes.windll.user32  # type: ignore[attr-defined]
        down = _INPUT()
        down.type = _INPUT_MOUSE
        down.mi.dwFlags = _MOUSEEVENTF_LEFTDOWN

        up = _INPUT()
        up.type = _INPUT_MOUSE
        up.mi.dwFlags = _MOUSEEVENTF_LEFTUP

        _dbg("send_lclick_here (no cursor move)")
        buf = (_INPUT * 2)(down, up)
        u32.SendInput(2, buf, ctypes.sizeof(_INPUT))
    except Exception as _e:
        _dbg(f"send_lclick_here exception: {_e}")
