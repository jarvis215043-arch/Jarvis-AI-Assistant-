@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   JARVIS Rebuild Script
echo ============================================
echo.

python build.py

echo.
pause