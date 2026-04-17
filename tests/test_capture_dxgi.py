"""Structural and lint tests for src/magnifier_bubble/capture_dxgi.py.

Phase 7 Plan 01: pure-Python tests that verify DXGICaptureWorker's
thread-safety contracts, BILINEAR usage, absence of ImageGrab, dxcam
thread-local safety (lazy import inside run()), and correct region format
(left, top, right, bottom — not left, top, width, height).
"""
from __future__ import annotations

import ast
import inspect
import pathlib
import threading

import pytest


CAPTURE_DXGI_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "magnifier_bubble" / "capture_dxgi.py"
)


class _FakeState:
    def __init__(self, rect=(100, 100, 400, 400, 2.0)):
        self._rect = rect
    def capture_region(self):
        return self._rect


_fake_cb = lambda img: None  # noqa: E731


def _source() -> str:
    return CAPTURE_DXGI_PATH.read_text(encoding="utf-8")


def _ast_tree():
    return ast.parse(_source())


def _find_funcdef(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found in capture_dxgi.py")


def test_module_import_does_not_load_dxcam():
    """Importing capture_dxgi must NOT pull dxcam into sys.modules at module level."""
    import sys
    sys.modules.pop("dxcam", None)
    sys.modules.pop("magnifier_bubble.capture_dxgi", None)
    from magnifier_bubble import capture_dxgi  # noqa: F811
    assert "dxcam" not in sys.modules, (
        "capture_dxgi.py imported dxcam at module level -- dxcam MUST be "
        "imported lazily inside DXGICaptureWorker.run() for thread safety"
    )


def test_dxgi_capture_worker_class_exists():
    """DXGICaptureWorker must be a subclass of threading.Thread."""
    from magnifier_bubble import capture_dxgi
    assert inspect.isclass(capture_dxgi.DXGICaptureWorker)
    assert issubclass(capture_dxgi.DXGICaptureWorker, threading.Thread)


def test_dxgi_capture_worker_init_signature():
    """__init__ signature is (self, state, on_frame, target_fps=30.0)."""
    from magnifier_bubble import capture_dxgi
    sig = inspect.signature(capture_dxgi.DXGICaptureWorker.__init__, eval_str=True)
    params = list(sig.parameters.values())
    assert params[0].name == "self"
    assert params[1].name == "state"
    assert params[2].name == "on_frame"
    assert params[3].name == "target_fps"
    assert params[3].default == 30.0


def test_dxgi_capture_worker_is_daemon():
    """Worker must be daemon and named 'magnifier-dxgi-capture'."""
    from magnifier_bubble import capture_dxgi
    worker = capture_dxgi.DXGICaptureWorker(_FakeState(), _fake_cb)
    assert worker.daemon is True
    assert worker.name.startswith("magnifier-dxgi-capture")


def test_stop_is_threading_event():
    """worker._stop must be a threading.Event instance."""
    from magnifier_bubble import capture_dxgi
    worker = capture_dxgi.DXGICaptureWorker(_FakeState(), _fake_cb)
    assert isinstance(worker._stop, threading.Event)


def test_get_fps_returns_zero_before_samples():
    """get_fps() returns 0.0 when no samples collected yet."""
    from magnifier_bubble import capture_dxgi
    worker = capture_dxgi.DXGICaptureWorker(_FakeState(), _fake_cb)
    assert worker.get_fps() == 0.0


def test_get_fps_returns_positive_after_samples():
    """get_fps() returns ~30 with 60 synthetic timestamps at 33.3ms spacing."""
    from magnifier_bubble import capture_dxgi
    worker = capture_dxgi.DXGICaptureWorker(_FakeState(), _fake_cb)
    base = 1.0
    for i in range(60):
        worker._fps_samples.append(base + i * (1.0 / 30.0))
    fps = worker.get_fps()
    assert 29.0 < fps < 31.0, f"Expected ~30 fps, got {fps}"


def test_no_imagegrab_in_capture_dxgi_source():
    """The literal substring 'ImageGrab' must NOT appear in capture_dxgi.py (CAPT-03)."""
    source = _source()
    assert "ImageGrab" not in source, (
        "capture_dxgi.py contains 'ImageGrab' -- CAPT-03 prohibits it"
    )


def test_capture_dxgi_uses_bilinear():
    """'BILINEAR' must appear in capture_dxgi.py (CAPT-04)."""
    source = _source()
    assert "BILINEAR" in source, (
        "capture_dxgi.py must use BILINEAR resampling (CAPT-04)"
    )


def test_region_coordinates_use_right_bottom():
    """Region must use (src_x, src_y, src_x+src_w, src_y+src_h) format (CAPT-01).

    dxcam region is (left, top, right, bottom), NOT (left, top, width, height).
    The source must contain 'src_x + src_w' and 'src_y + src_h' to prove
    the right/bottom corner is computed, not the width/height passed directly.
    """
    source = _source()
    assert "src_x + src_w" in source, (
        "capture_dxgi.py must compute right = src_x + src_w (dxcam region format)"
    )
    assert "src_y + src_h" in source, (
        "capture_dxgi.py must compute bottom = src_y + src_h (dxcam region format)"
    )


def test_dxcam_create_inside_run():
    """dxcam.create() must be called inside run(), never in __init__."""
    tree = _ast_tree()
    run_def = _find_funcdef(tree, "run")

    def _find_create_calls(subtree):
        calls = []
        for node in ast.walk(subtree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "create":
                if isinstance(func.value, ast.Name) and func.value.id == "dxcam":
                    calls.append(node)
        return calls

    run_calls = _find_create_calls(run_def)
    assert len(run_calls) >= 1, "dxcam.create() not found inside run()"

    all_calls = _find_create_calls(tree)
    outside = len(all_calls) - len(run_calls)
    assert outside == 0, (
        f"Found {outside} dxcam.create() call(s) outside run() -- "
        "dxcam.create() must be called on the worker thread inside run()"
    )


def test_camera_release_in_finally():
    """camera.release() must appear in the source (cleanup on worker exit)."""
    source = _source()
    assert "camera.release()" in source, (
        "capture_dxgi.py must call camera.release() in a finally block "
        "to allow the dxcam DXFactory singleton to release the reference"
    )


def test_no_cv2_in_source():
    """'cv2' must NOT appear in capture_dxgi.py — use processor_backend='numpy'."""
    source = _source()
    assert "cv2" not in source, (
        "capture_dxgi.py references cv2 -- opencv is not installed; "
        "use processor_backend='numpy' in dxcam.create()"
    )


def test_output_color_rgb():
    """'output_color' and 'RGB' must both appear in capture_dxgi.py."""
    source = _source()
    assert "output_color" in source, (
        "capture_dxgi.py must pass output_color= to dxcam.create()"
    )
    assert '"RGB"' in source or "'RGB'" in source, (
        "capture_dxgi.py must specify output_color='RGB'"
    )
