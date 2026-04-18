---
phase: 9
slug: build-and-package
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-17
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml (pytest.ini_options) |
| **Quick run command** | `pytest tests/test_build.py -x -q` |
| **Full suite command** | `pytest -x -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_build.py -x -q`
- **After every plan wave:** Run `pytest -x -q` (full 294-test suite)
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 9-01-01 | 01 | 0 | BULD-02 | source scan | `pytest tests/test_build.py::test_spec_hiddenimports -x` | ❌ W0 | ⬜ pending |
| 9-01-02 | 01 | 0 | BULD-02 | source scan | `pytest tests/test_build.py::test_spec_upx_false -x` | ❌ W0 | ⬜ pending |
| 9-01-03 | 01 | 0 | BULD-03 | file scan | `pytest tests/test_build.py::test_build_bat_exists -x` | ❌ W0 | ⬜ pending |
| 9-01-04 | 01 | 1 | BULD-05 | file scan | `pytest tests/test_build.py::test_readme_exists -x` | ❌ W0 | ⬜ pending |
| 9-01-05 | 01 | 1 | BULD-01 | source scan | `pytest tests/test_main_entry.py -x -q` | ✅ | ⬜ pending |
| 9-01-06 | 01 | 1 | BULD-04 | manual smoke | `set ULTIMATE_ZOOM_SMOKE=1 && dist\NomisLens.exe` | manual | ⬜ pending |
| 9-01-07 | 01 | 1 | BULD-06 | manual | `git log origin/master..HEAD --oneline` | manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_build.py` — structural lints: spec hiddenimports (`PIL._tkinter_finder`, `win32timezone`), `upx=False`, `build.bat` existence and content, `README.md` existence and required section headers

*All other test infrastructure already exists (294 tests collected). No framework installation needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| EXE runs on Windows without Python | BULD-04 | Requires OS-level isolation; no Python in PATH | `set ULTIMATE_ZOOM_SMOKE=1 && dist\NomisLens.exe` — exits 0 = pass |
| Source pushed to GitHub | BULD-06 | External network action requiring git credentials | `git push origin master` then verify at https://github.com/fresh-start-git/NomisLens.git |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
