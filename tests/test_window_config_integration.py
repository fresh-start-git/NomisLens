"""Phase 5 Task 2 unit tests — BubbleWindow.destroy() flush contract.

Uses a fake writer object so we don't need AppState + real config
plumbing; we only care that BubbleWindow.destroy() calls
flush_pending() on whatever object was handed to attach_config_writer.
"""
from __future__ import annotations

import sys
import types
import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="BubbleWindow requires Windows ctypes/WndProc; integration test is Win-only",
)


def _make_fake_writer() -> types.SimpleNamespace:
    fake = types.SimpleNamespace()
    fake.flush_calls = 0

    def _flush() -> None:
        fake.flush_calls += 1

    fake.flush_pending = _flush
    return fake


def test_attach_config_writer_sets_attribute(tk_session_root):
    from magnifier_bubble.state import AppState, StateSnapshot
    from magnifier_bubble.window import BubbleWindow

    state = AppState(StateSnapshot())
    bubble = BubbleWindow(state)
    try:
        assert bubble._config_writer is None
        fake = _make_fake_writer()
        bubble.attach_config_writer(fake)
        assert bubble._config_writer is fake
    finally:
        bubble.destroy()


def test_destroy_calls_flush_pending_exactly_once(tk_session_root):
    from magnifier_bubble.state import AppState, StateSnapshot
    from magnifier_bubble.window import BubbleWindow

    state = AppState(StateSnapshot())
    bubble = BubbleWindow(state)
    fake = _make_fake_writer()
    bubble.attach_config_writer(fake)

    bubble.destroy()
    assert fake.flush_calls == 1, (
        "BubbleWindow.destroy() must call writer.flush_pending() "
        "exactly once (PERS-04)"
    )


def test_destroy_without_writer_does_not_raise(tk_session_root):
    """Backward compat: a bubble with no attached writer must
    destroy cleanly (no AttributeError) so non-Phase-5 tests
    and the Phase 2/3/4 construction paths still work."""
    from magnifier_bubble.state import AppState, StateSnapshot
    from magnifier_bubble.window import BubbleWindow

    state = AppState(StateSnapshot())
    bubble = BubbleWindow(state)
    # No attach_config_writer call.
    bubble.destroy()  # Must not raise AttributeError or anything else.


def test_destroy_swallows_flush_exception(tk_session_root):
    """Phase 5 PERS-04 robustness: if flush_pending raises, destroy
    must still proceed to tear down root.  Ensures a writer bug
    never strands the process with a live window."""
    from magnifier_bubble.state import AppState, StateSnapshot
    from magnifier_bubble.window import BubbleWindow

    state = AppState(StateSnapshot())
    bubble = BubbleWindow(state)

    boom = types.SimpleNamespace()
    boom.flush_calls = 0

    def _explode() -> None:
        boom.flush_calls += 1
        raise RuntimeError("simulated writer failure")

    boom.flush_pending = _explode
    bubble.attach_config_writer(boom)

    bubble.destroy()  # Must not re-raise.
    assert boom.flush_calls == 1
