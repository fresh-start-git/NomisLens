---
phase: 01-foundation-dpi
plan: 02
type: execute
wave: 2
depends_on: ["01-foundation-dpi/01"]
files_modified:
  - src/magnifier_bubble/state.py
  - src/magnifier_bubble/dpi.py
  - tests/test_state.py
  - tests/test_dpi.py
autonomous: true
requirements: [OVER-05]
must_haves:
  truths:
    - "AppState holds x, y, w, h, zoom, shape, visible, always_on_top and is the ONLY place those values mutate"
    - "AppState setter calls fire registered observers synchronously"
    - "AppState.set_zoom clamps to [1.5, 6.0] and snaps to 0.25 steps"
    - "AppState.set_shape rejects values outside {'circle', 'rounded', 'rect'}"
    - "AppState.capture_region returns a (x, y, w, h, zoom) tuple safe for cross-thread reads"
    - "dpi.report() returns logical_w, logical_h, physical_w, physical_h, dpi, scale_pct, context_is_pmv2 keys"
    - "dpi.debug_print() writes one line to stdout that satisfies Phase 1 Criterion #5 (visible proof of PMv2 scale on 150% displays)"
    - "dpi.is_pmv2_active() returns a bool using AreDpiAwarenessContextsEqual (not pointer identity)"
    - "pytest tests/test_state.py tests/test_dpi.py both exit 0"
  artifacts:
    - path: src/magnifier_bubble/state.py
      provides: "Thread-safe AppState single-source-of-truth container with dataclass snapshot + observers"
      contains: "class AppState"
      min_lines: 60
    - path: src/magnifier_bubble/dpi.py
      provides: "DPI helpers: is_pmv2_active, report, debug_print + sentinel constants"
      contains: "def report"
      min_lines: 40
    - path: tests/test_state.py
      provides: "pytest unit tests for AppState snapshot, observer, zoom clamp, shape validation, capture_region, toggle_visible"
      contains: "def test_zoom_clamps_to_range"
      min_lines: 50
    - path: tests/test_dpi.py
      provides: "pytest unit tests for dpi.report keys, positive dims, scale_pct math, pmv2 check"
      contains: "def test_dpi_report_has_required_keys"
      min_lines: 30
  key_links:
    - from: tests/test_state.py
      to: src/magnifier_bubble/state.py
      via: "from magnifier_bubble.state import AppState, StateSnapshot"
      pattern: "from magnifier_bubble\\.state import"
    - from: tests/test_dpi.py
      to: src/magnifier_bubble/dpi.py
      via: "from magnifier_bubble import dpi"
      pattern: "from magnifier_bubble import dpi"
    - from: src/magnifier_bubble/state.py
      to: "(no other module)"
      via: "stdlib only: dataclasses, threading, typing"
      pattern: "from dataclasses import"
    - from: src/magnifier_bubble/dpi.py
      to: "(no other module)"
      via: "stdlib only: ctypes, typing"
      pattern: "import ctypes"
---

<objective>
Build the two load-bearing Python modules that Phase 1 requires: `state.py` (AppState container, Success Criterion #4) and `dpi.py` (DPI report + debug print, Success Criterion #5). Both ship with TDD pytest suites that run in <2 seconds and satisfy VALIDATION.md Wave 1 checks `pytest tests/test_state.py` and `pytest tests/test_dpi.py`.

Purpose: Every downstream phase depends on these two modules. Phase 3 CaptureWorker will read `state.capture_region()` on a background thread. Phase 5 ConfigStore will subscribe to `state.on_change()`. Phase 1 main.py will call `dpi.debug_print()` as the observable proof of PMv2 correctness.

Output: Two production modules and two test files. Tests written first (TDD); each test fails against an empty module, then passes once the module is filled in.
</objective>

<execution_context>
@C:/Users/Jsupport/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/Jsupport/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/01-foundation-dpi/01-RESEARCH.md
@.planning/phases/01-foundation-dpi/01-VALIDATION.md

<interfaces>
<!-- Plan 01 produced: -->
<!--   - src/magnifier_bubble/__init__.py   (empty — DO NOT add imports here) -->
<!--   - src/magnifier_bubble/__main__.py   (imports from magnifier_bubble.app — not yet created, ok) -->
<!--   - tests/__init__.py                   (empty) -->
<!--   - tests/conftest.py                   (defines `win_only` marker) -->
<!--   - pyproject.toml                      (sets pythonpath = ["src"]) -->
<!--   - requirements-dev.txt                (installs pytest) -->

<!-- This plan produces the contracts that plan 03 consumes: -->

```python
# src/magnifier_bubble/state.py
from dataclasses import dataclass
from typing import Callable

Shape = str  # "circle" | "rounded" | "rect"

@dataclass
class StateSnapshot:
    x: int = 200
    y: int = 200
    w: int = 400
    h: int = 400
    zoom: float = 2.0
    shape: Shape = "circle"
    visible: bool = True
    always_on_top: bool = True

class AppState:
    def __init__(self, initial: StateSnapshot | None = None) -> None: ...
    def on_change(self, cb: Callable[[], None]) -> None: ...
    def snapshot(self) -> StateSnapshot: ...
    def capture_region(self) -> tuple[int, int, int, int, float]: ...
    def set_position(self, x: int, y: int) -> None: ...
    def set_size(self, w: int, h: int) -> None: ...
    def set_zoom(self, zoom: float) -> None: ...            # clamps [1.5, 6.0], snaps 0.25
    def set_shape(self, shape: Shape) -> None: ...          # raises ValueError if invalid
    def set_visible(self, visible: bool) -> None: ...
    def toggle_visible(self) -> None: ...
    def toggle_aot(self) -> None: ...
```

```python
# src/magnifier_bubble/dpi.py
from typing import TypedDict

DPI_AWARENESS_CONTEXT_UNAWARE = -1
DPI_AWARENESS_CONTEXT_SYSTEM_AWARE = -2
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE = -3
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
DPI_AWARENESS_CONTEXT_UNAWARE_GDISCALED = -5

class DpiReport(TypedDict):
    logical_w: int
    logical_h: int
    physical_w: int
    physical_h: int
    dpi: int
    scale_pct: int
    context_is_pmv2: bool

def is_pmv2_active() -> bool: ...
def report() -> DpiReport: ...
def debug_print() -> None: ...
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: TDD AppState container (tests/test_state.py + src/magnifier_bubble/state.py)</name>
  <files>tests/test_state.py, src/magnifier_bubble/state.py</files>
  <read_first>
    - .planning/phases/01-foundation-dpi/01-RESEARCH.md (sections: Architecture Patterns > Pattern 2 Single Source of Truth AppState; Code Examples > state.py; Code Examples > tests/test_state.py; Pitfalls > Pitfall 6 Observer called from the wrong thread)
    - src/magnifier_bubble/__init__.py (from plan 01 — confirm it is empty, 0 bytes)
    - tests/conftest.py (from plan 01)
    - .planning/REQUIREMENTS.md (OVER-05, CTRL-05 zoom range 1.5-6.0 in 0.25 steps, CTRL-08 size clamps are Phase 4 concern)
  </read_first>
  <behavior>
    RED cycle — write tests that describe AppState behavior BEFORE implementing it:

    - test_default_snapshot: fresh `AppState()` with no args → snapshot has x=200, y=200, w=400, h=400, zoom=2.0, shape="circle", visible=True, always_on_top=True
    - test_custom_initial_snapshot: `AppState(StateSnapshot(x=10, y=20))` → snapshot.x == 10, snapshot.y == 20, other fields default
    - test_set_position_fires_observer: register observer, call set_position(123, 456) → observer called exactly once, snapshot.x == 123, snapshot.y == 456
    - test_set_size_fires_observer: observer called, snapshot reflects new w, h
    - test_set_zoom_fires_observer_and_clamps: set_zoom(2.5) → zoom == 2.5; set_zoom(10.0) → zoom == 6.0 (clamped high); set_zoom(0.1) → zoom == 1.5 (clamped low)
    - test_zoom_snaps_to_quarter_steps: set_zoom(2.37) → zoom == 2.25; set_zoom(2.49) → zoom == 2.5; set_zoom(3.874) → zoom == 3.75
    - test_set_shape_valid_values: set_shape("circle"), set_shape("rounded"), set_shape("rect") all succeed
    - test_set_shape_invalid_raises: set_shape("triangle") raises ValueError with "triangle" in the message
    - test_set_visible_fires_observer: set_visible(False) → visible False, observer called
    - test_toggle_visible_flips: start visible True, toggle → False, toggle → True; each call fires observer once
    - test_toggle_aot_flips: start always_on_top True, toggle → False, toggle → True
    - test_capture_region_returns_tuple: set_position(50, 60); set_size(300, 200); set_zoom(3.0); capture_region() == (50, 60, 300, 200, 3.0) exactly
    - test_snapshot_is_independent_copy: snap = state.snapshot(); mutate snap.x directly; state.snapshot().x is unchanged (snapshot returns a COPY, not a reference)
    - test_multiple_observers_all_fire: register 3 observers; set_position → all 3 called exactly once
  </behavior>
  <action>
    **RED step — write the failing tests first:**

    Create `tests/test_state.py` with exactly the 14 test functions described in `<behavior>` above. Use this structure:

```python
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
    assert snap.shape == "circle"
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
```

    Run `python -m pytest tests/test_state.py -x -q` — it MUST fail with `ModuleNotFoundError: magnifier_bubble.state` (RED confirmed).

    **GREEN step — create `src/magnifier_bubble/state.py`:**

```python
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
    shape: Shape = "circle"
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
```

    Run `python -m pytest tests/test_state.py -x -q` — it MUST now pass with 14 passing tests (GREEN confirmed).

    **Commit convention:** Two commits — first the failing test, then the passing implementation:
    - `test(01-02): add failing tests for AppState`
    - `feat(01-02): implement AppState container`

    Do NOT use `RLock` (Lock is sufficient per research §Open Questions #3).
    Do NOT add observer-unsubscribe API — YAGNI for Phase 1.
    Do NOT add JSON serialization — that's Phase 5 (PERS-01..04).
    Do NOT import anything from `magnifier_bubble.*` other modules — state.py is leaf-level.
  </action>
  <verify>
    <automated>python -m pytest tests/test_state.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `src/magnifier_bubble/state.py` exists
    - `src/magnifier_bubble/state.py` contains `class AppState`
    - `src/magnifier_bubble/state.py` contains `class StateSnapshot`
    - `src/magnifier_bubble/state.py` contains `from threading import Lock`
    - `src/magnifier_bubble/state.py` contains `from dataclasses import`
    - `src/magnifier_bubble/state.py` does NOT contain `import mss`
    - `src/magnifier_bubble/state.py` does NOT contain `import tkinter`
    - `src/magnifier_bubble/state.py` does NOT contain `import PIL`
    - `src/magnifier_bubble/state.py` does NOT contain `import win32` or `pywin32`
    - `tests/test_state.py` exists with at least 14 `def test_` functions (`grep -c '^def test_' tests/test_state.py` returns `>= 14` — noting parametrize counts as 1 def)
    - `tests/test_state.py` contains `from magnifier_bubble.state import AppState, StateSnapshot`
    - `tests/test_state.py` contains literal `def test_zoom_snaps_to_quarter_steps`
    - `tests/test_state.py` contains literal `def test_set_shape_invalid_raises`
    - `tests/test_state.py` contains literal `def test_capture_region_returns_tuple`
    - `python -m pytest tests/test_state.py -x -q` exits 0
    - `python -m pytest tests/test_state.py -v` reports at least 16 passed (14 test functions, with `test_set_shape_valid_values` parametrized over 3 shapes = 3 tests → 14 - 1 + 3 = 16)
  </acceptance_criteria>
  <done>
    `python -m pytest tests/test_state.py -v` shows all tests passing (≥16 passed). AppState holds every Phase 1 Criterion #4 field (x, y, w, h, zoom, shape, visible) plus always_on_top for Phase 7. Two commits in git log: one test-first RED, one feat-implementation GREEN.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: TDD DPI helper module (tests/test_dpi.py + src/magnifier_bubble/dpi.py)</name>
  <files>tests/test_dpi.py, src/magnifier_bubble/dpi.py</files>
  <read_first>
    - .planning/phases/01-foundation-dpi/01-RESEARCH.md (sections: Standard Stack > DPI API; Architecture Patterns > Pattern 3 DPI Verification Module; Common Pitfalls > Pitfall 1 Late DPI Awareness, Pitfall 3 Verifying without 150% display; Code Examples > dpi.py, tests/test_dpi.py)
    - .planning/REQUIREMENTS.md (OVER-05)
    - tests/conftest.py (provides `win_only` marker)
    - src/magnifier_bubble/state.py (from task 1 — confirms package layout works)
  </read_first>
  <behavior>
    RED cycle — write tests describing dpi.py behavior:

    - test_module_constants_exist: DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == -4, and the other four sentinel constants exist with values -1, -2, -3, -5
    - test_dpi_report_has_required_keys (Windows only): dpi.report() returns dict with keys logical_w, logical_h, physical_w, physical_h, dpi, scale_pct, context_is_pmv2
    - test_dpi_positive_dimensions (Windows only): logical_w > 0, logical_h > 0, dpi >= 96
    - test_scale_pct_matches_dpi (Windows only): scale_pct == dpi * 100 // 96
    - test_context_is_pmv2_returns_bool (Windows only): type(r["context_is_pmv2"]) is bool
    - test_is_pmv2_active_returns_bool (Windows only): is_pmv2_active() returns a bool
    - test_debug_print_writes_expected_format (Windows only, captured stdout): debug_print() output contains literal substrings "[dpi]", "pmv2=", "dpi=", "scale=", "logical=", "physical="
    - test_module_importable_without_running_dpi_init: `import magnifier_bubble.dpi` does NOT call SetProcessDpiAwarenessContext (verify by checking module has no init side effects — the import itself should be pure)
  </behavior>
  <action>
    **RED step — `tests/test_dpi.py`:**

```python
"""Unit tests for magnifier_bubble.dpi — DPI helper module.

Most tests require Windows (DPI APIs only exist on win32). The
`test_module_constants_exist` test runs on any platform because it
only inspects module-level constants.
"""
from __future__ import annotations

import io
import sys

import pytest

from magnifier_bubble import dpi

# Shortcut — matches conftest.py `win_only` marker
win_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")


def test_module_constants_exist():
    assert dpi.DPI_AWARENESS_CONTEXT_UNAWARE == -1
    assert dpi.DPI_AWARENESS_CONTEXT_SYSTEM_AWARE == -2
    assert dpi.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE == -3
    assert dpi.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == -4
    assert dpi.DPI_AWARENESS_CONTEXT_UNAWARE_GDISCALED == -5


def test_module_importable_without_side_effects():
    # Re-importing must not raise; module must be pure (no DPI init at import time).
    import importlib
    import magnifier_bubble.dpi as d2
    importlib.reload(d2)
    # If the module set DPI awareness at import time, reload would raise
    # ERROR_ACCESS_DENIED on the second call. Reaching here proves it's pure.


@win_only
def test_dpi_report_has_required_keys():
    r = dpi.report()
    for k in (
        "logical_w",
        "logical_h",
        "physical_w",
        "physical_h",
        "dpi",
        "scale_pct",
        "context_is_pmv2",
    ):
        assert k in r, f"missing key: {k}"


@win_only
def test_dpi_positive_dimensions():
    r = dpi.report()
    assert r["logical_w"] > 0
    assert r["logical_h"] > 0
    assert r["physical_w"] > 0
    assert r["physical_h"] > 0
    assert r["dpi"] >= 96


@win_only
def test_scale_pct_matches_dpi():
    r = dpi.report()
    assert r["scale_pct"] == r["dpi"] * 100 // 96


@win_only
def test_context_is_pmv2_returns_bool():
    r = dpi.report()
    assert isinstance(r["context_is_pmv2"], bool)


@win_only
def test_is_pmv2_active_returns_bool():
    assert isinstance(dpi.is_pmv2_active(), bool)


@win_only
def test_debug_print_writes_expected_format(capsys):
    dpi.debug_print()
    out = capsys.readouterr().out
    assert "[dpi]" in out
    assert "pmv2=" in out
    assert "dpi=" in out
    assert "scale=" in out
    assert "logical=" in out
    assert "physical=" in out
```

    Run `python -m pytest tests/test_dpi.py -x -q` — it MUST fail with `ModuleNotFoundError: magnifier_bubble.dpi` (RED confirmed).

    **GREEN step — `src/magnifier_bubble/dpi.py`:**

```python
"""DPI helpers for Ultimate Zoom.

This module is SAFE to import from anywhere — it does NOT call
SetProcessDpiAwarenessContext at import time. That call lives in
main.py (the first executable line), where it must be in order to
satisfy OVER-05 before any tkinter/mss/PIL import.

Exports:
    DPI_AWARENESS_CONTEXT_*      sentinel handle values (-1..-5)
    is_pmv2_active()             bool — is the current thread's DPI context PMv2?
    report()                     DpiReport — full logical/physical/scale cross-check
    debug_print()                print one line to stdout summarizing report()

Per-Monitor-V2 debugging (Phase 1 Success Criterion #5):
    On a 150%-scaled display, `debug_print()` should print a line like:
        [dpi] pmv2=True dpi=144 scale=150% logical=1920x1080 physical=1920x1080
    Under PMv2, logical and physical agree (both are physical pixels).
    Under V1 or System-aware, logical may equal physical * (96/dpi) and
    this mismatch is the smoking gun that DPI init failed.
"""
from __future__ import annotations

import ctypes
import sys
from typing import TypedDict

# Sentinel DPI_AWARENESS_CONTEXT handles from Windows <windef.h>.
# These are *negative integers* on the wire, interpreted as handles.
DPI_AWARENESS_CONTEXT_UNAWARE = -1
DPI_AWARENESS_CONTEXT_SYSTEM_AWARE = -2
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE = -3
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
DPI_AWARENESS_CONTEXT_UNAWARE_GDISCALED = -5

# GetSystemMetrics indices
SM_CXSCREEN = 0
SM_CYSCREEN = 1

USER_DEFAULT_SCREEN_DPI = 96


class DpiReport(TypedDict):
    logical_w: int
    logical_h: int
    physical_w: int
    physical_h: int
    dpi: int
    scale_pct: int
    context_is_pmv2: bool


def _u32():
    """Lazy access to user32 — avoids any side effects at module import.

    On non-Windows, ctypes.windll does not exist and accessing it would
    raise AttributeError. All callers of _u32() guard with sys.platform.
    """
    return ctypes.windll.user32  # type: ignore[attr-defined]


def is_pmv2_active() -> bool:
    """Returns True iff the calling thread's DPI context equals PMv2.

    Uses AreDpiAwarenessContextsEqual (not pointer identity) because
    Windows may return different handle wrappers for the same context.
    """
    if sys.platform != "win32":
        return False
    try:
        u32 = _u32()
        cur = u32.GetThreadDpiAwarenessContext()
        # AreDpiAwarenessContextsEqual takes two handles; we cast -4 to handle.
        return bool(u32.AreDpiAwarenessContextsEqual(
            cur, DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        ))
    except (AttributeError, OSError):
        return False


def report() -> DpiReport:
    """Collect logical + physical + DPI + scale_pct + PMv2 flag.

    Windows-only. Raises on non-Windows (callers should guard).
    """
    u32 = _u32()
    logical_w = int(u32.GetSystemMetrics(SM_CXSCREEN))
    logical_h = int(u32.GetSystemMetrics(SM_CYSCREEN))
    dpi_val = int(u32.GetDpiForSystem())
    physical_w = int(u32.GetSystemMetricsForDpi(SM_CXSCREEN, dpi_val))
    physical_h = int(u32.GetSystemMetricsForDpi(SM_CYSCREEN, dpi_val))
    return DpiReport(
        logical_w=logical_w,
        logical_h=logical_h,
        physical_w=physical_w,
        physical_h=physical_h,
        dpi=dpi_val,
        scale_pct=dpi_val * 100 // USER_DEFAULT_SCREEN_DPI,
        context_is_pmv2=is_pmv2_active(),
    )


def debug_print() -> None:
    """Print one line summarizing the DPI report.

    Satisfies Phase 1 Success Criterion #5 as an observable proof that
    PMv2 is active on the running display. Compare the printed physical
    dimensions against Windows Settings → Display to validate 150% scale.
    """
    r = report()
    print(
        f"[dpi] pmv2={r['context_is_pmv2']} "
        f"dpi={r['dpi']} scale={r['scale_pct']}% "
        f"logical={r['logical_w']}x{r['logical_h']} "
        f"physical={r['physical_w']}x{r['physical_h']}"
    )
```

    Run `python -m pytest tests/test_dpi.py -x -q` — it MUST now pass (all 8 tests; on non-Windows, 6 of 8 will be skipped via `win_only`, leaving 2 passing).

    **Commit convention:**
    - `test(01-02): add failing tests for dpi module`
    - `feat(01-02): implement dpi report + debug_print helpers`

    Do NOT call `SetProcessDpiAwarenessContext` inside `dpi.py` — that is main.py's job (see research Pattern 3 "Caveat").
    Do NOT import `win32api` or `pywin32` — use `ctypes` directly (research §Standard Stack).
    Do NOT add a `init()` function in Phase 1 (YAGNI; main.py has its own ctypes call).
    Do NOT log to stderr or use `logging` — plain `print` to stdout matches VALIDATION.md grep for "physical".
  </action>
  <verify>
    <automated>python -m pytest tests/test_dpi.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `src/magnifier_bubble/dpi.py` exists
    - `src/magnifier_bubble/dpi.py` contains `import ctypes`
    - `src/magnifier_bubble/dpi.py` contains `DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4`
    - `src/magnifier_bubble/dpi.py` contains `def is_pmv2_active()`
    - `src/magnifier_bubble/dpi.py` contains `def report()`
    - `src/magnifier_bubble/dpi.py` contains `def debug_print()`
    - `src/magnifier_bubble/dpi.py` contains `class DpiReport(TypedDict)`
    - `src/magnifier_bubble/dpi.py` does NOT contain `SetProcessDpiAwarenessContext` as a function CALL (grep for the literal call with parentheses `SetProcessDpiAwarenessContext(` returns 0 matches — this is load-bearing; the DPI init must live in main.py per Pattern 1)
    - `src/magnifier_bubble/dpi.py` does NOT contain `import win32api` or `import pywin32`
    - `src/magnifier_bubble/dpi.py` does NOT contain `import mss`
    - `src/magnifier_bubble/dpi.py` does NOT contain `import tkinter`
    - `src/magnifier_bubble/dpi.py` uses `AreDpiAwarenessContextsEqual` for the PMv2 check
    - `src/magnifier_bubble/dpi.py` calls `GetDpiForSystem` and `GetSystemMetricsForDpi`
    - `src/magnifier_bubble/dpi.py` calls `print(` in `debug_print` with `[dpi]` literal
    - `tests/test_dpi.py` exists
    - `tests/test_dpi.py` contains `from magnifier_bubble import dpi`
    - `tests/test_dpi.py` contains at least 8 `def test_` functions
    - `tests/test_dpi.py` uses `@win_only` or `pytestmark = pytest.mark.skipif(sys.platform != "win32"` on Windows-dependent tests
    - `python -m pytest tests/test_dpi.py -x -q` exits 0
    - On Windows, running the test file reports 8 passed, 0 skipped; on non-Windows, reports 2 passed, 6 skipped
  </acceptance_criteria>
  <done>
    `python -m pytest tests/test_dpi.py -v` passes. `dpi.debug_print()` prints a single-line report with the format `[dpi] pmv2=<bool> dpi=<int> scale=<int>% logical=<w>x<h> physical=<w>x<h>`. The module has NO import-time side effects, proving it's safe to import from app.py in plan 03 without triggering a DPI awareness call.
  </done>
</task>

</tasks>

<verification>
After both tasks, run the combined pytest suite:

1. `python -m pytest tests/test_state.py tests/test_dpi.py -v`
   Expected: All state tests pass (≥16), all dpi tests pass on Windows (8 passed) or mixed (2 passed + 6 skipped) on non-Windows.

2. `python -c "import sys; sys.path.insert(0,'src'); import magnifier_bubble.state, magnifier_bubble.dpi; print('OK')"`
   Expected: prints `OK` — both modules import cleanly with no errors.

3. Confirm `dpi.py` is safe to import (no DPI init at import time):
   `python -c "import sys; sys.path.insert(0,'src'); import magnifier_bubble.dpi; import magnifier_bubble.dpi"` (import twice)
   Expected: no error on second import — proves the module is idempotent and did not mutate process-wide DPI state.

4. Confirm `state.py` has zero third-party deps:
   `grep -E "^(import|from) " src/magnifier_bubble/state.py | grep -vE "^(from __future__|from dataclasses|from threading|from typing)"`
   Expected: 0 lines (only stdlib imports).
</verification>

<success_criteria>
- `pytest tests/test_state.py tests/test_dpi.py -v` green: ≥16 passed for state + (8 on win32 / 2 + 6 skipped elsewhere) for dpi
- `magnifier_bubble.state` and `magnifier_bubble.dpi` both importable via the src-layout pythonpath set in plan 01's pyproject.toml
- Neither module has import-time side effects (neither sets DPI awareness, neither imports mss/tkinter/PIL)
- AppState fields exactly match Phase 1 Success Criterion #4: x, y, w, h, zoom, shape, visible (plus always_on_top for Phase 7)
- dpi.debug_print() produces the exact line format that VALIDATION.md grep ("physical") will match
- Two clean TDD commit pairs in git log (test + feat for each of state, dpi)
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundation-dpi/01-02-SUMMARY.md` summarizing:
- Test counts (state: N passed; dpi: N passed / M skipped)
- Any deviation from the research.md code examples (note why)
- Example output line from running `python -c "from magnifier_bubble.dpi import debug_print; debug_print()"`
- Line counts for state.py and dpi.py (should both be under ~150 lines)
</output>
