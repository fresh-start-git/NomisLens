"""Phase 5: Config Persistence.

Debounced atomic writer for Ultimate Zoom's position/size/zoom/shape state.
Stdlib-only. Main-thread-only for the ConfigWriter. No ctypes, no threads,
no new dependencies. See .planning/phases/05-config-persistence/05-RESEARCH.md
for the pattern rationale (Patterns 1-4) and pitfall mitigations (1-10).

Structural invariants enforced by tests/test_config.py:
  - The POSIX atomic-replace call (NOT the non-atomic rename) is used.
  - Disk-flush is ordered BEFORE the atomic-replace call.
  - tempfile.NamedTemporaryFile is invoked with the dir= kwarg so
    the staging file lives on the same volume as the target.
  - No background-thread timer is used (the Tk after() primitive is
    the debounce mechanism — single-thread, cancelable).
  - ConfigWriter never invokes a state mutator method (read-only
    observer — prevents infinite notify loop, Pitfall 8).
  - The Windows-unreliable W_OK probe is NOT used; we probe by
    actually creating and removing a file.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from magnifier_bubble.state import AppState, StateSnapshot

if TYPE_CHECKING:
    import tkinter as tk  # noqa: F401 — type-only import


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_APP_NAME: str = "UltimateZoom"
_CONFIG_FILENAME: str = "config.json"
_DEBOUNCE_MS: int = 500
_SCHEMA_VERSION: int = 1
_PERSISTED_FIELDS: tuple[str, ...] = ("x", "y", "w", "h", "zoom", "shape")
_VALID_SHAPES: tuple[str, ...] = ("circle", "rounded", "rect")
_ZOOM_MIN: float = 1.5
_ZOOM_MAX: float = 6.0
_ZOOM_STEP: float = 0.25
_SIZE_MIN: int = 150
_SIZE_MAX: int = 700


# ---------------------------------------------------------------------------
# Clamp helpers — mirror state.py lines 39-42 so loaded values are pre-valid.
# ---------------------------------------------------------------------------


def _clamp_zoom(z: float) -> float:
    z = max(_ZOOM_MIN, min(_ZOOM_MAX, float(z)))
    return round(z / _ZOOM_STEP) * _ZOOM_STEP


def _clamp_size(n: int | float) -> int:
    return max(_SIZE_MIN, min(_SIZE_MAX, int(n)))


# ---------------------------------------------------------------------------
# Path resolution — Pattern 2.
# ---------------------------------------------------------------------------


def _app_dir() -> Path:
    """Return the directory the app's entry point lives in.

    - Frozen (PyInstaller one-file .exe): parent of sys.executable.
      sys.executable is the .exe itself; dirname(exe) is the folder
      the user put it in. NOT sys._MEIPASS (that's a temp extract — Pitfall 6).
    - Dev mode (python main.py): parent of sys.argv[0], which is
      main.py at the repo root.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(sys.argv[0]).resolve().parent


def _is_writable(directory: Path) -> bool:
    """Probe by creating and immediately removing a tiny test file.

    The W_OK-style probe lies on Windows with ACLs per Python docs;
    an actual write-probe is the only reliable check (Pitfall 10: wrap
    the unlink in try/except because AV scanners may briefly hold
    the file handle).
    """
    if not directory.exists():
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
    probe = directory / ".uz_write_probe"
    try:
        probe.write_text("", encoding="utf-8")
    except OSError:
        return False
    try:
        probe.unlink()
    except OSError:
        pass  # leaked probe is cosmetic (Pitfall 10)
    return True


def config_path() -> Path:
    """Resolve the config.json location.

    1. Try the app directory (PERS-01 primary).
    2. Fall back to %LOCALAPPDATA%\\UltimateZoom\\ if the primary
       is not writable (STATE.md:139 clinic IT lockdown concern).
    3. Last-resort fallback: ~/.UltimateZoom/config.json
       (triggered only if LOCALAPPDATA is unset — Pitfall 5).
    """
    primary = _app_dir() / _CONFIG_FILENAME
    if _is_writable(primary.parent):
        return primary
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / _APP_NAME / _CONFIG_FILENAME
    return Path.home() / f".{_APP_NAME}" / _CONFIG_FILENAME


# ---------------------------------------------------------------------------
# Atomic write — Pattern 1.
# ---------------------------------------------------------------------------


def _to_dict(snap: StateSnapshot) -> dict:
    """Extract the 6 persisted fields ONLY. Never use asdict(snap)
    wholesale — that leaks `visible` / `always_on_top` into the file
    (Pitfall 9)."""
    return {
        "version": _SCHEMA_VERSION,
        "x": int(snap.x),
        "y": int(snap.y),
        "w": int(snap.w),
        "h": int(snap.h),
        "zoom": float(snap.zoom),
        "shape": str(snap.shape),
    }


def write_atomic(path: Path, snap: StateSnapshot) -> None:
    """Atomically write the persisted subset of snap to path.

    tempfile in SAME DIRECTORY (Pitfall 2) -> flush -> fsync (Pitfall 4)
    -> os.replace (Pitfall 3). If anything fails before the replace,
    the target file is untouched. After the replace, the target is
    the new content. There is no observable intermediate state.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    persisted = _to_dict(snap)
    # NamedTemporaryFile MUST be in the target's parent directory
    # so os.replace is same-volume (atomic).
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as tf:
        json.dump(persisted, tf, indent=2, sort_keys=True)
        tf.flush()
        os.fsync(tf.fileno())
        tmp_name = tf.name
    os.replace(tmp_name, str(path))


# ---------------------------------------------------------------------------
# Graceful load — Pattern 4.
# ---------------------------------------------------------------------------


def load(path: Path) -> StateSnapshot:
    """Load a StateSnapshot from path. NEVER raises.

    - Missing file       -> StateSnapshot() defaults, silent.
    - JSONDecodeError    -> StateSnapshot() defaults, logged.
    - Root not a dict    -> StateSnapshot() defaults, logged.
    - Unknown fields     -> ignored.
    - Missing fields     -> filled from StateSnapshot() defaults.
    - Out-of-range vals  -> clamped to valid ranges.
    - Invalid shape      -> default "rect".
    """
    if not path.exists():
        return StateSnapshot()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        print(
            f"[config] corrupt json at path={path} err={exc}; using defaults",
            flush=True,
        )
        return StateSnapshot()
    if not isinstance(raw, dict):
        print(
            f"[config] root is not an object at path={path}; using defaults",
            flush=True,
        )
        return StateSnapshot()
    defaults = StateSnapshot()
    try:
        x = int(raw.get("x", defaults.x))
        y = int(raw.get("y", defaults.y))
        w = _clamp_size(raw.get("w", defaults.w))
        h = _clamp_size(raw.get("h", defaults.h))
        zoom = _clamp_zoom(raw.get("zoom", defaults.zoom))
    except (TypeError, ValueError):
        return defaults
    shape = raw.get("shape", defaults.shape)
    if shape not in _VALID_SHAPES:
        shape = defaults.shape
    return StateSnapshot(x=x, y=y, w=w, h=h, zoom=zoom, shape=shape)


# ---------------------------------------------------------------------------
# Phase 6: Hotkey schema parser (HOTK-04).
# Graceful — NEVER raises, always returns a (modifiers, vk) tuple.
# Not wired into load()'s StateSnapshot contract; Plan 06-03 picks up the
# "hotkey" field from a raw json load in app.py so Phase 5 persistence
# tests stay unchanged.
# ---------------------------------------------------------------------------

from magnifier_bubble.winconst import (
    MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, VK_Z,
)

_MOD_MAP: dict[str, int] = {
    "ctrl":  MOD_CONTROL,
    "alt":   MOD_ALT,
    "shift": MOD_SHIFT,
    "win":   MOD_WIN,
}

_HOTKEY_DEFAULT: tuple[int, int] = (MOD_CONTROL | MOD_ALT, VK_Z)


def parse_hotkey(raw) -> tuple[int, int]:
    """Parse a hotkey config dict -> (modifiers_bitmask, vk_code).

    Never raises.  Unknown modifier -> default.  Non-letter/non-digit vk ->
    default.  Non-dict input -> default.  Case-insensitive modifier names.

    Default: (MOD_CONTROL | MOD_ALT, VK_Z) == Ctrl+Alt+Z.  Avoids collision
    with Cornerstone's Ctrl+Z undo shortcut.
    """
    if not isinstance(raw, dict):
        return _HOTKEY_DEFAULT
    mods = 0
    mod_list = raw.get("modifiers")
    if mod_list is None or not isinstance(mod_list, list):
        return _HOTKEY_DEFAULT
    for name in mod_list:
        bit = _MOD_MAP.get(str(name).lower())
        if bit is None:
            return _HOTKEY_DEFAULT
        mods |= bit
    if mods == 0:
        return _HOTKEY_DEFAULT
    vk_raw = raw.get("vk")
    if vk_raw is None:
        return _HOTKEY_DEFAULT
    vk_raw = str(vk_raw).upper()
    if len(vk_raw) == 1 and "A" <= vk_raw <= "Z":
        return (mods, ord(vk_raw))
    if len(vk_raw) == 1 and "0" <= vk_raw <= "9":
        return (mods, ord(vk_raw))
    return _HOTKEY_DEFAULT


# ---------------------------------------------------------------------------
# Debounced observer — Pattern 3.
# ---------------------------------------------------------------------------


class ConfigWriter:
    """Debounced config persistence observer.

    Registered on AppState.on_change. On every notify, cancels any
    pending after-timer and schedules a fresh 500 ms one (Pitfall 1).
    The timer's callback writes the current snapshot atomically.

    flush_pending() is the shutdown hook: cancels the timer and writes
    synchronously if the current state differs from the last write
    (Pitfall 7).

    This class is READ-ONLY with respect to AppState: it NEVER calls
    the state's set_* writers (Pitfall 8 — infinite observer loop).
    """

    def __init__(self, state: AppState, root: "tk.Tk", path: Path) -> None:
        self._state = state
        self._root = root
        self._path = path
        self._after_id: Optional[str] = None
        self._last_written: Optional[StateSnapshot] = None

    def register(self) -> None:
        self._state.on_change(self._on_change)

    def _on_change(self) -> None:
        """Runs on the Tk main thread. Debounce: cancel any prior
        timer, then schedule a new one for 500 ms out."""
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass  # root may be mid-teardown; best-effort
        self._after_id = self._root.after(_DEBOUNCE_MS, self._write_now)

    def _write_now(self) -> None:
        """Timer callback: serialize current snapshot atomically."""
        self._after_id = None
        snap = self._state.snapshot()
        if snap == self._last_written:
            return
        try:
            write_atomic(self._path, snap)
            self._last_written = snap
        except OSError as exc:
            # Swallow - next change will retry. Log for diagnosis.
            print(
                f"[config] write failed path={self._path} err={exc}",
                flush=True,
            )

    def flush_pending(self) -> None:
        """Called from WM_DELETE_WINDOW (BubbleWindow.destroy).

        Cancels the pending timer (if any) and writes synchronously
        if the state has diverged from the last successful write
        (Pitfall 7: never reschedule via root.after during shutdown).
        Safe to call multiple times. Safe to call if no writes ever
        happened.
        """
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        self._write_now()
