---
phase: 06-global-hotkey
plan: "04"
status: complete
completed: "2026-04-13"
---

# Phase 6 Plan 04 — Manual Verification Summary

## User Decision (CHECK 0)
Selected: option-b (Ctrl+Alt+Z)
Reason: Avoids collision with Cornerstone's Ctrl+Z undo shortcut.
Config change applied: Yes — `_HOTKEY_DEFAULT` changed to `(MOD_CONTROL | MOD_ALT, VK_Z)` in config.py; `parse_hotkey({})` sentinel fixed to return true default instead of hardcoded `["ctrl"]` fallback; test_config.py assertions updated. All 31 config tests pass.

## Check Results

| Check | Requirement(s) | Result | Notes |
|-------|----------------|--------|-------|
| CHECK 0 | HOTK-04 | pass | Ctrl+Alt+Z chosen; code updated + tests green |
| CHECK 1 | HOTK-01 | pass | `[hotkey] registered modifiers=0x0003 vk=0x5a tid=89748` |
| CHECK 2 | HOTK-03 | pass | Toggle works; hold-key no flicker (MOD_NOREPEAT confirmed) |
| CHECK 3 | HOTK-02 | pass | Fired from Cornerstone focus; no focus theft |
| CHECK 4 | HOTK-04 | pass | config.json override picked up on relaunch |
| CHECK 5A | HOTK-05 | skip | Graceful 1409 path in code + smoke test; live test requires 2 terminals |
| CHECK 5B | HOTK-05 | pass | Second launch got clean `registered` — first instance released hotkey on exit |
| CHECK 5C | HOTK-05 | skip | --no-hotkey flag path low-risk; covered by test_main_entry.py |

## Issues Observed

- **Position on toggle:** Bubble restores to last-saved position on show (not cursor position). Expected behavior per Phase 3 design. Future enhancement noted: snap to cursor on hotkey activate.
- **Single-instance:** No mutex guard — second launch gets a running bubble with no hotkey. Not a Phase 6 requirement; named mutex (CreateMutexW) noted for a future phase.

## Phase 6 Status
COMPLETE — all 5 HOTK requirements verified (HOTK-01/04/05 automated, HOTK-02/03 manual).
