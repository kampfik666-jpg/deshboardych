@echo off
REM === LifeHub / DESHBORDYCH autostart installer ===
REM Registers a Windows Task Scheduler job that starts the dashboard at logon.
setlocal
set "ROOT=%~dp0"
set "PYW=%ROOT%.venv\Scripts\pythonw.exe"
set "RUNPY=%ROOT%run.py"
set "TASKNAME=LifeHub Dashboard"

if not exist "%PYW%" (
    echo ERROR: pythonw.exe not found at %PYW%
    echo Run this from the life-hub project folder with .venv installed.
    pause
    exit /b 1
)

schtasks /create /f /tn "%TASKNAME%" /tr "\"%PYW%\" \"%RUNPY%\"" /sc onlogon /rl limited
if %errorlevel%==0 (
    echo.
    echo OK! Task "%TASKNAME%" created.
    echo The dashboard will start automatically every time you log in to Windows.
    echo It also restarts itself if it crashes.
    echo.
    echo To start it right now without rebooting, run: start_now.bat
) else (
    echo Failed to create scheduled task. Try running this .bat as Administrator.
)
pause
