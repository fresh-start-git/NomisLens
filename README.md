# NomisLens — Magnifier for Naomi

NomisLens is a floating zoom lens for the clinic touchscreen. It magnifies a region of the screen so you can read small text without changing the application underneath. Clicks and touches pass through the lens to the app below — Cornerstone never loses focus.

---

## Quick Start

1. Copy `NomisLens.exe` to your desktop.
2. Double-click `NomisLens.exe` to launch. A tray icon (bottom-right of the taskbar) confirms the app is running.
3. The zoom bubble appears on screen. Drag the dark top strip to move it. Use the [+] and [−] buttons on the bottom strip to change the zoom level.
4. To hide or show the bubble: press **Ctrl+Alt+Z**, or right-click the tray icon and choose **Show/Hide**.
5. To close the app completely: right-click the tray icon and choose **Exit**.

---

## Antivirus

NomisLens.exe is not code-signed. Windows SmartScreen or your antivirus may flag it as unknown. This is a false positive — the app is safe.

**Windows SmartScreen (blue "Windows protected your PC" dialog):**
1. Click **More info**.
2. Click **Run anyway**.

**Antivirus software:**
Add `NomisLens.exe` to your antivirus exclusion or allowlist. Consult your antivirus documentation for the exact steps, or contact IT support.

---

## Keyboard Shortcut

**Ctrl+Alt+Z** — Toggle the zoom bubble visible/hidden from anywhere on screen, even when Cornerstone has focus.

To change the hotkey: open `config.json` (in the same folder as `NomisLens.exe`) in Notepad, edit the `"hotkey"` field, and relaunch the app.

---

## Configuration

NomisLens saves your settings (position, size, zoom level, shape) automatically in `config.json`, placed in the same folder as `NomisLens.exe`.

You do not need to edit this file manually. Changes are saved within one second of any adjustment.

---

## Running from Source

For IT staff who prefer to run from Python source rather than the prebuilt EXE:

**Requirements:** Python 3.11 (download from https://python.org), Windows 11.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

---

## Building the EXE from Source

To rebuild `dist\NomisLens.exe` after any code change:

1. Ensure `.venv` is set up (see **Running from Source** above).
2. Double-click `build.bat` in the repo root, or run it from a command prompt.
3. The EXE is written to `dist\NomisLens.exe`.

**Advanced / Developer flags (not needed for normal use):**
- `--no-hotkey` — Disables the global hotkey. Use if another app conflicts with Ctrl+Alt+Z.

---
