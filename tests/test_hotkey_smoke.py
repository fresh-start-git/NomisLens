"""Phase 6 Plan 02 Windows-only integration tests for hotkey.py.

Wave 0 stubs. Skipped on non-Windows via module-level pytestmark.
Skipped on Windows when hotkey.py is absent (pending Plan 06-02).
Plan 06-02 replaces each pytest.skip line with real PostThreadMessageW
+ threading.Event + GetMessageW exercise code.
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
    pytest.skip("stub pending Plan 06-02 implementation")

# ---------------------------------------------------------------------
# HOTK-05 integration (graceful double-register + clean stop)
# ---------------------------------------------------------------------

def test_second_register_fails_gracefully(tk_toplevel):
    _require_hotkey()
    pytest.skip("stub pending Plan 06-02 implementation")

def test_stop_posts_quit_and_joins(tk_toplevel):
    _require_hotkey()
    pytest.skip("stub pending Plan 06-02 implementation")
