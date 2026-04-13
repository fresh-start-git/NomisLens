"""Phase 4 Plan 03 cross-process click injection tests.

Structural lints run on any platform; Windows-only smoke tests use
monkeypatched fake u32 namespaces to validate control flow without
requiring real HWNDs.
"""
from __future__ import annotations

import inspect
import pathlib
import re
import sys
import types
from unittest.mock import MagicMock

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
    """Plan 04-03: the clickthru module must be importable."""
    from magnifier_bubble import clickthru  # noqa: F401
    assert CLICKTHRU_PATH.is_file(), f"missing {CLICKTHRU_PATH}"


def test_inject_click_signature():
    """Plan 04-03: inject_click(screen_x: int, screen_y: int, own_hwnd: int) -> bool.

    Uses eval_str=True because `from __future__ import annotations` (PEP
    563) would otherwise yield string annotations rather than types.
    """
    from magnifier_bubble import clickthru
    sig = inspect.signature(clickthru.inject_click, eval_str=True)
    params = list(sig.parameters)
    assert params == ["screen_x", "screen_y", "own_hwnd"], (
        f"inject_click params: {params}"
    )
    # Return annotation must evaluate to the bool type, not the string.
    assert sig.return_annotation is bool, (
        f"return annotation: {sig.return_annotation!r}"
    )


def test_clickthru_uses_childwindowfrompointex():
    src = _read_clickthru_source()
    assert src.count("ChildWindowFromPointEx") >= 1, (
        "clickthru.py must reference ChildWindowFromPointEx (research Pattern 6)"
    )


def test_clickthru_uses_cwp_skiptransparent():
    src = _read_clickthru_source()
    assert src.count("CWP_SKIPTRANSPARENT") >= 1, (
        "clickthru.py must set CWP_SKIPTRANSPARENT - without it, "
        "ChildWindowFromPointEx returns our own layered bubble (Pitfall I)"
    )


def test_clickthru_uses_postmessagew():
    src = _read_clickthru_source()
    # At least one call site per message; wParam/lParam pack is checked separately.
    assert src.count("PostMessageW") >= 2, (
        f"Expected >= 2 PostMessageW references (DOWN + UP); "
        f"got {src.count('PostMessageW')}"
    )


def test_clickthru_no_sendmessagew():
    src = _read_clickthru_source()
    assert src.count("SendMessageW") == 0, (
        "SendMessageW must never appear in clickthru.py - it blocks on "
        "the target message pump and triggers the Python 3.14 re-entrant "
        "WndProc crash (STATE.md Phase 3 decisions)"
    )


def test_clickthru_uses_screentoclient():
    src = _read_clickthru_source()
    # ScreenToClient appears both in argtypes setup and in the call body.
    assert src.count("ScreenToClient") >= 1, (
        "clickthru.py must call ScreenToClient so lParam encodes "
        "CLIENT-relative coordinates (not screen-relative)"
    )


def test_clickthru_no_pydll():
    src = _read_clickthru_source()
    assert src.count("PyDLL") == 0, (
        "clickthru.py must use ctypes.windll - not ctypes.PyDLL. "
        "Call sites are Tk main-thread button handlers, not hot-path "
        "WndProc callbacks. The PyDLL-holds-GIL rule is WndProc-only "
        "(see wndproc.py)."
    )


def test_clickthru_lparam_packs_client_coords():
    """Plan 04-03: lParam must be packed from the CLIENT-space point.

    Accepts any equivalent form like `((client_pt.y & 0xFFFF) << 16) |
    (client_pt.x & 0xFFFF)` - we grep for the (y << 16) | (x) shape.
    """
    src = _read_clickthru_source()
    pattern = re.compile(r"\(\(.*y.*\)\s*<<\s*16\)\s*\|\s*\(.*x.*\)")
    assert pattern.search(src), (
        "clickthru.py must pack lParam as ((client_y & 0xFFFF) << 16) | "
        "(client_x & 0xFFFF) - the canonical WM_LBUTTONDOWN encoding"
    )


def test_clickthru_self_hwnd_guard_present():
    """Pitfall I: explicit `target == own_hwnd` early-return."""
    src = _read_clickthru_source()
    assert "target == own_hwnd" in src, (
        "clickthru.py must compare target to own_hwnd and early-return "
        "False - belt-and-suspenders against CWP_SKIPTRANSPARENT gaps"
    )


def test_app_parses_no_click_injection_flag():
    """Plan 04-03: app.py gains argparse for --no-click-injection and
    forwards the negated value as click_injection_enabled to BubbleWindow.
    """
    src = APP_PATH.read_text(encoding="utf-8")
    assert "argparse" in src, "app.py must import argparse"
    assert "--no-click-injection" in src, (
        "app.py must expose the --no-click-injection CLI flag"
    )
    assert "click_injection_enabled=not args.no_click_injection" in src, (
        "app.py must wire args.no_click_injection into BubbleWindow "
        "as click_injection_enabled=not args.no_click_injection"
    )


# =================== Windows-only smoke tests ===================


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="ctypes.windll required for import side-effects",
)
def test_inject_click_skips_self_hwnd(monkeypatch):
    """Pitfall I: if ChildWindowFromPointEx returns our own HWND, the
    self-guard must prevent PostMessageW from ever firing.
    """
    from magnifier_bubble import clickthru

    fake_u32 = types.SimpleNamespace()
    fake_u32.GetDesktopWindow = MagicMock(return_value=999)
    fake_u32.ChildWindowFromPointEx = MagicMock(return_value=42)
    fake_u32.ScreenToClient = MagicMock(return_value=1)
    fake_u32.PostMessageW = MagicMock(return_value=1)
    monkeypatch.setattr(clickthru, "_u32", lambda: fake_u32)

    # own_hwnd matches the target returned by ChildWindowFromPointEx.
    result = clickthru.inject_click(100, 100, 42)

    assert result is False
    fake_u32.PostMessageW.assert_not_called()


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="ctypes.windll required",
)
def test_inject_click_calls_postmessagew_twice_on_success(monkeypatch):
    """On a happy-path call the module must post WM_LBUTTONDOWN then
    WM_LBUTTONUP - exactly two PostMessageW calls.
    """
    from magnifier_bubble import clickthru

    fake_u32 = types.SimpleNamespace()
    fake_u32.GetDesktopWindow = MagicMock(return_value=999)
    fake_u32.ChildWindowFromPointEx = MagicMock(return_value=7777)
    fake_u32.ScreenToClient = MagicMock(return_value=1)
    fake_u32.PostMessageW = MagicMock(return_value=1)
    monkeypatch.setattr(clickthru, "_u32", lambda: fake_u32)

    result = clickthru.inject_click(200, 300, 42)

    assert result is True
    assert fake_u32.PostMessageW.call_count == 2, (
        f"expected 2 PostMessageW calls (DOWN + UP); "
        f"got {fake_u32.PostMessageW.call_count}"
    )


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="ctypes.windll required",
)
def test_inject_click_returns_false_when_no_target(monkeypatch):
    """If ChildWindowFromPointEx returns 0 (no window at point), inject_click
    must short-circuit to False without posting messages.
    """
    from magnifier_bubble import clickthru

    fake_u32 = types.SimpleNamespace()
    fake_u32.GetDesktopWindow = MagicMock(return_value=999)
    fake_u32.ChildWindowFromPointEx = MagicMock(return_value=0)
    fake_u32.ScreenToClient = MagicMock(return_value=1)
    fake_u32.PostMessageW = MagicMock(return_value=1)
    monkeypatch.setattr(clickthru, "_u32", lambda: fake_u32)

    result = clickthru.inject_click(5000, 5000, 42)

    assert result is False
    fake_u32.PostMessageW.assert_not_called()
    fake_u32.ScreenToClient.assert_not_called()


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="ctypes.windll required",
)
def test_inject_click_never_raises(monkeypatch):
    """Any ctypes error must be swallowed - callers rely on the return
    value, not exceptions, so a misbehaving target can't crash the Tk
    main loop.
    """
    from magnifier_bubble import clickthru

    fake_u32 = types.SimpleNamespace()
    fake_u32.GetDesktopWindow = MagicMock(
        side_effect=OSError("simulated ctypes failure")
    )
    fake_u32.ChildWindowFromPointEx = MagicMock(return_value=0)
    fake_u32.ScreenToClient = MagicMock(return_value=1)
    fake_u32.PostMessageW = MagicMock(return_value=1)
    monkeypatch.setattr(clickthru, "_u32", lambda: fake_u32)

    # Must not raise.
    result = clickthru.inject_click(1, 2, 3)
    assert result is False
