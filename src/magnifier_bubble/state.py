"""AppState — single source of truth for Ultimate Zoom.

INVARIANT: All writes must come from the Tk main thread.
Worker threads mutate via ``root.after(0, state.set_*)``.
Readers may call from any thread (lock-protected snapshot).

This module has ZERO third-party dependencies — stdlib only.
Do NOT import mss, tkinter, PIL, or pywin32 here; those imports must
happen after main.py has set SetProcessDpiAwarenessContext(-4).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import Lock
from typing import Callable

Shape = str  # "circle" | "rounded" | "rect" — stringly-typed for JSON-compat


@dataclass
class StateSnapshot:
    """Value snapshot of AppState. Mutable, but passed by copy out of AppState."""
    x: int = 200
    y: int = 200
    w: int = 400
    h: int = 400
    zoom: float = 2.0
    shape: Shape = "rect"
    visible: bool = True
    always_on_top: bool = True


_VALID_SHAPES = ("circle", "rounded", "rect")
_ZOOM_MIN = 1.5
_ZOOM_MAX = 6.0
_ZOOM_STEP = 0.25


def _clamp_zoom(z: float) -> float:
    """Clamp to [1.5, 6.0] and snap to 0.25 increments."""
    z = max(_ZOOM_MIN, min(_ZOOM_MAX, z))
    return round(z / _ZOOM_STEP) * _ZOOM_STEP


class AppState:
    """Thread-safe container for app state with synchronous observer list."""

    def __init__(self, initial: StateSnapshot | None = None) -> None:
        self._lock = Lock()
        self._snap = initial if initial is not None else StateSnapshot()
        self._observers: list[Callable[[], None]] = []

    # --- observer registration ---
    def on_change(self, cb: Callable[[], None]) -> None:
        self._observers.append(cb)

    def _notify(self) -> None:
        for cb in list(self._observers):  # copy so observer-mutates-list is safe
            cb()

    # --- thread-safe reads ---
    def snapshot(self) -> StateSnapshot:
        with self._lock:
            return StateSnapshot(**asdict(self._snap))

    def capture_region(self) -> tuple[int, int, int, int, float]:
        with self._lock:
            s = self._snap
            return (s.x, s.y, s.w, s.h, s.zoom)

    # --- writers (Tk main thread only) ---
    def set_position(self, x: int, y: int) -> None:
        with self._lock:
            self._snap.x = x
            self._snap.y = y
        self._notify()

    def set_size(self, w: int, h: int) -> None:
        with self._lock:
            self._snap.w = w
            self._snap.h = h
        self._notify()

    def set_zoom(self, zoom: float) -> None:
        z = _clamp_zoom(float(zoom))
        with self._lock:
            self._snap.zoom = z
        self._notify()

    def set_shape(self, shape: Shape) -> None:
        if shape not in _VALID_SHAPES:
            raise ValueError(
                f"invalid shape: {shape!r} (expected one of {_VALID_SHAPES})"
            )
        with self._lock:
            self._snap.shape = shape
        self._notify()

    def set_visible(self, visible: bool) -> None:
        with self._lock:
            self._snap.visible = bool(visible)
        self._notify()

    def toggle_visible(self) -> None:
        with self._lock:
            self._snap.visible = not self._snap.visible
        self._notify()

    def toggle_aot(self) -> None:
        with self._lock:
            self._snap.always_on_top = not self._snap.always_on_top
        self._notify()
