# Phase 5: Config Persistence - Research

**Researched:** 2026-04-13
**Domain:** Debounced atomic JSON config persistence for a single-user Tk Windows 11 app, with graceful shutdown flush
**Confidence:** HIGH — every load-bearing claim grounded in (a) Python's own stdlib docs for `json`, `os.replace`, `tempfile`, `sys.executable`; (b) Tk `after` / `after_cancel` primitives already in use elsewhere in the project; (c) the existing committed source in `src/magnifier_bubble/` (`state.py`, `window.py`, `app.py`); (d) Phase 4 research's observer + Tk-main-thread discipline which Phase 5 extends unchanged. Two MEDIUM-confidence areas flagged: **Windows `os.replace` atomicity is "usually" but not "guaranteed" atomic** (MoveFileEx may silently fall back to copy on failure per a Microsoft employee statement referenced by the `atomicwrites` library) and **`%LOCALAPPDATA%` fallback location for the config file under clinic IT lockdown of the `%PROGRAMFILES%` install path** (flagged as concern in STATE.md; not yet verified against actual clinic policy).

---

## Summary

Phase 5 wires persistence into Ultimate Zoom: **on every `AppState` mutation (position, size, zoom, shape) debounce a 500 ms write of `config.json`; on launch load that file and pre-populate the initial `StateSnapshot`; on `WM_DELETE_WINDOW` flush any pending timer before destroying the root.** Every Win32 and threading primitive Phase 5 needs already exists — `AppState.on_change` (Phase 1 observer), `root.after` / `root.after_cancel` (Tk stdlib), `self.destroy` hook on `WM_DELETE_WINDOW` (installed at `window.py:386`), and `sys.executable` / `sys.frozen` (PyInstaller runtime). **Phase 5 adds pure-Python I/O — NO new Win32 surface, NO new threads, NO new ctypes, NO new third-party dependencies.**

The shape of the work is small and well-contained: one new module (`config.py`, ~120 lines), one new observer registered on `AppState` (the debounce-and-write observer, registered alongside the Phase 4 visual observer), and a ~15-line change in `app.py` to load config before constructing `AppState` + flush on shutdown. The `StateSnapshot` dataclass in `state.py:20-30` is already JSON-compatible (int / float / str / bool fields only) — `dataclasses.asdict(snap)` + `json.dump` serializes cleanly with zero mapping code, and `StateSnapshot(**json.load(f))` deserializes cleanly.

Three findings the planner must honor:

1. **Debounce the observer callback, not the writer.** Every `state.set_*` call fires `_notify()` synchronously on the Tk main thread. A naive "write on every notify" is WRONG — mashing `[+]` 10 times in 2s writes 10 times and violates success criterion 3. The correct pattern is: the Phase 5 observer schedules `root.after(500, write)` and stores the timer id; on subsequent notifies it calls `root.after_cancel(timer_id)` before rescheduling. Only the final call after 500 ms of quiet writes. This is debounce-trailing (write the LAST value after quiet), not debounce-leading (write the FIRST and ignore the rest).

2. **`WM_DELETE_WINDOW` MUST flush the pending debounce before `root.destroy()`.** `destroy()` tears down Tk, invalidating the timer id. Success criterion 4 requires that the last pending change is persisted. The flush is: if `self._debounce_id is not None` then `root.after_cancel(self._debounce_id)` AND immediately call the write function (synchronously, not scheduled). Order matters: cancel first so the scheduled callback doesn't also fire, then write synchronously so the exit doesn't race the disk write.

3. **Atomic write via `tempfile.NamedTemporaryFile(dir=target.parent, delete=False)` + `flush()` + `os.fsync()` + `os.replace()` — same-directory temp file is non-negotiable.** A temp file in `%TEMP%` crosses filesystem boundaries and makes `os.replace` fall back to non-atomic copy+delete. The temp file MUST live in the config's parent directory so `os.replace` is a same-volume MoveFileEx, which is atomic in the common case. The `flush()` + `os.fsync()` pair pushes Python and OS buffers to the disk controller before rename — without this a power loss between `replace()` and the actual physical flush can leave a zero-length file.

**Primary recommendation:** Build Phase 5 in **two plans**:

- **Plan 05-01 — Pure-Python `config.py` module (unit-testable on any platform):** new `config.py` with `config_path()` (resolves the target file location, handles PyInstaller-frozen + dev-mode + clinic-lockdown-fallback), `load(path) -> StateSnapshot` (graceful handling of missing/corrupt/schema-mismatch files), `write_atomic(path, snap)` (tempfile → flush → fsync → replace pattern), and `ConfigWriter(state, root)` class that encapsulates the debounce timer + observer registration + flush-on-shutdown method. All load/write/debounce logic lives here, testable with `tmp_path` pytest fixtures and a fake Tk `after`/`after_cancel` pair. No Tk imports at module scope — the writer class takes `root` as a constructor argument and uses `root.after` / `root.after_cancel` via instance attribute. Covers PERS-01, PERS-02, PERS-05-atomicity.

- **Plan 05-02 — Wire into `app.py` + `window.py` (integration + manual verification):** `app.py` loads `config.json` before constructing `AppState` (fall back to `StateSnapshot()` defaults on missing/corrupt); constructs `ConfigWriter` after `AppState` is created; registers it on `AppState.on_change`. `window.py`'s `destroy()` gets one new line before WndProc teardown: `self._config_writer.flush_pending()`. Optional: on-close position/size snapshot before destroy (so a "dragged but not committed" resize from `<B1-Motion>` is captured in the final config). Adds a Windows-only smoke test: mash `state.set_zoom` 10 times in a loop with `time.sleep(0.01)`, assert `os.path.getmtime(config_path)` shows one write ≥ 500 ms after the last call, assert `json.load(config_path)` matches the final zoom value. Covers PERS-02-debounce, PERS-03, PERS-04.

---

<user_constraints>
## User Constraints

**No CONTEXT.md exists for this phase.** No `/gsd:discuss-phase` was run before this research; constraints below come from `STATE.md`, `ROADMAP.md`, `REQUIREMENTS.md`, `PROJECT.md`, the user prompt's "additional context" block, and the accumulated Phase 1-4 decisions in `STATE.md:71-128`.

### Locked Decisions (from STATE.md, REQUIREMENTS.md, ROADMAP.md, and Phase 1-4 accumulated context)

- **Stack (pinned Phase 1, unchanged):** Python 3.11.9 target + Python 3.14.3 dev box + tkinter (stdlib) + `mss==10.1.0` + `pywin32==311` + `Pillow==12.1.1` (dev box; 11.3.0 on target is API-compatible) + `numpy==2.2.6`. **No new dependencies in Phase 5.** Everything Phase 5 needs is in the stdlib (`json`, `os`, `tempfile`, `pathlib`, `sys`, `dataclasses`).
- **Project layout:** `src/magnifier_bubble/` flat module src-layout. Phase 5 adds `config.py`. Phase 5 modifies `app.py` (load config + register writer + flush on exit), `window.py` (one-line `destroy()` flush call). Phase 5 must NOT touch `state.py` / `winconst.py` / `hit_test.py` / `wndproc.py` / `shapes.py` / `capture.py` / `controls.py` / `clickthru.py` — those are sealed APIs.
- **`AppState` is the single source of truth.** Phase 5's `ConfigWriter` registers via `AppState.on_change(self._on_change)` (the stable Phase 1 API, already consumed by Phase 4's `BubbleWindow._on_state_change`). The writer NEVER calls `state.set_*` — it is a read-only observer. On config load, `app.py` constructs `AppState(StateSnapshot(**loaded_fields))` once, before any observer exists, so there is no write-during-load reentrancy risk.
- **Thread safety:** `ConfigWriter` lives entirely on the Tk main thread. `root.after` / `root.after_cancel` are documented as Tk-main-thread-only APIs (Tk is not thread-safe). The write happens inside an `after` callback, on the Tk main thread. The synchronous flush on shutdown also happens on the Tk main thread (WM_DELETE_WINDOW handler runs there). No threading.Lock / no Queue / no background thread in Phase 5.
- **Python 3.14 + ctypes hot-path rule:** N/A — Phase 5 has zero ctypes calls. The `PyDLL` rule scoped to WndProc callbacks doesn't apply.
- **File location — PRIMARY:** `config.json` in the same directory as the app's entry point. For dev runs: `os.path.dirname(os.path.abspath(sys.argv[0]))` which resolves to the repo root (where `main.py` lives). For PyInstaller one-file builds: `os.path.dirname(sys.executable)` (the folder containing the `.exe`, NOT `sys._MEIPASS` which is the temp extraction dir). Detection gate: `getattr(sys, 'frozen', False)` — True inside a PyInstaller build, False in dev. This satisfies PERS-01's literal "same directory as the app executable."
- **File location — FALLBACK (STATE.md:139 "Phase 5 / runtime" blocker):** If the primary directory is NOT writable (e.g., clinic IT has installed the `.exe` under `C:\Program Files\` and UAC + ACLs block user writes — which Microsoft documents as the default behavior for `%PROGRAMFILES%` on Windows 11, bypassable only via UAC virtualization which only applies to 32-bit un-manifested apps), fall back to `os.path.join(os.environ["LOCALAPPDATA"], "UltimateZoom", "config.json")` and `os.makedirs(exist_ok=True)`. Probe at startup with a test write to the primary path; on `PermissionError` / `OSError(EACCES|EROFS)`, switch to the fallback for the session. Log which path was chosen (stdout print is fine for Phase 5; Phase 8 can route through a real logger). This is Claude's discretion on detection mechanism but the two-candidate order (primary then `%LOCALAPPDATA%`) is a locked decision from STATE.md.
- **Fields to persist (from PERS-01..04 + success criteria 1-2):** `x: int`, `y: int`, `w: int`, `h: int`, `zoom: float`, `shape: str`. The full persisted set maps 1:1 to six fields of `StateSnapshot`. **`visible` and `always_on_top` are explicitly NOT persisted in Phase 5** — they are Phase 6/7 concerns (HOTK toggles visibility; TRAY toggles always-on-top). Phase 5's load sets `visible=True` and `always_on_top=True` regardless of what's in the file, so a stray field from a future-version config is forward-ignored. Phase 5 writes ONLY the six locked fields.
- **Debounce window (PERS-02):** 500 ms. Success criterion 3 specifies "a single debounced write ~500 ms after the last change." `root.after(500, self._write)` is the canonical implementation. Any value in the range [250, 1000] is defensible but 500 is explicit in the roadmap — use 500.
- **Atomicity (PERS-02 + success criterion 5):** write temp file in SAME directory as target, `flush()` + `os.fsync()`, then `os.replace(tmp, target)`. Success criterion 5 says "pulling the plug or corrupting a write never leaves a broken config.json" — this is the standard "never observe a half-written file" guarantee and `os.replace` is the stdlib-canonical way to get it on Windows (MoveFileEx with MOVEFILE_REPLACE_EXISTING). A broken write falls back to the previously-good file on next launch; a missing file falls back to `StateSnapshot()` defaults.
- **Shutdown flush (PERS-04):** The `WM_DELETE_WINDOW` handler (installed at `window.py:386` as `self.root.protocol("WM_DELETE_WINDOW", self.destroy)`) runs on the Tk main thread. The `destroy()` method at `window.py:668-697` currently does: stop capture worker → uninstall WndProcs → root.destroy. Phase 5 inserts ONE call at the top of the `try:` block: `self._config_writer.flush_pending()`. `flush_pending()` cancels the pending `after` timer if any, then synchronously writes if the state differs from the last-written snapshot. No threading, no join, no timeout.
- **Load behavior on missing / corrupt / partial file (PERS-03 + implicit robustness requirement):** Missing file → use `StateSnapshot()` defaults. `JSONDecodeError` / `UnicodeDecodeError` on read → log-and-use-defaults (do NOT raise; the app must start). Unknown extra fields in the JSON → ignore. Missing expected fields → fill from `StateSnapshot` defaults (i.e., `StateSnapshot(**{**defaults_dict, **loaded_dict_filtered_to_known_fields})`). Out-of-range values (e.g., `zoom: 9.0` outside [1.5, 6.0]; `w: 5000` outside [150, 700]) → `AppState.set_*` clamps on its next write BUT on load we should pre-clamp so the initial `StateSnapshot` is valid (call `_clamp_zoom`, `max(150, min(700, w))`, etc. in `load()`). Invalid shape (not in `("circle", "rounded", "rect")`) → fall back to default `"rect"`.
- **PERS-01..04 coverage:**
  - **PERS-01:** "config.json saved in the same directory as the app executable" — primary path via `sys.executable` / `sys.argv[0]`; fallback to `%LOCALAPPDATA%` only on write-permission failure (decision above).
  - **PERS-02:** "Config is written on every change (position, size, zoom level, shape) using debounce (500 ms) and atomic os.replace()" — observer registered on `AppState.on_change`; 500 ms `root.after` debounce; tempfile → fsync → replace write pattern.
  - **PERS-03:** "On launch, app restores last known position, size, zoom level, and shape from config.json" — `config.load(path)` returns a `StateSnapshot` used to construct `AppState` in `app.py` before `BubbleWindow` is constructed.
  - **PERS-04:** "Config write pending at shutdown is flushed before exit (WM_DELETE_WINDOW handler)" — `BubbleWindow.destroy` calls `self._config_writer.flush_pending()` before `root.destroy()`.

### Claude's Discretion (areas where research recommends but does not mandate)

These are flagged for the planner — pick the simplest safe option, do not over-investigate:

- **Writer encapsulation: `ConfigWriter` class vs. free functions.** Recommend **`ConfigWriter` class** constructed with `(state, root, path)` + three methods: `on_change()` (observer, schedules the debounced write), `_write_now()` (actual tempfile → fsync → replace, called from the scheduled callback), `flush_pending()` (public shutdown hook). The class holds `self._after_id: str | None` and `self._last_written: StateSnapshot | None` as instance state. Free functions would pollute a module global for the timer id; a class is the Python-idiomatic scope for that state.
- **Probe mechanism for "is this directory writable?"** Two options: (a) try to create a `.write_probe` temp file in the primary path and `os.remove` it immediately; (b) `os.access(dir, os.W_OK)` (not reliable on Windows per Python docs — `os.access` checks the UID/mode but Windows uses ACLs and the check can lie). Recommend **(a) write-probe** — it reflects actual write permission including ACLs. Probe happens once at startup (cheap, ~1 ms); caches the chosen path for the session. Failure from the probe means we fall through to `%LOCALAPPDATA%`.
- **Path-resolution function:** Recommend a single `config_path() -> pathlib.Path` function in `config.py` that does primary-probe-then-fallback and returns the chosen path. Callers never construct paths by hand. Makes the decision testable (mock `sys.frozen`, mock `os.access` / the probe write).
- **Debounce semantics — trailing vs. leading:** Recommend **trailing** (schedule on notify; on subsequent notifies cancel-and-reschedule; fire only after 500 ms of quiet). Leading-edge (write immediately, suppress rest) would write the FIRST value in a 10-button-mash instead of the LAST — wrong for zoom where the user's intent is "end at 3.00" not "start at 2.25."
- **Serialization order:** Recommend `json.dump(asdict(snap_subset), f, indent=2, sort_keys=True)` with `sort_keys=True` so the file is deterministic across runs (nicer for git diff review if the user ever inspects it). The 6-field subset (x/y/w/h/zoom/shape) is extracted via a small `_to_dict(snap)` helper rather than `asdict(snap)` wholesale — this is how the planner enforces the "don't leak visible/always_on_top" constraint.
- **Version field in JSON:** Recommend adding `"version": 1` to the written JSON even though we don't branch on it today. Costs 12 bytes; buys forward-compatibility for a hypothetical v2 that e.g. adds multi-monitor per-display geometry. Load path ignores `version` (along with every unknown field); future v2 code can branch on it. If the planner prefers minimalism, dropping the version field is defensible — just document the decision.
- **Quiet on missing file:** First launch has no `config.json`. The load function should silently return `StateSnapshot()` defaults — NOT log a warning, NOT print anything. A missing config is the expected state on first run. Log-or-print only for the CORRUPT case (JSONDecodeError), where the user should know something went wrong.
- **Error logging:** Phase 5 can use `print()` for now; Phase 8 packaging may add structured logging. Keep the prints short and prefixed with `[config]` so they're grep-able: `[config] loaded path=C:\…\config.json zoom=3.00 shape=rect`, `[config] corrupt json at path=…; using defaults`, `[config] write-probe failed at primary path; falling back to %LOCALAPPDATA%`.
- **`_MEIPASS` defense:** For absolute robustness in a PyInstaller one-file build, a defensive assertion in `config_path()` that the returned path's parent is NOT `sys._MEIPASS` (even by accident) would catch a future bug where someone mistakenly uses `__file__` instead of `sys.executable`. Cheap, one-line assertion. Optional but recommended.
- **Pre-clamp on load:** Recommend pre-clamping zoom/w/h values in `load()` before constructing `StateSnapshot` so the loaded state is never invalid. Uses the existing `_clamp_zoom` pattern from `state.py:39-42` (Phase 5 can import and reuse it, or just inline `max(1.5, min(6.0, round(z*4)/4))`).

### Deferred Ideas (OUT OF SCOPE for Phase 5)

These are explicitly later phases — Phase 5 must NOT implement them:

- **Hotkey configuration field** — Phase 6 (HOTK-04 says "Hotkey is configurable in config.json"). Phase 5 does not add a `"hotkey"` field; Phase 6 extends the schema when it lands. Phase 5's load path ignoring unknown fields means Phase 6 can add this freely without breaking Phase 5.
- **`visible` / `always_on_top` persistence** — Phase 6 / Phase 7 concerns; the tray toggle and hotkey toggle own those fields' persistence story if/when we want it. Phase 5 explicitly does NOT persist them.
- **Multi-profile / named configurations** — never requested; out of scope.
- **Config GUI editor / settings dialog** — never requested; out of scope.
- **Auto-save throttle > 500 ms / less frequent writes** — user may wear out SSD if they zoom 1000 times a day; 500 ms debounce means at most 2 writes/sec of active use, which is fine for any modern SSD. No TTL, no batch-flush-every-N-minutes.
- **Config file schema validation with `jsonschema` or `pydantic`** — overkill; manual field-by-field extraction in `load()` with fallbacks is simpler and adds zero dependencies.
- **Encrypted / obfuscated config** — this is a user preference file, not credentials. Plain JSON.
- **Cross-machine sync (Roaming AppData vs. Local AppData)** — clinic PC is single-machine; `%LOCALAPPDATA%` is correct (not `%APPDATA%` which would roam).
- **Backup / `.bak` rotation** — the atomic replace plus the always-present defaults fallback mean a single corrupt write loses at most one session's changes. Adding `.bak` rotation doubles the I/O and doesn't meaningfully improve safety for a preference file. If the user ever asks, Phase 5b can add it in five lines. Not for v1.
- **File locking against concurrent processes** — there is one `main.py` process at a time; no lock needed. `fcntl` is Unix-only anyway.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PERS-01 | config.json saved in the same directory as the app executable | `config_path()` — primary via `os.path.dirname(sys.executable)` for frozen builds + `os.path.dirname(os.path.abspath(sys.argv[0]))` for dev, fallback to `%LOCALAPPDATA%\UltimateZoom\` on write-probe failure (Pattern 2 below). Handles the STATE.md:139 "clinic IT may block app-directory writes" concern. |
| PERS-02 | Config is written on every change (position, size, zoom level, shape) using debounce (500 ms) and atomic os.replace() | `ConfigWriter` class registered via `AppState.on_change` (Pattern 3); `root.after(500, ...)` trailing-edge debounce with `after_cancel` on re-trigger (Pattern 4); tempfile → flush → fsync → `os.replace` atomic write pattern (Pattern 1). |
| PERS-03 | On launch, app restores last known position, size, zoom level, and shape from config.json | `config.load(path) -> StateSnapshot` with graceful missing-file / JSONDecodeError / out-of-range-value handling + pre-clamping via `_clamp_zoom`; app.py constructs `AppState(load(config_path()))` before `BubbleWindow`. |
| PERS-04 | Config write pending at shutdown is flushed before exit (WM_DELETE_WINDOW handler) | `ConfigWriter.flush_pending()` called at the top of `BubbleWindow.destroy()` (existing `window.py:668-697`), before capture worker stop and WndProc teardown. Cancels the pending timer (if any), then synchronously writes if state differs from last-written snapshot. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `json` (stdlib) | Python 3.11 | Read/write the `config.json` file | The canonical stdlib mapping to a human-readable text config. Zero dependencies. `json.dump(..., indent=2, sort_keys=True)` produces diff-friendly output. |
| `os` (stdlib) | Python 3.11 | `os.replace`, `os.fsync`, `os.makedirs`, `os.environ`, `os.path.dirname`, `os.access` (limited) | `os.replace` is the stdlib-canonical atomic-rename on Windows (MoveFileEx with MOVEFILE_REPLACE_EXISTING) and POSIX. `os.fsync(fd)` pushes kernel buffers to the disk controller before the rename. |
| `tempfile` (stdlib) | Python 3.11 | `tempfile.NamedTemporaryFile(dir=target.parent, delete=False)` for the staging file | Produces a guaranteed-unique temp filename in the TARGET directory (not `%TEMP%`), which is required for `os.replace` to be atomic (same filesystem). `delete=False` keeps the file after close so `os.replace` can rename it. |
| `pathlib` (stdlib) | Python 3.11 | `pathlib.Path` for path construction, `Path.parent`, `Path.exists()` | Replaces `os.path.join` with a typed, cross-platform Path API. No functional gain on Windows-only code but cleaner signatures. |
| `sys` (stdlib) | Python 3.11 | `sys.executable`, `sys.argv[0]`, `getattr(sys, 'frozen', False)`, `sys._MEIPASS` (guard only) | `sys.frozen` is the PyInstaller runtime attribute that distinguishes dev mode from a frozen `.exe`. `sys.executable` in a frozen build is the path to the `.exe` itself — its parent is where `config.json` must live. |
| `dataclasses` (stdlib) | Python 3.11 | `asdict(snap)` for JSON-ready serialization | `StateSnapshot` is a dataclass with only JSON-compatible scalar fields — `asdict` gives us a plain dict with no custom `__dict__` tricks. |
| `tkinter` (stdlib, already used) | Python 3.11 | `root.after(delay, callback)`, `root.after_cancel(id)` | Canonical Tk debounce primitive. Main-thread-only. Returns an opaque id string. |

### Supporting
None. Phase 5 needs zero new libraries — every primitive is in the standard library and Tk stdlib is already imported by `window.py` / `app.py`.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib `json` + hand-rolled atomic write | `atomicwrites` (PyPI, 1.4.0, maintenance mode) | Adds a dependency (violates "no new deps in Phase 5" + Phase 1 lock). `atomicwrites` notes that its own Windows atomic guarantee is "best effort" — identical to what we get from `os.replace` directly. **Rejected.** |
| stdlib `json` | `tomllib` (stdlib, read-only) / `tomli-w` (3rd party write) | TOML is nice for human-edited config but users of Ultimate Zoom will never hand-edit this file. JSON is simpler, already used by the `gsd` tooling in `.planning/`, and pystray-era Python apps all ship JSON config. **Rejected.** |
| `root.after(500, write)` debounce | `threading.Timer` + lock + queue marshaling | A Timer thread would fire the callback off-main-thread, which then has to marshal back via `root.after(0, ...)` — exactly the pattern Phase 3 eliminated (the 3.14 GIL/PyEval crash path per STATE.md:141 and the `feedback_python314_ctypes_gil.md` memory entry). `root.after` stays on-main-thread-only and avoids the entire category of bugs. **Rejected.** |
| Write on every notify (no debounce) | N/A | Violates PERS-02's "debounce" clause and success criterion 3 ("not 10 writes"). **Rejected explicitly.** |
| `shutil.move` | `os.replace` | `shutil.move` falls back to copy+delete on cross-filesystem moves — if the temp file accidentally landed in `%TEMP%` (different volume from the config dir) this would silently become non-atomic. `os.replace` raises on cross-filesystem, making the bug impossible to hide. **`os.replace` wins.** |
| `os.rename` | `os.replace` | `os.rename` errors if target exists on Windows (unlike POSIX where it overwrites). `os.replace` explicitly overwrites on all platforms. This is a Windows correctness bug if you use `os.rename`. **`os.replace` wins.** |
| `config.json` in app dir (primary) | `%LOCALAPPDATA%\UltimateZoom\config.json` (always) | PERS-01 explicitly says "in the same directory as the app executable." The fallback to LOCALAPPDATA is for clinic IT lockdown only, not the default path. |

**Installation:**
No new packages. Everything is stdlib + already-pinned dependencies in `requirements.txt`.

**Version verification:**
Not applicable — all stdlib. Target runtime is `python>=3.11` per Phase 1 pin (verified against Python 3.11.9 locally: `python --version` → `Python 3.11.9`). `os.replace` landed in Python 3.3 (2012); `tempfile.NamedTemporaryFile(delete=False)` landed in 2.6. No version risk.

## Architecture Patterns

### Recommended Project Structure
```
src/magnifier_bubble/
├── config.py         # NEW — path resolution, load, atomic write, ConfigWriter
├── app.py            # MODIFIED — load config → AppState → construct writer → register observer
├── window.py         # MODIFIED — one-line flush_pending() call in destroy()
├── state.py          # UNCHANGED — StateSnapshot is already JSON-serializable
└── (all other modules unchanged)

tests/
├── test_config.py    # NEW — path resolution, load edge cases, atomic write, debounce
└── conftest.py       # UNCHANGED — existing tk_session_root fixture works
```

### Pattern 1: Atomic JSON Write — tempfile + fsync + replace

**What:** Write to a staging file in the target's parent directory, flush Python buffers, fsync to disk, then atomically rename over the target.

**When to use:** Every config write. Never use `open(path, 'w').write(...)` directly — a crash between truncation and flush leaves a zero-length config.

**Why:** `os.replace` on the same filesystem maps to `rename(2)` on POSIX (atomic) and `MoveFileEx(MOVEFILE_REPLACE_EXISTING)` on Windows (atomic in the common case — see "Common Pitfalls" for the edge case). The `flush()` + `os.fsync()` pair guarantees that on a hard-power-loss, either the old file or the new file is observable, never a half-written one.

**Example:**
```python
# Source: stdlib docs (os.replace, tempfile.NamedTemporaryFile, os.fsync)
#         + DEV Community "Crash-safe JSON at scale" production pattern
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

def write_atomic(path: Path, snap: StateSnapshot) -> None:
    """Atomically write the persisted subset of snap to path.

    tempfile in SAME DIRECTORY → flush → fsync → os.replace.
    If anything fails before the replace, the target file is
    untouched. After the replace, the target is the new content.
    There is no observable intermediate state.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    persisted = {
        "version": 1,
        "x": snap.x,
        "y": snap.y,
        "w": snap.w,
        "h": snap.h,
        "zoom": snap.zoom,
        "shape": snap.shape,
    }
    # NamedTemporaryFile MUST be in the target's parent directory
    # so os.replace is same-volume (atomic).
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as tf:
        json.dump(persisted, tf, indent=2, sort_keys=True)
        tf.flush()
        os.fsync(tf.fileno())
        tmp_name = tf.name
    os.replace(tmp_name, str(path))
```

### Pattern 2: Path Resolution with Fallback

**What:** Resolve the config file location by trying the primary path (app exe directory) and falling back to `%LOCALAPPDATA%` on write-probe failure.

**When to use:** Once per process, at startup. Cache the result for the lifetime of the process.

**Why:** PERS-01 specifies "same directory as the app executable" but STATE.md:139 flags that clinic IT may lock down `%PROGRAMFILES%`. A write-probe at startup catches this without assuming anything about IT policy; falls back gracefully.

**Example:**
```python
# Source: Python stdlib docs (sys.executable, os.environ, pathlib)
#         + PyInstaller 6.19.0 Run-time Information docs (sys.frozen, sys._MEIPASS)
import os
import sys
from pathlib import Path

_APP_NAME = "UltimateZoom"

def _app_dir() -> Path:
    """Return the directory the app's entry point lives in.

    - Frozen (PyInstaller one-file .exe): parent of sys.executable.
      sys.executable is the .exe itself; dirname(exe) is the folder
      the user put it in. NOT sys._MEIPASS (that's a temp extract).
    - Dev mode (python main.py): parent of sys.argv[0], which is
      main.py at the repo root.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(sys.argv[0]).resolve().parent

def _is_writable(directory: Path) -> bool:
    """Probe by creating and immediately removing a tiny test file.
    os.access(..., W_OK) lies on Windows with ACLs; actual write-probe
    is the only reliable check.
    """
    if not directory.exists():
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
    probe = directory / ".uz_write_probe"
    try:
        probe.write_text("", encoding="utf-8")
    except OSError:
        return False
    try:
        probe.unlink()
    except OSError:
        pass  # leaked probe is cosmetic
    return True

def config_path() -> Path:
    """Resolve the config.json location.

    1. Try the app directory (PERS-01 primary).
    2. Fall back to %LOCALAPPDATA%\UltimateZoom\ if the primary
       is not writable (STATE.md:139 clinic IT lockdown concern).
    """
    primary = _app_dir() / "config.json"
    if _is_writable(primary.parent):
        return primary
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        fallback_dir = Path(local_appdata) / _APP_NAME
        return fallback_dir / "config.json"
    # Last resort: ~/.UltimateZoom/config.json — should never hit
    # this on Windows but don't crash if LOCALAPPDATA is unset.
    return Path.home() / f".{_APP_NAME}" / "config.json"
```

### Pattern 3: Observer-driven Debounced Write (ConfigWriter)

**What:** Register a callback on `AppState.on_change`; on every change, cancel the pending `root.after` timer and schedule a new one for 500 ms out.

**When to use:** Exactly once per process, registered after `AppState` is constructed and before `BubbleWindow` is constructed (so no early state change is missed).

**Why:** PERS-02 requires debounced writes. The canonical Tk debounce uses `root.after_cancel` + `root.after` on the main thread — no extra threads needed. Follows the same observer pattern as Phase 4's visual redraw.

**Example:**
```python
# Source: Python tkinter stdlib docs (after, after_cancel)
#         + tkinter.after debounce pattern (pythonguides, pythontutorial)
#         + existing AppState.on_change contract in state.py:54
import tkinter as tk
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from magnifier_bubble.state import AppState, StateSnapshot

_DEBOUNCE_MS = 500

class ConfigWriter:
    """Debounced config persistence observer.

    Registered on AppState.on_change. On every notify, cancels any
    pending after-timer and schedules a fresh 500 ms one. The timer's
    callback writes the current snapshot atomically.

    flush_pending() is the shutdown hook: cancels the timer and writes
    synchronously if the current state differs from the last write.
    """

    def __init__(self, state: AppState, root: tk.Tk, path: Path) -> None:
        self._state = state
        self._root = root
        self._path = path
        self._after_id: Optional[str] = None
        self._last_written: Optional[StateSnapshot] = None

    def register(self) -> None:
        self._state.on_change(self._on_change)

    def _on_change(self) -> None:
        """Runs on the Tk main thread (AppState observers fire from the
        thread that called state.set_*; Phase 4 guarantees that's
        always the Tk main thread for user-initiated changes)."""
        if self._after_id is not None:
            self._root.after_cancel(self._after_id)
        self._after_id = self._root.after(_DEBOUNCE_MS, self._write_now)

    def _write_now(self) -> None:
        self._after_id = None
        snap = self._state.snapshot()
        if snap == self._last_written:
            return
        try:
            write_atomic(self._path, snap)  # Pattern 1
            self._last_written = snap
        except OSError as exc:
            # Swallow — next change will retry. Log for diagnosis.
            print(f"[config] write failed path={self._path} err={exc}", flush=True)

    def flush_pending(self) -> None:
        """Called from WM_DELETE_WINDOW (BubbleWindow.destroy).

        Cancels the pending timer (if any) and writes synchronously if
        the state has diverged from the last successful write. Safe to
        call multiple times. Safe to call if no writes ever happened.
        """
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except tk.TclError:
                pass  # root may already be gone in edge cases
            self._after_id = None
        # Synchronous final write
        self._write_now()
```

### Pattern 4: Load with Graceful Degradation

**What:** Load `config.json` into a `StateSnapshot`; on any failure (missing, corrupt, partial, out-of-range) fall back to defaults for the affected fields.

**When to use:** Exactly once, at `app.py` main() entry, BEFORE `AppState` is constructed.

**Why:** PERS-03 restores last state. The app must always start — a broken config must never prevent launch. Out-of-range values must be clamped on load so the initial state is valid.

**Example:**
```python
# Source: Python stdlib json docs (JSONDecodeError handling)
#         + existing state.py _clamp_zoom + _VALID_SHAPES
import json
from dataclasses import fields
from pathlib import Path
from magnifier_bubble.state import StateSnapshot

_VALID_SHAPES = ("circle", "rounded", "rect")
_ZOOM_MIN, _ZOOM_MAX, _ZOOM_STEP = 1.5, 6.0, 0.25
_SIZE_MIN, _SIZE_MAX = 150, 700

def _clamp_zoom(z: float) -> float:
    z = max(_ZOOM_MIN, min(_ZOOM_MAX, float(z)))
    return round(z / _ZOOM_STEP) * _ZOOM_STEP

def _clamp_size(n: int) -> int:
    return max(_SIZE_MIN, min(_SIZE_MAX, int(n)))

def load(path: Path) -> StateSnapshot:
    """Load a StateSnapshot from path. NEVER raises.

    - Missing file       → StateSnapshot() defaults, silent.
    - JSONDecodeError    → StateSnapshot() defaults, logged.
    - Unknown fields     → ignored.
    - Missing fields     → filled from StateSnapshot() defaults.
    - Out-of-range vals  → clamped to valid ranges.
    - Invalid shape      → default "rect".
    """
    if not path.exists():
        return StateSnapshot()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        print(f"[config] corrupt json at path={path} err={exc}; using defaults", flush=True)
        return StateSnapshot()
    if not isinstance(raw, dict):
        print(f"[config] root is not an object at path={path}; using defaults", flush=True)
        return StateSnapshot()
    defaults = StateSnapshot()
    x = int(raw.get("x", defaults.x))
    y = int(raw.get("y", defaults.y))
    w = _clamp_size(raw.get("w", defaults.w))
    h = _clamp_size(raw.get("h", defaults.h))
    zoom = _clamp_zoom(raw.get("zoom", defaults.zoom))
    shape = raw.get("shape", defaults.shape)
    if shape not in _VALID_SHAPES:
        shape = defaults.shape
    return StateSnapshot(x=x, y=y, w=w, h=h, zoom=zoom, shape=shape)
```

### Pattern 5: Wiring in app.py

**What:** Load config → construct AppState → construct ConfigWriter → register observer → construct BubbleWindow → pass writer to BubbleWindow so destroy can flush.

**When to use:** `main()` startup sequence, in the order shown.

**Why:** AppState must exist before the writer registers; the writer must register before BubbleWindow is constructed (so any state mutation during window construction is debounced correctly, though in practice Phase 4 construction only reads state); BubbleWindow needs the writer reference for `destroy()`'s flush call.

**Example:**
```python
# Source: existing app.py structure + config.py APIs above
import argparse
import os
import sys
from magnifier_bubble import config, dpi
from magnifier_bubble.state import AppState
from magnifier_bubble.window import BubbleWindow

def main() -> int:
    parser = argparse.ArgumentParser(description="Ultimate Zoom")
    parser.add_argument("--no-click-injection", action="store_true")
    args = parser.parse_args()

    dpi.debug_print()

    # Phase 5: resolve config path + load persisted snapshot
    path = config.config_path()
    snap = config.load(path)
    print(f"[config] loaded path={path} zoom={snap.zoom:.2f} shape={snap.shape}", flush=True)

    state = AppState(snap)

    bubble = BubbleWindow(
        state,
        click_injection_enabled=not args.no_click_injection,
    )

    # Phase 5: wire the debounced writer
    writer = config.ConfigWriter(state, bubble.root, path)
    writer.register()
    bubble.attach_config_writer(writer)  # so destroy() can flush_pending()

    if sys.platform == "win32":
        bubble.start_capture()
    if os.environ.get("ULTIMATE_ZOOM_SMOKE") == "1":
        bubble.root.after(50, bubble.destroy)
    bubble.root.mainloop()
    return 0
```

**BubbleWindow.destroy minimal diff:**
```python
def destroy(self) -> None:
    try:
        # Phase 5 addition — flush pending config write BEFORE
        # Tk teardown, so root.after_cancel still has a live root.
        if self._config_writer is not None:
            self._config_writer.flush_pending()
        # ... existing capture stop + wndproc uninstall ...
    finally:
        try:
            self.root.destroy()
        except tk.TclError:
            pass
```

### Anti-Patterns to Avoid

- **Writing on every notify with no debounce:** violates PERS-02 and success criterion 3. Mashing `[+]` 10× writes 10×. Always debounce.
- **Using `threading.Timer` for the debounce:** re-introduces the off-main-thread → `root.after(0, ...)` pattern Phase 3 eliminated for crash reasons (STATE.md:141, memory entry `feedback_python314_ctypes_gil.md`). Use `root.after` exclusively.
- **Temp file in `%TEMP%` / `tempfile.gettempdir()`:** different filesystem from the target on Windows clinic PCs (temp is usually on C:, but users install portable apps on D: removable media). `os.replace` will fail with EXDEV. ALWAYS pass `dir=path.parent` to `NamedTemporaryFile`.
- **`open(path, 'w')` + `json.dump` without the tempfile dance:** the `'w'` mode truncates the target FIRST. A crash between truncate and flush leaves a zero-length config. NEVER write in-place.
- **Forgetting `os.fsync()`:** `flush()` alone moves bytes from Python buffers into kernel buffers, not to disk. A power loss between `flush()` and `os.replace` can still corrupt. `os.fsync(fileno)` forces the kernel to push to the disk controller.
- **Not cancelling the pending `after` in `flush_pending`:** if the timer fires AFTER `destroy()` starts tearing down Tk, `root.after_cancel` becomes illegal. Always cancel first, THEN call `_write_now` directly.
- **Persisting `visible` / `always_on_top`:** Phase 5 scope excludes them. Writing them now locks in behavior Phase 6/7 might want to control differently.
- **Calling `state.set_*()` from the writer:** creates an infinite observer loop (same re-entrancy bug Phase 4 called out as "Pitfall G"). The writer is read-only.
- **Using `os.rename` instead of `os.replace`:** `os.rename` errors on existing target on Windows (Python docs explicit). `os.replace` is the correct overwriting variant.
- **Putting `config.json` in `sys._MEIPASS`:** the PyInstaller one-file temp dir is wiped on exit. Data written there is LOST. Always resolve via `sys.executable` / `sys.argv[0]`.
- **Using `os.access(path, os.W_OK)` on Windows:** Python docs note it does not reliably reflect ACLs. Actual write-probe (create-and-delete a test file) is the only correct detection.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic file replacement | Write-to-target-then-pray | `tempfile.NamedTemporaryFile(dir=parent, delete=False)` + `flush()` + `os.fsync()` + `os.replace()` | Any other pattern has a crash-window that corrupts the config. This exact 4-step recipe is what `atomicwrites` and every production crash-safe JSON writer distills to. |
| JSON schema validation | Bespoke `if 'zoom' in raw and 1.5 <= raw['zoom'] <= 6.0 ...` spider | Field-by-field `raw.get(key, default)` + `_clamp_*` helpers (Pattern 4) | Graceful degradation field-by-field is 10 lines; `jsonschema` is a dep; `pydantic` is a dep. For 6 scalar fields the hand-rolled version is clearer and more testable. |
| Debounce timer | `threading.Timer` + lock + queue | `root.after(ms, cb)` + `root.after_cancel(id)` | `after` is Tk-native, main-thread-only, trivially cancelable, and produces zero threading bugs. `Timer` fires off-thread and needs marshaling back — the exact pattern that broke on Python 3.14. |
| Path construction | String concat `+ "\\config.json"` | `pathlib.Path / "config.json"` | Typed, cross-platform, immutable, and `Path.parent` / `Path.exists()` are one-liner safe ops. |
| Write-permission check | `os.access(dir, os.W_OK)` | Try to write a `.write_probe` file and delete it | `os.access` on Windows does not see ACLs per Python stdlib docs. A probe-write is the only truthful check. |
| App-directory resolution | `os.getcwd()` | `sys.executable` (frozen) / `sys.argv[0]` (dev) + `.parent` | `getcwd()` reflects whatever directory the user launched from (Start menu → system32), not where the exe lives. |
| Temporary file naming | `str(uuid.uuid4())` + hand-rolled path | `tempfile.NamedTemporaryFile(prefix=name, suffix=".tmp", dir=parent, delete=False)` | Guaranteed unique, stdlib, `delete=False` keeps it for rename, `dir=` puts it in the right place. |

**Key insight:** Phase 5 is about composing stdlib primitives correctly, not building anything novel. Every single pattern above is a 40-year-old Unix idiom that the stdlib has mapped onto Windows correctly via `os.replace` (MoveFileEx) and `os.fsync`. Hand-rolled "save config" code is one of the most common sources of production data corruption in GUI apps — the distance between "works on my laptop" and "atomic under power loss on a clinic PC with BitLocker and a write-through SSD" is measured in these four lines of boilerplate.

## Common Pitfalls

### Pitfall 1: Debounce-without-cancel ("multi-timer loop")

**What goes wrong:** Writer schedules `root.after(500, write)` on every notify. Ten notifies in 2s schedule ten timers. Five timers fire in the 500-800 ms window, writing five times instead of once.

**Why it happens:** Forgetting the cancel step on re-trigger. `root.after` does NOT replace prior schedules — it adds a new one.

**How to avoid:** ALWAYS call `self._root.after_cancel(self._after_id)` before `self._after_id = self._root.after(...)`. Store the id; cancel-then-schedule is the canonical debounce pattern.

**Warning signs:** `os.path.getmtime(config.json)` updates multiple times within 500 ms after a burst. Test: loop `state.set_zoom(1.5 + 0.25*i)` 10 times with `time.sleep(0.01)`; assert mtime delta from last call to write is ≥ 500 ms AND ≤ 700 ms, and file content shows the 10th zoom value, not an intermediate.

### Pitfall 2: Cross-filesystem tempfile breaks atomicity

**What goes wrong:** `tempfile.NamedTemporaryFile()` with no `dir=` argument uses `tempfile.gettempdir()` which returns `%TEMP%` (usually `C:\Users\X\AppData\Local\Temp`). If `config.json` lives on `D:\` (USB stick) or `E:\` (mapped drive), `os.replace(tmp, target)` fails with `OSError: [WinError 17]` (cannot move across volumes).

**Why it happens:** `os.replace` only guarantees atomicity for SAME-FILESYSTEM renames. `MoveFileEx` on Windows either succeeds atomically or errors — no fallback.

**How to avoid:** ALWAYS pass `dir=path.parent` to `NamedTemporaryFile`. The staging file must live in the target's parent directory.

**Warning signs:** `OSError: [WinError 17]` on write, even though the write "worked" during dev testing (dev environment has config in a single-volume local repo).

### Pitfall 3: Windows `os.replace` "atomic usually" caveat

**What goes wrong:** On Windows, `os.replace` maps to `MoveFileEx(MOVEFILE_REPLACE_EXISTING)`. The `atomicwrites` library author quotes a Microsoft employee (Doug Cook) saying `MoveFileEx` is "usually" atomic when same-drive, "but in some cases it will silently fall back to a non-atomic method" — specifically when the rename fails for an internal reason and the OS downgrades to `CopyFile` (which is NOT atomic).

**Why it happens:** Low-level filesystem driver behavior (BitLocker, ReFS, SMB shares, antivirus real-time scanners holding file handles). Rare but real.

**How to avoid:** Accept this as MEDIUM-confidence risk for our use case. For Ultimate Zoom's single-user clinic-PC use case, this degrades-but-doesn't-corrupt: the worst case is a brief window where both old and new content coexist on disk, but the API-level contract is preserved (the target file, when observable, is always a valid JSON — either old or new). For our HIGH-stakes-ness level (a preference file for a single user), this is acceptable. If Phase 5 ever needed stronger guarantees, the escape hatch is `pywin32` + `MoveFileTransactedW` (deprecated in Windows 11 but still present) or a hand-rolled two-phase commit with a `.bak` rotation.

**Warning signs:** Corrupt config.json on next launch after a hard power loss during a write. Mitigation: the load path already falls back to defaults on JSONDecodeError — so a rare corruption degrades to "reverted to defaults," which is recoverable and non-catastrophic.

### Pitfall 4: `flush()` without `os.fsync()` loses data on power loss

**What goes wrong:** `file.flush()` moves bytes from Python's internal buffer into the kernel page cache. It does NOT push them to the disk controller. A power loss between `flush()` and `os.replace` can leave the renamed file empty on disk even though `replace` "succeeded."

**Why it happens:** Modern OSes lazily write dirty pages to the disk driver. `fsync` is the only way to force the page cache to the platter (or SSD flash).

**How to avoid:** ALWAYS call `os.fsync(tf.fileno())` AFTER `tf.flush()` and BEFORE `os.replace`.

**Warning signs:** Empty or zero-byte `config.json` after a power loss / forced reboot. Load path treats this as JSONDecodeError and reverts to defaults — so you might not notice, but the symptom is "zoom level forgot itself after power outage."

### Pitfall 5: `%LOCALAPPDATA%` fallback silently missing

**What goes wrong:** Some Windows environments (Microsoft Store apps, containers, locked-down enterprise) don't expose `LOCALAPPDATA` in `os.environ`. Your fallback expects it, crashes on `os.environ["LOCALAPPDATA"]` with `KeyError`.

**Why it happens:** Environment variables are per-session and the parent process may not export all user-level vars.

**How to avoid:** Use `os.environ.get("LOCALAPPDATA")` (not bracket-access), check for None, fall further back to `Path.home() / ".UltimateZoom" / "config.json"`.

**Warning signs:** `KeyError: 'LOCALAPPDATA'` on startup in a locked-down environment.

### Pitfall 6: PyInstaller one-file write to `sys._MEIPASS` — LOST data

**What goes wrong:** Developer uses `os.path.dirname(__file__)` or `sys._MEIPASS` for the config path, thinking it's the app directory. In a PyInstaller one-file build, both resolve to a temp directory (`C:\Users\X\AppData\Local\Temp\_MEIxxxxxx`) that gets WIPED by the bootloader on process exit. All writes are lost.

**Why it happens:** PyInstaller 6.x documentation explicitly notes: "assumptions that `os.path.dirname(sys.executable) == sys._MEIPASS` will break." The moved-to-_internal change broke a lot of code that was "working" before 6.0.

**How to avoid:** For user-facing persistent files, ALWAYS use `sys.executable` (not `__file__`, not `sys._MEIPASS`). An optional defensive assertion: `assert sys._MEIPASS not in path.parents` (if running frozen).

**Warning signs:** Config never persists across launches despite `os.path.exists(path)` returning True during a single session.

### Pitfall 7: Flush-on-shutdown races the Tk teardown

**What goes wrong:** Flush logic is `root.after(0, write_now)` (scheduling) instead of calling `_write_now()` directly. `root.destroy` executes before the scheduled callback fires. Write never happens.

**Why it happens:** Treating the shutdown flush as another "event" to schedule. Shutdown is not an event — it's the end of events.

**How to avoid:** `flush_pending` calls `_write_now()` SYNCHRONOUSLY (not via `root.after`). The sync call is safe because we're already on the Tk main thread (WM_DELETE_WINDOW handler runs there).

**Warning signs:** Closing the app mid-zoom-mash loses the final zoom value. Test: set zoom to 3.00, then close within 500 ms, then relaunch — should see 3.00 not defaults.

### Pitfall 8: Observer re-entrancy (calling `set_*` from the writer)

**What goes wrong:** Writer calls `state.set_zoom(snap.zoom)` in its callback (e.g., to "normalize" the value). This triggers another notify → another scheduled write → etc. Infinite observer loop; Tk hangs.

**Why it happens:** Same "Pitfall G" Phase 4 documented for the visual redraw observer. Anyone registering on `AppState.on_change` must treat `state.set_*` as OFF-LIMITS inside their callback.

**How to avoid:** Writer only READS state (`state.snapshot()`). Never writes. Documented in the class docstring + enforced by a structural lint test that greps `config.py` for `state.set_` and fails if found.

**Warning signs:** App hangs in an `after` loop that never returns; CPU spikes to 100%. Never observed if the writer is truly read-only.

### Pitfall 9: Config file contains `visible: false` → bubble never shows

**What goes wrong:** Phase 5 persists `visible` accidentally. User closes the app while bubble was hidden via Phase 6 hotkey (future). Next launch reads `visible=False` and never shows the bubble. User thinks the app is broken.

**Why it happens:** Overeager scope creep — persisting fields that are "easy" because StateSnapshot has them, even though they're not in PERS-01..04.

**How to avoid:** Phase 5's `_to_dict(snap)` extracts EXACTLY the 6 locked fields (x/y/w/h/zoom/shape). Never `asdict(snap)` wholesale. Load path does NOT read `visible` or `always_on_top` from the file; they always come from `StateSnapshot` defaults on construction.

**Warning signs:** Bubble invisible on launch after tray hide.

### Pitfall 10: Write-probe leaves `.uz_write_probe` behind

**What goes wrong:** The probe test file fails to delete (e.g., antivirus scanner opened it between create and unlink). User sees a mystery file in their app folder.

**Why it happens:** Windows doesn't guarantee file delete after close; AV products commonly hold read handles briefly.

**How to avoid:** Wrap the `probe.unlink()` in `try/except OSError: pass`. A leaked probe file is cosmetic — next startup will overwrite and attempt delete again. Optional: delete any stale `.uz_write_probe` on startup before the probe.

**Warning signs:** User reports mystery file. Low-impact.

## Code Examples

### Full `config.py` skeleton (load + write + writer class)

```python
# Source: Synthesis of all patterns above. Imports stdlib only.
"""Phase 5: Config Persistence.

Debounced atomic writer for Ultimate Zoom's position/size/zoom/shape state.
Stdlib-only. Main-thread-only. No ctypes, no threads, no dependencies.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import tkinter as tk
from dataclasses import fields
from pathlib import Path
from typing import Optional

from magnifier_bubble.state import AppState, StateSnapshot

_APP_NAME = "UltimateZoom"
_CONFIG_FILENAME = "config.json"
_DEBOUNCE_MS = 500
_SCHEMA_VERSION = 1
_PERSISTED_FIELDS = ("x", "y", "w", "h", "zoom", "shape")
_VALID_SHAPES = ("circle", "rounded", "rect")
_ZOOM_MIN, _ZOOM_MAX, _ZOOM_STEP = 1.5, 6.0, 0.25
_SIZE_MIN, _SIZE_MAX = 150, 700

# ... (patterns 2, 4, 1, 3 inlined in order) ...
```

### Unit-test sketches (pytest-friendly)

```python
# Source: synthesized from patterns; uses pytest tmp_path + monkeypatch.
import json
import os
import time
import pytest
from pathlib import Path
from magnifier_bubble import config
from magnifier_bubble.state import AppState, StateSnapshot

def test_load_missing_file_returns_defaults(tmp_path):
    path = tmp_path / "config.json"
    snap = config.load(path)
    assert snap == StateSnapshot()

def test_load_corrupt_json_returns_defaults(tmp_path, capsys):
    path = tmp_path / "config.json"
    path.write_text("not json {", encoding="utf-8")
    snap = config.load(path)
    assert snap == StateSnapshot()
    assert "corrupt json" in capsys.readouterr().out

def test_load_out_of_range_zoom_is_clamped(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"zoom": 99.0, "x": 0, "y": 0, "w": 400, "h": 400, "shape": "rect"}))
    snap = config.load(path)
    assert snap.zoom == 6.0

def test_load_invalid_shape_falls_back_to_rect(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"shape": "hexagon", "x": 0, "y": 0, "w": 400, "h": 400, "zoom": 2.0}))
    snap = config.load(path)
    assert snap.shape == "rect"

def test_write_atomic_produces_valid_json(tmp_path):
    path = tmp_path / "config.json"
    snap = StateSnapshot(x=100, y=200, w=300, h=400, zoom=3.0, shape="circle")
    config.write_atomic(path, snap)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["x"] == 100
    assert loaded["zoom"] == 3.0
    assert loaded["shape"] == "circle"
    assert "visible" not in loaded   # Pitfall 9 guard
    assert "always_on_top" not in loaded

def test_write_atomic_no_tempfile_leaks(tmp_path):
    path = tmp_path / "config.json"
    snap = StateSnapshot()
    config.write_atomic(path, snap)
    leaked = [p for p in tmp_path.iterdir() if p.name.startswith("config.json.")]
    assert leaked == []

def test_writer_debounce_produces_single_write(tmp_path, tk_session_root):
    # tk_session_root is the conftest fixture from Phase 2-02
    path = tmp_path / "config.json"
    state = AppState(StateSnapshot())
    writer = config.ConfigWriter(state, tk_session_root, path)
    writer.register()
    for i in range(10):
        state.set_zoom(1.5 + 0.25 * i)
    # Nothing written yet — debounce hasn't fired
    assert not path.exists()
    # Drain pending after callbacks for 700 ms
    deadline = time.monotonic() + 0.7
    while time.monotonic() < deadline:
        tk_session_root.update_idletasks()
        tk_session_root.update()
    # One file; final zoom value persisted
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["zoom"] == pytest.approx(3.75)  # 1.5 + 0.25*9

def test_flush_pending_writes_synchronously(tmp_path, tk_session_root):
    path = tmp_path / "config.json"
    state = AppState(StateSnapshot())
    writer = config.ConfigWriter(state, tk_session_root, path)
    writer.register()
    state.set_zoom(3.5)
    # Before debounce would fire:
    assert not path.exists()
    writer.flush_pending()
    # Synchronously written:
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["zoom"] == 3.5
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `os.rename` then manually delete old on Windows | `os.replace` (stdlib, Python 3.3+) | 2012 (Python 3.3) | Correct overwrite on Windows without extra code. |
| Hand-rolled `threading.Timer` debounce | `root.after` + `root.after_cancel` in Tk apps | Always (Tk 8.0+) | Main-thread safety; no GIL re-entrancy. |
| `tempfile.mktemp()` (race-prone) | `tempfile.NamedTemporaryFile(dir=..., delete=False)` | Python 2.3+ | No race window; portable; controllable delete. |
| ConfigParser for app settings | JSON with stdlib `json` | Trend since ~2015 | Better for nested structures, cross-language, human-readable, works with web tooling. |
| `%APPDATA%` (roaming) for per-user config | `%LOCALAPPDATA%` (local) for machine-specific | Win Vista+ pattern | Roaming is for cross-device sync; magnifier bubble geometry is machine-specific (screen layout). |
| `os.access(path, os.W_OK)` permission check | Write-probe (create/delete test file) | Always preferred on Windows | `os.access` doesn't see ACLs; probe is truthful. |
| `atomicwrites` library | stdlib `os.replace` + same-dir tempfile | Python 3.3+ made the lib redundant | No dep; equivalent guarantees; less code. |

**Deprecated/outdated:**
- `os.rename(src, dst)` on Windows where dst exists — errors out instead of replacing. Always use `os.replace` for replacement semantics.
- `sys._MEIPASS` for persistent data — the one-file temp dir gets wiped on exit. Always use `sys.executable` for user-visible files.
- `os.path.join(os.path.dirname(__file__), "config.json")` in frozen builds — resolves to a temp extract dir in PyInstaller ≥ 6.0. Always use `sys.executable` / `sys.argv[0]`.
- `atomicwrites` PyPI library — maintenance mode since 2022; stdlib equivalents cover all use cases for this phase.

## Open Questions

1. **Does `os.replace` on a BitLocker-encrypted Windows 11 volume maintain the "usually atomic" guarantee, or does BitLocker interpose in a way that triggers the `CopyFile` silent fallback?**
   - What we know: MoveFileEx + MOVEFILE_REPLACE_EXISTING is atomic in the common case. BitLocker is transparent to userland file APIs.
   - What's unclear: whether BitLocker's sector-level encryption adds latency that makes MoveFileEx prefer a fallback under load.
   - Recommendation: ACCEPT risk for Phase 5. Worst case is a brief window of dual-content; the load path's JSONDecodeError fallback recovers to defaults. If the clinic ever reports config corruption after power loss, Phase 5b can add `.bak` rotation (5-line add).

2. **Does the clinic IT policy actually block writes to `%PROGRAMFILES%\UltimateZoom\` for the deploy account?**
   - What we know: STATE.md:139 flags this as a concern. Microsoft Learn documents that standard users lack write access to `%PROGRAMFILES%` by default.
   - What's unclear: clinic-specific group policy; whether the `.exe` will be installed there vs. per-user via `%LOCALAPPDATA%\Programs\` or `Desktop`.
   - Recommendation: Ship the `%LOCALAPPDATA%` fallback from day one (Pattern 2). The write-probe makes the path choice invisible to the user. Test both paths in Plan 05-02 on the Windows dev box by running once from `%USERPROFILE%\Desktop\` and once from a manually-readonly'd dir.

3. **Should first-ever launch (no config.json) write defaults immediately, or wait for the first user action?**
   - What we know: PERS-02 says "on every change" — first-launch-no-change is literally no change.
   - What's unclear: UX — some users expect to see the file appear in the directory as proof the app is working.
   - Recommendation: Wait for first change. Writing defaults is wasteful IO and also confusing (why is there a config.json with the exact defaults?). Phase 5 plan can document this as a feature: "config.json appears after your first interaction."

4. **For PyInstaller one-file builds, should we bake a minimal default config.json as a bundled resource (via `--add-data`)?**
   - What we know: We could ship a default config.json inside `sys._MEIPASS` as a read-only template.
   - What's unclear: adds complexity; duplicates StateSnapshot defaults in two places (Python code + JSON file).
   - Recommendation: NO — the Python-side `StateSnapshot` defaults are the single source of truth. A bundled JSON adds drift risk. Phase 5 / Phase 8 should NOT bundle a template.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest >= 8.0` (already in `requirements-dev.txt`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `pythonpath = ["src"]`, `testpaths = ["tests"]` |
| Quick run command | `pytest tests/test_config.py -x --tb=short` |
| Full suite command | `pytest -x` |
| Phase 5 Windows smoke | `pytest tests/test_config_smoke.py -x` (gated with `@pytest.mark.skipif(sys.platform != "win32")`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| PERS-01 | config.json path = app dir primary, LOCALAPPDATA fallback | unit | `pytest tests/test_config.py::test_config_path_primary_writable -x` | NO (Wave 0) |
| PERS-01 | LOCALAPPDATA fallback on probe failure | unit | `pytest tests/test_config.py::test_config_path_falls_back_on_write_probe_failure -x` | NO (Wave 0) |
| PERS-01 | `sys._MEIPASS` guard (frozen detection) | unit | `pytest tests/test_config.py::test_app_dir_frozen_uses_sys_executable -x` | NO (Wave 0) |
| PERS-02 | Atomic write — no half-state observable | unit | `pytest tests/test_config.py::test_write_atomic_produces_valid_json -x` | NO (Wave 0) |
| PERS-02 | Temp file cleaned up on success | unit | `pytest tests/test_config.py::test_write_atomic_no_tempfile_leaks -x` | NO (Wave 0) |
| PERS-02 | `visible` / `always_on_top` NOT persisted (Pitfall 9) | unit | `pytest tests/test_config.py::test_write_atomic_omits_deferred_fields -x` | NO (Wave 0) |
| PERS-02 | Debounce 500 ms produces one write per burst | integration (Tk) | `pytest tests/test_config.py::test_writer_debounce_produces_single_write -x` | NO (Wave 0) |
| PERS-02 | `after_cancel` re-trigger pattern (Pitfall 1) | unit (mock Tk) | `pytest tests/test_config.py::test_writer_cancels_pending_on_retrigger -x` | NO (Wave 0) |
| PERS-03 | Load missing file → defaults, silent | unit | `pytest tests/test_config.py::test_load_missing_file_returns_defaults -x` | NO (Wave 0) |
| PERS-03 | Load corrupt JSON → defaults, logged | unit | `pytest tests/test_config.py::test_load_corrupt_json_returns_defaults -x` | NO (Wave 0) |
| PERS-03 | Out-of-range zoom clamped | unit | `pytest tests/test_config.py::test_load_out_of_range_zoom_is_clamped -x` | NO (Wave 0) |
| PERS-03 | Out-of-range size clamped | unit | `pytest tests/test_config.py::test_load_out_of_range_size_is_clamped -x` | NO (Wave 0) |
| PERS-03 | Invalid shape → default rect | unit | `pytest tests/test_config.py::test_load_invalid_shape_falls_back_to_rect -x` | NO (Wave 0) |
| PERS-03 | Unknown extra field ignored | unit | `pytest tests/test_config.py::test_load_ignores_unknown_fields -x` | NO (Wave 0) |
| PERS-03 | Partial file (missing fields) merged with defaults | unit | `pytest tests/test_config.py::test_load_partial_file_merges_with_defaults -x` | NO (Wave 0) |
| PERS-04 | `flush_pending` writes synchronously | integration (Tk) | `pytest tests/test_config.py::test_flush_pending_writes_synchronously -x` | NO (Wave 0) |
| PERS-04 | `flush_pending` idempotent (safe to double-call) | unit | `pytest tests/test_config.py::test_flush_pending_idempotent -x` | NO (Wave 0) |
| PERS-04 | `flush_pending` does nothing if state unchanged | unit | `pytest tests/test_config.py::test_flush_pending_skips_unchanged_state -x` | NO (Wave 0) |
| Structural | No `state.set_` in `config.py` (Pitfall 8) | lint | `pytest tests/test_config.py::test_config_does_not_call_state_set -x` | NO (Wave 0) |
| Structural | `config.py` uses `os.replace` (not `os.rename`) | lint | `pytest tests/test_config.py::test_config_uses_os_replace_not_rename -x` | NO (Wave 0) |
| Structural | `config.py` uses `os.fsync` | lint | `pytest tests/test_config.py::test_config_calls_fsync_before_replace -x` | NO (Wave 0) |
| Structural | No `threading.Timer` import in `config.py` (Pitfall debounce) | lint | `pytest tests/test_config.py::test_config_no_threading_timer -x` | NO (Wave 0) |
| Smoke (Win only) | Real Tk debounce with `root.after` on Windows dev box | integration | `pytest tests/test_config_smoke.py -x -m windows` | NO (Wave 0) |
| Integration | `app.py` main() loads config before constructing AppState | integration | `pytest tests/test_main_entry.py::test_app_loads_config_before_state -x` | Wave 0 extension |

### Sampling Rate
- **Per task commit:** `pytest tests/test_config.py -x --tb=short` (unit tests, ~0.5 s)
- **Per wave merge:** `pytest -x` (full suite including Phase 1-4 regression, ~8-12 s)
- **Phase gate:** Full suite green + manual verification on Windows dev box (5-step: change state → close → relaunch → state restored; kill mid-debounce → relaunch → last change persisted; cover `%PROGRAMFILES%` lockdown case by chmod'ing the repo dir)

### Wave 0 Gaps
- [ ] `tests/test_config.py` — unit tests for load / write_atomic / ConfigWriter (~20 tests per table above)
- [ ] `tests/test_config_smoke.py` — Windows-only integration smoke (debounce, flush on shutdown, atomic write under fsync)
- [ ] `tests/test_main_entry.py` — add one test asserting `app.py main()` calls `config.load` before `AppState(...)` construction (scan-based AST test, same technique as Phase 1 P03's DPI-before-import test)
- [ ] Optional: `tests/conftest.py` — reuse existing `tk_session_root` fixture; may add a `tmp_config_path` fixture that builds `tmp_path / "config.json"` and cleans up on teardown

*(Framework install: none needed — `pytest >= 8.0` already in `requirements-dev.txt`.)*

## Sources

### Primary (HIGH confidence)

- **Python stdlib docs — `os.replace`, `os.fsync`, `os.rename`:** https://docs.python.org/3/library/os.html
  - Atomic-rename semantics + cross-filesystem error behavior + MoveFileEx mapping on Windows.
- **Python stdlib docs — `tempfile.NamedTemporaryFile`:** https://docs.python.org/3/library/tempfile.html
  - `dir=` and `delete=False` parameters; staging-file-in-same-directory pattern.
- **Python stdlib docs — `json`:** https://docs.python.org/3/library/json.html
  - `JSONDecodeError` handling; `indent`/`sort_keys` for deterministic output.
- **Python stdlib docs — `sys` (`sys.executable`, `sys.frozen`):** https://docs.python.org/3/library/sys.html
  - Frozen-runtime attributes; canonical executable-path resolution.
- **PyInstaller 6.19.0 Run-time Information:** https://pyinstaller.org/en/stable/runtime-information.html
  - `sys.frozen` detection, `sys._MEIPASS` temp-dir semantics, why `os.path.dirname(sys.executable) != sys._MEIPASS` post-6.0.
- **Project source (state.py, window.py, app.py):** already-committed code that Phase 5 extends:
  - `src/magnifier_bubble/state.py:20-112` — StateSnapshot shape + observer contract.
  - `src/magnifier_bubble/window.py:386` — `root.protocol("WM_DELETE_WINDOW", self.destroy)` install.
  - `src/magnifier_bubble/window.py:668-697` — existing `destroy()` teardown sequence.
  - `src/magnifier_bubble/app.py:47-77` — main() startup; the integration target for Plan 05-02.

### Secondary (MEDIUM confidence)

- **DEV Community — "Crash-safe JSON at scale: atomic writes + recovery without a DB":** https://dev.to/constanta/crash-safe-json-at-scale-atomic-writes-recovery-without-a-db-3aic
  - Production-validated tempfile + flush + fsync + replace pattern with `.bak` rotation (we adopt without bak for v1).
- **python-atomicwrites 1.4.0 docs (library + caveats):** https://python-atomicwrites.readthedocs.io/
  - Microsoft Doug Cook quote on MoveFileEx "usually atomic" caveat; documents the fcntl-is-Unix-only limitation for our Windows-only target.
- **Tkinter `after` / `after_cancel` pattern guides:**
  - https://www.pythontutorial.net/tkinter/tkinter-after/
  - https://pythonguides.com/python-tkinter-after-method/
  - Canonical debounce pattern (store id, cancel-then-schedule).
- **Microsoft Learn — UAC Virtualization + Program Files ACLs:** https://learn.microsoft.com/en-us/archive/blogs/mrsnrub/uac-virtualization-allowing-standard-users-to-update-a-system-protected-area
  - Documents why `%PROGRAMFILES%` writes fail for standard users; validates the LOCALAPPDATA-fallback rationale in STATE.md:139.
- **Microsoft Learn — User Account Control settings and configuration:** https://learn.microsoft.com/en-us/windows/security/application-security/application-control/user-account-control/settings-and-configuration
  - UAC virtualization limitations (32-bit-only, un-manifested, not-admin) — applies to our 64-bit PyInstaller build and rules out UAC virtualization as a workaround.

### Tertiary (LOW confidence — flagged for validation)

- **ActiveState Code Recipe 579097 "Safely and atomically write to a file":** https://code.activestate.com/recipes/579097-safely-and-atomically-write-to-a-file/
  - Reference pattern; sanity-check only.
- **GitHub `python-atomicwrites` source:** https://github.com/untitaker/python-atomicwrites
  - Implementation reference; we do NOT depend on it.
- **GitHub issue python/cpython #8828 "Atomic function to rename a file":** https://bugs.python.org/issue8828
  - Historical context for why `os.replace` is the stdlib-sanctioned atomic-rename API.

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — all stdlib, already locked in Phase 1 pins, zero new dependencies.
- Architecture (debounce + observer + atomic write): **HIGH** — every primitive is used elsewhere in the project (Phase 4 observer pattern, Phase 3 queue-based drain, Phase 1 AppState contract). Pattern 1 is a 20-year-old Unix idiom.
- Path resolution (PyInstaller frozen vs dev): **HIGH** — PyInstaller 6.19.0 docs explicit; dev-mode path is `sys.argv[0]`.
- Fallback to `%LOCALAPPDATA%`: **MEDIUM** — the pattern is standard (Microsoft Learn-backed), but STATE.md's concern that clinic IT blocks the app dir is unverified until actual deploy. The write-probe auto-detects, so we're safe either way.
- Windows `os.replace` atomicity: **MEDIUM** — "usually atomic" per Microsoft's own Doug Cook, with documented silent-fallback-to-CopyFile in rare cases. For our preference-file use case the load-path-graceful-degradation makes this an acceptable MEDIUM risk.
- Pitfalls: **HIGH** — every pitfall is either documented in Python stdlib, observed elsewhere in the project (Pitfall 7/8 = Phase 4 Pitfall G re-entrancy), or attested by multiple production sources.

**Research date:** 2026-04-13
**Valid until:** 2026-05-13 (30 days — stack is stable; PyInstaller major releases could shift `sys._MEIPASS` semantics but 6.0 already did and we account for it)

---
*Researched by gsd-researcher for Phase 5: Config Persistence. Next step: planner consumes this RESEARCH.md + produces 05-01-PLAN.md (pure-Python config.py module) and 05-02-PLAN.md (integration + manual checkpoint).*
