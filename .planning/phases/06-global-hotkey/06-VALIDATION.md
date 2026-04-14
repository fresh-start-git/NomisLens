---
phase: 6
slug: global-hotkey
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-13
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ (from requirements-dev.txt) |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` (pythonpath=["src"], testpaths=["tests"]) |
| **Quick run command** | `pytest tests/test_hotkey.py -x` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~5 seconds (pure-Python lints fast; smoke tests on Windows ~10s) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_hotkey.py -x`
- **After every plan wave:** Run `pytest` (full suite; Windows-only smoke tests auto-skip on Linux via `@pytest.mark.skipif(sys.platform != "win32", ...)`)
- **Before `/gsd:verify-work`:** Full suite green + manual verification on Windows 11 dev box per 5 Success Criteria + user answer on Ctrl+Z default
- **Max feedback latency:** ~5 seconds (pure-Python unit layer)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 6-01-01 | 01 | 0 | HOTK-01 | unit (structural) | `pytest tests/test_hotkey.py::test_hotkey_uses_ctypes_not_keyboard_lib -x` | ❌ W0 | ⬜ pending |
| 6-01-02 | 01 | 0 | HOTK-01 | unit | `pytest tests/test_hotkey.py::test_winconst_mod_values_match_msdn -x` | ❌ W0 | ⬜ pending |
| 6-01-03 | 01 | 0 | HOTK-01 | unit (structural) | `pytest tests/test_hotkey.py::test_hotkey_applies_argtypes -x` | ❌ W0 | ⬜ pending |
| 6-01-04 | 01 | 0 | HOTK-05 | unit (structural) | `pytest tests/test_hotkey.py::test_hotkey_thread_is_non_daemon -x` | ❌ W0 | ⬜ pending |
| 6-01-05 | 01 | 0 | HOTK-05 | unit (structural) | `pytest tests/test_hotkey.py::test_register_and_unregister_in_same_function -x` | ❌ W0 | ⬜ pending |
| 6-02-01 | 02 | 1 | HOTK-04 | unit | `pytest tests/test_config.py::test_hotkey_roundtrip -x` | existing — EXTEND | ⬜ pending |
| 6-02-02 | 02 | 1 | HOTK-04 | unit | `pytest tests/test_config.py::test_hotkey_defaults_on_corrupt -x` | existing — EXTEND | ⬜ pending |
| 6-02-03 | 02 | 1 | HOTK-04 | unit | `pytest tests/test_config.py::test_hotkey_rejects_unknown_modifier -x` | existing — EXTEND | ⬜ pending |
| 6-03-01 | 03 | 2 | HOTK-03 | integration (Windows) | `pytest tests/test_hotkey_smoke.py::test_wm_hotkey_toggles_visible_via_after -x` | ❌ W0 | ⬜ pending |
| 6-03-02 | 03 | 2 | HOTK-03 | unit | `pytest tests/test_window_phase4.py::test_bubble_show_hide_toggle -x` | existing — EXTEND | ⬜ pending |
| 6-03-03 | 03 | 2 | HOTK-05 | integration (Windows) | `pytest tests/test_hotkey_smoke.py::test_second_register_fails_gracefully -x` | ❌ W0 | ⬜ pending |
| 6-03-04 | 03 | 2 | HOTK-05 | integration (Windows) | `pytest tests/test_hotkey_smoke.py::test_stop_posts_quit_and_joins -x` | ❌ W0 | ⬜ pending |
| 6-04-01 | 04 | 3 | HOTK-02 | manual | human-verify with real Cornerstone focus | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_hotkey.py` — stubs for HOTK-01, HOTK-05 (structural lint): ctypes usage, argtypes, non-daemon, same-thread unregister
- [ ] `tests/test_hotkey_smoke.py` — stubs for HOTK-03, HOTK-05 (integration): WM_HOTKEY toggle, double-register fail, stop/join
- [ ] Extend `tests/test_config.py` with `test_hotkey_roundtrip`, `test_hotkey_defaults_on_corrupt`, `test_hotkey_rejects_unknown_modifier`
- [ ] Extend `tests/test_window_phase4.py` (or new `tests/test_window_visibility.py`) with `test_bubble_show_hide_toggle`
- [ ] Add `WM_HOTKEY`, `MOD_CTRL`, `MOD_ALT`, `MOD_SHIFT`, `MOD_WIN`, `MOD_NOREPEAT`, `VK_Z`, `WM_QUIT`, `ERROR_HOTKEY_ALREADY_REGISTERED` to `winconst.py`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Hotkey fires while Cornerstone has focus | HOTK-02 | Requires a live Cornerstone instance with focus — cannot be simulated in pytest | 1. Launch Naomi Zoom. 2. Click into Cornerstone. 3. Press configured hotkey. 4. Verify bubble toggles visible/hidden. 5. Press again — verify it returns. |
| Hotkey is NOT a conflict with Cornerstone undo | HOTK-01 | Requires human judgment about Cornerstone's Ctrl+Z binding | Ask user: "Does Cornerstone use Ctrl+Z for undo?" — if yes, default to Ctrl+Alt+Z |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s (pure-Python layer)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
