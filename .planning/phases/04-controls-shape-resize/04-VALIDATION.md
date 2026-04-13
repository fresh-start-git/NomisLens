---
phase: 4
slug: controls-shape-resize
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-12
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (already configured in Phase 1 pyproject.toml) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (Phase 1 lock) |
| **Quick run command** | `pytest tests/test_controls.py -x` |
| **Full suite command** | `pytest tests/` |
| **Estimated runtime** | ~90 seconds (full suite including Windows-only integration) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_controls.py -x`
- **After every plan wave:** Run `pytest tests/`
- **Before `/gsd:verify-work`:** Full suite must be green + manual checklist (shape cycle 60 s no crash, resize smooth by finger, click injection lands on Notepad)
- **Max feedback latency:** 5 seconds (pure-Python quick run)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 4-01-01 | 01 | 1 | CTRL-09 | unit | `pytest tests/test_controls.py::test_button_rects_all_44x44_min -x` | ❌ W0 | ⬜ pending |
| 4-01-02 | 01 | 1 | CTRL-05, CTRL-08 | unit | `pytest tests/test_controls.py::test_zoom_button_dispatch_calls_set_zoom -x` | ❌ W0 | ⬜ pending |
| 4-01-03 | 01 | 1 | CTRL-08 | unit | `pytest tests/test_controls.py::test_resize_clamp_min_max -x` | ❌ W0 | ⬜ pending |
| 4-01-04 | 01 | 1 | CTRL-02 | unit | `pytest tests/test_controls.py::test_shape_cycle_dict -x` | ❌ W0 | ⬜ pending |
| 4-02-01 | 02 | 2 | CTRL-01 | structural + integration | `pytest tests/test_window_phase4.py::test_grip_glyph_drawn_centered -x` | ❌ W0 | ⬜ pending |
| 4-02-02 | 02 | 2 | CTRL-02, CTRL-03 | integration | `pytest tests/test_window_phase4.py::test_shape_button_cycles -x` | ❌ W0 | ⬜ pending |
| 4-02-03 | 02 | 2 | CTRL-04 | integration | `pytest tests/test_window_phase4.py::test_zoom_buttons_and_text_display -x` | ❌ W0 | ⬜ pending |
| 4-02-04 | 02 | 2 | CTRL-06, CTRL-07 | integration | `pytest tests/test_window_phase4.py::test_resize_button_drag -x` | ❌ W0 | ⬜ pending |
| 4-03-01 | 03 | 3 | (user-req, LAYT-02) | structural | `pytest tests/test_clickthru.py::test_inject_click_skips_self_hwnd -x` | ❌ W0 | ⬜ pending |
| 4-03-02 | 03 | 3 | (user-req, LAYT-02) | integration + manual | Manual: Notepad below bubble, click passes through | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_controls.py` — stubs/implementations for CTRL-05 clamp, CTRL-08 clamp, CTRL-09 44×44 minimum, CTRL-02 shape cycle dict
- [ ] `tests/test_window_phase4.py` — stubs for CTRL-01 grip glyph, CTRL-02/03 shape button, CTRL-04 zoom buttons, CTRL-06 resize drag
- [ ] `tests/test_clickthru.py` — structural lint for `clickthru.py`: asserts `ChildWindowFromPointEx` with `CWP_SKIPTRANSPARENT`, no `SendMessageW`, `PostMessageW` present, self-HWND guard present
- [ ] Extend `tests/test_shapes_smoke.py` from 50 cycles to 100 cycles + interleaved resize (guards against Pitfall F regression)

*Framework install: none needed — pytest already in `requirements-dev.txt` from Phase 1.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Click injection reaches Notepad | LAYT-02 (deferred) | Cross-process HWND resolution cannot be simulated without a live Win32 message pump | Open Notepad, position bubble over it, click middle zone, verify cursor appears in Notepad |
| Click injection reaches Cornerstone | LAYT-02 (deferred) | Custom Cornerstone controls may ignore PostMessage — clinic hardware required | Clinic PC only: click through bubble over Cornerstone field, verify input received |
| Shape cycle no crash over 60 s | CTRL-02, CTRL-03 | HRGN ownership (Pitfall F) stress requires live SetWindowRgn traffic | Tap shape button repeatedly for 60 s; no crash, no GDI leak |
| Resize smooth by finger | CTRL-06, CTRL-07 | Touch latency requires physical touchscreen | Drag resize grip on clinic touchscreen; motion is smooth, size updates live |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
