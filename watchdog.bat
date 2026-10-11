@echo off
setlocal enabledelayedexpansion

set "JARVIS_DIR=%~dp0dist\Jarvis"
set "JARVIS_EXE=%JARVIS_DIR%\Jarvis.exe"

echo ============================================
echo   JARVIS Watchdog
echo   Restarts Jarvis.exe automatically if it crashes.
echo   Close THIS window to stop watching (and it will
echo   stop relaunching JARVIS after that).
echo ============================================
echo.

:loop
tasklist /FI "IMAGENAME eq Jarvis.exe" 2>nul | find /I "Jarvis.exe" >nul
if errorlevel 1 (
    echo [%date% %time%] Jarvis.exe not running - starting it...
    start "" /D "%JARVIS_DIR%" "%JARVIS_EXE%"
    timeout /t 5 /nobreak >nul
)
timeout /t 10 /nobreak >nul
goto loop