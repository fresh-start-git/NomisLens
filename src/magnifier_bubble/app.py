"""Ultimate Zoom - Phase 2 entry point.

Replaces the Phase 1 scaffold body: we now construct a BubbleWindow and
drive the Tk mainloop. main.py's first-line DPI call (OVER-05) is still
the caller; this file does NOT touch DPI.

Smoke test escape hatch: if ULTIMATE_ZOOM_SMOKE=1 is set in the
environment, we schedule root.after(50, bubble.destroy) so the process
exits cleanly within ~100 ms. This keeps the Phase 1 test_main_entry.py
subprocess smoke tests runnable without a human having to close the
window. The normal interactive path (no env var) runs mainloop until
the user closes the bubble.
"""
from __future__ import annotations

import os

from magnifier_bubble import dpi
from magnifier_bubble.state import AppState, StateSnapshot
from magnifier_bubble.window import BubbleWindow


def main() -> int:
    # Observable proof that PMv2 survived the Phase 2 Tk + ctypes imports.
    dpi.debug_print()

    # Phase 1 criterion 4: AppState is still the single source of truth.
    state = AppState(StateSnapshot())

    # Phase 2: create the bubble and drive the Tk event loop.
    bubble = BubbleWindow(state)
    print(
        f"[bubble] hwnd={bubble._hwnd} "
        f"geometry={state.snapshot().w}x{state.snapshot().h}"
        f"+{state.snapshot().x}+{state.snapshot().y} "
        f"shape={state.snapshot().shape}"
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
