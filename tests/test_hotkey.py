"""Phase 6 Plan 02 pure-Python lints for hotkey.py.

Wave 0 stubs only. Each test imports magnifier_bubble.hotkey; if the
module is absent (Plan 06-02 not yet run), skip. Otherwise call
pytest.skip("stub pending Plan 06-02 implementation") — Plan 06-02
replaces each skip line with the real assertion body.

All tests here run on every platform (Linux CI included) because they
are structural lints over the module source, not live Win32 calls.
Live integration lives in tests/test_hotkey_smoke.py.
"""
from __future__ import annotations

import pathlib

import pytest


_HOTKEY_SRC_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src" / "magnifier_bubble" / "hotkey.py"
)


def _require_hotkey():
    if not _HOTKEY_SRC_PATH.exists():
        pytest.skip("hotkey.py not yet implemented (pending Plan 06-02)")
    try:
        from magnifier_bubble import hotkey  # noqa: F401
    except ImportError:
        pytest.skip("hotkey.py import failed (pending Plan 06-02)")


def _hotkey_src() -> str:
    return _HOTKEY_SRC_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------
# HOTK-01 structural lints
# ---------------------------------------------------------------------

def test_hotkey_uses_ctypes_not_keyboard_lib():
    _require_hotkey()
    pytest.skip("stub pending Plan 06-02 implementation")

def test_winconst_mod_values_match_msdn():
    _require_hotkey()
    pytest.skip("stub pending Plan 06-02 implementation")

def test_hotkey_applies_argtypes():
    _require_hotkey()
    pytest.skip("stub pending Plan 06-02 implementation")

# ---------------------------------------------------------------------
# HOTK-05 structural lints
# ---------------------------------------------------------------------

def test_hotkey_thread_is_non_daemon():
    _require_hotkey()
    pytest.skip("stub pending Plan 06-02 implementation")

def test_register_and_unregister_in_same_function():
    _require_hotkey()
    pytest.skip("stub pending Plan 06-02 implementation")
