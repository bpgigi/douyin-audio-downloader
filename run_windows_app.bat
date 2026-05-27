@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  ".venv\Scripts\pythonw.exe" "windows_app.py"
) else (
  python "windows_app.py"
)
