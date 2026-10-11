@echo off
cd /d "%~dp0"
chcp 65001 >nul
title JARVIS - zip the whole folder
python make_zip.py %*
echo.
pause
