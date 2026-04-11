"""Ultimate Zoom — Phase 1 entry point.

This is the first phase — there is no Tk mainloop yet. The Phase 1 job is
to prove that the DPI-first main.py shim successfully:
  1. Set Per-Monitor-V2 DPI awareness (verified by dpi.debug_print).
  2. Constructed an AppState (verified by a round-trip set+snapshot).
  3. Exited cleanly with code 0.

Later phases replace this body: Phase 2 creates the bubble window here,
Phase 3 kicks off the capture thread, Phase 6 registers the hotkey, etc.
"""
from __future__ import annotations

from magnifier_bubble import dpi
from magnifier_bubble.state import AppState, StateSnapshot


def main() -> int:
    # Phase 1 Criterion 5: observable proof that DPI awareness worked.
    dpi.debug_print()

    # Phase 1 Criterion 4: AppState is the single source of truth.
    state = AppState(StateSnapshot())

    # Smoke: mutate then snapshot to prove the container round-trips.
    state.set_position(300, 400)
    snap = state.snapshot()
    print(
        f"[state] snapshot after set_position(300,400): "
        f"x={snap.x} y={snap.y} w={snap.w} h={snap.h} "
        f"zoom={snap.zoom} shape={snap.shape} "
        f"visible={snap.visible} always_on_top={snap.always_on_top}"
    )

    # Phase 1 has no mainloop — scaffold only. Exit cleanly.
    print("[app] phase 1 scaffold OK; exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
