---
phase: 3
slug: capture-loop
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-11
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | CAPT-01,CAPT-02 | unit | `python -m pytest tests/test_capture.py -x -q` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | CAPT-04 | unit | `python -m pytest tests/test_capture.py -x -q` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | CAPT-03 | unit | `python -m pytest tests/test_capture.py -k exclusion -x -q` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 1 | CAPT-05 | unit | `python -m pytest tests/test_capture.py -k memory -x -q` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 2 | CAPT-06 | lint | `grep -r "ImageGrab" src/` | ✅ | ⬜ pending |
| 03-02-02 | 02 | 2 | CAPT-01,CAPT-02 | integration | `python -m pytest tests/test_capture_smoke.py -x -q` | ❌ W0 | ⬜ pending |
| 03-02-03 | 02 | 2 | CAPT-03 | integration | `python -m pytest tests/test_capture_smoke.py -k hall_of_mirrors -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_capture.py` — unit test stubs for CAPT-01..05 (CaptureWorker, paste pattern, exclusion rect)
- [ ] `tests/test_capture_smoke.py` — Windows-only smoke tests for CAPT-01/02/03/05/06 (fps, memory, hall-of-mirrors, wired to BubbleWindow canvas)

*Existing infrastructure covers conftest.py and pyproject.toml from Phase 1.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 30fps sustained on clinic PC | CAPT-02 | Requires target hardware; dev-box timing is an estimate | Run app for 60s, check frame-time log output; calculate average fps |
| Hall-of-mirrors not visible | CAPT-03 | Requires visual inspection on real screen | Move bubble; confirm bubble content shows background app, not itself |
| Memory stable after 10min | CAPT-05 | Requires long-running observation | Watch Task Manager for 10 min; drift < 5 MB |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
