"""Phase 7 click-through tests.

Phase 4 injection tests removed (inject_click/inject_right_click deleted in
Phase 7). Structural lints updated to reflect the reduced module surface.
"""
from __future__ import annotations

import pathlib

import pytest


CLICKTHRU_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "magnifier_bubble" / "clickthru.py"
)
APP_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "magnifier_bubble" / "app.py"
)


def _read_clickthru_source() -> str:
    return CLICKTHRU_PATH.read_text(encoding="utf-8")


# =================== Structural lints (any platform) ===================


def test_clickthru_module_exists():
    """The clickthru module must be importable."""
    from magnifier_bubble import clickthru  # noqa: F401
    assert CLICKTHRU_PATH.is_file(), f"missing {CLICKTHRU_PATH}"


def test_clickthru_no_sendmessagew():
    src = _read_clickthru_source()
    assert src.count("SendMessageW") == 0, (
        "SendMessageW must never appear in clickthru.py - it blocks on "
        "the target message pump and triggers the Python 3.14 re-entrant "
        "WndProc crash (STATE.md Phase 3 decisions)"
    )


def test_clickthru_no_pydll():
    src = _read_clickthru_source()
    assert src.count("PyDLL") == 0, (
        "clickthru.py must use ctypes.windll - not ctypes.PyDLL. "
        "Call sites are Tk main-thread button handlers, not hot-path "
        "WndProc callbacks. The PyDLL-holds-GIL rule is WndProc-only "
        "(see wndproc.py)."
    )


# =================== Phase 7 deletion tests ===================


def test_inject_click_deleted():
    """Phase 7: inject_click must NOT exist in clickthru.py."""
    from magnifier_bubble import clickthru
    assert not hasattr(clickthru, "inject_click"), (
        "inject_click must be deleted in Phase 7 — click injection replaced "
        "by WS_EX_TRANSPARENT content zone"
    )


def test_inject_right_click_deleted():
    """Phase 7: inject_right_click must NOT exist in clickthru.py."""
    from magnifier_bubble import clickthru
    assert not hasattr(clickthru, "inject_right_click"), (
        "inject_right_click must be deleted in Phase 7"
    )


def test_send_rclick_at_deleted():
    """Phase 7: send_rclick_at must NOT exist in clickthru.py."""
    from magnifier_bubble import clickthru
    assert not hasattr(clickthru, "send_rclick_at"), (
        "send_rclick_at must be deleted in Phase 7"
    )


def test_debug_log_disabled():
    """Phase 7: _DEBUG_LOG must be None in clickthru.py (production mode)."""
    src = CLICKTHRU_PATH.read_text(encoding="utf-8")
    assert "_DEBUG_LOG = None" in src, (
        "_DEBUG_LOG must be set to None before shipping (production mode)"
    )
