r"""
updater.py — Keeps JARVIS up to date from YOUR GitHub repository.

Two ways it can update, picked automatically:
  1. The folder is a git clone (you ran setup_github.bat or cloned it)
       → "git pull". Your keys, memory and settings are ignored by git, so
         they're never touched.
  2. GitHub Releases (set "update_repo": "owner/repo" in Advanced Settings)
       • Jarvis.exe installs  → downloads the newest JARVIS-Setup-x.y.z.exe and runs it
       • source installs      → downloads the release zip and copies the new files
         in. Existing settings/memory .json files and locked keys are never
         overwritten; every replaced file is backed up to backups\before-<version>\.
Private repo? Add a read-only "github_token" in Advanced Settings.

  update.bat                       check + install (JARVIS must be closed)
  python updater.py --check        just say whether an update exists
  "Jarvis, check for updates" / "update yourself"   (voice)

UPDATE ZIPS (2.6) — the JARVIS_x.y_update.zip / _complete.zip files you're sent:
  "Jarvis, install the update"     finds the newest one in Downloads / Desktop and installs it
  install_update.bat               same (or drag a zip onto it)
  "Jarvis, undo the last update"   / python updater.py --rollback
Every replaced file is backed up to backups\before-<version>\ first; files YOU had
edited since the last install are named in the result (your copy is in that backup);
keys, settings and memory are never touched.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

NO_WIN = 0x08000000 if sys.platform == "win32" else 0


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE = base_dir()
sys.path.insert(0, str(BASE))


def _cfg() -> dict:
    try:
        from core.secure_config import read_config
        return read_config()
    except Exception:
        try:
            return json.loads((BASE / "config" / "api_keys.json").read_text(encoding="utf-8"))
        except Exception:
            return {}


def current_version() -> str:
    try:
        return (BASE / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return "0.0.0"


def _vtuple(v: str) -> tuple:
    out = []
    for part in v.lstrip("vV").split("."):
        num = "".join(ch for ch in part if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out + [0] * (3 - len(out)))


def _git(*args, timeout=60):
    try:                                                    # USB / exFAT drives: "dubious ownership" fix
        from core.git_sync import ensure_safe
        ensure_safe(BASE)
    except Exception:
        pass
    return subprocess.run(["git", *args], cwd=str(BASE), capture_output=True, text=True, timeout=timeout,
                          creationflags=NO_WIN)


def _is_git() -> bool:
    return (BASE / ".git").exists() and shutil.which("git") is not None


def _api(url: str):
    import requests
    tok = (_cfg().get("github_token") or "").strip()
    h = {"Accept": "application/vnd.github+json"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    r = requests.get(url, headers=h, timeout=20)
    if r.status_code == 404:
        raise RuntimeError("repo or release not found (private repo? add a github_token)")
    r.raise_for_status()
    return r.json()


def check() -> dict:
    """{'available': bool, 'current', 'latest', 'mode', 'message', ...}"""
    cur = current_version()
    if _is_git():
        f = _git("fetch", "--quiet")
        if f.returncode != 0:
            return {"available": False, "current": cur, "mode": "git", "message": "Couldn't reach GitHub: " + f.stderr.strip()[:120]}
        n = _git("rev-list", "--count", "HEAD..@{u}")
        behind = int(n.stdout.strip() or 0) if n.returncode == 0 else 0
        return {"available": behind > 0, "current": cur, "latest": f"{behind} new change(s)", "mode": "git",
                "message": f"{behind} update(s) available." if behind else "JARVIS is up to date."}
    repo = (_cfg().get("update_repo") or "").strip()
    if not repo:
        return {"available": False, "current": cur, "mode": "none",
                "message": "Updates aren't set up yet — run setup_github.bat, or set 'update_repo' in Advanced Settings."}
    rel = _api(f"https://api.github.com/repos/{repo}/releases/latest")
    latest = rel.get("tag_name", "0")
    avail = _vtuple(latest) > _vtuple(cur)
    return {"available": avail, "current": cur, "latest": latest, "mode": "release", "release": rel,
            "message": f"Version {latest} is available (you have {cur})." if avail else f"JARVIS {cur} is up to date."}


def _download(url: str, dest: Path, accept="application/octet-stream") -> Path:
    import requests
    tok = (_cfg().get("github_token") or "").strip()
    h = {"Accept": accept}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    with requests.get(url, headers=h, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(1 << 16):
                fh.write(chunk)
    return dest


PROTECT_DIRS = {"memory/chat_history", "memory/journal", "backups", "dist", "build", ".git"}


def _protected(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    if any(rel == d or rel.startswith(d + "/") for d in PROTECT_DIRS):
        return True
    if rel.endswith(".locked") or rel == "config/api_keys.json":
        return True
    return False


def apply_source_release(info: dict) -> str:
    rel = info["release"]
    asset = next((a for a in rel.get("assets", []) if a["name"].lower().endswith(".zip")), None)
    tmp = Path(tempfile.mkdtemp(prefix="jarvis_update_"))
    zpath = tmp / "update.zip"
    if asset:
        _download(asset["url"], zpath)
    else:
        _download(rel["zipball_url"], zpath, accept="application/vnd.github+json")
    out = tmp / "x"
    with zipfile.ZipFile(zpath) as z:
        for m in z.namelist():
            if ".." in Path(m).parts or Path(m).is_absolute():
                raise RuntimeError("unsafe path in update zip — not installed")
        z.extractall(out)
    root = next((p.parent for p in out.rglob("main.py") if (p.parent / "ui.py").exists()), None)
    if root is None:
        raise RuntimeError("the release zip doesn't contain JARVIS (no main.py/ui.py)")
    backup = BASE / "backups" / f"before-{info['latest']}"
    changed = 0
    for f in root.rglob("*"):
        if not f.is_file() or "__pycache__" in f.parts:
            continue
        rel_path = f.relative_to(root).as_posix()
        if _protected(rel_path):
            continue
        dst = BASE / rel_path
        if dst.suffix == ".json" and dst.exists() and rel_path.split("/")[0] in ("config", "memory"):
            continue                                     # your settings / memory stay yours
        if dst.exists():
            if dst.read_bytes() == f.read_bytes():
                continue
            (backup / rel_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, backup / rel_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        changed += 1
    shutil.rmtree(tmp, ignore_errors=True)
    return f"Updated to {info['latest']} ({changed} files; old versions saved in backups\\before-{info['latest']})."


# ── update zips (2.6) ─────────────────────────────────────────────────────────
import hashlib
import re as _re

MANIFEST = BASE / "memory" / "install_manifest.json"
SKIP_NAMES = _re.compile(r"(?i)^(INSTALL - .*\.txt|START HERE.*\.txt|.*\.pyc)$")


def _md5(data: bytes) -> str:
    return hashlib.md5(data.replace(b"\r\n", b"\n")).hexdigest()       # line endings don't count as edits


def find_update_zip() -> Path | None:
    """Newest JARVIS update / complete zip in Downloads, Desktop or next to the Jarvis folder."""
    home = Path.home()
    spots = [home / "Downloads", home / "Desktop", home / "OneDrive" / "Desktop", BASE.parent]
    found = []
    for d in spots:
        try:
            found += [p for p in d.glob("*.zip") if _re.match(r"(?i)^jarvis[ _-]?\d+(\.\d+)*[ _-](update|complete)", p.name)]
        except Exception:
            pass
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def _zip_root(names: list[str]) -> str:
    files = [n for n in names if not n.endswith("/")]
    tops = {n.split("/", 1)[0] for n in files}
    known = {"actions", "core", "plugins", "config", "memory", "dashboard", "arduino", "main.py", "ui.py", "VERSION"}
    if len(tops) == 1 and all("/" in n for n in files) and next(iter(tops)) not in known:
        return next(iter(tops)) + "/"
    return ""


def install_zip(zpath, dry: bool = False) -> dict:
    """Installs a JARVIS update/complete zip into this folder. Returns what happened."""
    zpath = Path(zpath)
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        for m in names:
            if ".." in Path(m).parts or Path(m).is_absolute() or m.startswith(("/", "\\")):
                raise RuntimeError("unsafe path in the zip — not installed")
        root = _zip_root(names)
        entries = {}
        for m in names:
            if m.endswith("/") or not m.startswith(root):
                continue
            rel = m[len(root):]
            if not rel or "__pycache__" in rel or SKIP_NAMES.match(Path(rel).name) or _protected(rel):
                continue
            if rel.split("/")[0] in ("config", "memory") and rel.endswith(".json"):
                continue                                                 # your settings / memory stay yours
            entries[rel] = z.read(m)
    if not any(r in entries for r in ("main.py", "ui.py", "VERSION")) and not any(r.startswith(("actions/", "core/")) for r in entries):
        raise RuntimeError("that zip doesn't look like a JARVIS update")
    new_ver = entries.get("VERSION", b"").decode("utf-8", "replace").strip() or zpath.stem
    old_ver = current_version()
    manifest = {}
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        pass
    replaced, added, same, edited = [], [], [], []
    for rel, data in entries.items():
        dst = BASE / rel
        if dst.exists():
            cur = dst.read_bytes()
            if _md5(cur) == _md5(data):
                same.append(rel); continue
            if rel in manifest and manifest[rel] != _md5(cur):
                edited.append(rel)                                      # you changed it since the last install
            replaced.append(rel)
        else:
            added.append(rel)
    backup = BASE / "backups" / f"before-{new_ver}"
    if backup.exists():
        backup = BASE / "backups" / f"before-{new_ver}-{time.strftime('%Y%m%d-%H%M%S')}"
    result = {"from": old_ver, "to": new_ver, "zip": str(zpath), "replaced": replaced, "added": added,
              "unchanged": len(same), "edited_by_you": edited, "backup": str(backup)}
    if dry:
        return result
    for rel in replaced:
        (backup / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BASE / rel, backup / rel)
    backup.mkdir(parents=True, exist_ok=True)
    (backup / "_info.json").write_text(json.dumps({**result, "date": time.strftime("%Y-%m-%d %H:%M")}, indent=1),
                                      encoding="utf-8")
    for rel, data in entries.items():
        if rel in same:
            continue
        dst = BASE / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".new")
        tmp.write_bytes(data)
        os.replace(tmp, dst)
    for rel, data in entries.items():
        manifest[rel] = _md5(data)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=0), encoding="utf-8")
    if _is_git():                                                       # keep a history if you use GitHub
        _git("add", "-A"); _git("commit", "-m", f"Installed JARVIS {new_ver} from {zpath.name}")
    return result


def rollback() -> str:
    """Undo the most recent zip install (restores the backed-up files, removes added ones)."""
    root = BASE / "backups"
    infos = sorted(root.glob("before-*/_info.json"), key=lambda p: p.stat().st_mtime) if root.exists() else []
    if not infos:
        return "There's no installed update to undo."
    info_p = infos[-1]
    info = json.loads(info_p.read_text(encoding="utf-8"))
    bdir = info_p.parent
    for rel in info.get("replaced", []):
        src = bdir / rel
        if src.exists():
            shutil.copy2(src, BASE / rel)
    for rel in info.get("added", []):
        try:
            (BASE / rel).unlink()
        except FileNotFoundError:
            pass
    try:
        MANIFEST.unlink()                                               # can't trust it after a rollback
    except FileNotFoundError:
        pass
    bdir.rename(bdir.with_name("rolled-back-" + bdir.name[len("before-"):]))
    return (f"Undid the update to {info.get('to')}: {len(info.get('replaced', []))} files restored, "
            f"{len(info.get('added', []))} removed. You're back on {info.get('from')}.")


def describe_install(r: dict) -> str:
    msg = (f"Installed JARVIS {r['to']} (was {r['from']}): {len(r['replaced'])} files updated, "
           f"{len(r['added'])} new, {r['unchanged']} already up to date.")
    if r["edited_by_you"]:
        msg += (" You had changed " + ", ".join(r["edited_by_you"][:5])
                + " yourself — your versions are saved in " + r["backup"] + ".")
    return msg


def download_installer(info: dict) -> Path:
    rel = info["release"]
    asset = next((a for a in rel.get("assets", []) if a["name"].lower().endswith(".exe")), None)
    if not asset:
        raise RuntimeError("this release has no installer (.exe) attached")
    return _download(asset["url"], Path(tempfile.gettempdir()) / asset["name"])


def apply(info: dict | None = None) -> str:
    info = info or check()
    if not info.get("available"):
        return info.get("message", "Nothing to update.")
    if info["mode"] == "git":
        r = _git("pull", "--ff-only", timeout=180)
        if r.returncode != 0:
            return "git pull failed: " + (r.stderr or r.stdout).strip()[:200]
        return "Updated from GitHub (git pull)."
    if getattr(sys, "frozen", False):
        exe = download_installer(info)
        subprocess.Popen([str(exe)], close_fds=True)
        return f"Installer for {info['latest']} started."
    return apply_source_release(info)


def _wait_for(pid: int, secs: int = 60) -> None:
    try:
        import psutil
        p = psutil.Process(pid)
        p.wait(timeout=secs)
    except Exception:
        time.sleep(3)


def restart_jarvis() -> None:
    pyw = Path(sys.executable).with_name("pythonw.exe")
    py = str(pyw if pyw.exists() else sys.executable)
    subprocess.Popen([py, str(BASE / "main.py")], cwd=str(BASE), close_fds=True)


def main() -> int:
    args = sys.argv[1:]
    if "--wait" in args:
        _wait_for(int(args[args.index("--wait") + 1]))
    if "--rollback" in args:
        print(rollback())
        if "--restart" in args and not getattr(sys, "frozen", False):
            restart_jarvis()
        return 0
    if "--install-zip" in args:
        i = args.index("--install-zip")
        z = args[i + 1] if i + 1 < len(args) and not args[i + 1].startswith("--") else None
        z = Path(z) if z else find_update_zip()
        if not z or not Path(z).exists():
            print("No JARVIS update zip found in Downloads or on the Desktop. Drag the zip onto install_update.bat.")
            return 1
        print(f"Installing {Path(z).name} ...")
        try:
            print(describe_install(install_zip(z)))
        except Exception as e:
            print(f"Not installed: {e}")
            return 1
        if "--restart" in args and not getattr(sys, "frozen", False):
            restart_jarvis()
        return 0
    try:
        info = check()
    except Exception as e:
        print(f"Couldn't check for updates: {e}")
        return 1
    print(info["message"])
    if "--check" in args or not info.get("available"):
        return 0
    try:
        print(apply(info))
    except Exception as e:
        print(f"Update failed: {e}\nNothing important was changed — your settings and memory are untouched.")
        return 1
    if "--restart" in args and not getattr(sys, "frozen", False):
        restart_jarvis()
    return 0


if __name__ == "__main__":
    sys.exit(main())
