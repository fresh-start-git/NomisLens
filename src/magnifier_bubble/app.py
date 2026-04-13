"""Ultimate Zoom - Phase 2 entry point.

Replaces the Phase 1 scaffold body: we now construct a BubbleWindow and
drive the Tk mainloop. main.py's first-line DPI call (OVER-05) is still
the caller; this file does NOT touch DPI.

Phase 4 Plan 03 additions:
- argparse for --no-click-injection (falls back to Phase 2 behavior
  when PostMessageW injection misbehaves against a target — e.g.
  Cornerstone, per research Open Question #1).

Smoke test escape hatch: if ULTIMATE_ZOOM_SMOKE=1 is set in the
environment, we schedule root.after(50, bubble.destroy) so the process
exits cleanly within ~100 ms. This keeps the Phase 1 test_main_entry.py
subprocess smoke tests runnable without a human having to close the
window. The normal interactive path (no env var) runs mainloop until
the user closes the bubble.
"""
from __future__ import annotations

import argparse
import os

from magnifier_bubble import dpi
from magnifier_bubble.state import AppState, StateSnapshot
from magnifier_bubble.window import BubbleWindow


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ultimate Zoom - floating magnifier bubble"
    )
    parser.add_argument(
        "--no-click-injection",
        action="store_true",
        help=(
            "Disable cross-process click injection. Middle-zone clicks "
            "will be consumed by the bubble (Phase 2 fallback behavior). "
            "Use if PostMessageW injection misbehaves against Cornerstone."
        ),
    )
    args = parser.parse_args()

    # Observable proof that PMv2 survived the Phase 2 Tk + ctypes imports.
    dpi.debug_print()

    # Phase 1 criterion 4: AppState is still the single source of truth.
    state = AppState(StateSnapshot())

    # Phase 2: create the bubble and drive the Tk event loop.
    # Phase 4 Plan 03: click_injection_enabled is wired from the CLI flag.
    bubble = BubbleWindow(
        state,
        click_injection_enabled=not args.no_click_injection,
    )
    print(
        f"[bubble] hwnd={bubble._hwnd} "
        f"geometry={state.snapshot().w}x{state.snapshot().h}"
        f"+{state.snapshot().x}+{state.snapshot().y} "
        f"shape={state.snapshot().shape} "
        f"click_injection={bubble._click_injection_enabled}"
    )

    # Phase 3: start the 30 fps capture producer thread.
    # (Does nothing on non-Windows because CaptureWorker.run()'s
    # `import mss` will fail — we gate by sys.platform to avoid a
    # confusing ModuleNotFoundError on CI / non-Windows dev machines.)
    import sys as _sys
    if _sys.platform == "win32":
        bubble.start_capture()

    if os.environ.get("ULTIMATE_ZOOM_SMOKE") == "1":
        # Non-interactive smoke: tear down after 50 ms so the subprocess
        # exits cleanly for CI / test_main_entry.py.
        bubble.root.after(50, bubble.destroy)

    bubble.root.mainloop()
    print("[app] phase 2 mainloop exited; goodbye")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
