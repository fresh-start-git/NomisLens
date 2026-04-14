"""Phase 6 Plan 02 Windows-only integration tests for hotkey.py.

Exercises the real RegisterHotKey + PostThreadMessageW + GetMessageW cycle
on the worker thread. All three tests use an obscure Ctrl+Alt+Shift+Win+F12
combo so we do not collide with PowerToys / Cornerstone / OS bindings on
the dev box.
"""
from __future__ import annotations

import pathlib
import sys

import pytest


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")


_HOTKEY_SRC_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "magnifier_bubble" / "hotkey.py"
)


def _require_hotkey():
    if not _HOTKEY_SRC_PATH.exists():
        pytest.skip("hotkey.py not yet implemented (pending Plan 06-02)")
    try:
        from magnifier_bubble import hotkey  # noqa: F401
    except ImportError:
        pytest.skip("hotkey.py import failed (pending Plan 06-02)")


# ---------------------------------------------------------------------
# HOTK-03 integration (toggle visible via WM_HOTKEY -> root.after)
# ---------------------------------------------------------------------

def test_wm_hotkey_toggles_visible_via_after(tk_toplevel):
    _require_hotkey()
    import ctypes
    import threading
    import time
    from magnifier_bubble.hotkey import HotkeyManager, _HOTKEY_ID
    from magnifier_bubble.winconst import (
        MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, WM_HOTKEY,
    )
    top, _hwnd = tk_toplevel
    # Cross-thread Tk calls (root.after from the hotkey worker) require the
    # main thread to actually be INSIDE mainloop() -- top.update() in a loop
    # does NOT count on Python 3.11 / Tcl 8.6, and raises "main thread is
    # not in main loop" from the worker.  Using top.mainloop() processes
    # events for the shared Tcl interpreter; top.quit() exits the mainloop
    # without destroying the Toplevel or the session root, so subsequent
    # tests see a clean fixture state.
    counter = {"n": 0}

    def on_hotkey():
        counter["n"] += 1
        top.after(10, top.quit)  # exit mainloop after recording

    mgr = HotkeyManager(
        top,
        on_hotkey,
        MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_WIN,
        0x7B,  # VK_F12 -- unlikely to collide with PowerToys / Cornerstone
    )
    assert mgr.start(timeout=1.0) is True, (
        f"start() failed with reg_err={mgr._reg_err} "
        "(hotkey combo may already be registered on the dev box)"
    )
    try:
        # Simulate a WM_HOTKEY by posting it directly to the worker's
        # thread queue.  In production the OS posts this on real key press.
        ok = ctypes.windll.user32.PostThreadMessageW(
            mgr._tid, WM_HOTKEY, _HOTKEY_ID, 0,
        )
        assert ok, (
            f"PostThreadMessageW failed: err={ctypes.get_last_error()}"
        )

        # Watchdog: break out of mainloop after 2s if the callback never
        # fires (prevents a hung test if the PostThreadMessage never reaches
        # the worker's queue).
        def _watchdog():
            time.sleep(2.0)
            try:
                top.after(0, top.quit)
            except RuntimeError:
                pass
        threading.Thread(target=_watchdog, daemon=True).start()

        # Enter mainloop -- on_hotkey calls top.after(10, top.quit) once it
        # fires, exiting this call normally.  The Toplevel shares the Tcl
        # interpreter with the session root, so mainloop dispatches for both.
        top.mainloop()
        assert counter["n"] == 1, (
            f"callback not called within 2s; counter={counter['n']}"
        )
    finally:
        mgr.stop()


# ---------------------------------------------------------------------
# HOTK-05 integration (graceful double-register + clean stop)
# ---------------------------------------------------------------------

def test_second_register_fails_gracefully(tk_toplevel):
    _require_hotkey()
    from magnifier_bubble.hotkey import HotkeyManager
    from magnifier_bubble.winconst import (
        ERROR_HOTKEY_ALREADY_REGISTERED,
        MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN,
    )
    top, _ = tk_toplevel
    mods = MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_WIN
    vk = 0x7B  # VK_F12
    mgr1 = HotkeyManager(top, lambda: None, mods, vk)
    mgr2 = HotkeyManager(top, lambda: None, mods, vk)
    try:
        ok1 = mgr1.start(timeout=1.0)
        assert ok1 is True, f"first register failed: err={mgr1._reg_err}"
        ok2 = mgr2.start(timeout=1.0)
        assert ok2 is False, (
            "second register should have failed but reported success"
        )
        assert mgr2._reg_err == ERROR_HOTKEY_ALREADY_REGISTERED, (
            f"expected err=ERROR_HOTKEY_ALREADY_REGISTERED (1409), "
            f"got {mgr2._reg_err}"
        )
    finally:
        mgr1.stop()
        mgr2.stop()


def test_stop_posts_quit_and_joins(tk_toplevel):
    _require_hotkey()
    import time
    from magnifier_bubble.hotkey import HotkeyManager
    from magnifier_bubble.winconst import (
        MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN,
    )
    top, _ = tk_toplevel
    mgr = HotkeyManager(
        top, lambda: None,
        MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_WIN, 0x7B,
    )
    assert mgr.start(timeout=1.0) is True
    t0 = time.perf_counter()
    mgr.stop()
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, f"stop() took {elapsed:.3f}s (>1s budget)"
    assert mgr._thread is None, "stop() did not null _thread"
