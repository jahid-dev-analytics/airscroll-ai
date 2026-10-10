@echo off
REM One-time setup for Windows: creates .venv, installs packages, downloads the hand model.
cd /d "%~dp0"

where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>nul || (
  echo Python 3.11+ was not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause & exit /b 1
)

if not exist .venv (
  echo Creating virtual environment...
  %PY% -m venv .venv || (echo Could not create .venv & pause & exit /b 1)
)
echo Installing packages (first time takes a few minutes)...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt || (echo Package install failed - see messages above & pause & exit /b 1)

echo Downloading the MediaPipe hand model...
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, '.'); from airscroll.tracker import ensure_model; print('Model ready:', ensure_model())" || (pause & exit /b 1)

echo.
echo Setup complete. Next: load the "extension" folder in Chrome/Edge (see README), then run run.bat
pause
