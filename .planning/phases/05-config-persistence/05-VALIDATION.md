---
phase: 5
slug: config-persistence
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-13
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `tests/conftest.py` (Wave 0 installs if absent) |
| **Quick run command** | `python -m pytest tests/test_config.py -q` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_config.py -q`
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 5-01-01 | 01 | 1 | PERS-01 | unit | `python -m pytest tests/test_config.py::test_path_resolution -q` | ❌ W0 | ⬜ pending |
| 5-01-02 | 01 | 1 | PERS-03 | unit | `python -m pytest tests/test_config.py::test_atomic_write -q` | ❌ W0 | ⬜ pending |
| 5-01-03 | 01 | 1 | PERS-03 | unit | `python -m pytest tests/test_config.py::test_debounce -q` | ❌ W0 | ⬜ pending |
| 5-01-04 | 01 | 1 | PERS-04 | unit | `python -m pytest tests/test_config.py::test_load_edge_cases -q` | ❌ W0 | ⬜ pending |
| 5-02-01 | 02 | 2 | PERS-01 | integration | `python -m pytest tests/test_config_integration.py -q` | ❌ W0 | ⬜ pending |
| 5-02-02 | 02 | 2 | PERS-02 | integration | `python -m pytest tests/test_config_integration.py::test_restore_on_launch -q` | ❌ W0 | ⬜ pending |
| 5-02-03 | 02 | 2 | PERS-04 | manual | N/A — WM_DELETE_WINDOW race | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_config.py` — unit stubs for PERS-01, PERS-03, PERS-04
- [ ] `tests/test_config_integration.py` — integration stubs for PERS-01, PERS-02
- [ ] `tests/conftest.py` — shared fixtures (tmp_path, fake StateSnapshot)
- [ ] `pytest` install check — if no `pytest` detected in env

*Wave 0 must create test file stubs before any implementation tasks.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| WM_DELETE_WINDOW flushes pending write before destroy | PERS-04 | Requires live Tk main loop + kill timing | 1. Launch app. 2. Trigger a zoom change. 3. Within 500ms, close window via X button. 4. Open config.json — must contain the change. |
| No partially-written config.json on kill | PERS-04 | Requires kill-mid-write simulation | 1. Add artificial delay to atomic write. 2. Kill process during write. 3. Verify config.json is either the old valid version or the new valid version — never corrupt. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
