"""Structural lints for Phase 9 build artifacts.

BULD-02: spec hiddenimports, upx=False
BULD-03: build.bat existence and content
BULD-05: README.md existence and required sections
"""
from __future__ import annotations
import pathlib

REPO_ROOT = pathlib.Path(__file__).parent.parent
SPEC_PATH = REPO_ROOT / "naomi_zoom.spec"
BAT_PATH  = REPO_ROOT / "build.bat"
README_PATH = REPO_ROOT / "README.md"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"


def test_spec_hiddenimports():
    """BULD-02: spec contains both required missing hiddenimports."""
    src = SPEC_PATH.read_text(encoding="utf-8")
    assert "'PIL._tkinter_finder'" in src, (
        "naomi_zoom.spec is missing 'PIL._tkinter_finder' in hiddenimports — "
        "add it or ImageTk.PhotoImage will crash on EXE launch"
    )
    assert "'win32timezone'" in src, (
        "naomi_zoom.spec is missing 'win32timezone' in hiddenimports — "
        "add it or the EXE will raise ImportError on some Windows configs"
    )


def test_spec_upx_false():
    """BULD-02: spec must have upx=False to avoid AV false positives."""
    src = SPEC_PATH.read_text(encoding="utf-8")
    assert "upx=False" in src, "naomi_zoom.spec must have upx=False"
    assert "upx=True" not in src, "naomi_zoom.spec must NOT have upx=True"


def test_spec_pystray_already_present():
    """Regression: pystray._win32 must still be present (Phase 8 addition)."""
    src = SPEC_PATH.read_text(encoding="utf-8")
    assert "'pystray._win32'" in src, (
        "naomi_zoom.spec is missing 'pystray._win32' — regression from Phase 8"
    )


def test_build_bat_exists():
    """BULD-03: build.bat must exist at repo root."""
    assert BAT_PATH.exists(), f"build.bat not found at {BAT_PATH}"


def test_build_bat_content():
    """BULD-03: build.bat must activate venv and invoke pyinstaller with --noconfirm."""
    src = BAT_PATH.read_text(encoding="utf-8")
    assert "activate" in src.lower(), (
        "build.bat must activate the .venv before running PyInstaller"
    )
    assert "pyinstaller" in src.lower(), (
        "build.bat must invoke PyInstaller"
    )
    assert "naomi_zoom.spec" in src, (
        "build.bat must reference naomi_zoom.spec explicitly"
    )
    assert "--noconfirm" in src, (
        "build.bat must pass --noconfirm to suppress 'Remove dist?' prompt"
    )


def test_readme_exists():
    """BULD-05: README.md must exist at repo root."""
    assert README_PATH.exists(), f"README.md not found at {README_PATH}"


def test_readme_sections():
    """BULD-05: README.md must contain all required sections for clinic staff."""
    src = README_PATH.read_text(encoding="utf-8")
    required_sections = [
        "Quick Start",
        "Antivirus",        # AV allowlist note
        "Running from Source",
        "Building",         # build.bat instructions
        "Keyboard",         # hotkey reference
        "Configuration",    # config.json description
    ]
    missing = [s for s in required_sections if s not in src]
    assert not missing, (
        f"README.md is missing these required sections: {missing}"
    )


def test_gitignore_excludes_debug_artifacts():
    """Prevents zoom_log.txt and agent scaffolding from being pushed to GitHub."""
    src = GITIGNORE_PATH.read_text(encoding="utf-8")
    required = ["zoom_log.txt", ".claude/", ".remember/"]
    missing = [entry for entry in required if entry not in src]
    assert not missing, (
        f".gitignore is missing these entries (would be pushed to public GitHub): {missing}"
    )
