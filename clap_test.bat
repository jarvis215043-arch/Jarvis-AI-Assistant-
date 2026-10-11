@echo off
cd /d "%~dp0"
echo Clap test: clap twice and watch for "Double clap!". Close this window when done.
python clap_launcher.py --test
pause
