"""actions/auto_backup.py — Backs up the whole Jarvis folder (code, settings,
memory) so losing a USB never matters again. Targets: your OneDrive folder
(syncs to the cloud by itself), Google Drive (uses your Google login; needs the
Google Drive API enabled), or any folder. Weekly automatic backups optional.
Your keys are stored LOCKED in the backup (only your Windows account on this PC
can open them); on a new PC you re-enter the Gemini key and log in to Google."""
import os
import shutil
import threading
import time
import zipfile
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
STATE = H.mem_path("backup.json")
SKIP_DIRS = {"dist", "build", "__pycache__", ".git", ".venv", "venv", "generated_images", "node_modules"}


def _make_zip() -> Path:
    base = H.base_dir()
    out = Path(os.environ.get("TEMP", "/tmp")) / f"JARVIS backup {datetime.now():%Y-%m-%d %H-%M}.zip"
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("core.secure_config", str(base / "core" / "secure_config.py"))
        sc = importlib.util.module_from_spec(spec); spec.loader.exec_module(sc)
        secrets = sc.secret_files() if sc.available() else []
    except Exception:
        sc, secrets = None, []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                fp = Path(root) / f
                if fp.suffix.lower() in (".wav", ".mp4") and "config" not in fp.parts:
                    continue
                if fp in secrets or fp.name.endswith(".locked"):
                    continue                         # added below, locked
                try:
                    z.write(fp, Path("Jarvis") / fp.relative_to(base))
                except Exception:
                    pass
        # Keys go in LOCKED (only this Windows account can open them), never readable.
        for fp in secrets:
            try:
                z.writestr(str(Path("Jarvis") / fp.relative_to(base)) + ".locked", sc.protect(fp.read_bytes()))
            except Exception:
                pass
    return out


def _onedrive() -> Path | None:
    od = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    return Path(od) if od and Path(od).exists() else None


def _drive_upload(path: Path) -> str:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    scopes = ["https://www.googleapis.com/auth/drive.file"]       # only files JARVIS itself creates
    tok = H.base_dir() / "config" / "google_drive_token.json"
    creds = Credentials.from_authorized_user_file(str(tok), scopes) if tok.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            c = H.cfg()
            cid, sec = c.get("google_calendar_client_id"), c.get("google_calendar_client_secret")
            if not cid or not sec:
                raise RuntimeError("no Google Client ID/secret saved (same ones as Calendar)")
            flow = InstalledAppFlow.from_client_config({"installed": {
                "client_id": cid, "client_secret": sec, "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": ["http://localhost"]}}, scopes)
            creds = flow.run_local_server(port=0, timeout_seconds=120)
        tok.write_text(creds.to_json(), encoding="utf-8")
    svc = build("drive", "v3", credentials=creds)
    st = H.load_json(STATE, {})
    folder = st.get("drive_folder")
    if not folder:
        folder = svc.files().create(body={"name": "JARVIS Backups", "mimeType": "application/vnd.google-apps.folder"}, fields="id").execute()["id"]
        st["drive_folder"] = folder; H.save_json(STATE, st)
    f = svc.files().create(body={"name": path.name, "parents": [folder]},
                           media_body=MediaFileUpload(str(path), resumable=True), fields="id").execute()
    return f"Google Drive → JARVIS Backups ({path.name})"


def backup_now() -> str:
    st = H.load_json(STATE, {})
    target = st.get("target") or ("onedrive" if _onedrive() else "")
    if not target:
        return "Where should I back up? Say 'back up to OneDrive', 'back up to Google Drive', or give me a folder."
    z = _make_zip()
    mb = z.stat().st_size / 1e6
    try:
        if target == "onedrive":
            od = _onedrive()
            if not od:
                return "OneDrive isn't set up on this PC."
            d = od / "JARVIS Backups"; d.mkdir(exist_ok=True)
            shutil.copy2(z, d / z.name)
            olds = sorted(d.glob("JARVIS backup *.zip"))[:-4]                # keep the newest 4
            for o in olds:
                o.unlink()
            where = f"OneDrive → JARVIS Backups ({z.name})"
        elif target == "drive":
            where = _drive_upload(z)
        else:
            d = Path(target); d.mkdir(parents=True, exist_ok=True); shutil.copy2(z, d / z.name)
            where = str(d / z.name)
    finally:
        try:
            z.unlink()
        except Exception:
            pass
    st["last"] = datetime.now().isoformat(timespec="seconds"); H.save_json(STATE, st)
    return f"Backed up the Jarvis folder ({mb:.1f} MB) to {where}."


def _watch() -> None:
    time.sleep(300)
    while True:
        st = H.load_json(STATE, {})
        if st.get("weekly") and st.get("target"):
            last = st.get("last")
            if not last or (datetime.now() - datetime.fromisoformat(last)).days >= 7:
                try:
                    msg = backup_now(); H.log(None, "SYS: " + msg)
                except Exception as e:
                    H.log(None, f"SYS: Weekly backup failed: {e}")
        time.sleep(3 * 3600)


H.on_ready(_watch)


def auto_backup(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "now").lower()
    st = H.load_json(STATE, {})
    if act == "set_target":
        t = str(p.get("target") or "").strip()
        t = "onedrive" if "onedrive" in t.lower() else "drive" if "drive" in t.lower() and "google" in t.lower() or t.lower() == "drive" else t
        if not t:
            return "Where to? onedrive, google drive, or a folder path."
        st["target"] = t; H.save_json(STATE, st)
        return f"Backups will go to {t}."
    if act in ("weekly_on", "weekly_off"):
        st["weekly"] = act == "weekly_on"; H.save_json(STATE, st)
        return "Weekly automatic backups on." if st["weekly"] else "Weekly backups off."
    if act == "status":
        return f"Target: {st.get('target') or 'not set'}; weekly: {'on' if st.get('weekly') else 'off'}; last backup: {st.get('last') or 'never'}."
    def _bg():
        try:
            H.say("[BACKUP] Tell the user: " + backup_now())
        except Exception as e:
            H.say(f"[BACKUP] Tell the user the backup failed: {e}")
    threading.Thread(target=_bg, daemon=True).start()
    return "Backing up the Jarvis folder now — I'll tell you when it's done."


TOOL = {
    "name": "auto_backup",
    "description": ("Backs up the Jarvis folder. action='now' (default); 'set_target' (target: 'onedrive', 'google drive' "
                    "or a folder path); 'weekly_on' / 'weekly_off'; 'status'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'now', 'set_target', 'weekly_on', 'weekly_off' or 'status'."},
        "target": {"type": "STRING", "description": "'onedrive', 'google drive', or a folder path."}}, "required": []},
    "handler": auto_backup,
}
