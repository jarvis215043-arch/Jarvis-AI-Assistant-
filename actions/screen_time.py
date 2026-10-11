"""actions/screen_time.py — Records which app is in front every few seconds and
reports how long you spent in each app (memory/screen_time.json, this PC only)."""
import sys
import time
from datetime import date, timedelta

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
FILE = H.mem_path("screen_time.json")
STEP = 5   # seconds between samples


def _front_app() -> str:
    if sys.platform != "win32":
        return ""
    import ctypes
    import psutil
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        name = psutil.Process(pid.value).name()
    except Exception:
        return ""
    return name.rsplit(".", 1)[0]


def _idle_seconds() -> float:
    if sys.platform != "win32":
        return 0
    import ctypes

    class LII(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    li = LII(); li.cbSize = ctypes.sizeof(LII)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li))
    return (ctypes.windll.kernel32.GetTickCount() - li.dwTime) / 1000.0


def _watch() -> None:
    pending, last_save = {}, time.monotonic()
    while True:
        try:
            if _idle_seconds() < 300:                # don't count time away from the PC
                app = _front_app()
                if app:
                    pending[app] = pending.get(app, 0) + STEP
            if time.monotonic() - last_save > 60 and pending:
                data = H.load_json(FILE, {})
                day = data.setdefault(H.today(), {})
                for a, s in pending.items():
                    day[a] = day.get(a, 0) + s
                for k in sorted(data)[:-30]:         # keep 30 days
                    data.pop(k)
                H.save_json(FILE, data)
                pending, last_save = {}, time.monotonic()
        except Exception:
            pass
        time.sleep(STEP)


H.on_ready(_watch)


def _fmt(s: int) -> str:
    h, m = divmod(int(s) // 60, 60)
    return f"{h} h {m} min" if h else f"{m} min"


def screen_time(parameters: dict, player=None) -> str:
    when = str((parameters or {}).get("day") or "today").lower()
    d = date.today() - timedelta(days=1) if when == "yesterday" else date.today()
    data = H.load_json(FILE, {})
    if when == "week":
        tot = {}
        for k, v in data.items():
            if k >= (date.today() - timedelta(days=6)).isoformat():
                for a, s in v.items():
                    tot[a] = tot.get(a, 0) + s
        label = "the last 7 days"
    else:
        tot = data.get(d.isoformat(), {})
        label = "today" if when != "yesterday" else "yesterday"
    if not tot:
        return f"No screen time recorded for {label} yet (it's counted while JARVIS is running)."
    rows = sorted(tot.items(), key=lambda kv: -kv[1])
    H.show(player, f"SCREEN TIME — {label}", "\n".join(f"{a:<22} {_fmt(s)}" for a, s in rows[:15])
           + f"\n\nTotal: {_fmt(sum(tot.values()))}")
    return f"Screen time {label}: {_fmt(sum(tot.values()))} in total. Top: " + ", ".join(f"{a} {_fmt(s)}" for a, s in rows[:3]) + "."


TOOL = {
    "name": "screen_time",
    "description": ("How long the user spent in each app (counted while JARVIS runs; idle time "
                    "excluded). day='today' (default), 'yesterday' or 'week'."),
    "parameters": {"type": "OBJECT", "properties": {
        "day": {"type": "STRING", "description": "'today', 'yesterday' or 'week'."}}, "required": []},
    "handler": screen_time,
}
