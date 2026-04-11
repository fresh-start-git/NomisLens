"""Unit tests for magnifier_bubble.state — AppState single source of truth."""
from __future__ import annotations

import pytest

from magnifier_bubble.state import AppState, StateSnapshot


def test_default_snapshot():
    s = AppState()
    snap = s.snapshot()
    assert snap.x == 200
    assert snap.y == 200
    assert snap.w == 400
    assert snap.h == 400
    assert snap.zoom == 2.0
    assert snap.shape == "rect"
    assert snap.visible is True
    assert snap.always_on_top is True


def test_custom_initial_snapshot():
    s = AppState(StateSnapshot(x=10, y=20))
    snap = s.snapshot()
    assert snap.x == 10
    assert snap.y == 20
    assert snap.w == 400  # default preserved


def test_set_position_fires_observer():
    s = AppState()
    calls = []
    s.on_change(lambda: calls.append(s.snapshot()))
    s.set_position(123, 456)
    assert len(calls) == 1
    assert calls[0].x == 123
    assert calls[0].y == 456


def test_set_size_fires_observer():
    s = AppState()
    calls = []
    s.on_change(lambda: calls.append(s.snapshot()))
    s.set_size(250, 350)
    assert len(calls) == 1
    assert calls[0].w == 250
    assert calls[0].h == 350


def test_set_zoom_fires_observer_and_clamps():
    s = AppState()
    calls = []
    s.on_change(lambda: calls.append(s.snapshot()))
    s.set_zoom(2.5)
    assert calls[-1].zoom == 2.5
    s.set_zoom(10.0)
    assert calls[-1].zoom == 6.0  # clamped high
    s.set_zoom(0.1)
    assert calls[-1].zoom == 1.5  # clamped low
    assert len(calls) == 3


def test_zoom_snaps_to_quarter_steps():
    s = AppState()
    s.set_zoom(2.37)
    assert s.snapshot().zoom == 2.25
    s.set_zoom(2.49)
    assert s.snapshot().zoom == 2.5
    s.set_zoom(3.874)
    assert s.snapshot().zoom == 3.75


@pytest.mark.parametrize("shape", ["circle", "rounded", "rect"])
def test_set_shape_valid_values(shape):
    s = AppState()
    s.set_shape(shape)
    assert s.snapshot().shape == shape


def test_set_shape_invalid_raises():
    s = AppState()
    with pytest.raises(ValueError, match="triangle"):
        s.set_shape("triangle")


def test_set_visible_fires_observer():
    s = AppState()
    calls = []
    s.on_change(lambda: calls.append(None))
    s.set_visible(False)
    assert s.snapshot().visible is False
    assert len(calls) == 1


def test_toggle_visible_flips():
    s = AppState()
    calls = []
    s.on_change(lambda: calls.append(None))
    assert s.snapshot().visible is True
    s.toggle_visible()
    assert s.snapshot().visible is False
    s.toggle_visible()
    assert s.snapshot().visible is True
    assert len(calls) == 2


def test_toggle_aot_flips():
    s = AppState()
    assert s.snapshot().always_on_top is True
    s.toggle_aot()
    assert s.snapshot().always_on_top is False
    s.toggle_aot()
    assert s.snapshot().always_on_top is True


def test_capture_region_returns_tuple():
    s = AppState()
    s.set_position(50, 60)
    s.set_size(300, 200)
    s.set_zoom(3.0)
    assert s.capture_region() == (50, 60, 300, 200, 3.0)


def test_snapshot_is_independent_copy():
    s = AppState()
    snap = s.snapshot()
    snap.x = 9999
    fresh = s.snapshot()
    assert fresh.x == 200  # original unchanged


def test_multiple_observers_all_fire():
    s = AppState()
    a_calls = []
    b_calls = []
    c_calls = []
    s.on_change(lambda: a_calls.append(None))
    s.on_change(lambda: b_calls.append(None))
    s.on_change(lambda: c_calls.append(None))
    s.set_position(1, 2)
    assert len(a_calls) == 1
    assert len(b_calls) == 1
    assert len(c_calls) == 1
