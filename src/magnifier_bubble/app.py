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

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "NomisLens"


def _register_startup() -> None:
    """Add NomisLens to HKCU startup so it launches with Windows.

    Uses the current executable path (sys.executable == NomisLens.exe when
    packaged).  Silent no-op on any error or non-Windows platform.
    """
    if sys.platform != "win32":
        return
    try:
        import winreg
        exe = sys.executable
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, f'"{exe}"')
    except Exception:
        pass


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
    parser.add_argument(
        "--no-hotkey",
        action="store_true",
        help=(
            "Disable the global show/hide hotkey. Bubble must be closed "
            "via tray (Phase 7) or process kill. Use if Phase 6 RegisterHotKey "
            "conflicts with clinic keyboard hook software."
        ),
    )
    args = parser.parse_args()

    # Register in Windows startup so Ctrl+Alt+Z is always available.
    _register_startup()

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

    # Phase 6 (HOTK-04): parse the raw hotkey field from the same file
    # config.load consumed.  config.load returns a StateSnapshot and
    # ignores unknown fields (hotkey is one), so we re-read the raw
    # dict just for the hotkey parse.  Missing / corrupt -> parse_hotkey
    # returns the (MOD_CONTROL, VK_Z) default.
    import json as _json
    raw_cfg: dict = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as _f:
                raw_cfg = _json.load(_f)
                if not isinstance(raw_cfg, dict):
                    raw_cfg = {}
        except (OSError, _json.JSONDecodeError):
            raw_cfg = {}
    hotkey_mods, hotkey_vk = config.parse_hotkey(raw_cfg.get("hotkey"))
    print(
        f"[config] hotkey modifiers=0x{hotkey_mods:04x} vk=0x{hotkey_vk:02x}",
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

    # Phase 6: construct HotkeyManager AFTER attach_config_writer (bubble.root
    # is live), BEFORE start_capture (capture worker should only spin up if
    # the app is actually ready to pump messages).  stop() ordering is handled
    # by BubbleWindow.destroy() which runs _hotkey_manager.stop() BEFORE
    # capture_worker.stop() (Open Question #4 in 06-RESEARCH.md).
    if args.no_hotkey:
        print("[hotkey] disabled by --no-hotkey flag", flush=True)
    elif sys.platform == "win32":
        from magnifier_bubble.hotkey import HotkeyManager
        hm = HotkeyManager(
            bubble.root,
            bubble.toggle,          # main-thread callback; HOTK-03 handoff
            hotkey_mods,
            hotkey_vk,
        )
        ok = hm.start(timeout=1.0)
        if ok:
            bubble.attach_hotkey_manager(hm)
            print(
                f"[hotkey] registered modifiers=0x{hotkey_mods:04x} "
                f"vk=0x{hotkey_vk:02x} tid={hm._tid}",
                flush=True,
            )
        else:
            # Graceful failure — app continues (tray in Phase 7 will still
            # provide Show/Hide).  HotkeyManager itself already logged the
            # specific [hotkey] registration-failed message with the error code.
            print(
                "[hotkey] continuing without hotkey support",
                flush=True,
            )
    else:
        print("[hotkey] skipped (non-Windows platform)", flush=True)

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
