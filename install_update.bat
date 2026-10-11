@echo off
cd /d "%~dp0"
chcp 65001 >nul
echo Close JARVIS first. Installing the newest JARVIS update zip
echo (from Downloads / Desktop, or the zip you dragged onto this file)...
echo.
python updater.py --install-zip %1
echo.
echo Undo: python updater.py --rollback   ^|  Jarvis.exe users: run rebuild.bat next.
pause
