"""Win32 constants used by Phase 2+ of Ultimate Zoom.

This module is a pure constants dump — ZERO third-party imports. It exists
so that other modules (wndproc.py, shapes.py, window.py) can reference
named values instead of magic hex literals, and so tests can lint the
exact values against Microsoft Learn documentation.

All values verified 2026-04-11 against:
- https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowlongw
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowlongptrw
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setlayeredwindowattributes
- https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-nchittest
- https://learn.microsoft.com/en-us/windows/win32/winmsg/about-messages-and-message-queues

DO NOT add function definitions, class definitions, or runtime imports here.
DO NOT call any Win32 API from this module (that is wndproc.py / shapes.py / window.py).
"""
from __future__ import annotations

# Extended window styles (used via GetWindowLongW(hwnd, GWL_EXSTYLE) | bits).
WS_EX_LAYERED     = 0x00080000
WS_EX_TOOLWINDOW  = 0x00000080
WS_EX_NOACTIVATE  = 0x08000000
# WS_EX_TRANSPARENT is included as a documented DO-NOT-USE sentinel —
# see PITFALLS.md Pitfall 1: whole-window transparent kills the drag bar.
# Use per-region WM_NCHITTEST -> HTTRANSPARENT for click-through instead.
WS_EX_TRANSPARENT = 0x00000020

# GetWindowLong / SetWindowLong / SetWindowLongPtr indices.
GWL_EXSTYLE  = -20
GWLP_WNDPROC = -4

# SetLayeredWindowAttributes dwFlags.
LWA_ALPHA    = 0x00000002
LWA_COLORKEY = 0x00000001

# WM_NCHITTEST hit-test return codes (winuser.h). HTTRANSPARENT routes the
# click through to the next window in the same thread — the basis for
# LAYT-02 click-through on the middle zone.
HTCLIENT      = 1
HTCAPTION     = 2
HTTRANSPARENT = -1
HTBOTTOMRIGHT = 17  # reserved for Phase 4 resize grip

# Window messages.
WM_MOUSEACTIVATE = 0x0021
WM_NCHITTEST     = 0x0084
WM_NCLBUTTONDOWN = 0x00A1
WM_MOUSEMOVE     = 0x0200
WM_LBUTTONDOWN   = 0x0201
WM_DESTROY       = 0x0002

# WM_MOUSEACTIVATE return codes (winuser.h).
# MA_NOACTIVATE: don't activate the window, but pass the click through.
MA_NOACTIVATE = 3

# SetWindowDisplayAffinity dwAffinity values (winuser.h).
# WDA_EXCLUDEFROMCAPTURE (Win10 2004+) tells the OS to exclude this
# window from all screen-capture paths — BitBlt+CAPTUREBLT, DXGI
# Desktop Duplication, screenshot tools, Teams/Zoom screen share.
# Primary hall-of-mirrors defense (Path A) per 03-RESEARCH.md.
WDA_NONE               = 0x00000000
WDA_MONITOR            = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011

# ---- Phase 4 additions ----

# ChildWindowFromPointEx flags (winuser.h).
# CWP_SKIPTRANSPARENT is load-bearing - without it, ChildWindowFromPointEx
# returns our own WS_EX_LAYERED bubble and PostMessageW injection would
# recurse into our canvas. See Pitfall I in 04-RESEARCH.md.
CWP_SKIPINVISIBLE    = 0x0001
CWP_SKIPDISABLED     = 0x0002
CWP_SKIPTRANSPARENT  = 0x0004

# Mouse button state bit flags for WM_*BUTTON* message wParam (winuser.h).
MK_LBUTTON = 0x0001

# Mouse button message to complement the already-present WM_LBUTTONDOWN.
# Used by clickthru.py to post UP immediately after DOWN - some targets
# don't consume a lone DOWN.
WM_LBUTTONUP = 0x0202
