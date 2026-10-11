@echo off
cd /d "%~dp0"
echo Close JARVIS first. Checking for updates...
python updater.py
echo.
echo If files changed and you use Jarvis.exe, run rebuild.bat next.
pause
