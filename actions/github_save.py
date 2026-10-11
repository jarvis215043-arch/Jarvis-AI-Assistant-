"""actions/github_save.py — JARVIS saves its own code to GitHub, and zips itself (2.7).

  "save my code to GitHub" / "push to git"          → action='save' (optional message)
  "is my code saved on GitHub?"                       → action='status'
  "save to GitHub every day" / "stop daily saves"     → action='auto_on' / 'auto_off'
  "make a zip of yourself" / "zip the latest from GitHub" → action='zip' (source 'pc' or 'github')
Progress shows in the HUD log as a percentage. Keys, settings and memory never go
to GitHub (safety-checked every time). First time: double-click setup_github.bat
once (it signs you in to GitHub and makes your private repo).
"""
import sys
import threading
import time


def _load_helpers():
    import importlib.util
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
_busy = {"on": False}


def _progress(player, label):
    last = {"p": -25}
    def cb(pct, text):
        if pct >= last["p"] + 25 or pct == 100:                  # every 25% in the HUD log
            last["p"] = pct
            H.log(player, f"SYS: {label} {pct}% — {text}")
    return cb


def _make_zip(source: str, player):
    import importlib.util
    spec = importlib.util.spec_from_file_location("jarvis_make_zip", str(H.base_dir() / "make_zip.py"))
    mz = importlib.util.module_from_spec(spec); spec.loader.exec_module(mz)

    class _HudProgress(mz.Progress):                              # same counter, shown in the HUD log
        def __init__(self, tb, tf, label):
            super().__init__(tb, tf, label); self._shown = -10
            H.log(player, f"SYS: {label}")

        def add(self, nbytes=0, files=0, force=False):
            super().add(nbytes, files, force)
            pct = min(100, int(self.b * 100 / self.tb))
            if pct >= self._shown + 10:
                self._shown = pct - pct % 10
                H.log(player, f"SYS: zip {pct}%  ({self.f}/{self.tf} files)")

        def done(self):
            super().done()
            H.log(player, f"SYS: zip 100% — {self.tf} files done")
    mz.Progress = _HudProgress
    stamp = time.strftime("%Y-%m-%d-%H%M")
    if source == "github":
        return mz.zip_github(H.base_dir().parent / f"Jarvis-github-{stamp}.zip")
    return mz.zip_local(H.base_dir().parent / f"Jarvis-full-{stamp}.zip")


def _auto_loop():
    from core import git_sync as G
    time.sleep(600)
    while True:
        try:
            cfg = H.cfg()
            if cfg.get("git_auto_save") and cfg.get("git_auto_day") != H.today() and not _busy["on"]:
                st = G.status()
                if st.get("ready") and (st.get("pending") or st.get("unpushed")):
                    _busy["on"] = True
                    try:
                        msg = G.save("JARVIS daily auto-save " + time.strftime("%d %b %Y"))
                    finally:
                        _busy["on"] = False
                    H.save_cfg("git_auto_day", H.today())
                    H.log(None, f"SYS: Daily GitHub save — {msg}")
        except Exception as e:
            print(f"[GitHub] auto-save skipped: {e}")
        time.sleep(3600)


H.on_ready(_auto_loop)


def github_save(parameters: dict, player=None) -> str:
    from core import git_sync as G
    p = parameters or {}
    act = str(p.get("action") or "save").lower().strip()
    if act in ("auto_on", "auto_off"):
        H.save_cfg("git_auto_save", act == "auto_on")
        return ("I'll save your code to GitHub once a day when something has changed." if act == "auto_on"
                else "Daily GitHub saves are off.")
    if act == "status":
        st = G.status()
        if not st["ready"]:
            return st["reason"]
        n = len(st["pending"])
        return (f"Last saved: {st['last'] or 'never'}. " + (f"{n} file(s) changed since then." if n else "No unsaved changes.")
                + (f" {st['unpushed']} save(s) not uploaded yet." if st.get("unpushed") else ""))
    if _busy["on"]:
        return "I'm already doing that — one moment."
    if act == "zip":
        source = "github" if "git" in str(p.get("source") or "").lower() else "pc"

        def _z():
            _busy["on"] = True
            try:
                path = _make_zip(source, player)
                H.say(f"[ZIP] Tell the user in one sentence: the zip is ready — '{path.name}', next to the Jarvis folder "
                      f"({path.stat().st_size / 1e6:.0f} MB)" + (" — it includes their memory, so don't share it publicly"
                                                                  if source == "pc" else " — the version saved on GitHub") + ".")
            except Exception as e:
                H.say(f"[ZIP] Tell the user the zip couldn't be made: {e}")
            finally:
                _busy["on"] = False
        threading.Thread(target=_z, daemon=True, name="jarvis-zip").start()
        return "Making the zip — progress is in the HUD log. I'll say when it's ready."
    st = G.status()
    if not st["ready"]:
        return st["reason"]

    def _go():
        _busy["on"] = True
        try:
            msg = G.save(str(p.get("message") or ""), progress=_progress(player, "GitHub"))
            H.say(f"[GITHUB] Tell the user in one short sentence: {msg}")
        except Exception as e:
            H.say(f"[GITHUB] Tell the user saving to GitHub failed: {e}")
        finally:
            _busy["on"] = False
    threading.Thread(target=_go, daemon=True, name="github-save").start()
    n = len(st["pending"])
    return f"Saving {n} changed file(s) to GitHub — progress is in the HUD log." if n else "Checking GitHub is up to date…"


TOOL = {
    "name": "github_save",
    "description": ("Saves JARVIS's own code to the user's private GitHub (commit + push, keys/memory never uploaded), or "
                    "makes a zip of the whole Jarvis folder. action='save' (default; message optional), 'status', "
                    "'auto_on'/'auto_off' (daily save), 'zip' (source='pc' = this folder incl. memory, or 'github' = "
                    "latest saved version). Use for 'save my code to GitHub', 'push to git', 'make a zip of yourself'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "save | status | auto_on | auto_off | zip"},
        "message": {"type": "STRING", "description": "Optional note for this save."},
        "source": {"type": "STRING", "description": "For zip: 'pc' (default) or 'github'."}}, "required": []},
    "handler": github_save,
}
