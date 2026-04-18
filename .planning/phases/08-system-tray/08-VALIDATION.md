---
phase: 8
slug: system-tray
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-17
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml (pytest.ini_options) |
| **Quick run command** | `pytest tests/test_tray.py -x -q` |
| **Full suite command** | `pytest -x -q` |
| **Estimated runtime** | ~15 seconds (structural); ~5s extra for smoke on Windows |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_tray.py -x -q`
- **After every plan wave:** Run `pytest -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 8-01-01 | 01 | 0 | TRAY-02 | structural | `pytest tests/test_tray.py::test_tray_menu_items_present -x` | ❌ W0 | ⬜ pending |
| 8-01-02 | 01 | 0 | TRAY-03 | structural | `pytest tests/test_tray.py::test_tray_showHide_is_default -x` | ❌ W0 | ⬜ pending |
| 8-01-03 | 01 | 0 | TRAY-04 | structural | `pytest tests/test_tray.py::test_tray_callbacks_use_root_after -x` | ❌ W0 | ⬜ pending |
| 8-01-04 | 01 | 0 | TRAY-04 | structural | `pytest tests/test_tray.py::test_tray_thread_is_non_daemon -x` | ❌ W0 | ⬜ pending |
| 8-01-05 | 01 | 0 | TRAY-05 | structural | `pytest tests/test_tray.py::test_tray_stop_before_destroy_ordering -x` | ❌ W0 | ⬜ pending |
| 8-01-06 | 01 | 0 | TRAY-01 | structural | `pytest tests/test_tray.py::test_tray_src_exists -x` | ❌ W0 | ⬜ pending |
| 8-01-07 | 01 | 1 | TRAY-01 | Windows smoke | `pytest tests/test_tray_smoke.py::test_create_tray_image_returns_pil_image -x` | ❌ W0 | ⬜ pending |
| 8-01-08 | 01 | 1 | TRAY-04/05 | Windows smoke | `pytest tests/test_tray_smoke.py::test_tray_icon_start_stop -x` | ❌ W0 | ⬜ pending |
| 8-02-01 | 02 | 2 | TRAY-01..05 | Windows smoke + manual | `pytest tests/test_tray_smoke.py -x` + manual checklist | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tray.py` — structural lints (cross-platform, runs on Linux CI)
- [ ] `tests/test_tray_smoke.py` — Windows-only integration stubs (skipif non-win32)
- [ ] `src/magnifier_bubble/tray.py` — module skeleton (imported by structural tests)

*Note: pyproject.toml and pytest infrastructure already exist from prior phases.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Tray icon appears in Windows notification area | TRAY-01 | Requires visual inspection of taskbar | Launch `python main.py`; look for teal magnifier in tray |
| Right-click menu renders correctly | TRAY-02 | GUI menu not scriptable in CI | Right-click icon; verify Show/Hide, Always on Top (checked), separator, Exit |
| Left-click toggles bubble | TRAY-03 | Requires live window + tray interaction | Left-click tray icon; verify bubble shows/hides |
| Always on Top checkmark + behavior | TRAY-02 | Requires visual + window-layer check | Click "Always on Top"; verify checkmark toggles AND window can be covered |
| Clean process exit via tray | TRAY-05 | Requires OS process inspection | Click "Exit"; verify process ends within 2s, no ghost tray icon |
| No deadlock after 5 min of menu use | TRAY-04 | Requires sustained manual interaction | Interact with tray menu repeatedly for 5 min; verify app remains responsive |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
