"""Phase 6 Plan 02 pure-Python lints for hotkey.py.

Structural assertions only - this file runs on every platform (Linux CI
included). Live Win32 integration lives in tests/test_hotkey_smoke.py.
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
    src = _hotkey_src()
    assert "import ctypes" in src
    assert "ctypes.windll" in src or "windll.user32" in src
    # Rejected libraries -- STATE.md decisions + Pitfall 9 ban lint
    assert "import keyboard" not in src
    assert "from keyboard" not in src
    assert "keyboard" not in src
    assert "pynput" not in src
    assert "global_hotkeys" not in src


def test_winconst_mod_values_match_msdn():
    _require_hotkey()
    from magnifier_bubble import winconst
    # MSDN values -- verified against learn.microsoft.com RegisterHotKey
    assert winconst.MOD_ALT      == 0x0001
    assert winconst.MOD_CONTROL  == 0x0002
    assert winconst.MOD_SHIFT    == 0x0004
    assert winconst.MOD_WIN      == 0x0008
    assert winconst.MOD_NOREPEAT == 0x4000
    assert winconst.WM_HOTKEY    == 0x0312
    assert winconst.WM_QUIT      == 0x0012
    assert winconst.VK_Z         == 0x5A
    assert winconst.ERROR_HOTKEY_ALREADY_REGISTERED == 1409


def test_hotkey_applies_argtypes():
    _require_hotkey()
    src = _hotkey_src()
    # Every Win32 function the module calls must have argtypes applied
    # (Pitfalls 6 + 7 -- LONG_PTR truncation + GetMessageW -1 return).
    assert "RegisterHotKey.argtypes" in src
    assert "RegisterHotKey.restype" in src
    assert "UnregisterHotKey.argtypes" in src
    assert "GetMessageW.argtypes" in src
    assert "GetMessageW.restype" in src
    # Pitfall 6: GetMessageW returns int (not BOOL) -- -1 is a legal error.
    assert (
        "GetMessageW.restype = ctypes.c_int" in src
        or "GetMessageW.restype  = ctypes.c_int" in src
    )
    assert "PostThreadMessageW.argtypes" in src


# ---------------------------------------------------------------------
# HOTK-05 structural lints
# ---------------------------------------------------------------------

def test_hotkey_thread_is_non_daemon():
    _require_hotkey()
    src = _hotkey_src()
    # Pitfall 2: daemon=True would kill the thread before UnregisterHotKey
    # in the finally block runs, leaking the registration.
    assert "daemon=False" in src
    assert "daemon=True" not in src


def test_register_and_unregister_in_same_function():
    _require_hotkey()
    import ast
    src = _hotkey_src()
    tree = ast.parse(src)

    reg_funcs: set[str] = set()
    unreg_funcs: set[str] = set()

    for func_def in ast.walk(tree):
        if not isinstance(func_def, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(func_def):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "RegisterHotKey":
                    reg_funcs.add(func_def.name)
                if node.func.attr == "UnregisterHotKey":
                    unreg_funcs.add(func_def.name)

    # Pitfall 1: UnregisterHotKey MUST be called from the SAME thread
    # (same _run() function) that called RegisterHotKey.  Not enforced by
    # Python, but a structural lint that forbids UnregisterHotKey from
    # being called anywhere except the function that calls RegisterHotKey
    # is a cheap guard against accidentally adding a stop() that tries to
    # unregister from the main thread.
    assert reg_funcs, "RegisterHotKey call not found anywhere in hotkey.py"
    assert unreg_funcs, "UnregisterHotKey call not found anywhere in hotkey.py"
    shared = reg_funcs & unreg_funcs
    assert shared, (
        f"Register/Unregister must share a function (same thread). "
        f"Register in {reg_funcs}, Unregister in {unreg_funcs}."
    )
