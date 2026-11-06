@echo off
REM Starts the dashboard right now (hidden, via pythonw)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0run.py"
echo Dashboard started in background. Open http://127.0.0.1:8765
timeout /t 3 >nul
