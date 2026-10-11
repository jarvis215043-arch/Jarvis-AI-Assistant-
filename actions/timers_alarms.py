"""actions/timers_alarms.py — Named timers (several at once, on the HUD), a smart
alarm (music, then the weather and your day) and a class-link opener."""
import threading
import time
import webbrowser
from datetime import datetime

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
ALARMS = H.mem_path("alarms.json")
_timers: dict = {}          # name → end time (monotonic)
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _hud():
    if not _timers:
        return
    now = time.monotonic()
    H.show(None, "TIMERS", "\n".join(f"{n:<18} {int(max(0, e - now)) // 60:02d}:{int(max(0, e - now)) % 60:02d}"
                                     for n, e in sorted(_timers.items(), key=lambda kv: kv[1])))


def _timer_loop() -> None:
    while True:
        now = time.monotonic()
        for name, end in list(_timers.items()):
            if now >= end:
                _timers.pop(name, None)
                H.say(f"[TIMER] Tell the user: the '{name}' timer is done.")
        time.sleep(0.5)


def _alarm_loop() -> None:
    time.sleep(20)
    while True:
        now = datetime.now()
        hm, wd = now.strftime("%H:%M"), DAYS[now.weekday()]
        data = H.load_json(ALARMS, {"alarms": [], "classes": [], "fired": {}})
        stamp = now.strftime("%Y-%m-%d %H:%M")
        for a in data["alarms"]:
            if a.get("on", True) and a["time"] == hm and (not a.get("days") or wd in a["days"]) and data["fired"].get(a["time"]) != stamp:
                data["fired"][a["time"]] = stamp
                try:
                    from core import tool_bus
                    tool_bus.run_tool("music_control", {"action": "play", "query": a.get("music") or "morning wake up music"}, timeout=30)
                except Exception:
                    pass
                H.say("[ALARM] Wake the user up warmly: say good morning and the time. Then check today's "
                      "weather with rain_alert and their calendar with google_calendar, and give a short "
                      "two-sentence plan for the day.")
                if not a.get("days"):
                    a["on"] = False
        for c in data["classes"]:
            key = "class:" + c["name"]
            t = datetime.strptime(c["time"], "%H:%M")
            early = (t.hour * 60 + t.minute - 1) % 1440
            if f"{early // 60:02d}:{early % 60:02d}" == hm and (not c.get("days") or wd in c["days"]) and data["fired"].get(key) != stamp:
                data["fired"][key] = stamp
                webbrowser.open(c["link"])
                H.say(f"[CLASS] Tell the user: your {c['name']} class starts in a minute — I've opened the link.")
        H.save_json(ALARMS, data)
        time.sleep(20)


H.on_ready(_timer_loop)
H.on_ready(_alarm_loop)


def _days(text: str):
    t = (text or "").lower()
    if not t or "every day" in t or "daily" in t:
        return []
    if "weekday" in t or "school day" in t:
        return DAYS[:5]
    if "weekend" in t:
        return DAYS[5:]
    return [d for d in DAYS if d in t]


def _hhmm(text: str):
    t = (text or "").strip().lower().replace(".", ":")
    for f in ("%H:%M", "%I:%M %p", "%I %p", "%I:%M%p", "%I%p"):
        try:
            return datetime.strptime(t, f).strftime("%H:%M")
        except ValueError:
            pass
    return None


def timers_alarms(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    data = H.load_json(ALARMS, {"alarms": [], "classes": [], "fired": {}})
    if act == "timer_start":
        try:
            mins = float(p.get("minutes") or 0)
        except (TypeError, ValueError):
            mins = 0
        if mins <= 0:
            return "How many minutes?"
        name = str(p.get("name") or f"timer {len(_timers) + 1}").strip()
        _timers[name] = time.monotonic() + mins * 60; _hud()
        return f"Started '{name}' for {mins:g} minute{'s' if mins != 1 else ''}."
    if act == "timer_list":
        if not _timers:
            return "No timers running."
        _hud()
        now = time.monotonic()
        return "Timers: " + "; ".join(f"{n} — {int(e - now) // 60} min {int(e - now) % 60} s" for n, e in _timers.items())
    if act == "timer_cancel":
        name = str(p.get("name") or "").strip()
        if name in _timers:
            _timers.pop(name); return f"Cancelled '{name}'."
        if name.lower() in ("all", "everything"):
            _timers.clear(); return "All timers cancelled."
        return f"No timer called '{name}'."
    if act == "alarm_set":
        hm = _hhmm(str(p.get("time") or ""))
        if not hm:
            return "What time? e.g. 6:30 am."
        data["alarms"] = [a for a in data["alarms"] if a["time"] != hm] + [{"time": hm, "days": _days(str(p.get("days") or "")), "music": p.get("music") or "", "on": True}]
        H.save_json(ALARMS, data)
        return f"Alarm set for {hm}{' on ' + ', '.join(_days(str(p.get('days') or ''))) if _days(str(p.get('days') or '')) else ''}. Keep the PC on with JARVIS running."
    if act == "alarm_list":
        on = [a for a in data["alarms"] if a.get("on", True)]
        return ("Alarms: " + "; ".join(f"{a['time']} {','.join(a['days']) or 'once'}" for a in on)) if on else "No alarms set."
    if act == "alarm_cancel":
        hm = _hhmm(str(p.get("time") or ""))
        data["alarms"] = [a for a in data["alarms"] if hm and a["time"] != hm]; H.save_json(ALARMS, data)
        return "Alarm cancelled." if hm else "All alarms cancelled."
    if act == "class_add":
        hm, link, name = _hhmm(str(p.get("time") or "")), str(p.get("link") or "").strip(), str(p.get("name") or "class").strip()
        if not hm or not link.startswith("http"):
            return "Tell me the class name, the time and the link (starting with https)."
        data["classes"] = [c for c in data["classes"] if c["name"] != name] + [{"name": name, "time": hm, "link": link, "days": _days(str(p.get("days") or ""))}]
        H.save_json(ALARMS, data)
        return f"I'll open the {name} link a minute before {hm}."
    if act == "class_list":
        return ("Classes: " + "; ".join(f"{c['name']} {c['time']} {','.join(c['days']) or 'daily'}" for c in data["classes"])) if data["classes"] else "No class links saved."
    if act == "class_remove":
        name = str(p.get("name") or "")
        data["classes"] = [c for c in data["classes"] if c["name"] != name]; H.save_json(ALARMS, data)
        return "Removed."
    return "Timers/alarms: timer_start, timer_list, timer_cancel, alarm_set, alarm_list, alarm_cancel, class_add, class_list, class_remove."


TOOL = {
    "name": "timers_alarms",
    "description": ("Named timers, alarms and class links. 'timer_start' (minutes, name), 'timer_list', "
                    "'timer_cancel' (name or 'all'). Smart alarm (music then a good-morning): 'alarm_set' (time "
                    "like '6:30 am', optional days 'weekdays'/'mon,wed', music), 'alarm_list', 'alarm_cancel'. "
                    "Online classes: 'class_add' (name, time, link, days) opens the link a minute before; "
                    "'class_list', 'class_remove'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "minutes": {"type": "NUMBER", "description": "Timer length."},
        "name": {"type": "STRING", "description": "Timer or class name."},
        "time": {"type": "STRING", "description": "e.g. '6:30 am' or '18:00'."},
        "days": {"type": "STRING", "description": "'weekdays', 'weekends', 'mon,wed,fri' or empty for once/daily."},
        "music": {"type": "STRING", "description": "Alarm music to play."},
        "link": {"type": "STRING", "description": "Class meeting link."}},
        "required": ["action"]},
    "handler": timers_alarms,
}
