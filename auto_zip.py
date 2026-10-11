r"""
auto_zip.py — Keeps a zip of your Jarvis folder up to date by itself.

Whenever you change, add or delete a file in the Jarvis folder, this waits until
you've stopped saving for a few seconds and then rebuilds ONE zip next to the
folder:
      ...\3D Objects\Jarvis-latest.zip        (inside it: a "Jarvis" folder)

LEFT OUT, so the zip is safe to share or back up:
  • your keys and Google sign-in (config\api_keys.json, *.locked, token /
    client_secret / credentials files)
  • your personal memory (memory\ — chat history, journal, notes…)
    → add  --with-memory  to include it (keys are never included)
  • junk: __pycache__, .git, build, dist, backups, logs, temp files

HOW TO USE
  auto_zip.bat                 start watching (a small window; close it to stop)
  auto_zip_startup.bat         start watching hidden every time Windows starts
  python auto_zip.py --once    just make the zip now
  python auto_zip.py --uninstall     stop starting with Windows
Options: --out "D:\Backups\Jarvis.zip"   --with-memory   --quiet-seconds 8
(or "auto_zip_path" / "auto_zip_memory" in config\api_keys.json)

It only reads file dates and sizes every 3 seconds, so it uses almost no CPU.
Only one copy runs at a time.
"""
import argparse
import fnmatch
import json
import os
import socket
import sys
import time
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
try:
    sys.stdout.reconfigure(line_buffering=True)          # show each line at once (no-op when hidden)
except Exception:
    pass
POLL = 3.0
LOCK_PORT = 47613                                  # one watcher at a time

SKIP_DIRS = {"__pycache__", ".git", ".vscode", ".idea", "build", "dist", "backups", "venv", ".venv",
             "env", "node_modules", ".pytest_cache", ".mypy_cache"}
SKIP_FILES = ["*.pyc", "*.pyo", "*.log", "*.tmp", "*.temp", "~$*", "*.swp", "Thumbs.db", "desktop.ini", ".DS_Store",
              "*.zip"]
SECRET_FILES = ["api_keys.json", "*token*.json", "client_secret*.json", "*credentials*.json", "*.locked",
                "*.locked.tmp", ".env"]


def _cfg() -> dict:
    try:
        sys.path.insert(0, str(BASE))
        from core.secure_config import read_config
        return read_config()
    except Exception:
        try:
            return json.loads((BASE / "config" / "api_keys.json").read_text(encoding="utf-8"))
        except Exception:
            return {}


def included(rel: str, with_memory: bool) -> bool:
    parts = rel.split("/")
    if any(p in SKIP_DIRS for p in parts[:-1]):
        return False
    name = parts[-1]
    if any(fnmatch.fnmatch(name, pat) for pat in SKIP_FILES):
        return False
    if any(fnmatch.fnmatch(name.lower(), pat) for pat in SECRET_FILES):
        return False                                      # keys never leave the PC
    if parts[0] == "memory" and not with_memory:
        return False
    return True


def snapshot(with_memory: bool) -> dict:
    """{relative path: (modified time, size)} of every file that goes in the zip."""
    out = {}
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            p = Path(root) / f
            rel = p.relative_to(BASE).as_posix()
            if not included(rel, with_memory):
                continue
            try:
                st = p.stat()
                out[rel] = (st.st_mtime_ns, st.st_size)
            except OSError:
                pass
    return out


def build(out_path: Path, files: list, folder_name: str = "Jarvis") -> tuple:
    """Writes the zip to a temp file, then swaps it in (never a half-written zip)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".part")
    n = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for rel in sorted(files):
            src = BASE / rel
            try:
                z.write(src, f"{folder_name}/{rel}")
                n += 1
            except OSError as e:                          # file vanished / locked mid-save — next pass gets it
                print(f"[AutoZip] skipped {rel}: {e}")
    for attempt in range(10):
        try:
            os.replace(tmp, out_path)
            break
        except PermissionError:                           # zip open in Explorer / being copied — retry
            time.sleep(1.0)
    else:
        raise PermissionError(f"{out_path.name} is in use — will try again on the next change")
    return n, out_path.stat().st_size


def default_out() -> Path:
    custom = str(_cfg().get("auto_zip_path") or "").strip()
    return Path(custom) if custom else BASE.parent / f"{BASE.name}-latest.zip"


def _summary(old: dict, new: dict) -> str:
    if not old:
        return "first build"
    added = len(new.keys() - old.keys()); removed = len(old.keys() - new.keys())
    changed = sum(1 for k in new.keys() & old.keys() if new[k] != old[k])
    bits = [f"{changed} changed" if changed else "", f"{added} added" if added else "", f"{removed} removed" if removed else ""]
    return ", ".join(b for b in bits if b) or "first build"


def watch(out_path: Path, with_memory: bool, quiet: float) -> None:
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", LOCK_PORT))
    except OSError:
        print("[AutoZip] Already running — nothing to do.")
        return
    print(f"[AutoZip] Watching {BASE}\n[AutoZip] Zip: {out_path}\n"
          f"[AutoZip] Keys are never included; memory is {'included' if with_memory else 'left out'}. "
          "Close this window to stop.")
    last_built = {}
    if out_path.exists():                                 # don't rebuild on start if nothing changed since
        try:
            with zipfile.ZipFile(out_path) as z:
                names = {i.filename.split("/", 1)[1] for i in z.infolist() if "/" in i.filename and not i.is_dir()}
            cur = snapshot(with_memory)
            newest = max((v[0] for v in cur.values()), default=0) / 1e9
            if names == set(cur) and newest <= out_path.stat().st_mtime:
                last_built = cur
                print("[AutoZip] Zip is already up to date.")
        except Exception:
            pass
    pending_since = None
    seen = last_built
    while True:
        try:
            cur = snapshot(with_memory)
        except Exception as e:
            print(f"[AutoZip] couldn't read the folder: {e}")
            time.sleep(POLL); continue
        if cur != seen:                                   # something is still being saved — wait for quiet
            seen, pending_since = cur, time.monotonic()
        elif cur != last_built and (pending_since is None or time.monotonic() - pending_since >= quiet):
            try:
                n, size = build(out_path, list(cur))
                print(f"[AutoZip] {time.strftime('%H:%M:%S')}  updated {out_path.name}  "
                      f"({n} files, {size / 1e6:.1f} MB) — {_summary(last_built, cur)}")
                last_built, pending_since = cur, None
            except Exception as e:
                print(f"[AutoZip] {e}")
                pending_since = time.monotonic()
        time.sleep(POLL)


# ── start with Windows (hidden) ──
def _startup_file() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "JARVIS auto-zip.vbs"


def install(args_extra: str) -> None:
    pyw = Path(sys.executable).with_name("pythonw.exe")
    py = pyw if pyw.exists() else Path(sys.executable)
    vbs = (f'Set sh = CreateObject("WScript.Shell")\r\n'
           f'sh.CurrentDirectory = "{BASE}"\r\n'
           f'sh.Run """{py}"" ""{BASE / "auto_zip.py"}""{args_extra}", 0, False\r\n')
    f = _startup_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(vbs, encoding="utf-8")
    os.startfile(str(f)) if hasattr(os, "startfile") else None      # start it now too
    print(f"[AutoZip] Will start hidden every time Windows starts (and is running now).\n"
          f"[AutoZip] Zip: {default_out()}\n[AutoZip] To stop: python auto_zip.py --uninstall")


def uninstall() -> None:
    f = _startup_file()
    if f.exists():
        f.unlink()
        print("[AutoZip] Removed from start-up. (A copy running now stops when you sign out, "
              "or end 'pythonw.exe' in Task Manager.)")
    else:
        print("[AutoZip] It wasn't set to start with Windows.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Keep a zip of the Jarvis folder up to date.")
    ap.add_argument("--out", help="where the zip goes (default: next to the Jarvis folder)")
    ap.add_argument("--with-memory", action="store_true", help="also include memory\\ (never keys)")
    ap.add_argument("--quiet-seconds", type=float, default=8.0, help="wait this long after the last save")
    ap.add_argument("--once", action="store_true", help="make the zip now and exit")
    ap.add_argument("--install", action="store_true", help="start hidden with Windows")
    ap.add_argument("--uninstall", action="store_true", help="stop starting with Windows")
    a = ap.parse_args()
    out = Path(a.out) if a.out else default_out()
    mem = a.with_memory or bool(_cfg().get("auto_zip_memory", False))
    try:                                                 # the zip must not be inside the folder it watches
        out.resolve().relative_to(BASE)
        print(f"[AutoZip] The zip can't go inside the Jarvis folder — using {BASE.parent} instead.")
        out = BASE.parent / out.name
    except ValueError:
        pass
    if a.uninstall:
        uninstall(); return 0
    if a.install:
        extra = (f' --out ""{out}""' if a.out else "") + (" --with-memory" if a.with_memory else "")
        install(extra); return 0
    if a.once:
        files = list(snapshot(mem))
        n, size = build(out, files)
        print(f"[AutoZip] {out}  ({n} files, {size / 1e6:.1f} MB)")
        return 0
    try:
        watch(out, mem, a.quiet_seconds)
    except KeyboardInterrupt:
        print("[AutoZip] Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
