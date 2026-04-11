---
phase: 1
slug: foundation-dpi
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-11
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (Wave 0 installs) |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 0 | OVER-05 | scaffold | `test -f requirements.txt && test -f requirements-dev.txt` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 0 | OVER-05 | scaffold | `test -f src/magnifier_bubble/__init__.py` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 1 | OVER-05 | unit | `pytest tests/test_dpi.py -x -q` | ❌ W0 | ⬜ pending |
| 1-01-04 | 01 | 1 | OVER-05 | unit | `pytest tests/test_state.py -x -q` | ❌ W0 | ⬜ pending |
| 1-01-05 | 01 | 2 | OVER-05 | smoke | `python main.py --debug-dpi 2>&1 \| grep "physical"` | ❌ W0 | ⬜ pending |
| 1-01-06 | 01 | 3 | OVER-05 | integration | `pytest tests/ -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/__init__.py` — empty, makes tests a package
- [ ] `tests/conftest.py` — shared fixtures (mock AppState, DPI skip markers)
- [ ] `tests/test_state.py` — stubs for OVER-05 (AppState fields, observer, zoom clamp)
- [ ] `tests/test_dpi.py` — stubs for OVER-05 (Windows-only, report keys, PMv2 detection)
- [ ] `pytest` in `requirements-dev.txt` — if not already present

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 150%-scaled display shows correct physical dimensions | OVER-05 | Requires physical or VM with 150% DPI | Run `python main.py` on 150%-scaled display; check console output shows logical ≠ physical and matches Windows Display Settings |
| PMv2 is truly first executable line before imports | OVER-05 | Code inspection only | Open `main.py`; verify line 1 is `import ctypes`, line 2 is `ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)` with fallback ladder before any `import mss`, `import PIL`, `import tkinter` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
