@echo off
cd /d "%~dp0"
chcp 65001 >nul
python auto_zip.py --install %*
echo.
pause
