"""Phase 5 Plan 01 unit tests for config.py — path resolution, atomic write,
graceful load, and structural lints.

Platform-independent (no Tk, no ctypes). Plan 01 Task 3 adds the Windows-only
Tk smoke tests to tests/test_config_smoke.py.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

from magnifier_bubble import config
from magnifier_bubble.state import StateSnapshot


_CONFIG_SRC_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "magnifier_bubble"
    / "config.py"
)


def _config_src() -> str:
    return _CONFIG_SRC_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# PATH RESOLUTION (PERS-01, Pattern 2, Pitfalls 5 & 6)
# ---------------------------------------------------------------------------


def test_config_path_returns_pathlib_path():
    p = config.config_path()
    assert isinstance(p, Path)


def test_config_path_filename_is_config_json():
    p = config.config_path()
    assert p.name == "config.json"


def test_config_path_primary_writable_returns_app_dir(monkeypatch, tmp_path):
    # Force dev mode (not frozen) so sys.argv[0] drives the lookup.
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    fake_main = tmp_path / "main.py"
    fake_main.write_text("x", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [str(fake_main)])
    # Do not override _is_writable — tmp_path is a real, writable directory.
    p = config.config_path()
    assert p.parent == tmp_path
    assert p.name == "config.json"


def test_config_path_falls_back_to_localappdata_on_unwritable_primary(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
    monkeypatch.setattr(config, "_is_writable", lambda p: False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    p = config.config_path()
    assert p == tmp_path / "UltimateZoom" / "config.json"


def test_config_path_frozen_uses_sys_executable(monkeypatch, tmp_path):
    fake_exe = tmp_path / "fake.exe"
    fake_exe.write_text("x", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(config, "_is_writable", lambda p: True)
    p = config.config_path()
    assert p.parent == tmp_path
    assert p.name == "config.json"


def test_config_path_falls_back_to_homedir_if_localappdata_unset(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
    monkeypatch.setattr(config, "_is_writable", lambda p: False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    p = config.config_path()
    assert str(p).startswith(str(Path.home()))
    assert ".UltimateZoom" in str(p)
    assert p.name == "config.json"


# ---------------------------------------------------------------------------
# WRITE_ATOMIC (PERS-02, Pattern 1, Pitfalls 2 / 3 / 4 / 9)
# ---------------------------------------------------------------------------


def test_write_atomic_produces_valid_json(tmp_path):
    path = tmp_path / "config.json"
    snap = StateSnapshot(x=100, y=200, w=300, h=400, zoom=3.0, shape="circle")
    config.write_atomic(path, snap)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["version"] == 1
    assert loaded["x"] == 100
    assert loaded["y"] == 200
    assert loaded["w"] == 300
    assert loaded["h"] == 400
    assert loaded["zoom"] == 3.0
    assert loaded["shape"] == "circle"


def test_write_atomic_omits_visible_and_always_on_top(tmp_path):
    path = tmp_path / "config.json"
    snap = StateSnapshot(
        x=1, y=2, w=300, h=400, zoom=2.0, shape="rect",
        visible=False, always_on_top=False,
    )
    config.write_atomic(path, snap)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert "visible" not in loaded
    assert "always_on_top" not in loaded


def test_write_atomic_no_tempfile_leaks(tmp_path):
    path = tmp_path / "config.json"
    config.write_atomic(path, StateSnapshot())
    entries = list(tmp_path.iterdir())
    assert len(entries) == 1, f"tempfile leaked: {entries}"
    assert entries[0].name == "config.json"


def test_write_atomic_uses_sort_keys(tmp_path):
    path = tmp_path / "config.json"
    snap = StateSnapshot(x=1, y=2, w=300, h=400, zoom=2.0, shape="rect")
    config.write_atomic(path, snap)
    raw_text = path.read_text(encoding="utf-8")
    # Parse preserving order so we can confirm alphabetical sorting.
    pairs = json.loads(raw_text, object_pairs_hook=list)
    keys = [k for k, _ in pairs]
    assert keys == sorted(keys), f"keys not sorted alphabetically: {keys}"


def test_write_atomic_creates_parent_dir_if_missing(tmp_path):
    path = tmp_path / "subdir" / "config.json"
    config.write_atomic(path, StateSnapshot())
    assert path.exists()


def test_write_atomic_overwrites_existing(tmp_path):
    path = tmp_path / "config.json"
    config.write_atomic(
        path, StateSnapshot(x=1, y=2, w=300, h=400, zoom=2.0, shape="rect")
    )
    config.write_atomic(
        path, StateSnapshot(x=1, y=2, w=300, h=400, zoom=4.0, shape="rect")
    )
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["zoom"] == 4.0


def test_write_atomic_includes_schema_version(tmp_path):
    path = tmp_path / "config.json"
    config.write_atomic(path, StateSnapshot())
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["version"] == 1


# ---------------------------------------------------------------------------
# LOAD (PERS-03, Pattern 4)
# ---------------------------------------------------------------------------


def test_load_missing_file_returns_defaults(tmp_path, capsys):
    path = tmp_path / "missing.json"
    loaded = config.load(path)
    assert loaded == StateSnapshot()
    captured = capsys.readouterr()
    assert captured.out == ""


def test_load_corrupt_json_returns_defaults(tmp_path, capsys):
    path = tmp_path / "corrupt.json"
    path.write_text("not json {", encoding="utf-8")
    loaded = config.load(path)
    assert loaded == StateSnapshot()
    captured = capsys.readouterr()
    assert "[config] corrupt json" in captured.out


def test_load_out_of_range_zoom_is_clamped(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(
        json.dumps({"zoom": 99.0, "x": 0, "y": 0, "w": 400, "h": 400, "shape": "rect"}),
        encoding="utf-8",
    )
    loaded = config.load(path)
    assert loaded.zoom == 6.0


def test_load_out_of_range_zoom_below_min_is_clamped(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(
        json.dumps({"zoom": 0.1, "x": 0, "y": 0, "w": 400, "h": 400, "shape": "rect"}),
        encoding="utf-8",
    )
    loaded = config.load(path)
    assert loaded.zoom == 1.5


def test_load_out_of_range_size_is_clamped(tmp_path):
    path_big = tmp_path / "big.json"
    path_big.write_text(
        json.dumps({"x": 0, "y": 0, "w": 5000, "h": 10, "zoom": 2.0, "shape": "rect"}),
        encoding="utf-8",
    )
    loaded_big = config.load(path_big)
    assert loaded_big.w == 700
    assert loaded_big.h == 150

    path_small = tmp_path / "small.json"
    path_small.write_text(
        json.dumps({"x": 0, "y": 0, "w": 10, "h": 10, "zoom": 2.0, "shape": "rect"}),
        encoding="utf-8",
    )
    loaded_small = config.load(path_small)
    assert loaded_small.w == 150
    assert loaded_small.h == 150


def test_load_invalid_shape_falls_back_to_rect(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(
        json.dumps(
            {"x": 0, "y": 0, "w": 400, "h": 400, "zoom": 2.0, "shape": "hexagon"}
        ),
        encoding="utf-8",
    )
    loaded = config.load(path)
    assert loaded.shape == "rect"


def test_load_unknown_fields_are_ignored(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(
        json.dumps(
            {
                "x": 0, "y": 0, "w": 400, "h": 400, "zoom": 2.0, "shape": "rect",
                "hotkey": "ctrl+z",  # unknown — must not break load.
            }
        ),
        encoding="utf-8",
    )
    loaded = config.load(path)
    assert isinstance(loaded, StateSnapshot)


def test_load_partial_file_merges_with_defaults(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"zoom": 3.5}), encoding="utf-8")
    loaded = config.load(path)
    assert loaded.zoom == 3.5
    assert loaded.x == StateSnapshot().x  # 200 default preserved
    assert loaded.y == StateSnapshot().y
    assert loaded.w == StateSnapshot().w


def test_load_root_is_not_dict_returns_defaults(tmp_path, capsys):
    path = tmp_path / "c.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    loaded = config.load(path)
    assert loaded == StateSnapshot()
    captured = capsys.readouterr()
    assert "not an object" in captured.out


# ---------------------------------------------------------------------------
# STRUCTURAL LINTS — enforce research-mandated patterns by grepping source.
# ---------------------------------------------------------------------------


def test_config_uses_os_replace_not_os_rename():
    src = _config_src()
    assert "os.replace(" in src
    assert "os.rename(" not in src


def test_config_calls_fsync_before_replace():
    src = _config_src()
    fsync_idx = src.index("os.fsync(")
    replace_idx = src.index("os.replace(")
    assert fsync_idx < replace_idx, (
        "os.fsync must be called before os.replace (Pitfall 4)"
    )


def test_config_uses_tempfile_with_dir_kwarg():
    src = _config_src()
    match = re.search(r"NamedTemporaryFile\s*\([^)]*dir\s*=", src, re.DOTALL)
    assert match is not None, (
        "NamedTemporaryFile must be called with dir= kwarg (Pitfall 2)"
    )


def test_config_no_threading_timer_import():
    src = _config_src()
    assert "threading.Timer" not in src
    assert "from threading import Timer" not in src


def test_config_does_not_call_state_set():
    """Pitfall 8 — ConfigWriter is a read-only observer."""
    src = _config_src()
    assert "state.set_" not in src
    assert "self._state.set_" not in src


def test_config_no_os_access_w_ok():
    src = _config_src()
    assert "os.access" not in src
