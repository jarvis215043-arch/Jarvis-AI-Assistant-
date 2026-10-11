@echo off
setlocal
cd /d "%~dp0"
echo Building Jarvis.exe ...
python build.py || goto :fail
set /p VER=<VERSION
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo.
  echo Inno Setup 6 is not installed. Get it free from https://jrsoftware.org/isdl.php
  echo then run this again.
  goto :end
)
"%ISCC%" /DAppVer=%VER% installer.iss || goto :fail
echo.
echo Done! Installer: installer\JARVIS-Setup-%VER%.exe
echo Upload it to a GitHub Release (tag v%VER%) so other PCs can auto-update.
goto :end
:fail
echo.
echo BUILD FAILED - see the messages above.
:end
pause
