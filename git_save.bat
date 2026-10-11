@echo off
cd /d "%~dp0"
chcp 65001 >nul
title JARVIS - save to GitHub
echo Saving your JARVIS code to GitHub (keys, settings and memory are never uploaded)...
echo.
python -m core.git_sync %*
echo.
pause
