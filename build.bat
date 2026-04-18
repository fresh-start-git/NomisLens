@echo off
REM NomisLens -- build script
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
