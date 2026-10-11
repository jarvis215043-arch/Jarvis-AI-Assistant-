@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo   Put JARVIS on GitHub (private) - so a lost USB never matters
echo ============================================================
echo.
where git >nul 2>nul || (
  echo Git is not installed. Get it from https://git-scm.com/download/win
  echo ^(click Next through the installer^), then run this again.
  goto :end
)
python -c "import sys;sys.path.insert(0,'.');from core import git_sync as G;G.ensure_safe()"
if not exist ".git" (
  git init -b main >nul
  git config user.name  >nul 2>nul || git config user.name  "JARVIS"
  git config user.email >nul 2>nul || git config user.email "jarvis@localhost"
)
echo Checking that no keys or personal data will be uploaded...
python -c "import sys,subprocess;sys.path.insert(0,'.');from core import git_sync as G;r=subprocess.run(['git','ls-files','--others','--cached','--exclude-standard'],capture_output=True,text=True);r.returncode and (print('  STOPPED - git could not list the files:',r.stderr.strip()[:200]),sys.exit(1));f=r.stdout.splitlines();bad=G.blocked(f) if f else ['(no files found - nothing checked)'];print('  BLOCKED:',bad) if bad else print('  OK - keys, settings and memory are excluded.');sys.exit(1 if bad else 0)" || goto :end
git add -A
git commit -m "JARVIS update %DATE% %TIME%" >nul 2>nul
git remote get-url origin >nul 2>nul && goto :push
where gh >nul 2>nul && (
  gh auth status >nul 2>nul || gh auth login
  gh repo create jarvis --private --source . --remote origin --push && goto :done
)
echo.
echo 1. Open https://github.com/new  ^(sign in or create a free account^)
echo 2. Repository name: jarvis    -  choose PRIVATE  -  click "Create repository"
echo 3. Copy the URL it shows ^(https://github.com/^<you^>/jarvis.git^)
echo.
set /p URL=Paste the URL here and press Enter: 
git remote add origin %URL% || git remote set-url origin %URL% || goto :end
:push
git push -u origin main || (
  echo Push failed - check the URL and that you are signed in to GitHub.
  goto :end
)
:done
echo.
echo Done! JARVIS is saved privately on GitHub.
echo  - From now on: git_save.bat, or say "save my code to GitHub".
echo  - On a new PC:  git clone ^<your repo URL^>  then  python setup.py
echo  - update.bat / "update yourself" now pulls the newest version.
:end
pause
