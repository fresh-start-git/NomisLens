"""TrayManager — Phase 8 system tray icon lifecycle.

Manages a pystray.Icon running on its own non-daemon thread.
Mirrors the HotkeyManager pattern exactly: start() + stop() + attach_tray_manager.

THREADING CONTRACT:
  - TrayManager.start() spawns a non-daemon thread that calls icon.run().
  - All three pystray callbacks (_cb_toggle, _cb_toggle_aot, _cb_exit) marshal
    to the Tk main thread via self._root.after(0, callable).
  - Never call Tk APIs directly from callback bodies (Pitfall T-1).
  - Never call Tk teardown methods from pystray thread (Pitfall T-2).
  - stop() is called by BubbleWindow.destroy() AFTER hotkey_manager.stop()
    and BEFORE capture_worker.stop() (see destroy() ordering in window.py).

NON-DAEMON THREAD RATIONALE:
  daemon=False guarantees that if Python starts shutting down while the icon
  is still running, the thread is NOT killed mid-teardown and the tray icon
  is properly removed from the Windows notification area (Pitfall T-6 mitigation).
  Without this, a force-killed process leaves a ghost icon until Explorer restarts.

PITFALL T-7 COMPLIANCE:
  pystray is NOT imported at module scope in window.py or app.py.
  In app.py, 'from magnifier_bubble.tray import TrayManager' lives inside
  the 'if sys.platform == "win32":' block, matching the hotkey deferred-import pattern.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pystray
from PIL import Image, ImageDraw

if TYPE_CHECKING:
    pass  # avoid runtime imports for type hints


def create_tray_image(size: int = 64) -> Image.Image:
    """Draw a teal magnifier icon. Returns 64x64 RGBA PIL Image.

    No external asset needed — drawn in memory from the app's teal palette.
    Verified implementation from 08-RESEARCH.md Pattern 2.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dc = ImageDraw.Draw(img)
    cx = cy = size // 2 - size // 8
    r = size // 3
    lw = max(2, size // 16)
    dc.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        outline=(46, 196, 182, 255),
        width=lw,
    )
    hx0 = cx + int(r * 0.7)
    hy0 = cy + int(r * 0.7)
    hx1 = size - size // 8
    hy1 = size - size // 8
    dc.line([hx0, hy0, hx1, hy1], fill=(46, 196, 182, 255), width=lw)
    return img


class TrayManager:
    """Owns the pystray.Icon lifecycle.

    Usage (from app.py):
        tm = TrayManager(bubble.root, bubble)
        tm.start()
        bubble.attach_tray_manager(tm)
        # ...
        # destroy() calls tm.stop() automatically
    """

    def __init__(self, root, bubble) -> None:
        self._root = root      # Tk root — for self._root.after(0, ...) marshaling
        self._bubble = bubble  # BubbleWindow — exposes toggle/toggle_aot_and_apply/destroy
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Build the icon and start the non-daemon tray pump thread."""
        self._icon = self._build_icon()
        self._thread = threading.Thread(
            target=self._run,
            name="tray-pump",
            daemon=False,  # guarantees icon.stop() in finally runs on interpreter exit
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal icon.stop() and wait up to 1 second for thread to exit.

        Safe to call multiple times — idempotent.
        Called by BubbleWindow.destroy() AFTER hotkey_manager.stop().
        """
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception as exc:
                print(f"[tray] icon.stop() raised: {exc}", flush=True)
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _run(self) -> None:
        """Blocking loop — runs on the tray-pump thread.

        icon.run() blocks until icon.stop() is called. Exceptions are
        caught and logged so a pystray failure doesn't kill the thread
        silently (which would leave stop() hanging on join()).
        """
        try:
            self._icon.run()
        except Exception as exc:
            print(f"[tray] icon.run() raised: {exc}", flush=True)

    def _build_icon(self) -> pystray.Icon:
        """Construct the pystray.Icon with menu and teal magnifier image."""
        def _is_aot(item):
            # Called from pystray's thread when the menu is opened.
            # snapshot() is lock-protected — safe from non-main thread.
            return self._bubble.state.snapshot().always_on_top

        menu = pystray.Menu(
            pystray.MenuItem("Show / Hide", self._cb_toggle, default=True),
            pystray.MenuItem(
                "Always on Top",
                self._cb_toggle_aot,
                checked=_is_aot,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._cb_exit),
        )
        return pystray.Icon(
            "NomisLens",
            icon=create_tray_image(),
            title="NomisLens \u2014 Ctrl+Alt+Z to toggle",
            menu=menu,
        )

    # --- Callbacks (fire on pystray's thread — marshal to Tk main thread) ---
    # MANDATORY: every body must be exactly self._root.after(0, callable).
    # Never call any Tk API or AppState.set_*() directly here (Pitfall T-1).

    def _cb_toggle(self, icon, item) -> None:
        """Left-click on tray icon or 'Show / Hide' menu item."""
        self._root.after(0, self._bubble.toggle)

    def _cb_toggle_aot(self, icon, item) -> None:
        """'Always on Top' menu item — calls toggle_aot_and_apply on main thread."""
        self._root.after(0, self._bubble.toggle_aot_and_apply)

    def _cb_exit(self, icon, item) -> None:
        """'Exit' menu item — calls bubble.destroy() on main thread."""
        self._root.after(0, self._bubble.destroy)
