---
phase: 04-controls-shape-resize
verified: 2026-04-13T00:00:00Z
status: passed
score: 9/9 requirements verified
---

# Phase 4: Controls, Shape Cycle, Resize Verification Report

**Phase Goal:** Deliver all Phase 4 controls — drag strip with grip glyph, shape-cycle button, zoom buttons, live zoom text, resize drag, and cross-process click-through injection. All 9 CTRL requirements must be satisfied.
**Verified:** 2026-04-13
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Pure controls module exposes ButtonRect, layout_controls, hit_button, SHAPE_CYCLE, zoom_step, resize_clamp | VERIFIED | `src/magnifier_bubble/controls.py` exists, 93 lines, zero banned imports; 23 unit tests pass |
| 2 | All button rects >= 44x44 for w=h=150 and w=h=700 (CTRL-09) | VERIFIED | `test_button_rects_all_44x44_min_at_150` and `test_button_rects_all_44x44_min_at_700` pass |
| 3 | SHAPE_CYCLE maps circle->rounded->rect->circle exactly (CTRL-02) | VERIFIED | `SHAPE_CYCLE` literal in controls.py; `test_shape_cycle_dict` passes |
| 4 | zoom_step clamps to [1.5, 6.0] and snaps to 0.25 grid (CTRL-05) | VERIFIED | zoom_step uses math.floor/ceil; 6 zoom tests pass including clamp and snap edge cases |
| 5 | resize_clamp clamps both axes to [150, 700] (CTRL-08) | VERIFIED | `resize_clamp` in controls.py; 4 clamp tests pass including independent-axes case |
| 6 | Top drag strip shows grip glyph (U+2261) and shape button (U+25CE); top strip is draggable (CTRL-01, CTRL-02) | VERIFIED | window.py lines 252-271 create grip text + shape button Canvas items; `_on_canvas_press` routes drag; structural tests pass |
| 7 | Bottom strip shows zoom buttons ([−] U+2212, [+] U+002B), live zoom text ("N.NNx"), resize button (U+2922); tapping updates state (CTRL-04, CTRL-05, CTRL-06) | VERIFIED | window.py lines 273-322 create all bottom-strip Canvas items; `_on_canvas_press` dispatches to zoom_step/set_zoom; structural lint tests pass |
| 8 | Resize button press+drag+release calls resize_clamp and root.geometry; NO SendMessageW (CTRL-06, CTRL-07, CTRL-08) | VERIFIED | `_on_canvas_drag` computes resize via resize_clamp; SendMessageW/HTBOTTOMRIGHT absent; `test_resize_button_drag` and `test_resize_clamp_on_drag_motion` pass |
| 9 | inject_click posts WM_LBUTTONDOWN+WM_LBUTTONUP via PostMessageW; self-HWND guard; ScreenToClient for lParam; --no-click-injection CLI flag (CTRL LAYT-02 close) | VERIFIED | `src/magnifier_bubble/clickthru.py` exists, 117 lines; all 15 test_clickthru tests pass; app.py has argparse --no-click-injection |

**Score:** 9/9 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/magnifier_bubble/controls.py` | Pure-Python control layout + helpers | VERIFIED | 93 lines; `@dataclass(frozen=True) ButtonRect`, layout_controls, hit_button, SHAPE_CYCLE, zoom_step, resize_clamp; zero tkinter/ctypes/win32gui imports confirmed by AST scan |
| `tests/test_controls.py` | 21+ unit tests for CTRL-02/05/08/09 | VERIFIED | 150 lines; 23 tests; all pass (`23 passed, 0.12s`) |
| `src/magnifier_bubble/window.py` | BubbleWindow with Phase 4 controls wired | VERIFIED | 697 lines (>320 minimum); imports controls.py; all button Canvas items created; observer registered; resize drag wired; strip_top/strip_bottom on every apply_shape call |
| `tests/test_window_phase4.py` | Integration tests with real assertions | VERIFIED | 561 lines (>180 minimum); 17 tests; contains test_grip_glyph_drawn_centered; 0 skip stubs remaining for Phase 4 tests (1 skip only for the Windows-only fixture guard on non-Windows) |
| `src/magnifier_bubble/clickthru.py` | inject_click via PostMessageW + ChildWindowFromPointEx | VERIFIED | 117 lines (>80 minimum); inject_click signature correct; CWP_SKIPTRANSPARENT + ScreenToClient + PostMessageW all present; no SendMessageW; no PyDLL |
| `src/magnifier_bubble/winconst.py` | Phase 4 CWP_SKIP* + MK_LBUTTON + WM_LBUTTONUP constants | VERIFIED | 83 lines; CWP_SKIPTRANSPARENT=0x0004, CWP_SKIPINVISIBLE=0x0001, CWP_SKIPDISABLED=0x0002, MK_LBUTTON=0x0001, WM_LBUTTONUP=0x0202 all present |
| `tests/test_clickthru.py` | Structural lint + Windows smoke for click injection | VERIFIED | 249 lines (>120 minimum); 15 tests; all pass |
| `src/magnifier_bubble/app.py` | argparse --no-click-injection wired into BubbleWindow | VERIFIED | argparse present; `--no-click-injection` flag; `click_injection_enabled=not args.no_click_injection` |
| `tests/test_shapes_smoke.py` | 100-cycle interleaved resize smoke test | VERIFIED | 234 lines; `test_apply_shape_100_cycle_interleaved_resize_no_crash` present at line 208; `range(100)` confirmed |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `window.py` | `controls.py` | `from magnifier_bubble.controls import ButtonRect, SHAPE_CYCLE, hit_button, layout_controls, resize_clamp, zoom_step` | WIRED | Line 45-52; exactly 1 import block |
| `window.py` | `state.py` | `self.state.on_change(self._on_state_change)` | WIRED | Line 397; `_on_state_change` defined at line 520 |
| `window.py` | `shapes.py` | `shapes.apply_shape(...)` with strip_top + strip_bottom | WIRED | 3 call sites (lines 365, 535, 544); all 3 pass strip_top=DRAG_STRIP_HEIGHT + strip_bottom=CONTROL_STRIP_HEIGHT (strip-aware HRGN fix ae1a072) |
| `_on_canvas_press` | `controls.hit_button` | `btn = hit_button(event.x, event.y, self._buttons)` | WIRED | Line 438; dispatches shape/zoom_in/zoom_out/resize by name |
| `window.py` | `clickthru.py` | deferred import inside content-zone handler: `from magnifier_bubble.clickthru import inject_click` | WIRED | Lines 476-477; guarded by `_click_injection_enabled and sys.platform == "win32"` |
| `app.py` | `window.py` | `BubbleWindow(state, click_injection_enabled=not args.no_click_injection)` | WIRED | Line 54 in app.py |
| `clickthru.py` | `ctypes.windll.user32.ChildWindowFromPointEx` | Lazy _u32() binding + CWP_SKIPTRANSPARENT flag | WIRED | Lines 49-51, 96-98 in clickthru.py |
| `clickthru.py` | `ctypes.windll.user32.PostMessageW` | Two posts: WM_LBUTTONDOWN then WM_LBUTTONUP | WIRED | Lines 110-111; `PostMessageW` count = 4 in source (2 argtypes + 2 call sites) |
| `controls.py` | `hit_test.py` | DRAG_BAR_HEIGHT=44 redeclared (not imported) | WIRED | Line 19 in controls.py; `DRAG_BAR_HEIGHT: int = 44` |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CTRL-01 | 04-02 | Grip indicator (≡) + draggable top bar | SATISFIED | Grip glyph U+2261 created at line 252 window.py; drag-start in `_on_canvas_press` line 456; `test_grip_glyph_drawn_centered` passes on Windows |
| CTRL-02 | 04-01, 04-02 | Shape-cycle button (⊙) circles Circle→Rounded→Rect→Circle | SATISFIED | SHAPE_CYCLE dict in controls.py; shape button U+25CE at line 269 window.py; `self.state.set_shape(SHAPE_CYCLE[cur_shape])` line 441; structural tests pass |
| CTRL-03 | 04-02 | SetWindowRgn; HRGN not freed after successful call | SATISFIED | shapes.apply_shape owns HRGN; `DeleteObject` absent from window.py (grep confirmed 0 matches); structural test `test_shape_cycle_calls_apply_shape_no_deleteobject` passes |
| CTRL-04 | 04-02 | Bottom strip [−] and [+] with live zoom display | SATISFIED | U+2212, "+", zoom text Canvas items at lines 273-308 window.py; `itemconfig` zoom update in `_on_state_change` line 552; `test_zoom_buttons_and_text_display` passes |
| CTRL-05 | 04-01, 04-02 | Zoom 1.5x–6x in 0.25x steps | SATISFIED | zoom_step in controls.py; ZOOM_MIN=1.5, ZOOM_MAX=6.0, ZOOM_STEP=0.25; all 6 zoom unit tests pass |
| CTRL-06 | 04-02 | Resize button [⤢] bottom-right drag-to-resize | SATISFIED | Resize button U+2922 at line 320 window.py; `_resize_origin` state machine in `_on_canvas_press`/`_on_canvas_drag`; `test_resize_button_drag` passes |
| CTRL-07 | 04-02 | Window corner grip secondary resize via drag | SATISFIED | `_on_canvas_drag` handles resize via `_resize_origin`; `root.geometry()` moves bottom-right corner with top-left fixed; covered by `test_resize_button_drag` |
| CTRL-08 | 04-01, 04-02 | Minimum 150x150, maximum 700x700 | SATISFIED | `resize_clamp` in controls.py; MIN_SIZE=150, MAX_SIZE=700; `_on_canvas_drag` calls `resize_clamp(raw_w, raw_h)`; `test_resize_clamp_on_drag_motion` verifies both bounds pass |
| CTRL-09 | 04-01 | All touch targets minimum 44x44px | SATISFIED | DRAG_BAR_HEIGHT=44, CONTROL_BAR_HEIGHT=44; layout_controls returns 4 rects all 44x44; `test_button_rects_all_44x44_min_at_150` and `test_button_rects_all_44x44_min_at_700` pass |

**All 9 CTRL requirements satisfied.**

---

### Notable Fixes Delivered in Phase 4

**Strip-aware HRGN fix (commit ae1a072, referenced in window.py line 358):**
shapes.apply_shape was extended with `strip_top` and `strip_bottom` parameters that CombineRgn-union the shape clip with full-width strip rectangles. Without this fix, cycling to "circle" clipped the corner buttons (shape/zoom/resize) out of the HRGN, making them invisible and non-hittable. Every `shapes.apply_shape(` call in window.py passes both kwargs — confirmed by grep (3 calls, 3 strip_top, 3 strip_bottom matches). Structural lint `test_window_passes_strip_heights_to_apply_shape` guards this.

**Python 3.14 PhotoImage regression fix (commit c756a92):**
`ImageTk.PhotoImage(...)` calls pass `master=self.root` in both the constructor (line 224-226) and the resize rebuild path (line 643). This prevents cross-interpreter GC crashes in Python 3.14 when the PhotoImage is created in one interpreter context and used in another.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | — |

No TODO/FIXME/placeholder/stub anti-patterns found in Phase 4 files. No `return null` / empty implementations detected. No `SendMessageW` or `tk.Button` in window.py.

---

### Pre-Existing Deferred Items (NOT Phase 4 regressions)

These were documented in `deferred-items.md` before Phase 4 started and are confirmed as pre-existing:

1. `tests/test_window_integration.py::test_source_has_pattern_2b_drag_workaround` — Phase 2 structural lint now semantically obsolete after Phase 3's SendMessageW removal. Fails identically on the Phase 3 commit before any Phase 4 edits. Not a Phase 4 regression.
2. Full-suite `pytest tests/` Tk-churn errors (23 errors) — pre-existing since Phase 2/3; Python 3.14 + Tk 8.6 instability when multiple test modules construct separate `tk.Tk()` roots in the same process. Phase 4 isolated mitigation: `test_window_phase4.py` uses a module-scoped fixture (17/17 pass in isolation).

---

### Human Verification Required

The following behaviors are fully wired in code but require a running Windows session to confirm visually:

1. **Grip glyph centered alignment**
   - Test: Run the app on Windows; observe that the ≡ glyph appears horizontally centered in the left portion of the top strip (not overlapping the shape button)
   - Expected: Teal ≡ visible left-of-center; ⊙ shape button in top-right 44px
   - Why human: Pixel-exact centering depends on font metrics of "Segoe UI Symbol" at size 20 on the clinic display

2. **Shape cycle visual transition**
   - Test: Tap the ⊙ button three times; verify circle → rounded → rect → circle
   - Expected: Window outline changes shape each tap; shape clips correctly without losing corner buttons
   - Why human: SetWindowRgn visual output cannot be verified headlessly

3. **Resize drag feel on clinic touchscreen**
   - Test: Press-drag the ⤢ button; verify the window resizes smoothly and clamps at 150/700
   - Expected: Bottom-right corner follows finger; top-left stays fixed; snaps to clamp limits
   - Why human: Touch event latency and coordinate accuracy require physical interaction

4. **Click-through to Cornerstone via PostMessageW**
   - Test: Position bubble over Cornerstone; tap in the content zone; verify click lands in Cornerstone
   - Expected: Cornerstone responds to the click; bubble does not absorb it
   - Why human: Requires live Cornerstone session; PostMessageW delivery depends on target message pump

---

### Test Execution Summary

| Suite | Command | Result |
|-------|---------|--------|
| Pure math unit tests | `pytest tests/test_controls.py -x -q` | 23 passed in 0.12s |
| Phase 4 structural + Windows integration | `pytest tests/test_window_phase4.py tests/test_clickthru.py -x -q` | 32 passed in 0.43s |
| All pure-Python unit tests (no Tk window) | `pytest tests/ -q` (excluding capture_smoke, shapes_smoke, window_integration) | 175 passed in 2.30s |
| Combined Phase 4 + core | `pytest tests/test_controls.py tests/test_window_phase4.py tests/test_clickthru.py tests/test_winconst.py tests/test_state.py tests/test_hit_test.py tests/test_dpi.py tests/test_main_entry.py -q` | 146 passed in 1.79s |
| controls.py purity (AST scan) | Python AST walk for banned imports | PASS — BANNED IMPORTS: set() |

---

_Verified: 2026-04-13_
_Verifier: Claude (gsd-verifier)_
