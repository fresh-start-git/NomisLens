"""Phase 5 Plan 01 Task 3 — Windows-only live-Tk smoke tests for config.ConfigWriter.

These tests require a real Tk root (tk_session_root fixture) and exercise
root.after(500, ...) timing + AppState.on_change dispatch. They are skipped
on non-Windows because the session-root fixture itself skips there.

Complementary to tests/test_config.py which uses mocks / tmp_path only.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from magnifier_bubble import config
from magnifier_bubble.state import AppState, StateSnapshot

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only Tk smoke tests")


def _pump_until(root, predicate, timeout_s: float) -> bool:
    """Drain Tk's event queue, running scheduled after() callbacks, until
    predicate() is True or timeout expires. Returns whether predicate
    became True.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        root.update_idletasks()
        root.update()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_writer_debounce_produces_single_write_after_burst(
    tmp_path, tk_session_root
):
    """Debounce fires ONCE after a burst of 10 mutations; final value wins."""
    path = tmp_path / "config.json"
    state = AppState(StateSnapshot())
    writer = config.ConfigWriter(state, tk_session_root, path)
    writer.register()
    # Mash set_zoom 10 times in quick succession.
    for i in range(10):
        state.set_zoom(1.5 + 0.25 * i)
    # Immediately: nothing written yet (500 ms debounce hasn't fired).
    assert not path.exists(), "debounce fired too early"
    # Pump for up to 1.5 s — one write expected around the 500 ms mark.
    # Generous ceiling vs plan's 0.8 s to ride out sluggish CI timing.
    ok = _pump_until(tk_session_root, lambda: path.exists(), timeout_s=1.5)
    assert ok, "debounce never fired after 1.5 s"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    # Final zoom value (1.5 + 0.25*9 = 3.75) should be persisted, not intermediate.
    assert loaded["zoom"] == pytest.approx(3.75)


def test_flush_pending_writes_synchronously(tmp_path, tk_session_root):
    """flush_pending writes synchronously without pumping the event loop."""
    path = tmp_path / "config.json"
    state = AppState(StateSnapshot())
    writer = config.ConfigWriter(state, tk_session_root, path)
    writer.register()
    state.set_zoom(3.5)
    # Before debounce would fire:
    assert not path.exists()
    writer.flush_pending()
    # Synchronously written — NO event-loop pump required.
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["zoom"] == 3.5


def test_flush_pending_idempotent(tmp_path, tk_session_root):
    """flush_pending is safe to call multiple times; no rewrite if unchanged."""
    path = tmp_path / "config.json"
    state = AppState(StateSnapshot())
    writer = config.ConfigWriter(state, tk_session_root, path)
    writer.register()
    state.set_zoom(4.0)
    writer.flush_pending()
    mtime1 = path.stat().st_mtime_ns
    # Second + third call with no state change -> no-op (mtime unchanged).
    time.sleep(0.02)  # ensure mtime resolution boundary.
    writer.flush_pending()
    writer.flush_pending()
    mtime2 = path.stat().st_mtime_ns
    assert mtime1 == mtime2, "flush_pending rewrote file even though state unchanged"


def test_flush_pending_skips_unchanged_state(tmp_path, tk_session_root):
    """flush_pending skips writing if state matches last_written."""
    path = tmp_path / "config.json"
    state = AppState(StateSnapshot())
    writer = config.ConfigWriter(state, tk_session_root, path)
    writer.register()
    state.set_zoom(3.0)
    writer.flush_pending()
    assert path.exists()
    first_mtime = path.stat().st_mtime_ns
    # No further state change.
    time.sleep(0.02)  # ensure mtime resolution boundary.
    writer.flush_pending()
    assert path.stat().st_mtime_ns == first_mtime


def test_writer_cancels_pending_on_retrigger(tmp_path, tk_session_root):
    """Pitfall 1: after_cancel then reschedule on every mutation."""
    path = tmp_path / "config.json"
    state = AppState(StateSnapshot())
    writer = config.ConfigWriter(state, tk_session_root, path)
    writer.register()
    state.set_zoom(2.0)
    first_after_id = writer._after_id
    assert first_after_id is not None
    state.set_zoom(2.5)
    second_after_id = writer._after_id
    assert second_after_id is not None
    assert second_after_id != first_after_id, (
        "writer did not reschedule after second mutation"
    )


def test_write_atomic_real_fs_round_trip(tmp_path, tk_session_root):
    """End-to-end: write_atomic on a real FS produces a leak-free round-trip."""
    path = tmp_path / "config.json"
    snap = StateSnapshot(
        x=123, y=456, w=350, h=400, zoom=2.75, shape="circle"
    )
    config.write_atomic(path, snap)
    assert path.exists()
    leaked = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leaked == [], f"tempfile leaked: {leaked}"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == {
        "version": 1,
        "x": 123,
        "y": 456,
        "w": 350,
        "h": 400,
        "zoom": 2.75,
        "shape": "circle",
    }
