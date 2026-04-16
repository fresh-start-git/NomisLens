"""Cross-process click-through injection.

Closes the Phase 2 LAYT-02 documented gap: HTTRANSPARENT works in-process
but cross-process Tk-frame propagation is blocked. This module posts a
synthetic WM_LBUTTONDOWN + WM_LBUTTONUP to the HWND below our layered
bubble so a click in the content zone reaches Notepad / Cornerstone.

CRITICAL rules (from 04-RESEARCH.md Pattern 6 and Pitfalls I/K):

1. Do NOT use ChildWindowFromPointEx(desktop, pt, CWP_SKIPTRANSPARENT) to
   find the window below us. CWP_SKIPTRANSPARENT only skips WS_EX_TRANSPARENT
   windows; our bubble uses WS_EX_LAYERED (intentionally — WS_EX_TRANSPARENT
   breaks the drag bar), so it would return our own HWND regardless.
   Instead, walk GetWindow(own_hwnd, GW_HWNDNEXT) to skip our window by
   identity, then drill into children with ChildWindowFromPointEx.
2. lParam must be CLIENT-relative, not screen-relative. Always call
   ScreenToClient FIRST, then pack.
3. Use ctypes.windll (NOT the GIL-holding variant). Call sites are Tk
   main-thread button handlers, not inside a WndProc callback. The
   GIL-holding-DLL rule is scoped to hot-path WndProc calls only
   (see wndproc.py).
4. PostMessageW only - never the synchronous Send variant. PostMessage
   is asynchronous and safe cross-process; the synchronous sibling blocks
   on the target message pump and also triggers the Python 3.14
   re-entrant-WndProc crash mode (see STATE.md Phase 3 decisions).
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
_DEBUG_LOG = None  # set to a file path (string) to re-enable


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


def inject_click(screen_x: int, screen_y: int, own_hwnd: int) -> bool:
    """Post WM_LBUTTONDOWN + WM_LBUTTONUP to the window beneath
    (screen_x, screen_y), skipping our own layered bubble.

    Args:
        screen_x: screen-relative X (event.x_root from Tk)
        screen_y: screen-relative Y (event.y_root from Tk)
        own_hwnd: our bubble's toplevel HWND (from BubbleWindow._hwnd)

    Returns:
        True  — target found and messages posted via PostMessageW.
        False — target needs SW_HIDE + SendInput (mouse path).
        None  — target needs SW_HIDE + two-phase WinUI3 hover→click path.

    Never raises - on any ctypes error the click is silently dropped
    and the caller falls back to Phase 2 behavior (click consumed by bubble).

    NOTE: We cannot use ChildWindowFromPointEx(desktop, pt, CWP_SKIPTRANSPARENT)
    here because our bubble has WS_EX_LAYERED (not WS_EX_TRANSPARENT), so that
    flag does NOT skip us — we'd get our own HWND back every time.  Instead we
    walk the Z-order below own_hwnd to find the first visible top-level window
    whose bounding rect contains the click point, then drill into its children.
    """
    try:
        u32 = _u32()

        # Step 1 — find the top-level window below our bubble in Z-order that
        # contains (screen_x, screen_y).  GetWindow(hwnd, GW_HWNDNEXT) walks
        # siblings toward the bottom of the Z-stack, which for a WS_EX_TOPMOST
        # overlay means we quickly reach normal (non-topmost) app windows.
        #
        # Some transparent overlay windows sit above real apps in Z-order and
        # consume hardware input without forwarding it:
        #   ApplicationFrameWindow (no title) — Win11 snap/system overlay
        #   HwndWrapper[...] — WPF overlay apps (Grammarly, etc.)
        # We skip these so the walk reaches the real app underneath.
        hwnd = u32.GetWindow(own_hwnd, wc.GW_HWNDNEXT)
        target_toplevel = None
        while hwnd:
            if u32.IsWindowVisible(hwnd):
                rect = wintypes.RECT()
                u32.GetWindowRect(hwnd, ctypes.byref(rect))
                if (rect.left <= screen_x < rect.right and
                        rect.top <= screen_y < rect.bottom):
                    _ocls = ctypes.create_unicode_buffer(128)
                    u32.GetClassNameW(hwnd, _ocls, 128)
                    _otitle = ctypes.create_unicode_buffer(64)
                    u32.GetWindowTextW(hwnd, _otitle, 64)
                    if (
                        (_ocls.value == "ApplicationFrameWindow" and not _otitle.value)
                        or _ocls.value.startswith("HwndWrapper[")
                    ):
                        hwnd = u32.GetWindow(hwnd, wc.GW_HWNDNEXT)
                        continue
                    target_toplevel = hwnd
                    break
            hwnd = u32.GetWindow(hwnd, wc.GW_HWNDNEXT)

        if not target_toplevel:
            return False

        # Step 2 — drill into target_toplevel's children to find the deepest
        # child window at this point.
        # ChildWindowFromPointEx needs CLIENT-relative coordinates of the parent.
        client_pt = wintypes.POINT(screen_x, screen_y)
        u32.ScreenToClient(target_toplevel, ctypes.byref(client_pt))
        target = u32.ChildWindowFromPointEx(
            target_toplevel, client_pt,
            wc.CWP_SKIPINVISIBLE | wc.CWP_SKIPDISABLED,
        ) or target_toplevel
        child_cls = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(target, child_cls, 256)

        # Chrome_WidgetWin_0 is a non-interactive Chrome overlay (Teams WebView2,
        # Electron popups). The actual render host may be nested several levels
        # deep — keep drilling while each child is still Chrome_WidgetWin_0.
        # Teams hierarchy: outer Chrome_WidgetWin_0 → inner Chrome_WidgetWin_0
        # → Chrome_WidgetWin_1 (or Chrome_RenderWidgetHostHWND).
        # Safety cap: real chains are ≤ 4 deep.
        _drill_limit = 4
        while child_cls.value == "Chrome_WidgetWin_0" and _drill_limit > 0:
            _drill_limit -= 1
            deep_pt = wintypes.POINT(screen_x, screen_y)
            u32.ScreenToClient(target, ctypes.byref(deep_pt))
            deeper = u32.ChildWindowFromPointEx(
                target, deep_pt,
                wc.CWP_SKIPINVISIBLE | wc.CWP_SKIPDISABLED,
            )
            if not deeper or deeper == target:
                break  # no deeper child; use current target as-is
            deep_cls = ctypes.create_unicode_buffer(256)
            u32.GetClassNameW(deeper, deep_cls, 256)
            target = deeper
            child_cls = deep_cls  # update loop condition

        # File Explorer: ShellTabWindowClass is the outer shell tab container.
        # The actual interactive window (DirectUIHWND / SysListView32) may be
        # several levels deep (ShellTabWindowClass → DUIViewWndClassName →
        # DirectUIHWND).  Keep drilling until ChildWindowFromPointEx stops
        # finding a new child.
        if child_cls.value == "ShellTabWindowClass":
            _stw_limit = 8
            while _stw_limit > 0:
                _stw_limit -= 1
                inner_pt = wintypes.POINT(screen_x, screen_y)
                u32.ScreenToClient(target, ctypes.byref(inner_pt))
                inner = u32.ChildWindowFromPointEx(
                    target, inner_pt,
                    wc.CWP_SKIPINVISIBLE | wc.CWP_SKIPDISABLED,
                )
                if not inner or inner == target:
                    break  # reached the leaf
                inner_cls = ctypes.create_unicode_buffer(256)
                u32.GetClassNameW(inner, inner_cls, 256)
                target = inner
                child_cls = inner_cls

        # Win11 Notepad: NotepadTextBox is a WinUI3 wrapper that ignores
        # PostMessageW and blocks SendInput (Grammarly overlay absorbs it).
        # Use FindWindowExW to locate RichEditD2DPT directly inside the
        # Notepad toplevel and PostMessageW to it — bypasses both layers.
        _dbg(f"inject_click target_cls={child_cls.value!r} screen=({screen_x},{screen_y})")

        if child_cls.value == "NotepadTextBox":
            rich_hwnd = u32.FindWindowExW(target, None, "RichEditD2DPT", None)
            if rich_hwnd:
                u32.SetForegroundWindow(target_toplevel)
                client_pt3 = wintypes.POINT(screen_x, screen_y)
                u32.ScreenToClient(rich_hwnd, ctypes.byref(client_pt3))
                lp3 = ((client_pt3.y & 0xFFFF) << 16) | (client_pt3.x & 0xFFFF)
                u32.PostMessageW(rich_hwnd, wc.WM_MOUSEMOVE, 0, lp3)
                u32.PostMessageW(rich_hwnd, wc.WM_LBUTTONDOWN, wc.MK_LBUTTON, lp3)
                u32.PostMessageW(rich_hwnd, wc.WM_LBUTTONUP, 0, lp3)
                return True
            # RichEditD2DPT not found — fall through to SendInput
            u32.SetForegroundWindow(target_toplevel)
            return False

        # These classes require SW_HIDE + SendInput (real hardware-level input)
        # instead of PostMessageW:
        # - ContentIslandWindow / ApplicationFrameInputSinkWindow: use
        #   EnableMouseInPointer(TRUE) and silently drop posted WM_POINTER msgs.
        # - SysTreeView32: calls GetCursorPos() inside WM_LBUTTONDOWN to find
        #   the clicked item; posted messages arrive after the cursor has moved
        #   back to the overlay, so the hit-test fails and navigation is ignored.
        _CHILD_NEEDS_SENDINPUT = frozenset({
            "ContentIslandWindow",
            "ApplicationFrameInputSinkWindow",
        })
        # SysTreeView32 (File Explorer nav pane) needs the two-phase hover→click
        # path: hover arms the item visually (T+50ms), click navigates (T+200ms).
        # Single-phase SendInput arrived before the window fully settled as
        # foreground; the extra 150ms gap resolves this.
        _CHILD_NEEDS_WINUI3_PATH = frozenset({
            "SysTreeView32",
        })
        if child_cls.value in _CHILD_NEEDS_SENDINPUT:
            _dbg(f"  → False (SendInput path): {child_cls.value!r}")
            u32.SetForegroundWindow(target_toplevel)
            return False

        if child_cls.value in _CHILD_NEEDS_WINUI3_PATH:
            _dbg(f"  → None (two-phase path): {child_cls.value!r}")
            u32.SetForegroundWindow(target_toplevel)
            return None

        # DesktopChildSiteBridge hosts WinUI3 content (File Explorer address bar
        # and search box).  PostMessageW is silently dropped by WinUI3.
        # Single-phase SendInput also fails for the BreadcrumbBar: the control
        # needs PointerEntered (hover) before it arms PointerPressed.
        # Return None so window.py uses the two-phase hover→click path:
        #   Phase 1 — send_hover_at (MOVE only, triggers WinUI3 PointerEntered)
        #   Phase 2 — send_click_at (DOWN+UP, 150 ms later)
        # On touch hardware, inject_touch_at is tried first (goes through the OS
        # pointer stack WinUI3 registers for); two-phase is the non-touch fallback.
        if child_cls.value == "Microsoft.UI.Content.DesktopChildSiteBridge":
            _dbg(f"  → None (WinUI3 two-phase path): {child_cls.value!r}")
            u32.SetForegroundWindow(target_toplevel)
            return None  # sentinel: caller uses inject_touch_at / two-phase mouse

        # WPF overlay windows (e.g. Grammarly "Project Llama Overlay") sit above
        # real app windows in Z-order but are transparent to hardware input.
        # HwndWrapper[ is the WPF HWND host class — any such overlay should be
        # bypassed via SW_HIDE + SendInput so the click reaches the app below.
        if child_cls.value.startswith("HwndWrapper["):
            u32.SetForegroundWindow(target_toplevel)
            return False

        # Step 3 — activate target's toplevel so WM_LBUTTONDOWN is processed
        # correctly.  Edit controls (Notepad) and Electron render hosts call
        # SetFocus() internally inside their WM_LBUTTONDOWN handlers, which
        # only succeeds when the parent toplevel is the foreground window.
        # Our process just received a click (WM_LBUTTONDOWN on our overlay),
        # so Windows allows SetForegroundWindow from this call site.
        u32.SetForegroundWindow(target_toplevel)

        # Step 4 — translate screen coords -> client coords for the final
        # target, then post mouse messages.
        client_pt2 = wintypes.POINT(screen_x, screen_y)
        if not u32.ScreenToClient(target, ctypes.byref(client_pt2)):
            return False
        lparam = ((client_pt2.y & 0xFFFF) << 16) | (client_pt2.x & 0xFFFF)
        # WM_MOUSEMOVE first: updates the target's internal hover/hit-test
        # state so the subsequent click lands on the right sub-element
        # (e.g. Chrome's omnibox, focused text input in web apps).
        _dbg(f"  → True (PostMessageW path): {child_cls.value!r}")
        u32.PostMessageW(target, wc.WM_MOUSEMOVE, 0, lparam)
        u32.PostMessageW(target, wc.WM_LBUTTONDOWN, wc.MK_LBUTTON, lparam)
        u32.PostMessageW(target, wc.WM_LBUTTONUP, 0, lparam)
        return True
    except Exception as _exc:
        _dbg(f"  → exception: {_exc}")
        return False


def inject_right_click(screen_x: int, screen_y: int, own_hwnd: int) -> bool:
    """Post WM_RBUTTONDOWN + WM_RBUTTONUP to the window beneath the cursor.

    Same window-finding logic as inject_click. No SW_HIDE needed — PostMessageW
    goes directly to the target's queue regardless of z-order. DefWindowProc in
    the target processes WM_RBUTTONUP and generates WM_CONTEXTMENU automatically.

    Returns True if messages were posted, False on any failure.
    """
    try:
        u32 = _u32()

        # Walk z-order below own_hwnd to find the first visible toplevel
        # whose rect contains (screen_x, screen_y).
        hwnd = u32.GetWindow(own_hwnd, wc.GW_HWNDNEXT)
        target_toplevel = None
        while hwnd:
            if u32.IsWindowVisible(hwnd):
                rect = wintypes.RECT()
                u32.GetWindowRect(hwnd, ctypes.byref(rect))
                if (rect.left <= screen_x < rect.right and
                        rect.top <= screen_y < rect.bottom):
                    _cls = ctypes.create_unicode_buffer(128)
                    u32.GetClassNameW(hwnd, _cls, 128)
                    _ttl = ctypes.create_unicode_buffer(64)
                    u32.GetWindowTextW(hwnd, _ttl, 64)
                    if (
                        (_cls.value == "ApplicationFrameWindow" and not _ttl.value)
                        or _cls.value.startswith("HwndWrapper[")
                    ):
                        hwnd = u32.GetWindow(hwnd, wc.GW_HWNDNEXT)
                        continue
                    target_toplevel = hwnd
                    break
            hwnd = u32.GetWindow(hwnd, wc.GW_HWNDNEXT)

        if not target_toplevel:
            return False

        # Drill into children to find the deepest window at this point.
        client_pt = wintypes.POINT(screen_x, screen_y)
        u32.ScreenToClient(target_toplevel, ctypes.byref(client_pt))
        target = u32.ChildWindowFromPointEx(
            target_toplevel, client_pt,
            wc.CWP_SKIPINVISIBLE | wc.CWP_SKIPDISABLED,
        ) or target_toplevel

        u32.SetForegroundWindow(target_toplevel)

        client_pt2 = wintypes.POINT(screen_x, screen_y)
        if not u32.ScreenToClient(target, ctypes.byref(client_pt2)):
            return False
        lparam = ((client_pt2.y & 0xFFFF) << 16) | (client_pt2.x & 0xFFFF)
        # Screen-coord lParam for WM_CONTEXTMENU (MAKELPARAM(x, y) screen).
        sc_lparam = ((screen_y & 0xFFFF) << 16) | (screen_x & 0xFFFF)
        u32.PostMessageW(target, wc.WM_MOUSEMOVE, 0, lparam)
        u32.PostMessageW(target, wc.WM_RBUTTONDOWN, wc.MK_RBUTTON, lparam)
        u32.PostMessageW(target, wc.WM_RBUTTONUP, 0, lparam)
        u32.PostMessageW(target, wc.WM_CONTEXTMENU, target, sc_lparam)
        return True
    except Exception:
        return False


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


def send_rclick_at(screen_x: int, screen_y: int) -> None:
    """Move cursor to (screen_x, screen_y), inject a right-click, then restore
    the cursor to its original position — all in one atomic SendInput batch so
    the visible cursor jump is imperceptible (sub-frame).

    Caller MUST add WS_EX_TRANSPARENT to the overlay before calling so the
    injected events reach the window below.  The OS generates WM_CONTEXTMENU
    automatically after the RIGHTDOWN + RIGHTUP pair, same as a real hardware
    click.  WM_CONTEXTMENU carries the position from the RIGHTUP event (not the
    restored cursor position), so the menu appears at (screen_x, screen_y).

    Never raises.
    """
    try:
        u32 = ctypes.windll.user32  # type: ignore[attr-defined]
        # Capture original cursor position BEFORE we change it.
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
        down.mi.dwFlags = _MOUSEEVENTF_RIGHTDOWN

        up = _INPUT()
        up.type = _INPUT_MOUSE
        up.mi.dwFlags = _MOUSEEVENTF_RIGHTUP

        restore = _INPUT()
        restore.type = _INPUT_MOUSE
        restore.mi.dx = orig_nx
        restore.mi.dy = orig_ny
        restore.mi.dwFlags = _MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE | _MOUSEEVENTF_VIRTUALDESK

        buf = (_INPUT * 4)(move, down, up, restore)
        u32.SendInput(4, buf, ctypes.sizeof(_INPUT))
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
