@echo off
cd /d "%~dp0"
chcp 65001 >nul
echo Making a JARVIS bug report (keys are never included)...
echo.
python -m core.bug_report
echo.
pause
