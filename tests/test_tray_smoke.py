"""Phase 8 Plan 01 Windows-only integration tests for tray.py.

Skipped on non-Windows platforms. Requires pystray 0.19.5 installed.
"""
from __future__ import annotations

import sys
import time

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows-only: requires pystray._win32"
)


class _StubBubble:
    """Minimal bubble stub — has .state, .toggle, .toggle_aot_and_apply, .destroy."""

    class _StubState:
        @staticmethod
        def snapshot():
            from magnifier_bubble.state import StateSnapshot
            return StateSnapshot()

    state = _StubState()

    @staticmethod
    def toggle():
        pass

    @staticmethod
    def toggle_aot_and_apply():
        pass

    @staticmethod
    def destroy():
        pass


def test_create_tray_image_returns_pil_image():
    from magnifier_bubble.tray import create_tray_image
    from PIL import Image
    img = create_tray_image()
    assert isinstance(img, Image.Image)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"


def test_tray_icon_start_stop(tk_session_root):
    """TrayManager.start() creates an icon; stop() terminates cleanly within 2s."""
    from magnifier_bubble.tray import TrayManager

    tm = TrayManager(tk_session_root, _StubBubble())
    tm.start()
    time.sleep(0.3)   # allow icon to appear in shell notification area
    tm.stop()
    assert tm._thread is None or not tm._thread.is_alive(), (
        "TrayManager thread must be stopped within 1s join timeout"
    )
