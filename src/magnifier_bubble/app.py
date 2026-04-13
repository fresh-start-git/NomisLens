"""Ultimate Zoom - Phase 5 entry point.

Replaces the Phase 2 main(): config.load runs before AppState is
constructed so PERS-03 (restore on launch) takes effect.  The
ConfigWriter is constructed after BubbleWindow (so root.after has
a live Tk root) and is handed back to the bubble so destroy() can
flush pending writes synchronously before Tk teardown (PERS-04).

main.py's first-line DPI call (OVER-05) is still the caller; this
file does NOT touch DPI.
"""
from __future__ import annotations

import argparse
import os
import sys

from magnifier_bubble import config, dpi
from magnifier_bubble.state import AppState
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

    # OVER-05 proof: PMv2 survived Phase 2's Tk + ctypes imports.
    dpi.debug_print()

    # Phase 5 PERS-01 + PERS-03: resolve path, load snapshot BEFORE
    # AppState is constructed.  load() NEVER raises — missing/corrupt
    # config returns StateSnapshot() defaults silently.
    path = config.config_path()
    snap = config.load(path)
    print(
        f"[config] loaded path={path} "
        f"zoom={snap.zoom:.2f} shape={snap.shape} "
        f"geometry={snap.w}x{snap.h}+{snap.x}+{snap.y}",
        flush=True,
    )

    # Phase 1 criterion 4: AppState is still the single source of
    # truth.  Phase 5 change: it is now seeded with the loaded snap.
    state = AppState(snap)

    # Phase 2/4: create the bubble and drive the Tk event loop.
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

    # Phase 5 PERS-02 + PERS-04: construct the debounced writer
    # AFTER the bubble (so bubble.root is a live Tk instance) and
    # hand it back to the bubble so destroy() can flush synchronously
    # BEFORE tearing Tk down.  register() must happen before the
    # mainloop so user mutations reach the writer.
    writer = config.ConfigWriter(state, bubble.root, path)
    writer.register()
    bubble.attach_config_writer(writer)

    # Phase 3: start the 30 fps capture producer thread.  Gated by
    # sys.platform so non-Windows CI does not blow up on `import mss`.
    if sys.platform == "win32":
        bubble.start_capture()

    if os.environ.get("ULTIMATE_ZOOM_SMOKE") == "1":
        # Non-interactive smoke: tear down after 50 ms so the subprocess
        # exits cleanly for CI / test_main_entry.py.  destroy() will
        # call writer.flush_pending() before WndProc teardown.
        bubble.root.after(50, bubble.destroy)

    bubble.root.mainloop()
    print("[app] phase 5 mainloop exited; goodbye")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
