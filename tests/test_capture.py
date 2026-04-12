"""Structural and lint tests for src/magnifier_bubble/capture.py.

Phase 3 Plan 01 Wave 0: pure-Python tests that verify CaptureWorker's
thread-safety contracts, BILINEAR usage, absence of ImageGrab, mss
thread-local safety (lazy import inside run()), and frame-pacing via
Event.wait instead of the non-interruptible alternative.

Every test is deterministic, < 100 ms, and uses no platform-specific
imports (no mss, no tkinter, no PIL, no ctypes at module level).
"""
from __future__ import annotations

import ast
import inspect
import pathlib
import threading
import time


# ---------------------------------------------------------------------------
# Helpers: FakeState + FakeCallback + source/ast accessors
# ---------------------------------------------------------------------------

class _FakeState:
    """Minimal AppState stand-in for CaptureWorker construction."""

    def __init__(self, rect=(100, 100, 400, 400, 2.0)):
        self._rect = rect

    def capture_region(self):
        return self._rect


_fake_cb = lambda img: None  # noqa: E731


def _capture_source() -> str:
    import magnifier_bubble.capture as mod
    return pathlib.Path(mod.__file__).read_text(encoding="utf-8")


def _capture_ast():
    return ast.parse(_capture_source())


def _find_funcdef(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found in capture.py")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_module_import_does_not_load_mss():
    """Importing capture.py must NOT pull mss into sys.modules."""
    import sys
    sys.modules.pop("mss", None)
    sys.modules.pop("magnifier_bubble.capture", None)
    from magnifier_bubble import capture  # noqa: F811
    assert "mss" not in sys.modules, (
        "capture.py imported mss at module level -- mss MUST be "
        "imported lazily inside CaptureWorker.run() for the "
        "thread-local contract (03-RESEARCH.md Correction 2)"
    )


def test_capture_module_imports():
    """from magnifier_bubble import capture works without side-effects."""
    from magnifier_bubble import capture  # noqa: F811
    assert hasattr(capture, "CaptureWorker")


def test_captureworker_class_exists():
    """CaptureWorker must be a subclass of threading.Thread."""
    from magnifier_bubble import capture
    assert inspect.isclass(capture.CaptureWorker)
    assert issubclass(capture.CaptureWorker, threading.Thread)


def test_captureworker_init_signature():
    """__init__ signature is (self, state, on_frame, target_fps=30.0)."""
    from magnifier_bubble import capture
    sig = inspect.signature(capture.CaptureWorker.__init__, eval_str=True)
    params = list(sig.parameters.values())
    # params[0] = self
    assert params[0].name == "self"
    assert params[1].name == "state"
    assert params[2].name == "on_frame"
    assert params[3].name == "target_fps"
    assert params[3].default == 30.0


def test_captureworker_is_daemon_by_default():
    """Worker must be daemon and named 'magnifier-capture'."""
    from magnifier_bubble import capture
    worker = capture.CaptureWorker(_FakeState(), _fake_cb)
    assert worker.daemon is True
    assert worker.name.startswith("magnifier-capture")


def test_stop_is_threading_event():
    """worker._stop must be a threading.Event instance."""
    from magnifier_bubble import capture
    worker = capture.CaptureWorker(_FakeState(), _fake_cb)
    assert isinstance(worker._stop, threading.Event)


def test_get_fps_returns_zero_before_samples():
    """get_fps() returns 0.0 when no samples collected yet."""
    from magnifier_bubble import capture
    worker = capture.CaptureWorker(_FakeState(), _fake_cb)
    assert worker.get_fps() == 0.0


def test_get_fps_returns_positive_after_samples():
    """get_fps() returns ~30 with 60 synthetic timestamps at 33.3ms spacing."""
    from magnifier_bubble import capture
    worker = capture.CaptureWorker(_FakeState(), _fake_cb)
    base = 1.0
    for i in range(60):
        worker._fps_samples.append(base + i * (1.0 / 30.0))
    fps = worker.get_fps()
    assert 29.0 < fps < 31.0, f"Expected ~30 fps, got {fps}"


def test_no_imagegrab_in_capture_source():
    """The literal substring 'ImageGrab' must NOT appear in capture.py (CAPT-03)."""
    source = _capture_source()
    assert "ImageGrab" not in source, (
        "capture.py contains 'ImageGrab' -- use mss for screen capture (CAPT-03)"
    )


def test_capture_uses_bilinear_literal():
    """'Resampling.BILINEAR' must appear exactly once in capture.py (CAPT-04)."""
    source = _capture_source()
    count = source.count("Resampling.BILINEAR")
    assert count == 1, (
        f"Expected exactly 1 occurrence of 'Resampling.BILINEAR', found {count}"
    )


def test_mss_mss_constructed_inside_run():
    """mss.mss() Call node must exist inside run(), nowhere else."""
    tree = _capture_ast()
    run_def = _find_funcdef(tree, "run")

    def _find_mss_calls(subtree):
        calls = []
        for node in ast.walk(subtree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "mss":
                if isinstance(func.value, ast.Name) and func.value.id == "mss":
                    calls.append(node)
        return calls

    run_calls = _find_mss_calls(run_def)
    assert len(run_calls) >= 1, "mss.mss() not found inside run()"

    # Check no mss.mss() outside run()
    all_calls = _find_mss_calls(tree)
    outside = len(all_calls) - len(run_calls)
    assert outside == 0, (
        f"Found {outside} mss.mss() call(s) outside run() -- "
        "mss must be constructed inside run() for thread-local safety"
    )


def test_capture_uses_capture_region_not_snapshot():
    """capture.py must call state.capture_region(), never state.snapshot()."""
    source = _capture_source()
    assert "state.capture_region(" in source or "self._state.capture_region(" in source, (
        "capture.py does not call state.capture_region()"
    )
    assert "state.snapshot(" not in source and "self._state.snapshot(" not in source, (
        "capture.py calls state.snapshot() -- use state.capture_region() instead"
    )


def test_run_uses_event_wait_not_time_sleep():
    """run() must use self._stop.wait() for pacing (>= 2 calls), never any .sleep() call."""
    tree = _capture_ast()
    run_def = _find_funcdef(tree, "run")

    sleep_calls = []
    wait_calls = []
    for node in ast.walk(run_def):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr == "sleep":
                sleep_calls.append(node)
            if (func.attr == "wait"
                    and isinstance(func.value, ast.Attribute)
                    and func.value.attr == "_stop"):
                wait_calls.append(node)

    assert len(sleep_calls) == 0, (
        f"Found {len(sleep_calls)} .sleep() call(s) inside run() -- "
        "use self._stop.wait() for interruptible pacing"
    )
    assert len(wait_calls) >= 2, (
        f"Expected >= 2 self._stop.wait() calls in run() "
        f"(frame pacing + reconnect backoff), found {len(wait_calls)}"
    )


def test_run_has_outer_reconnect_loop():
    """run() must have 2 while loops: outer reconnect + inner frame loop."""
    tree = _capture_ast()
    run_def = _find_funcdef(tree, "run")
    while_nodes = [n for n in ast.walk(run_def) if isinstance(n, ast.While)]
    assert len(while_nodes) == 2, (
        f"Expected exactly 2 while-loops in run() "
        f"(outer reconnect + inner frame), found {len(while_nodes)}"
    )
