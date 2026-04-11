---
phase: 2
slug: overlay-window
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-11
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` (already installed via `requirements-dev.txt` from Phase 1) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`pythonpath = ["src"]`, `testpaths = ["tests"]`) |
| **Quick run command** | `python -m pytest tests/test_winconst.py tests/test_hit_test.py -x` |
| **Full suite command** | `python -m pytest -x` |
| **Estimated runtime** | ~1s (quick), ~5s (full suite; Windows-only tests skip on CI/Linux) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_winconst.py tests/test_hit_test.py -x`
- **After every plan wave:** Run `python -m pytest -x`
- **Before `/gsd:verify-work`:** Full suite must be green AND manual smoke checklist run on dev box (5-min hover + Notepad focus theft test + visual taskbar check)
- **Max feedback latency:** ~5 seconds (automated); manual smoke is one-time phase gate

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 2-W0-01 | 01 | 0 | OVER-01 | integration | `pytest tests/test_window_integration.py::test_ext_styles_set -x` | ❌ W0 | ⬜ pending |
| 2-W0-02 | 01 | 0 | OVER-02 | integration | `pytest tests/test_window_integration.py::test_overrideredirect_set -x` | ❌ W0 | ⬜ pending |
| 2-W0-03 | 01 | 0 | OVER-03 | integration | `pytest tests/test_window_integration.py::test_layered_style_set -x` | ❌ W0 | ⬜ pending |
| 2-W0-04 | 01 | 0 | OVER-04 | integration + smoke | `pytest tests/test_window_integration.py::test_noactivate_style_set -x` | ❌ W0 | ⬜ pending |
| 2-W0-05 | 01 | 0 | LAYT-01 | unit | `pytest tests/test_hit_test.py -x` | ❌ W0 | ⬜ pending |
| 2-W0-06 | 01 | 0 | LAYT-02 | unit (no Tk) | `pytest tests/test_hit_test.py::test_middle_returns_content -x` | ❌ W0 | ⬜ pending |
| 2-W0-07 | 01 | 0 | LAYT-03 | unit + win32 | `pytest tests/test_wndproc_smoke.py::test_wndproc_returns_httransparent_for_middle -x` | ❌ W0 | ⬜ pending |
| 2-W0-08 | 01 | 0 | LAYT-04 | unit + integration | `pytest tests/test_window_integration.py::test_wndproc_keepalive_attribute -x` | ❌ W0 | ⬜ pending |
| 2-W0-09 | 01 | 0 | LAYT-05 | unit | `pytest tests/test_window_integration.py::test_strip_rectangles_drawn -x` | ❌ W0 | ⬜ pending |
| 2-W0-10 | 01 | 0 | LAYT-06 | unit | `pytest tests/test_window_integration.py::test_border_drawn -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_winconst.py` — covers reading Win32 constant values; ~10 assertions, runs everywhere
- [ ] `tests/test_hit_test.py` — covers `compute_zone` for OVER-/LAYT-01..03 boundary cases; pure Python, no Tk
- [ ] `tests/test_wndproc_smoke.py` — Windows-only; creates a throwaway Tk root, installs the wndproc, sends synthetic WM_NCHITTEST messages via `SendMessageW`, asserts return values
- [ ] `tests/test_shapes_smoke.py` — Windows-only; creates a throwaway Tk root, calls `apply_shape` 50 times for each shape, asserts process alive
- [ ] `tests/test_window_integration.py` — Windows-only; creates BubbleWindow, asserts hwnd valid, asserts ext styles, asserts `compute_zone` results at known points, asserts canvas items present, asserts `_wndproc_keepalive` is held

*No new framework install needed — pytest is already in `requirements-dev.txt`.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Clicking bubble does not steal focus from Cornerstone | OVER-04 | Requires two live processes and human observation of cursor/typing continuity | Open Cornerstone, start typing; click bubble; verify Cornerstone retains focus and cursor does not reset |
| App survives 5+ minutes of hover interaction without GC crash | LAYT-04 | Requires sustained real-time observation; no automated timer-based crash detection | Launch app, hover and click drag bar for 5 minutes, verify no exception/crash |
| Visual: semi-transparent dark strips legible against both light and dark backgrounds | LAYT-05 | Color perception and contrast ratio require visual inspection | Open app over white desktop, then dark desktop; verify both strips are visible |
| Visual: 3–4 px teal border legible against light/dark backgrounds | LAYT-06 | Same as above | Open app over white and dark backgrounds; measure border width visually |
| Click-through: middle zone passes clicks to app underneath | LAYT-02 | Requires live click target (Notepad) underneath the overlay | Open Notepad under bubble middle zone; click in middle zone; verify Notepad receives the click (cursor moves or text inserts) |
| Touch click-through (touchscreen only) | LAYT-02 | Hardware-blocked — clinic touchscreen required | If touchscreen available: tap middle zone; verify underlying app receives tap. Mark as deferred if hardware unavailable. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
