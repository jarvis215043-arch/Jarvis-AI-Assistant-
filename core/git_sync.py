"""
core/git_sync.py — Save JARVIS's code to GitHub (2.7).

  "JARVIS, save my code to GitHub"   (actions/github_save.py)
  git_save.bat                       (double-click, works without JARVIS)

What it does, in order:
  1. checks Git is installed and this folder is connected to GitHub
     (if not: run setup_github.bat ONCE — it signs you in and makes a private repo)
  2. stages every changed file that .gitignore allows
  3. SAFETY CHECK — stops (and uploads nothing) if any key, Google sign-in, locked
     file, settings, memory/log file, or a file over 95 MB would be uploaded
  4. commits ("JARVIS 2.7.0 — saved 11 Oct 2026 18:40, 3 files changed")
  5. pushes, showing GitHub's progress as a percentage
Your keys, settings and memory never go to GitHub — only the code.
"""
import fnmatch
import re
import subprocess
import sys
import time
from pathlib import Path

NO_WIN = 0x08000000 if sys.platform == "win32" else 0
MAX_MB = 95                                            # GitHub refuses files over 100 MB
BLOCK = ["config/*.json", "config/*.locked", "*.locked", "*token*.json", "*client_secret*", "*credentials*",
         ".env", ".env.*", "memory/*.json", "memory/*.db", "memory/chat_history/*", "memory/journal/*",
         "memory/logs/*", "*.log", "config/certs/*", "config/whatsapp_web/*"]


def base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_safe_done = set()


def ensure_safe(cwd=None) -> None:
    """USB / exFAT / FAT32 drives don't record file owners, and Git then refuses the folder
    ("detected dubious ownership"). Mark THIS folder as yours once (git's own fix)."""
    path = Path(cwd or base()).resolve().as_posix()
    if path in _safe_done:
        return
    _safe_done.add(path)
    try:
        have = subprocess.run(["git", "config", "--global", "--get-all", "safe.directory"], capture_output=True,
                              text=True, timeout=15, creationflags=NO_WIN).stdout.splitlines()
        if path not in [h.strip() for h in have] and "*" not in [h.strip() for h in have]:
            subprocess.run(["git", "config", "--global", "--add", "safe.directory", path], capture_output=True,
                           timeout=15, creationflags=NO_WIN)
    except Exception:
        pass


def git(*args, timeout=120, cwd=None) -> subprocess.CompletedProcess:
    ensure_safe(cwd)
    return subprocess.run(["git", *args], cwd=str(cwd or base()), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout, creationflags=NO_WIN)


def have_git() -> bool:
    try:
        return git("--version", timeout=15).returncode == 0
    except Exception:
        return False


def is_repo(cwd=None) -> bool:
    return (Path(cwd or base()) / ".git").exists()


def remote_url(cwd=None) -> str:
    r = git("remote", "get-url", "origin", cwd=cwd)
    return r.stdout.strip() if r.returncode == 0 else ""


def blocked(paths: list[str], cwd=None) -> list[str]:
    """Files that must never be uploaded (keys, settings, memory, huge files)."""
    root = Path(cwd or base())
    bad = []
    for p in paths:
        q = p.replace("\\", "/")
        name = q.rsplit("/", 1)[-1]
        if any(fnmatch.fnmatch(q, pat) or fnmatch.fnmatch(name, pat) for pat in BLOCK):
            bad.append(q)
            continue
        try:
            if (root / q).stat().st_size > MAX_MB * 1_000_000:
                bad.append(q + f"  (over {MAX_MB} MB)")
        except OSError:
            pass
    return bad


def status(cwd=None) -> dict:
    """{'ready', 'reason', 'remote', 'pending' (changed files), 'last' (last commit)}"""
    if not have_git():
        return {"ready": False, "reason": "Git isn't installed (git-scm.com/download/win)."}
    if not is_repo(cwd) or not remote_url(cwd):
        return {"ready": False, "reason": "This folder isn't connected to GitHub yet — double-click setup_github.bat once "
                                         "(it signs you in and creates your private repo)."}
    pending = [l[3:] for l in git("status", "--porcelain", cwd=cwd).stdout.splitlines() if l.strip()]
    last = git("log", "-1", "--format=%cd · %s", "--date=format:%d %b %Y %H:%M", cwd=cwd).stdout.strip()
    ahead = git("rev-list", "--count", "@{u}..HEAD", cwd=cwd)
    return {"ready": True, "remote": remote_url(cwd), "pending": pending, "last": last,
            "unpushed": int(ahead.stdout.strip() or 0) if ahead.returncode == 0 else None}


def save(message: str = "", progress=None, cwd=None) -> str:
    """Commit + push. progress(percent: int, text: str) is called along the way."""
    say = progress or (lambda p, t: None)
    st = status(cwd)
    if not st["ready"]:
        return st["reason"]
    say(5, "Checking what changed…")
    git("add", "-A", cwd=cwd)
    staged = [l for l in git("diff", "--cached", "--name-only", cwd=cwd).stdout.splitlines() if l.strip()]
    bad = blocked(staged, cwd)
    if bad:
        git("reset", "-q", cwd=cwd)                                     # unstage everything — nothing goes up
        return ("Stopped — nothing was uploaded. These must never go to GitHub: " + ", ".join(bad[:6])
                + ". Check .gitignore (or move those files), then try again.")
    say(20, f"{len(staged)} changed file(s) — safety check passed")
    if staged:
        try:
            ver = (Path(cwd or base()) / "VERSION").read_text(encoding="utf-8").strip()
        except Exception:
            ver = ""
        msg = message.strip() or f"JARVIS {ver} — saved {time.strftime('%d %b %Y %H:%M')}, {len(staged)} file(s) changed"
        c = git("commit", "-m", msg, cwd=cwd)
        if c.returncode != 0 and "nothing to commit" not in (c.stdout + c.stderr):
            if "user.email" in c.stderr or "user.name" in c.stderr:
                git("config", "user.name", "JARVIS", cwd=cwd); git("config", "user.email", "jarvis@localhost", cwd=cwd)
                c = git("commit", "-m", msg, cwd=cwd)
            if c.returncode != 0:
                return "Couldn't save (commit failed): " + (c.stderr or c.stdout).strip()[:200]
    elif not st.get("unpushed"):
        say(100, "Nothing new")
        return "Nothing new to save — GitHub already has your latest code."
    say(30, "Uploading to GitHub…")
    ensure_safe(cwd)
    p = subprocess.Popen(["git", "push", "--progress", "-u", "origin", "HEAD"], cwd=str(cwd or base()),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace", creationflags=NO_WIN)
    err_lines, buf = [], ""
    while True:                                                         # git writes progress with \r
        ch = p.stderr.read(1)
        if not ch:
            break
        if ch in "\r\n":
            line, buf = buf.strip(), ""
            if not line:
                continue
            err_lines.append(line)
            m = re.search(r"(Counting|Compressing|Writing) objects:\s+(\d+)%", line)
            if m:
                stage = {"Counting": (30, 0.1), "Compressing": (33, 0.2), "Writing": (53, 0.45)}[m.group(1)]
                say(int(stage[0] + stage[1] * int(m.group(2))), line)
        else:
            buf += ch
    p.wait(timeout=600)
    if p.returncode != 0:
        tail = " ".join(err_lines[-3:])
        if "rejected" in tail or "fetch first" in tail:
            return ("GitHub has newer changes (saved from another PC). Run update.bat (or say 'check for updates') "
                    "to get them first, then save again.")
        if "Authentication" in tail or "could not read Username" in tail or "403" in tail:
            return "GitHub sign-in failed — run setup_github.bat once to sign in again."
        return "Upload failed: " + tail[:220]
    say(100, "Saved on GitHub")
    n = len(staged)
    return (f"Saved to GitHub — {n} changed file(s)." if n else "Saved to GitHub.") + f" ({st['remote']})"


def _bar(pct: int, text: str = "") -> None:
    n = max(0, min(30, pct * 30 // 100))
    sys.stdout.write(f"\r  [{'#' * n}{'-' * (30 - n)}] {pct:3d}%  {text[:44]:<44}")
    sys.stdout.flush()


if __name__ == "__main__":                                              # git_save.bat
    msg = " ".join(a for a in sys.argv[1:] if a != "save")
    result = save(msg, progress=_bar)
    print("\n\n" + result)
