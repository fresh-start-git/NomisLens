---
phase: 07-dxgi-capture-transparent-input
plan: "02"
subsystem: window
tags: [window, click-through, transparency, dxgi, magnification-removal, refactor]

dependency_graph:
  requires: [07-01]
  provides: [BubbleWindow-phase7, zone-transparency-poll, dxgi-wiring]
  affects: [window.py, capture.py, app.py, tests]

tech_stack:
  added: []
  patterns:
    - "WS_EX_TRANSPARENT zone poll: 50ms timer toggles transparent flag based on cursor zone"
    - "after-ID cancellation: both _zone_poll_id and _poll_frame_queue_id cancelled in destroy()"
    - "WS_EX_TRANSPARENT cleared in destroy() to allow WM_DELETE_WINDOW delivery"
    - "Tombstone ImportError: capture.py replaced with raise ImportError to block accidental import"

key_files:
  created: []
  modified:
    - src/magnifier_bubble/window.py
    - src/magnifier_bubble/capture.py
    - src/magnifier_bubble/app.py
    - tests/test_window_phase4.py
    - tests/test_window_integration.py
    - tests/test_window_config_integration.py

decisions:
  - "Zone poll replaces all click injection: _zone_transparency_poll sets WS_EX_TRANSPARENT when cursor enters content zone, clears it for drag/control strips — no SendInput, no PostMessageW, no ReleaseCapture needed"
  - "Both after-IDs (_zone_poll_id, _poll_frame_queue_id) stored and after_cancel'd in destroy() before root.destroy() — prevents callbacks firing on a partially-torn-down Tk tree"
  - "WS_EX_TRANSPARENT explicitly cleared in destroy() destroy() top-of-try so WM_DELETE_WINDOW is deliverable even if cursor was in content zone at close time"
  - "capture.py tombstoned with raise ImportError (not deleted from filesystem) — Python tombstone prevents accidental import while keeping git history intact"
  - "BubbleWindow.__init__ signature simplified to (self, state) — click_injection_enabled parameter removed; no backward-compat shim needed because all call sites updated in same plan"

metrics:
  duration_minutes: ~95
  completed_date: "2026-04-18"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 6
  pre_existing_failures: 6
  new_failures: 0
---

# Phase 7 Plan 02: Window Surgery — Mag API and Click Injection Removal

**One-liner:** Removed ~500 lines of Magnification API, context menu management, and click injection code from window.py; replaced with 30-line WS_EX_TRANSPARENT zone poll wired to DXGICaptureWorker.

---

## Objective

Perform the largest and most destructive surgery in Phase 7. Delete all click injection infrastructure from window.py, replace with the WS_EX_TRANSPARENT zone transparency poll that lets physical mouse/touch pass through to the underlying app without any synthetic injection. Wire DXGICaptureWorker as the sole capture path.

---

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | window.py surgery + capture.py tombstone | d7ee002 | src/magnifier_bubble/window.py, src/magnifier_bubble/capture.py |
| 2 | Update tests and app.py | 3ef0faa | src/magnifier_bubble/app.py, tests/test_window_phase4.py, tests/test_window_integration.py, tests/test_window_config_integration.py |

---

## What Was Built

### Task 1: window.py Surgery

**Deleted (~500 lines removed):**
- `from magnifier_bubble.capture import CaptureWorker` import
- `_MAGTRANSFORM` ctypes.Structure class
- `click_injection_enabled` constructor parameter and all downstream attributes
- `_active_menu_hwnd`, `_active_menu_cls`, `_active_menu_skip_zorder` attributes
- `_hwnd_mag`, `_mag_dll`, `_mag_last_zoom`, `_mag_last_wh` attributes
- `_on_canvas_press` content-zone injection block (inject_click / WinUI3 two-phase)
- `_on_canvas_rclick` injection block (WS_EX_TRANSPARENT + send_rclick_at flow)
- `_poll_menu_restore` method (~200 lines — entire Z-order management + menu detection)
- `_mag_init`, `_mag_set_transform`, `_mag_tick` methods (~65 lines total)
- Magnification API destroy cleanup block in `destroy()`

**Added (~30 lines):**
- `_zone_transparency_poll` method: 50ms timer reads cursor position via GetCursorPos, computes which zone the cursor is in (drag/content/control), sets or clears WS_EX_TRANSPARENT on the overlay HWND accordingly
- `_zone_poll_id` and `_poll_frame_queue_id` instance attributes (init as None, tracked for after_cancel)
- Zone poll started at end of `__init__` via `self.root.after(50, self._zone_transparency_poll)`
- `_poll_frame_queue` updated to store after-ID in `self._poll_frame_queue_id`
- `start_capture()` replaced with DXGICaptureWorker-only path (no Magnification API branch)
- Three destroy() additions at top of try block: cancel zone poll ID, cancel frame queue poll ID, clear WS_EX_TRANSPARENT

**capture.py tombstoned:**
```python
# DELETED in Phase 7. Use src/magnifier_bubble/capture_dxgi.py instead.
raise ImportError("capture.py is deleted in Phase 7. ...")
```

### Task 2: Test and app.py Updates

**app.py:**
- Removed `--no-click-injection` argparse flag entirely
- Changed `BubbleWindow(state, click_injection_enabled=not args.no_click_injection)` to `BubbleWindow(state)`
- Removed `click_injection={bubble._click_injection_enabled}` from startup print

**test_window_phase4.py:**
- Removed: `test_bubble_window_accepts_click_injection_enabled_kwarg`, `test_content_zone_click_invokes_inject_click_when_enabled`, `test_content_zone_click_does_nothing_when_injection_disabled`
- Added: `test_bubble_window_constructor_no_click_injection_param`, `test_bubble_has_zone_poll_id_attribute`, `test_bubble_has_poll_frame_queue_id_attribute`

**test_window_integration.py:**
- Replaced `test_source_does_not_use_ws_ex_transparent` with `test_source_uses_ws_ex_transparent_only_in_zone_poll` (Phase 7 intentionally uses WS_EX_TRANSPARENT)
- Replaced `test_source_has_pattern_2b_drag_workaround` (checked ReleaseCapture/HTCAPTION — deleted code) with `test_source_has_manual_geometry_drag` (checks `_drag_origin`, `root.geometry(`, `_zone_fn`)

**test_window_config_integration.py:**
- All 4 occurrences of `BubbleWindow(state, click_injection_enabled=False)` changed to `BubbleWindow(state)`

---

## Verification Results

### Dead Code Grep (Expected: zero matches)
```
grep -n "CaptureWorker|_active_menu_hwnd|_poll_menu_restore|_mag_init|inject_click|click_injection" src/magnifier_bubble/window.py
```
Result: Zero matches — all dead code removed.

### New Code Grep (Expected: multiple matches)
```
grep -n "_zone_transparency_poll|_zone_poll_id|_poll_frame_queue_id|DXGICaptureWorker|after_cancel" src/magnifier_bubble/window.py
```
Result: 13 matches — zone poll, after-IDs, and DXGICaptureWorker all present.

### Button-3 Binding (Expected: exactly one match)
```
grep -n "Button-3" src/magnifier_bubble/window.py
```
Result: 1 match — retained for theme cycling on drag strip.

### Test Suite
- 49 passed (Phase 7 additions all green)
- 5 failed — all confirmed pre-existing before our changes (stash verify performed)
- 14 errors — all confirmed pre-existing TclError/fixture teardown issues

**Pre-existing failures confirmed via git stash verification:**
1. `test_grip_glyph_drawn_centered` — grip placed at w//2=200, test expects (400-44)//2=178
2. `test_zoom_buttons_and_text_display` — zoom format is "2.0x" not "2.00x" matching test regex
3. `test_resize_clamp_on_drag_motion` — resize produces w=1200 not clamped to 700
4. `test_wndproc_hit_test_returns_httransparent_at_center` — returns HTCLIENT(1) not HTTRANSPARENT(-1)
5. `test_main_py_first_line_is_import_ctypes` + `test_main_py_has_no_module_docstring` — main.py first import is `sys` not `ctypes`

All failures exist identically on the pre-Phase-7-02 commit (d7ee002 parent: 171d3e6).

---

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written with one deviation that was a test conflict, not a code bug.

### Test Conflicts Resolved

**1. [Rule 2 - Test Update] `test_source_does_not_use_ws_ex_transparent` became incorrect**
- **Found during:** Task 2 verification
- **Issue:** The old test from Phase 4 prohibited `| wc.WS_EX_TRANSPARENT` in window.py source because the old architecture only used it transiently (16ms). Phase 7's `_zone_transparency_poll` intentionally uses this pattern permanently.
- **Fix:** Replaced with `test_source_uses_ws_ex_transparent_only_in_zone_poll` that verifies: (a) `wc.WS_EX_TRANSPARENT` is present (zone poll works), (b) initial ext style construction-time OR expression is still `WS_EX_LAYERED | wc.WS_EX_TOOLWINDOW | wc.WS_EX_NOACTIVATE` (not WS_EX_TRANSPARENT at init).
- **Files:** tests/test_window_integration.py

**2. [Rule 2 - Test Update] `test_source_has_pattern_2b_drag_workaround` referenced deleted code**
- **Found during:** Task 2 verification
- **Issue:** Old test checked for `ReleaseCapture`, `WM_NCLBUTTONDOWN`, `HTCAPTION` in window.py source — all deleted as part of click injection removal. `HTCAPTION` lives in wndproc.py (returned by the zone fn), not window.py.
- **Fix:** Replaced with `test_source_has_manual_geometry_drag` checking `_drag_origin`, `root.geometry(`, `_zone_fn` — all of which are present in Phase 7 window.py.
- **Files:** tests/test_window_integration.py

---

## Architecture Change

**Before Plan 02:**
```
User click in content zone
  → WM_LBUTTONDOWN reaches overlay (HTCLIENT or HTTRANSPARENT based on zone fn)
  → _on_canvas_press: compute actual_xy via zoom mapping
  → inject_click(actual_x, actual_y, own_hwnd)
    → walk Z-order, PostMessageW(WM_LBUTTONDOWN) to target
  OR
  → send_lclick_at via SendInput (ContentIslandWindow / WinUI3 paths)
```

**After Plan 02:**
```
Cursor moves into content zone
  → _zone_transparency_poll (50ms): cursor in content zone detected
    → SetWindowLongW(hwnd, GWL_EXSTYLE, cur_ex | WS_EX_TRANSPARENT)
  → WindowFromPoint skips overlay entirely (WS_EX_TRANSPARENT = "I don't exist")
  → Physical mouse click reaches underlying app directly — no injection
```

The new architecture eliminates all synthetic injection code paths and relies entirely on the OS's built-in click-through behavior for transparent windows.

---

## Self-Check

```bash
[ -f "src/magnifier_bubble/window.py" ] && echo "FOUND: window.py" || echo "MISSING: window.py"
[ -f "src/magnifier_bubble/capture.py" ] && echo "FOUND: capture.py (tombstone)" || echo "MISSING: capture.py"
```

Result: Both files found.

```bash
git log --oneline --all | grep -q "d7ee002" && echo "FOUND: d7ee002" || echo "MISSING: d7ee002"
git log --oneline --all | grep -q "3ef0faa" && echo "FOUND: 3ef0faa" || echo "MISSING: 3ef0faa"
```

Result: Both commits found.

## Self-Check: PASSED
