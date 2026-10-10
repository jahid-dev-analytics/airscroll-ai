@echo off
REM Starts AirScroll AI and opens the dashboard. Close this window (or press Ctrl+C) to quit.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run setup.bat first.
  pause & exit /b 1
)
.venv\Scripts\python.exe run.py %*
if errorlevel 1 pause
