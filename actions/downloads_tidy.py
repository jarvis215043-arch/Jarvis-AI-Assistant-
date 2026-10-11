"""actions/downloads_tidy.py — Sorts the Downloads folder into subfolders by type,
automatically once a week (if auto is on) or when asked. Never overwrites, skips
unfinished downloads, and can undo the last tidy-up."""
import shutil
import time
from datetime import datetime
from pathlib import Path

def _load_helpers():
    import importlib.util, sys
    from pathlib import Path
    key = "actions._helpers"
    if key in sys.modules:
        return sys.modules[key]
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(key, str(base / "actions" / "_helpers.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


H = _load_helpers()
STATE = H.mem_path("downloads_tidy.json")
GROUPS = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic"},
    "Videos": {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv"},
    "Music": {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".ppt", ".pptx", ".xls", ".xlsx", ".csv", ".odt", ".md"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Installers": {".exe", ".msi", ".apk"},
    "Code": {".py", ".js", ".html", ".css", ".json", ".ino", ".cpp", ".java"},
}
SKIP = {".crdownload", ".part", ".tmp", ".download", ".partial"}


def _downloads() -> Path:
    return Path.home() / "Downloads"


def tidy() -> tuple[int, dict]:
    src = _downloads()
    moved, counts = [], {}
    if not src.exists():
        return 0, {}
    for f in src.iterdir():
        if not f.is_file() or f.suffix.lower() in SKIP or f.name.startswith("."):
            continue
        if time.time() - f.stat().st_mtime < 120:      # still being written? leave it
            continue
        group = next((g for g, exts in GROUPS.items() if f.suffix.lower() in exts), "Other")
        dest_dir = src / group
        dest_dir.mkdir(exist_ok=True)
        dest = dest_dir / f.name
        n = 1
        while dest.exists():
            dest = dest_dir / f"{f.stem} ({n}){f.suffix}"
            n += 1
        try:
            shutil.move(str(f), str(dest))
            moved.append([str(dest), str(f)])
            counts[group] = counts.get(group, 0) + 1
        except Exception:
            pass
    st = H.load_json(STATE, {})
    st.update(last_run=datetime.now().isoformat(timespec="seconds"), last_moves=moved)
    H.save_json(STATE, st)
    return len(moved), counts


def _watch() -> None:
    time.sleep(120)
    while True:
        st = H.load_json(STATE, {})
        if st.get("auto"):
            last = st.get("last_run")
            if not last or (datetime.now() - datetime.fromisoformat(last)).days >= 7:
                n, _ = tidy()
                if n:
                    H.log(None, f"SYS: Weekly Downloads tidy-up moved {n} file(s).")
        time.sleep(6 * 3600)


H.on_ready(_watch)


def downloads_tidy(parameters: dict, player=None) -> str:
    action = str((parameters or {}).get("action") or "now").lower()
    st = H.load_json(STATE, {})
    if action in ("auto_on", "weekly"):
        st["auto"] = True; H.save_json(STATE, st)
        return "Done — I'll tidy your Downloads folder automatically once a week."
    if action == "auto_off":
        st["auto"] = False; H.save_json(STATE, st)
        return "Weekly tidy-up switched off."
    if action == "undo":
        moves = st.get("last_moves") or []
        back = 0
        for dest, orig in reversed(moves):
            try:
                if Path(dest).exists() and not Path(orig).exists():
                    shutil.move(dest, orig); back += 1
            except Exception:
                pass
        st["last_moves"] = []; H.save_json(STATE, st)
        return f"Put {back} file(s) back where they were."
    n, counts = tidy()
    if not n:
        return "Your Downloads folder is already tidy."
    H.show(player, "DOWNLOADS TIDIED", "\n".join(f"{g}: {c}" for g, c in sorted(counts.items())))
    return f"Moved {n} file(s) into folders: " + ", ".join(f"{c} {g}" for g, c in counts.items()) + ". Say 'undo the tidy-up' to put them back."


TOOL = {
    "name": "downloads_tidy",
    "description": ("Sorts the Downloads folder into Images, Videos, Music, Documents, Archives, "
                    "Installers, Code and Other. action='now' (default); 'auto_on' to do it weekly; "
                    "'auto_off'; 'undo' puts the last tidy-up back."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'now', 'auto_on', 'auto_off' or 'undo'."}},
        "required": []},
    "handler": downloads_tidy,
}
