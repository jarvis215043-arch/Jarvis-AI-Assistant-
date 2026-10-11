"""actions/system_plus.py — Power plan (battery saver / balanced / performance),
sleep or shutdown timer (CONFIRM), close a frozen app (CONFIRM), top processes,
biggest folders, a screen recorder, a PC specs report, and saving the clipboard
to a file."""
import os
import platform
import subprocess
import sys
import threading
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
NO_WIN = 0x08000000 if sys.platform == "win32" else 0
PLANS = {"saver": "a1841308-3541-4fab-bc81-f71556f20b4a", "balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
         "performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"}
_rec = {"on": False, "stop": False, "file": ""}


def _record(path: str, fps: int, max_s: int) -> None:
    import cv2, mss, numpy as np
    with mss.mss() as sct:
        mon = sct.monitors[1]
        w, h = mon["width"] // 2 * 2, mon["height"] // 2 * 2
        out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        t0 = time.monotonic(); n = 0
        while not _rec["stop"] and time.monotonic() - t0 < max_s:
            frame = np.asarray(sct.grab(mon))[:h, :w, :3]
            out.write(frame); n += 1
            time.sleep(max(0, t0 + n / fps - time.monotonic()))
        out.release()
    _rec["on"] = False
    H.say("[RECORDING] Tell the user the screen recording is saved in Videos, JARVIS.")


def system_plus(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    if act == "power":
        mode = str(p.get("mode") or "").lower()
        key = "saver" if "sav" in mode or "battery" in mode else "performance" if "perf" in mode or "high" in mode else "balanced"
        r = subprocess.run(["powercfg", "/setactive", PLANS[key]], capture_output=True, text=True, creationflags=NO_WIN)
        return f"Power plan set to {key}." if r.returncode == 0 else f"Windows didn't allow that plan ({(r.stderr or r.stdout).strip()[:80]})."
    if act == "timer":
        kind = "shutdown" if "shut" in str(p.get("mode") or "") else "sleep"
        mins = max(1, int(float(p.get("minutes") or 30)))
        from core import confirm as gate

        def _go():
            def later():
                time.sleep(mins * 60)
                if kind == "shutdown":
                    subprocess.run(["shutdown", "/s", "/t", "30"], creationflags=NO_WIN)
                else:
                    subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=NO_WIN)
            threading.Thread(target=later, daemon=True).start()
            return f"OK — the PC will {kind} in {mins} minutes. (Cancel a shutdown with: shutdown /a)"
        return gate.request("pc_timer", f"{kind.title()} the PC in {mins} minutes?", "Save your work first.", _go)
    if act == "kill":
        import psutil
        name = str(p.get("app") or "").lower().replace(".exe", "").strip()
        procs = [pr for pr in psutil.process_iter(["name"]) if name and name in (pr.info["name"] or "").lower()]
        if not procs:
            return f"No running app called '{name}'."
        from core import confirm as gate

        def _go():
            for pr in procs:
                try: pr.kill()
                except Exception: pass
            return f"Closed {procs[0].info['name']} ({len(procs)} process{'es' if len(procs) > 1 else ''})."
        return gate.request("kill_app", f"Force-close {procs[0].info['name']}?", "Unsaved work in it will be lost.", _go)
    if act == "top":
        import psutil
        ps = []
        for pr in psutil.process_iter(["name", "memory_info"]):
            try: ps.append((pr.info["memory_info"].rss, pr.info["name"]))
            except Exception: pass
        agg = {}
        for mem, n in ps:
            agg[n] = agg.get(n, 0) + mem
        rows = sorted(agg.items(), key=lambda kv: -kv[1])[:10]
        H.show(player, "TOP APPS BY MEMORY", "\n".join(f"{n:<28} {m / 1e9:.2f} GB" for n, m in rows))
        return "Using the most memory: " + ", ".join(f"{n} {m / 1e9:.1f} GB" for n, m in rows[:4]) + "."
    if act == "folder_sizes":
        root = Path(str(p.get("path") or Path.home())).expanduser()
        if not root.exists():
            return "That folder doesn't exist."
        sizes = []
        for sub in root.iterdir():
            if sub.is_dir() and not sub.name.startswith("."):
                tot = 0
                for dp, _, fns in os.walk(sub):
                    for fn in fns:
                        try: tot += (Path(dp) / fn).stat().st_size
                        except Exception: pass
                sizes.append((tot, sub.name))
        sizes.sort(reverse=True)
        H.show(player, f"BIGGEST FOLDERS — {root}", "\n".join(f"{s / 1e9:7.2f} GB  {n}" for s, n in sizes[:12]))
        return "Biggest: " + ", ".join(f"{n} {s / 1e9:.1f} GB" for s, n in sizes[:4]) + "."
    if act == "record_start":
        if _rec["on"]:
            return "Already recording — say 'stop recording the screen'."
        d = Path.home() / "Videos" / "JARVIS"; d.mkdir(parents=True, exist_ok=True)
        f = str(d / f"screen {datetime.now():%Y-%m-%d %H-%M-%S}.mp4")
        _rec.update(on=True, stop=False, file=f)
        threading.Thread(target=_record, args=(f, 12, int(float(p.get("minutes") or 10)) * 60), daemon=True).start()
        return "Recording the screen (no sound). Say 'stop recording the screen' when done."
    if act == "record_stop":
        if not _rec["on"]:
            return "Not recording."
        _rec["stop"] = True
        return "Stopping — saving the video."
    if act == "specs":
        import psutil
        info = [f"Windows: {platform.platform()}", f"CPU: {platform.processor() or 'unknown'} ({psutil.cpu_count()} threads)",
                f"RAM: {psutil.virtual_memory().total / 1e9:.1f} GB"]
        try:
            gpu = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"],
                                 capture_output=True, text=True, timeout=15, creationflags=NO_WIN).stdout.strip()
            if gpu: info.append("GPU: " + gpu.replace("\n", ", "))
        except Exception:
            pass
        for part in psutil.disk_partitions():
            try:
                u = psutil.disk_usage(part.mountpoint)
                if u.total > 5e9: info.append(f"Disk {part.mountpoint} {u.total / 1e9:.0f} GB ({u.free / 1e9:.0f} GB free)")
            except Exception:
                pass
        H.show(player, "PC SPECS", "\n".join(info))
        return "; ".join(info)
    if act == "save_clipboard":
        text = H.clipboard_text()
        if not text:
            return "The clipboard is empty."
        f = H.documents_dir("Clips") / f"clip {datetime.now():%Y-%m-%d %H-%M-%S}.txt"
        f.write_text(text, encoding="utf-8")
        return f"Saved the clipboard to Documents, JARVIS, Clips ({len(text.split())} words)."
    return "System: power (mode), timer (mode sleep/shutdown, minutes), kill (app), top, folder_sizes (path), record_start, record_stop, specs, save_clipboard."


TOOL = {
    "name": "system_plus",
    "description": ("PC system extras. 'power' (mode saver/balanced/performance); 'timer' (mode sleep/shutdown, minutes; asks to "
                    "CONFIRM); 'kill' (app; force-closes a frozen app after CONFIRM); 'top' (apps using most memory); "
                    "'folder_sizes' (path, default home); 'record_start' (minutes) / 'record_stop' screen recording; 'specs'; "
                    "'save_clipboard'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "mode": {"type": "STRING", "description": "Power mode, or sleep/shutdown for timer."},
        "minutes": {"type": "NUMBER", "description": "Timer / max recording minutes."},
        "app": {"type": "STRING", "description": "App to close."},
        "path": {"type": "STRING", "description": "Folder path."}}, "required": ["action"]},
    "handler": system_plus,
}
