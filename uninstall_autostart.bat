@echo off
REM Removes the autostart task
schtasks /delete /f /tn "LifeHub Dashboard"
echo Autostart task removed.
pause
