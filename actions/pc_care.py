"""actions/pc_care.py — PC clean-up (temp files + recycle bin, after you press
CONFIRM), startup apps, internet check, Windows/driver update checker, and a
password-strength checker that runs only in your browser (never sent anywhere)."""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
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
STARTUP_BACKUP = H.base_dir() / "config" / "startup_backup.json"
NO_WIN = 0x08000000 if sys.platform == "win32" else 0


def _ps(cmd: str, timeout: int = 60) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                       timeout=timeout, creationflags=NO_WIN)
    return (r.stdout or "") + (r.stderr or "")


def _temp_dirs():
    dirs = {Path(tempfile.gettempdir())}
    if sys.platform == "win32":
        dirs.add(Path(os.environ.get("WINDIR", "C:/Windows")) / "Temp")
    return [d for d in dirs if d.exists()]


def _size(paths, older_than: float = 86400):
    total, files = 0, []
    cutoff = time.time() - older_than
    for d in paths:
        for root, _, fns in os.walk(d):
            for fn in fns:
                f = Path(root) / fn
                try:
                    st = f.stat()
                    if st.st_mtime < cutoff:
                        total += st.st_size; files.append(f)
                except Exception:
                    pass
    return total, files


def _run_keys():
    import winreg
    out = []
    for hive, hname in ((winreg.HKEY_CURRENT_USER, "HKCU"), (winreg.HKEY_LOCAL_MACHINE, "HKLM")):
        try:
            k = winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Run")
            i = 0
            while True:
                try:
                    n, v, _ = winreg.EnumValue(k, i); out.append((hname, n, v)); i += 1
                except OSError:
                    break
        except OSError:
            pass
    return out


PW_HTML = """<!doctype html><html><head><meta charset=utf-8><title>Password checker</title><style>
body{background:#000;color:#ffb070;font-family:Segoe UI,Arial;display:flex;flex-direction:column;align-items:center;padding:60px}
input{width:460px;font-size:22px;padding:10px;background:#120700;color:#ffe2c4;border:1px solid #ff7a1a}#bar{width:480px;height:14px;background:#2a1405;margin-top:16px}
#fill{height:100%;width:0}#r{margin-top:14px;font-size:20px}ul{color:#c88050}</style></head><body><h2>PASSWORD STRENGTH CHECKER</h2>
<p style="color:#a86030">Runs only in this page — nothing is saved or sent anywhere.</p><input id=p type=password placeholder="Type a password">
<label style="margin-top:8px"><input type=checkbox onclick="p.type=this.checked?'text':'password'" style="width:auto"> show</label>
<div id=bar><div id=fill></div></div><div id=r></div><ul id=t></ul><script>
const common=["password","123456","qwerty","111111","iloveyou","abc123","admin","welcome","letmein","football","monkey","dragon","jarvis"];
p.oninput=()=>{let v=p.value,s=0,tips=[],pool=0;if(/[a-z]/.test(v))pool+=26;else tips.push("add lowercase letters");if(/[A-Z]/.test(v))pool+=26;else tips.push("add CAPITAL letters");
if(/[0-9]/.test(v))pool+=10;else tips.push("add numbers");if(/[^A-Za-z0-9]/.test(v))pool+=32;else tips.push("add symbols like ! ? #");
let bits=v.length*Math.log2(pool||1);if(v.length<12)tips.push("make it at least 12 characters");if(/(.)\\1\\1/.test(v)){bits-=10;tips.push("avoid repeating characters")}
if(common.some(c=>v.toLowerCase().includes(c))){bits=Math.min(bits,20);tips.push("don't use common words or patterns")}
let lvl=bits<36?["Very weak","#ff3b3b",20]:bits<60?["Weak","#ff7a1a",45]:bits<80?["Good","#ffd24a",72]:["Strong","#4dff88",100];
fill.style.width=lvl[2]+"%";fill.style.background=lvl[1];r.textContent=v?lvl[0]+"  ("+Math.round(bits)+" bits)":"";t.innerHTML=v?tips.map(x=>"<li>"+x+"</li>").join(""):""};p.focus()</script></body></html>"""


def pc_care(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    if act == "cleanup":
        size, files = _size(_temp_dirs())
        mb = size / 1e6
        from core import confirm as gate

        def _run():
            freed = 0
            for f in files:
                try:
                    s = f.stat().st_size; f.unlink(); freed += s
                except Exception:
                    pass
            try:
                _ps("Clear-RecycleBin -Force -ErrorAction SilentlyContinue", 60)
            except Exception:
                pass
            return f"Cleaned up {freed / 1e6:.0f} MB of temporary files and emptied the recycle bin."
        return gate.request("pc_cleanup", "Clean up the PC?",
                            f"Delete {len(files)} old temporary files (~{mb:.0f} MB) and empty the recycle bin.", _run)
    if act == "startup_list":
        try:
            items = _run_keys()
        except Exception as e:
            return f"I couldn't read the startup list: {e}"
        folder = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
        files = [f.stem for f in folder.glob("*")] if folder.exists() else []
        rows = [f"{n}  ({h})" for h, n, _ in items] + [f"{n}  (startup folder)" for n in files]
        H.show(player, "STARTUP APPS", "\n".join(rows) or "nothing")
        return f"{len(rows)} things start with Windows: " + ", ".join(n for h, n, _ in items) + (", " + ", ".join(files) if files else "")
    if act in ("startup_disable", "startup_enable"):
        import winreg
        name = str(p.get("name") or "").strip()
        backup = H.load_json(STARTUP_BACKUP, {})
        if act == "startup_enable":
            if name not in backup:
                return f"I haven't disabled anything called {name}."
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, backup.pop(name)); H.save_json(STARTUP_BACKUP, backup)
            return f"{name} will start with Windows again."
        match = next(((h, n, v) for h, n, v in _run_keys() if n.lower() == name.lower()), None)
        if not match:
            return f"Nothing called {name} in your startup list."
        if match[0] != "HKCU":
            return f"{name} is a system-wide startup item; turn it off in Task Manager → Startup apps instead."
        from core import confirm as gate

        def _run():
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(k, match[1]); backup[match[1]] = match[2]; H.save_json(STARTUP_BACKUP, backup)
            return f"{match[1]} won't start with Windows any more (say 'enable {match[1]} at startup' to undo)."
        return gate.request("startup_disable", f"Stop {match[1]} starting with Windows?", "You can turn it back on any time.", _run)
    if act == "internet":
        out = []
        try:
            ts = []
            for _ in range(3):
                t0 = time.perf_counter(); socket.create_connection(("1.1.1.1", 443), timeout=3).close(); ts.append((time.perf_counter() - t0) * 1000)
            out.append(f"ping {min(ts):.0f} ms")
        except Exception:
            return "You seem to be offline — I can't reach the internet."
        try:
            import requests
            t0 = time.perf_counter()
            r = requests.get("https://speed.cloudflare.com/__down?bytes=15000000", timeout=30)
            secs = time.perf_counter() - t0
            out.append(f"download about {len(r.content) * 8 / secs / 1e6:.0f} Mbps")
        except Exception:
            out.append("speed test failed")
        if sys.platform == "win32":
            txt = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, creationflags=NO_WIN).stdout
            ssid = next((l.split(":", 1)[1].strip() for l in txt.splitlines() if l.strip().startswith("SSID") and "BSSID" not in l), "")
            sig = next((l.split(":", 1)[1].strip() for l in txt.splitlines() if l.strip().startswith("Signal")), "")
            if ssid:
                out.append(f"Wi-Fi '{ssid}' signal {sig}")
        return "Internet: " + ", ".join(out) + "."
    if act == "updates":
        def _check():
            try:
                res = _ps("=New-Object -ComObject Microsoft.Update.Session;=.CreateUpdateSearcher().Search('IsInstalled=0 and IsHidden=0');"
                          ".Updates | ForEach-Object { .Title }", 300)
                titles = [l.strip() for l in res.splitlines() if l.strip() and "Exception" not in l]
                if titles:
                    H.show(None, "UPDATES AVAILABLE", "\n".join(titles[:20]))
                    H.say(f"[UPDATES] Tell the user: {len(titles)} Windows or driver update(s) are available — the list is on screen; "
                          "they can install them in Settings, Windows Update.")
                else:
                    H.say("[UPDATES] Tell the user: Windows and drivers are up to date.")
            except Exception as e:
                H.say(f"[UPDATES] Tell the user the update check failed: {e}")
        threading.Thread(target=_check, daemon=True).start()
        return "Checking for Windows and driver updates in the background — this can take a minute or two."
    if act == "password_checker":
        f = H.documents_dir() / "Password checker.html"
        f.write_text(PW_HTML, encoding="utf-8")
        webbrowser.open(f.as_uri())
        return "Opened the password checker in your browser. Type the password THERE — never say it to me; nothing leaves your PC."
    return "PC care: cleanup, startup_list, startup_disable, startup_enable, internet, updates, password_checker."


TOOL = {
    "name": "pc_care",
    "description": ("PC care. 'cleanup' (temp files + recycle bin, asks to CONFIRM); 'startup_list', 'startup_disable' / "
                    "'startup_enable' (name); 'internet' (ping, speed, Wi-Fi signal); 'updates' (checks Windows & "
                    "driver updates in the background); 'password_checker' opens a local page — tell the user to type "
                    "the password there, never to you."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "name": {"type": "STRING", "description": "Startup item name."}}, "required": ["action"]},
    "handler": pc_care,
}
