"""Phase 8 Plan 01 pure-Python lints for tray.py.

Structural assertions only — runs on every platform (Linux CI included).
Live Win32 integration lives in tests/test_tray_smoke.py.
"""
from __future__ import annotations

import pathlib
import pytest

_TRAY_SRC_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "magnifier_bubble" / "tray.py"
)
_WINDOW_SRC_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "magnifier_bubble" / "window.py"
)
_APP_SRC_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "magnifier_bubble" / "app.py"
)


def _require_tray():
    if not _TRAY_SRC_PATH.exists():
        pytest.skip("tray.py not yet implemented (pending Plan 08-01)")
    try:
        from magnifier_bubble import tray  # noqa: F401
    except ImportError:
        pytest.skip("tray.py import failed (pending Plan 08-01)")


def _tray_src() -> str:
    return _TRAY_SRC_PATH.read_text(encoding="utf-8")


def _window_src() -> str:
    return _WINDOW_SRC_PATH.read_text(encoding="utf-8")


def _app_src() -> str:
    return _APP_SRC_PATH.read_text(encoding="utf-8")


def test_tray_src_exists():
    assert _TRAY_SRC_PATH.exists(), "src/magnifier_bubble/tray.py must exist"


def test_tray_uses_pystray():
    _require_tray()
    src = _tray_src()
    assert "pystray" in src


def test_tray_menu_items_present():
    _require_tray()
    src = _tray_src()
    assert "Show" in src
    assert "Always on Top" in src
    assert "Exit" in src


def test_tray_showHide_is_default():
    _require_tray()
    src = _tray_src()
    assert "default=True" in src


def test_tray_callbacks_use_root_after():
    _require_tray()
    src = _tray_src()
    assert "self._root.after(0," in src
    assert "root.destroy()" not in src
    assert "root.withdraw()" not in src
    assert "root.deiconify()" not in src


def test_tray_thread_is_non_daemon():
    _require_tray()
    src = _tray_src()
    assert "daemon=False" in src
    assert "daemon=True" not in src


def test_tray_stop_before_destroy_ordering():
    src = _window_src()
    stop_pos = src.find("tray_manager.stop()")
    destroy_pos = src.find("root.destroy()")
    assert stop_pos != -1, "tray_manager.stop() not found in window.py"
    assert destroy_pos != -1, "root.destroy() not found in window.py"
    assert stop_pos < destroy_pos, (
        f"tray_manager.stop() (pos {stop_pos}) must appear before "
        f"root.destroy() (pos {destroy_pos}) in window.py"
    )


def test_tray_no_module_level_pystray_in_window():
    import ast
    src = _window_src()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "pystray" not in alias.name, (
                        "pystray must not be imported at window.py module scope"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert "pystray" not in node.module, (
                        "pystray must not be imported at window.py module scope"
                    )


def test_tray_no_module_level_pystray_in_app():
    src = _app_src()
    pre_platform_check = src.split("if sys.platform")[0]
    assert "import pystray" not in pre_platform_check, (
        "pystray import must be inside 'if sys.platform' block in app.py"
    )
