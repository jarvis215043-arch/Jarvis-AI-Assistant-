@echo off
cd /d "%~dp0"
chcp 65001 >nul
title JARVIS auto-zip
echo Keeping Jarvis-latest.zip (next to this folder) up to date.
echo Your keys are never included. Close this window to stop.
echo.
python auto_zip.py %*
pause
