"""Phase 6: Global hotkey worker for Ultimate Zoom.

Low-level input-hook libraries are rejected in favor of Windows' built-in
RegisterHotKey primitive running on a dedicated non-daemon worker thread.
RegisterHotKey is first-come-first-served, system-wide, and does not
require admin rights or conflict with Cornerstone's own input handling.

Design (HOTK-01 .. HOTK-05):
  - A worker thread owns the hotkey registration for its full lifetime.
    Registration and the matching Unregister call BOTH live inside _run()
    because Win32 ties hotkey ownership to the registering thread id.
  - The worker runs a blocking GetMessageW loop. WM_HOTKEY is translated
    into a Tk main-thread callback via root.after(0, on_hotkey) -- the only
    thread-safe Tk handoff documented by Python.
  - Shutdown is cooperative: main thread calls stop() which posts WM_QUIT
    via PostThreadMessageW; the worker's GetMessageW returns 0, the while
    loop exits, and the finally block runs UnregisterHotKey on the same
    thread that registered. A non-daemon worker (Thread constructor
    flagged explicitly) guarantees the finally runs even under abrupt
    interpreter teardown (Python 3.14 tightened the daemon-termination
    semantics).
  - MOD_NOREPEAT is always ORed into the user's modifier bits so holding
    the key produces ONE WM_HOTKEY event, not a flood of auto-repeats.
  - GetMessageW.restype is ctypes.c_int (not BOOL) because the function
    returns -1 on error, which the BOOL width would quietly mask.

Structural bans (enforced by tests/test_hotkey.py):
  - This module does NOT import or reference low-level hook libraries
    (see STATE.md decision -- rejected for Windows 11 reliability and
    admin-rights overhead).
  - This module does NOT use the GIL-holding ctypes variant -- the
    worker loop runs on its own thread, not inside a WINFUNCTYPE callback,
    so the default GIL-releasing ctypes.windll accessor is correct here.

All Win32 call signatures are applied lazily on first use via
_apply_signatures(user32). Module import is side-effect-free; this module
imports cleanly on Linux CI where ctypes.windll is not available.
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import TYPE_CHECKING, Callable, Optional

from magnifier_bubble.winconst import (
    ERROR_HOTKEY_ALREADY_REGISTERED,
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    MOD_WIN,
    VK_Z,
    WM_HOTKEY,
    WM_QUIT,
)

if TYPE_CHECKING:
    import tkinter as tk  # noqa: F401 -- type-only import


# App-range hotkey id (must be 0x0000..0xBFFF per MSDN RegisterHotKey).
_HOTKEY_ID = 0x0001

_SIGNATURES_APPLIED: bool = False


def _apply_signatures(user32) -> None:
    """Apply argtypes/restype to every user32 function this module calls.

    Idempotent via the module-level sentinel. Mirrors Phase 2 wndproc.py's
    _SIGNATURES_APPLIED pattern. Without these declarations, x64 Python's
    default c_int ABI truncates wide types (HWND, DWORD, LPARAM) and
    PostThreadMessageW silently fails with ERROR_INVALID_THREAD_ID (1444)
    on TIDs whose high bit is set. GetMessageW.restype MUST be ctypes.c_int
    (NOT wintypes.BOOL) because -1 is a legal error return and BOOL width
    would mask it.
    """
    global _SIGNATURES_APPLIED
    if _SIGNATURES_APPLIED:
        return
    user32.RegisterHotKey.argtypes = [
        wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT,
    ]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND, wintypes.UINT, wintypes.UINT,
    ]
    user32.GetMessageW.restype = ctypes.c_int  # -1 legal error; not BOOL
    user32.PostThreadMessageW.argtypes = [
        wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ]
    user32.PostThreadMessageW.restype = wintypes.BOOL
    user32.PeekMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT,
    ]
    user32.PeekMessageW.restype = wintypes.BOOL
    _SIGNATURES_APPLIED = True


def _log_registration_failure(err: int) -> None:
    """Print a clinic-friendly graceful-failure message for the
    ERROR_HOTKEY_ALREADY_REGISTERED case; log the raw GetLastError value
    for every other failure. Stdout only -- the app continues to run,
    just without the hotkey binding.
    """
    if err == ERROR_HOTKEY_ALREADY_REGISTERED:
        print(
            "[hotkey] registration failed: another app is already using "
            f"this combination (GetLastError={err}). The bubble will "
            "still run, but will not respond to the hotkey. "
            "Edit config.json to change the hotkey and relaunch.",
            flush=True,
        )
    else:
        print(
            f"[hotkey] registration failed: GetLastError={err}",
            flush=True,
        )


class HotkeyManager:
    """Register a global hotkey and deliver its callback on the Tk main thread.

    Lifecycle contract (HOTK-05):
      mgr = HotkeyManager(root, on_hotkey, modifiers, vk)
      if mgr.start(timeout=1.0):   # blocks until worker attempted register
          ...                      # app runs normally
      mgr.stop()                   # WM_QUIT + join; Unregister runs on worker

    start() returns True iff RegisterHotKey succeeded. On False, _reg_err
    holds the GetLastError value (ERROR_HOTKEY_ALREADY_REGISTERED ==
    already registered is the common graceful-failure case; caller should
    surface without crashing).

    Constructor arguments:
      root       -- Tk root (provides root.after for the cross-thread hop)
      on_hotkey  -- zero-arg callable scheduled on Tk main thread per press
      modifiers  -- bitmask of MOD_* constants (MOD_NOREPEAT is added
                    automatically; callers MUST NOT include it themselves)
      vk         -- virtual-key code (e.g. VK_Z = 0x5A for 'Z')
    """

    def __init__(
        self,
        root,
        on_hotkey: Callable[[], None],
        modifiers: int,
        vk: int,
    ) -> None:
        self._root = root
        self._on_hotkey = on_hotkey
        self._modifiers = modifiers | MOD_NOREPEAT  # Pitfall 5
        self._vk = vk
        self._tid: int = 0
        self._ready = threading.Event()
        self._reg_ok: bool = False
        self._reg_err: int = 0
        self._thread: Optional[threading.Thread] = None

    def start(self, timeout: float = 1.0) -> bool:
        """Launch the worker thread and wait up to `timeout` seconds for
        the registration attempt to complete. Returns True iff registration
        succeeded. On False, self._reg_err holds the GetLastError value.
        """
        self._thread = threading.Thread(
            target=self._run,
            name="hotkey-pump",
            daemon=False,  # Pitfall 2: finally MUST run to UnregisterHotKey
        )
        self._thread.start()
        self._ready.wait(timeout=timeout)
        return self._reg_ok

    def stop(self) -> None:
        """Signal the worker to exit and join within 1 second.

        Safe to call repeatedly and safe to call on a never-started manager.
        Uses PostThreadMessageW(WM_QUIT) to break the worker's GetMessageW
        block; the finally in _run runs UnregisterHotKey on the correct
        (registering) thread before exiting.
        """
        if self._thread is None or self._tid == 0:
            return
        ctypes.windll.user32.PostThreadMessageW(  # type: ignore[attr-defined]
            self._tid, WM_QUIT, 0, 0,
        )
        self._thread.join(timeout=1.0)
        self._thread = None

    def _run(self) -> None:
        """Worker-thread entry point. Do NOT call directly -- start() handles
        thread creation. All Win32 state ownership (hotkey registration,
        message pump, unregister) lives in this single function so Pitfall 1
        (cross-thread Unregister) cannot happen.
        """
        # ctypes.windll is the GIL-releasing variant; correct here because
        # _run is the thread entry point, NOT a WINFUNCTYPE callback re-entered
        # by the OS dispatcher. The GIL-holding variant is required only on
        # hot-path WndProc callbacks where Tk timer dispatch might interleave.
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        _apply_signatures(user32)
        self._tid = kernel32.GetCurrentThreadId()

        msg = wintypes.MSG()
        # Force the thread's message queue into existence BEFORE any outside
        # thread could call PostThreadMessageW against self._tid. PeekMessage
        # on the WM_USER range with PM_NOREMOVE=0 is the documented idiom.
        user32.PeekMessageW(ctypes.byref(msg), None, 0x0400, 0x0400, 0)

        ok = user32.RegisterHotKey(
            None, _HOTKEY_ID, self._modifiers, self._vk,
        )
        if not ok:
            self._reg_err = ctypes.get_last_error()
            self._reg_ok = False
            _log_registration_failure(self._reg_err)
            self._ready.set()
            return
        self._reg_ok = True
        self._ready.set()

        try:
            while True:
                rc = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if rc == 0 or rc == -1:
                    break  # WM_QUIT (0) or error (-1)
                if msg.message == WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                    # Cross-thread handoff. If root is mid-teardown the
                    # after() call raises RuntimeError; swallow it so the
                    # worker still reaches its UnregisterHotKey finally.
                    try:
                        self._root.after(0, self._on_hotkey)
                    except RuntimeError:
                        pass
        finally:
            # Must run on the SAME thread as RegisterHotKey (Pitfall 1).
            # Non-daemon worker + cooperative WM_QUIT stop guarantees
            # this fires on a clean exit.
            user32.UnregisterHotKey(None, _HOTKEY_ID)


# Re-exports for tests / Plan 06-03 convenience -- importing MOD_* through
# hotkey keeps Plan 06-03's app.py from needing to touch winconst directly.
__all__ = [
    "HotkeyManager",
    "MOD_ALT",
    "MOD_CONTROL",
    "MOD_SHIFT",
    "MOD_WIN",
    "VK_Z",
]
