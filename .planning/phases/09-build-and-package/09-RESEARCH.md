# Phase 9: Build and Package - Research

**Researched:** 2026-04-17
**Domain:** PyInstaller 6.11.1 single-file EXE, build.bat, README authoring, GitHub push
**Confidence:** HIGH (PyInstaller already installed in .venv; existing spec already builds a working EXE; all module imports verified against installed packages)

---

## Summary

Phase 9 is primarily an integration and documentation phase, not a new-feature phase. The PyInstaller spec (`naomi_zoom.spec`) already exists and already produces a working single-file `NomisLens.exe` (28–29 MB, built April 17 2026). The existing EXE includes all Phase 1–8 code and was built successfully from the current spec. The three implementation gaps are narrow and well-defined:

1. **Two missing `hiddenimports`**: `PIL._tkinter_finder` and `win32timezone` are specified in BULD-02 but absent from the current spec. Both modules exist in the venv (`PIL._tkinter_finder: EXISTS`, `win32timezone: EXISTS`). Adding them is a two-line spec edit.

2. **No `build.bat`**: The build command (`pyinstaller naomi_zoom.spec --noconfirm`) must be wrapped in a `build.bat` script that activates the venv and runs in the repo root. This is a ~10-line script.

3. **No `README.md` and no GitHub push**: A plain-English README must be written for non-technical clinic staff. The git remote (`origin`) points to `https://github.com/fresh-start-git/NomisLens.git` — the actual active repo. The REQUIREMENTS.md mentions `Ultimate-Zoom.git` as the target, but the live remote is `NomisLens.git`. The planner must treat `NomisLens.git` as the authoritative target. There are 31 commits ahead of the remote that need to be pushed.

The EXE already runs on Windows 11 with no Python installed (the existing `dist/NomisLens.exe` was hand-verified during Phase 8). The `.gitignore` correctly excludes `dist/`, `build/`, `config.json`, and `theme.json`. The `naomi_zoom.spec` is already tracked in git. The test suite stands at 294 tests.

**Primary recommendation:** One plan is sufficient. Wave 0: add two hiddenimports to spec + create build.bat. Wave 1: write README.md + push to GitHub. No new Python modules. No new test files needed (existing `test_clickthru.py::test_debug_log_disabled` already guards the production-mode requirement; the build.bat and README are not Python code).

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BULD-01 | requirements.txt with pinned versions provided | Already exists and is tracked in git. `requirements.txt` pins 7 packages (mss 10.1.0, dxcam 0.3.0, pywin32 311, Pillow 12.1.1, numpy 2.2.6, pystray 0.19.5, pyinstaller 6.11.1). No changes needed. |
| BULD-02 | .spec file includes hiddenimports=['pystray._win32', 'PIL._tkinter_finder', 'win32timezone'] and upx=False | `pystray._win32` and `upx=False` already in spec. `PIL._tkinter_finder` and `win32timezone` are missing — two-line addition. |
| BULD-03 | build.bat compiles app to single portable .exe | No `build.bat` exists yet. Must activate venv, run `pyinstaller naomi_zoom.spec --noconfirm`. |
| BULD-04 | Output .exe runs on clinic PC without Python installed | Existing `dist/NomisLens.exe` (built April 17) already verified working. Rebuild after spec fix will produce the final artifact. |
| BULD-05 | README.md with plain-English setup for non-technical user | No `README.md` exists yet. Must cover: install Python 3.11, install deps, run from source, run the .exe, AV allowlist note. |
| BULD-06 | Code pushed to GitHub repo | 31 commits are ahead of `origin/master`. Remote is `https://github.com/fresh-start-git/NomisLens.git`. Must push full source tree + spec + build.bat + README. |
</phase_requirements>

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyInstaller | 6.11.1 | Bundles Python app to single-file EXE | Already pinned in requirements.txt; installed in .venv; spec already working |
| Python | 3.11.9 | Runtime for development and build | Installed in .venv; clinic README must target 3.11.x |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| PIL._tkinter_finder | (Pillow 12.1.1 internal) | PyInstaller hook that resolves Tk DLL path inside the bundled EXE | Must be in hiddenimports; prevents "no module named PIL._tkinter_finder" crash on startup |
| win32timezone | (pywin32 311) | pywin32 timezone support; imported at runtime by pywin32 internals | Must be in hiddenimports; prevents "Failed to execute script" startup crash on some Windows configs |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyInstaller `--onefile` | `--onedir` | `--onefile` is required (BULD-03: "single portable .exe with no external dependencies"). `--onedir` produces a folder — not portable for clinic staff. |
| `upx=False` | `upx=True` | UPX compression shrinks EXE but triggers false-positive AV detections. REQUIREMENTS.md Out of Scope: "Code signing". AV allowlist is the mitigation; UPX makes that harder. |
| `console=False` | `console=True` | `console=True` opens a CMD window on launch — confusing for clinic staff. |

**Installation:** No new packages needed. All dependencies already in `.venv`.

**Version verification (confirmed against venv):**

```
Python:       3.11.9   (confirmed: .venv/Scripts/python.exe --version)
PyInstaller:  6.11.1   (confirmed: pip show pyinstaller)
PIL._tkinter_finder: EXISTS in venv (confirmed: python -c "import PIL._tkinter_finder")
win32timezone:        EXISTS in venv (confirmed: python -c "import win32timezone")
```

---

## Architecture Patterns

### Recommended Project Structure

```
Naomi Zoom/
├── main.py                   # Entry point (DPI-first — DO NOT change)
├── naomi_zoom.spec           # AMEND: add PIL._tkinter_finder, win32timezone to hiddenimports
├── build.bat                 # NEW: build script for clinic IT
├── README.md                 # NEW: plain-English setup guide
├── requirements.txt          # NO CHANGE: already complete
├── requirements-dev.txt      # NO CHANGE: already complete
└── src/magnifier_bubble/     # NO CHANGE
```

### Pattern 1: build.bat — Venv-Aware Build Script

**What:** A Windows batch file that activates the project venv and runs PyInstaller. Clinic IT runs this once to regenerate the EXE after any update.

**When to use:** Any time a rebuild is needed from source.

**Example:**

```bat
@echo off
REM Build NomisLens.exe — run this from the repo root
REM Requires: Python 3.11 installed, pip install -r requirements.txt already done

cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m PyInstaller naomi_zoom.spec --noconfirm
echo.
echo Build complete. Output: dist\NomisLens.exe
pause
```

**Key choices:**
- `cd /d "%~dp0"` — ensures the script works regardless of working directory (double-click from Explorer).
- `call .venv\Scripts\activate.bat` — uses the project venv, not any system Python.
- `--noconfirm` — suppresses "delete dist?" prompt for unattended builds.
- `pause` — keeps the window open so clinic IT can see the output.

### Pattern 2: naomi_zoom.spec — Minimal Additions Required

**What:** Add two hidden imports to the existing working spec. The spec is already single-file (`EXE` without `COLLECT`), `upx=False`, `console=False`.

**Diff from current spec:**

```python
# In hiddenimports list, after 'pystray._win32':
'PIL._tkinter_finder',   # Pillow/Tk bridge — prevents startup crash in one-file EXE
'win32timezone',          # pywin32 internal — prevents "Failed to execute script" on some Windows
```

**Why `PIL._tkinter_finder`:** When PyInstaller bundles Pillow + tkinter together into a one-file EXE, it extracts to a temp directory. `PIL._tkinter_finder` is a Pillow hook that locates the Tk DLL relative to the bundled layout. Without it, `ImageTk.PhotoImage` raises `RuntimeError: No tk.h found` at startup in the EXE (but not in the development run where the system Tk is on PATH).

**Why `win32timezone`:** pywin32's `win32api` imports `win32timezone` lazily at runtime for timezone operations. PyInstaller does not detect lazy imports. Without it, the EXE raises `ImportError: No module named 'win32timezone'` on first win32api usage on some Windows configurations.

**Confidence:** Both are established PyInstaller + pywin32/Pillow patterns. `pystray._win32` was already added using this same pattern in Phase 8.

### Pattern 3: README.md — Non-Technical User Format

**What:** A plain-English guide for a non-technical clinic administrator. No markdown headers with angle brackets; no code jargon. Sections match the BULD-05 spec exactly.

**Required sections (per BULD-05):**

1. **What is NomisLens?** — One-paragraph description for Naomi's context.
2. **Quick Start (Running the .exe)** — Copy `NomisLens.exe` to desktop, double-click, antivirus note.
3. **Antivirus Allowlist Note** — "Windows SmartScreen or your antivirus may flag NomisLens.exe because it is not code-signed. This is a false positive. To allow it: [steps for SmartScreen bypass, steps for generic AV allowlist]."
4. **Running from Source (for IT)** — Step by step: install Python 3.11, `pip install -r requirements.txt`, `python main.py`.
5. **Building the EXE from Source** — Run `build.bat`.
6. **Keyboard Shortcut** — Ctrl+Alt+Z toggles the bubble.
7. **Configuration** — Brief description of `config.json` placement.

**Tone:** "Double-click `NomisLens.exe` on your desktop." Not "Execute the binary artifact."

### Pattern 4: GitHub Push

**What:** `git push origin master` pushes the 31 accumulated commits (Phases 7 and 8 work) plus Phase 9 additions (spec fix, build.bat, README) to the GitHub remote.

**Repository:** `https://github.com/fresh-start-git/NomisLens.git` (the live remote — confirmed via `git remote -v`). The REQUIREMENTS.md references `Ultimate-Zoom.git` but the actual configured remote is `NomisLens.git`. Use the live remote as-is.

**Files to NOT push:**
- `dist/` — excluded by `.gitignore` (correct; EXE is 29 MB, not suitable for git)
- `build/` — excluded by `.gitignore`
- `config.json` — excluded by `.gitignore`
- `theme.json` — excluded by `.gitignore`
- `zoom_log.txt` — not in `.gitignore`, but should be added before the push

**Files that SHOULD be pushed but may need `.gitignore` review:**
- `.planning/` — currently tracked (all 31 commits include planning docs). Leave as-is.
- `.claude/` — currently untracked (listed in `git status ?? .claude/`). The planner should decide whether to add this. Recommendation: add to `.gitignore`.
- `.remember/` — currently untracked. Add to `.gitignore`.

### Anti-Patterns to Avoid

- **Changing main.py DPI setup for PyInstaller:** `main.py`'s first lines set DPI awareness before any import. Do NOT add any PyInstaller-specific bootstrap code here — it breaks the DPI guarantee.
- **Adding datas= entries for config.json or theme.json:** These are runtime state files written by the app. They are NOT bundled assets. PyInstaller `datas=[]` stays empty.
- **Using `pyinstaller --onefile` CLI flag instead of the spec:** The spec already encodes all settings. Always build via `pyinstaller naomi_zoom.spec`, not `pyinstaller --onefile main.py`.
- **Using `UPX=True`:** AV evasion is a known UPX concern. The spec already has `upx=False`. Do not change this.
- **Omitting `--noconfirm` in build.bat:** Without it, PyInstaller prompts "Remove dist? [y/N]" and the batch script hangs.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Single-file EXE bundling | Custom packaging script, cx_Freeze, Nuitka | PyInstaller 6.11.1 (already pinned) | PyInstaller spec already working; switching would restart the hiddenimports discovery from scratch |
| AV evasion | UPX, code obfuscation | README AV allowlist instructions | Code signing is Out of Scope per REQUIREMENTS.md. The README approach is the documented solution. |
| GitHub release artifact | `gh release create` with binary upload | `git push` only (BULD-06) | BULD-06 requires source push only; no requirement for GitHub Releases. The EXE is NOT pushed (`.gitignore` excludes `dist/`). Clinic gets EXE by building from source via `build.bat`. |

**Key insight:** This phase is 90% documentation and 10% spec surgery. The hard work (PyInstaller integration, hidden imports discovery for dxcam/pystray/pywin32) was done in Phases 7 and 8. Phase 9 closes the remaining two known gaps (`PIL._tkinter_finder`, `win32timezone`) and produces the human-facing artifacts.

---

## Common Pitfalls

### Pitfall B-1: Missing PIL._tkinter_finder causes ImageTk crash in EXE
**What goes wrong:** `RuntimeError: No tk.h found` or `ImportError: No module named PIL._tkinter_finder` when the EXE calls `ImageTk.PhotoImage`.
**Why it happens:** In one-file mode, PyInstaller extracts to a temp dir. Pillow's tkinter bridge uses `PIL._tkinter_finder` to locate the Tk DLL relative to the bundle layout. In development, the system Tk is on PATH and this module is never imported. In the EXE, it must be explicitly included.
**How to avoid:** Add `'PIL._tkinter_finder'` to `hiddenimports` in the spec.
**Warning signs:** App works in `python main.py` but crashes on launch in `NomisLens.exe`.

### Pitfall B-2: win32timezone ImportError in EXE
**What goes wrong:** `ImportError: No module named 'win32timezone'` — typically manifests as "Failed to execute script main" on the PyInstaller bootloader error dialog.
**Why it happens:** pywin32 imports `win32timezone` lazily (not at module load time). PyInstaller's import-graph analysis only sees static imports.
**How to avoid:** Add `'win32timezone'` to `hiddenimports`.
**Warning signs:** EXE fails to start; error dialog visible in Event Viewer.

### Pitfall B-3: build.bat fails if not run from repo root
**What goes wrong:** `naomi_zoom.spec` not found; paths resolve relative to the user's shell CWD rather than the repo root.
**Why it happens:** Batch scripts inherit the calling shell's working directory.
**How to avoid:** Add `cd /d "%~dp0"` as the first real line of `build.bat`. `%~dp0` expands to the drive and path of the batch file itself, regardless of where the user double-clicked it.
**Warning signs:** `pyinstaller` reports "Cannot find spec file 'naomi_zoom.spec'".

### Pitfall B-4: zoom_log.txt committed to git
**What goes wrong:** Debug log (containing timestamps of exceptions from Phase 7 development) is committed and pushed to the public GitHub repo.
**Why it happens:** `zoom_log.txt` is currently untracked but not in `.gitignore`. If the planner adds it to git and then pushes, it leaks debug info.
**How to avoid:** Add `zoom_log.txt` to `.gitignore` before the push. Do NOT add it to the git index.
**Warning signs:** `git status` shows `?? zoom_log.txt`; `git add .` would inadvertently include it.

### Pitfall B-5: .claude/ and .remember/ accidentally committed
**What goes wrong:** Internal agent scaffolding and session memory files appear in the public repo, revealing internal tooling structure.
**Why it happens:** Both directories are currently untracked (`?? .claude/`, `?? .remember/` in `git status`). A careless `git add .` would include them.
**How to avoid:** Add `.claude/` and `.remember/` to `.gitignore` before the final push.
**Warning signs:** `git status` shows both directories as untracked.

### Pitfall B-6: GitHub remote URL mismatch (NomisLens vs Ultimate-Zoom)
**What goes wrong:** Confusion between the REQUIREMENTS.md reference (`Ultimate-Zoom.git`) and the live configured remote (`NomisLens.git`).
**Why it happens:** The repo may have been created under the name `NomisLens` on GitHub, and the REQUIREMENTS.md requirement was written with an earlier name.
**How to avoid:** Use the live remote as-is. `git push origin master` targets `https://github.com/fresh-start-git/NomisLens.git`. Do NOT change the remote URL without user confirmation that the GitHub repo was renamed.
**Warning signs:** `git remote -v` shows `NomisLens.git`; BULD-06 says `Ultimate-Zoom.git`.

### Pitfall B-7: Windows SmartScreen blocking EXE download
**What goes wrong:** Clinic staff downloads or copies the EXE, double-clicks it, and sees "Windows protected your PC" SmartScreen dialog.
**Why it happens:** The EXE is not code-signed. SmartScreen flags unsigned executables from unknown publishers.
**How to avoid:** README must include explicit allowlist instructions: "Click 'More info' then 'Run anyway'" for SmartScreen, plus generic AV allowlist instructions. Code signing is Out of Scope per REQUIREMENTS.md.
**Warning signs:** User reports "app won't open" or "blue screen" (SmartScreen dialog).

### Pitfall B-8: `--no-click-injection` flag in README confuses users
**What goes wrong:** Clinic staff reads the README, sees the `--no-click-injection` CLI flag, and wonders if they need it.
**Why it happens:** The flag was added in Phase 4 as a developer escape hatch. It should NOT appear in the non-technical README sections.
**How to avoid:** CLI flags go in an "Advanced / Developer" section only, after the simple EXE usage instructions.

---

## Code Examples

### build.bat (complete)

```bat
@echo off
REM NomisLens — build script
REM Run this from the repo root to produce dist\NomisLens.exe
REM Requires: .venv set up via "pip install -r requirements.txt"

cd /d "%~dp0"
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Could not activate virtual environment.
    echo Run: python -m venv .venv ^&^& pip install -r requirements.txt
    pause
    exit /b 1
)
python -m PyInstaller naomi_zoom.spec --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller build failed. See output above.
    pause
    exit /b 1
)
echo.
echo Build complete. Output: dist\NomisLens.exe
pause
```

### naomi_zoom.spec hiddenimports addition (diff)

```python
# Source: PyInstaller docs on hidden imports; pattern established in Phase 8 for pystray._win32
hiddenimports=[
    # ... existing entries (win32gui, win32api, win32con, pywintypes, dxcam.*, comtypes.*, pystray._win32) ...

    # NEW additions for BULD-02:
    'PIL._tkinter_finder',  # Pillow/Tk bridge — prevents ImageTk crash in one-file EXE
    'win32timezone',         # pywin32 internal — prevents startup ImportError on some Windows
],
```

### .gitignore additions

```
# Agent scaffolding (not for public repo)
.claude/
.remember/

# Debug artifacts
zoom_log.txt
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PyInstaller 5.x + `upx=True` | PyInstaller 6.11.1 + `upx=False` | PyInstaller 6.0 (2023) | 6.x has better one-file EXE boot time and improved hook detection; UPX off avoids AV false positives |
| Manual hidden import discovery | Existing working spec | Phases 7–8 | The dxcam and pystray hidden import lists were already discovered and validated. Phase 9 only adds 2 more. |
| cx_Freeze / Nuitka | PyInstaller | Project inception | PyInstaller chosen because existing project knowledge and one-file mode is well-proven |

**Deprecated/outdated:**
- `PIL.ImageTk` direct import in spec: Not needed. The `PIL._tkinter_finder` hidden import is the correct hook-based approach for Pillow 12+.

---

## Open Questions

1. **GitHub remote URL: NomisLens.git vs Ultimate-Zoom.git**
   - What we know: `git remote -v` returns `https://github.com/fresh-start-git/NomisLens.git`. REQUIREMENTS.md BULD-06 says `Ultimate-Zoom.git`.
   - What's unclear: Was the repo renamed on GitHub? Does the user want the remote changed?
   - Recommendation: Use `NomisLens.git` as-is (it's the live remote with 31 commits already synced). Note the discrepancy in the plan for human verification. Do NOT silently change the remote.

2. **Should the .planning/ directory be pushed to GitHub?**
   - What we know: All 21 completed plan files, research docs, and summary docs are tracked in git and will be pushed.
   - What's unclear: The user may not want internal planning docs visible on the public GitHub repo.
   - Recommendation: Push as-is (planning docs are the project's design history and are useful for future contributors). Flag in human-verify step so user can gitignore `.planning/` if they prefer.

3. **Should the EXE be distributed via GitHub Releases?**
   - What we know: BULD-06 says "full source tree, .spec, build.bat, and README.md are pushed". It does NOT say "EXE is published as a GitHub Release".
   - What's unclear: Whether the clinic needs a downloadable EXE from GitHub.
   - Recommendation: Do NOT create a GitHub Release in this phase. BULD-06 is satisfied by source push + build.bat. A GitHub Release is a v2 enhancement.

4. **`--no-click-injection` flag: is it still needed?**
   - What we know: Phase 7 replaced all click injection with the WS_EX_TRANSPARENT zone poll. The `--no-click-injection` flag in `app.py` was added in Phase 4 and likely no longer does anything meaningful (click injection was deleted in Phase 7).
   - What's unclear: Whether `app.py` still has the argparse flag and whether it has any effect.
   - Recommendation: Check `app.py` argparse; if the flag is now a no-op, remove it in this phase to avoid confusing clinic IT who might read the README's advanced section.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x (from requirements-dev.txt) |
| Config file | pyproject.toml (pytest.ini_options) |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest -x -q` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BULD-01 | requirements.txt has correct pinned packages | Source scan | `pytest tests/test_main_entry.py -x -q` (existing) | Yes |
| BULD-02 | spec has PIL._tkinter_finder, win32timezone, upx=False | Source scan (new) | `pytest tests/test_build.py::test_spec_hiddenimports -x` | Wave 0 |
| BULD-02 | spec has upx=False | Source scan (new) | `pytest tests/test_build.py::test_spec_upx_false -x` | Wave 0 |
| BULD-03 | build.bat exists and contains pyinstaller invocation | File existence + content scan (new) | `pytest tests/test_build.py::test_build_bat_exists -x` | Wave 0 |
| BULD-04 | EXE runs on Windows without Python | Manual smoke | `ULTIMATE_ZOOM_SMOKE=1 ./dist/NomisLens.exe` | manual |
| BULD-05 | README.md exists and contains required sections | File existence + content scan (new) | `pytest tests/test_build.py::test_readme_exists -x` | Wave 0 |
| BULD-06 | Source pushed to GitHub | Manual (git push) | manual | manual |

**Note on BULD-04:** The automated `ULTIMATE_ZOOM_SMOKE=1` env var causes the app to tear down after 50 ms. This can be used to smoke-test the EXE without a GUI: `set ULTIMATE_ZOOM_SMOKE=1 && dist\NomisLens.exe`. If it exits cleanly (exit code 0), the EXE launches correctly.

### Sampling Rate

- **Per task commit:** `pytest tests/test_build.py -x -q`
- **Per wave merge:** `pytest -x -q` (full 294-test suite)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_build.py` — structural lints: spec hiddenimports, upx=False, build.bat existence, README.md existence and section headers

*(All other test infrastructure already exists. No framework installation needed.)*

---

## Pre-Build Checklist (for Planner)

The planner should structure tasks to complete these in order:

1. **Spec surgery**: Add `PIL._tkinter_finder` and `win32timezone` to hiddenimports.
2. **Wave 0 tests**: Create `tests/test_build.py` with structural lints for spec/bat/README.
3. **build.bat**: Create `build.bat` at repo root.
4. **README.md**: Write plain-English guide.
5. **`.gitignore` additions**: Add `zoom_log.txt`, `.claude/`, `.remember/`.
6. **Rebuild EXE**: Run `build.bat` (via human verification step).
7. **Full test suite green**: `pytest -x -q` with 294+ tests passing.
8. **GitHub push**: `git push origin master` (human verification step — 31+ commits ahead).

---

## Sources

### Primary (HIGH confidence)

- `naomi_zoom.spec` — read directly; current state verified (upx=False, pystray._win32 present, PIL._tkinter_finder and win32timezone absent)
- `requirements.txt` — read directly; 7 packages pinned, Python 3.11.9, PyInstaller 6.11.1
- `.venv/Scripts/python.exe --version` — confirmed Python 3.11.9
- `pip show pyinstaller` in .venv — confirmed 6.11.1
- `python -c "import PIL._tkinter_finder"` in .venv — confirmed EXISTS
- `python -c "import win32timezone"` in .venv — confirmed EXISTS
- `git remote -v` — confirmed `https://github.com/fresh-start-git/NomisLens.git`
- `git log origin/master..HEAD --oneline` — confirmed 31 commits ahead
- `.gitignore` — read directly; dist/, build/, config.json excluded; zoom_log.txt, .claude/, .remember/ NOT yet excluded
- `pytest --co` — confirmed 294 tests collected
- `dist/NomisLens.exe` — confirmed 29 MB, built April 17 2026 (post Phase 8)

### Secondary (MEDIUM confidence)

- PyInstaller documentation (established community pattern): `PIL._tkinter_finder` and `win32timezone` are both well-documented PyInstaller + pywin32/Pillow hidden import requirements. The `pystray._win32` precedent (already in the spec) confirms this project already applies this pattern correctly.

### Tertiary (LOW confidence)

- None. All critical claims are directly verified against the live project state.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions confirmed against installed .venv
- Architecture: HIGH — based on direct inspection of existing working spec and project files
- Pitfalls: HIGH — B-1 and B-2 are confirmed gaps in the existing spec; B-3 through B-8 are direct observations from the live `git status` and file system

**Research date:** 2026-04-17
**Valid until:** 2026-07-17 (PyInstaller 6.11.1 is stable; all other dependencies are pinned)
