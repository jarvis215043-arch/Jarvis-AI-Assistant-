"""actions/system_alerts.py — Warns when the laptop battery is low (20% and 10%,
when not charging) or a drive is nearly full (under 10% free, once a day)."""
import time

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
STATE = H.mem_path("system_alerts.json")


def _drives():
    import psutil
    out = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts or not part.fstype:
            continue
        try:
            u = psutil.disk_usage(part.mountpoint)
            if u.total > 5e9:                 # skip tiny / virtual drives
                out.append((part.mountpoint, u.free, u.total))
        except Exception:
            pass
    return out


def _watch() -> None:
    import psutil
    time.sleep(120)
    warned_batt = set()
    while True:
        try:
            st = H.load_json(STATE, {})
            if st.get("enabled", True):
                b = psutil.sensors_battery()
                if b is not None:
                    if b.power_plugged:
                        warned_batt.clear()
                    else:
                        for level in (20, 10):
                            if b.percent <= level and level not in warned_batt:
                                warned_batt.add(level)
                                H.say(f"[BATTERY] Tell the user in one short sentence: the battery is at {int(b.percent)} percent — plug in the charger.")
                                break
                if st.get("disk_day") != H.today():
                    low = [(m, f) for m, f, t in _drives() if t and f / t < 0.10]
                    if low:
                        st["disk_day"] = H.today(); H.save_json(STATE, st)
                        m, f = low[0]
                        H.say(f"[DISK] Tell the user in one short sentence: drive {m} is nearly full, only {f / 1e9:.1f} GB left. Suggest the Downloads tidy-up or deleting big files.")
        except Exception:
            pass
        time.sleep(120)


H.on_ready(_watch)


def system_alerts(parameters: dict, player=None) -> str:
    import psutil
    action = str((parameters or {}).get("action") or "status").lower()
    st = H.load_json(STATE, {})
    if action in ("on", "off"):
        st["enabled"] = action == "on"; H.save_json(STATE, st)
        return f"Battery and disk alerts {'on' if action == 'on' else 'off'}."
    b = psutil.sensors_battery()
    batt = (f"Battery {int(b.percent)}% ({'charging' if b.power_plugged else 'on battery'})" if b else "No battery (desktop PC)")
    disks = "; ".join(f"{m} {f / 1e9:.0f} GB free of {t / 1e9:.0f} GB" for m, f, t in _drives())
    return f"{batt}. Disks: {disks}. Alerts are {'on' if st.get('enabled', True) else 'off'}."


TOOL = {
    "name": "system_alerts",
    "description": ("Battery and disk-space alerts. action='status' (default) shows battery and free "
                    "space; 'on'/'off' switch the automatic warnings."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'status', 'on' or 'off'."}}, "required": []},
    "handler": system_alerts,
}
