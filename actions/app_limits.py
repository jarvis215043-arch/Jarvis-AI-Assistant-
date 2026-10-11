"""actions/app_limits.py — Your own daily time limits for apps ("max 60 minutes of
Valorant on school days"). Uses the screen-time counts; warns at 80% and closes
the app when the limit is reached."""
import time
from datetime import date

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
FILE = H.mem_path("app_limits.json")


def _today_usage() -> dict:
    return H.load_json(H.mem_path("screen_time.json"), {}).get(H.today(), {})


def _applies(rule) -> bool:
    d = rule.get("days", "all")
    wd = date.today().weekday()
    return d == "all" or (d == "weekdays" and wd < 5) or (d == "weekends" and wd >= 5)


def _watch() -> None:
    import psutil
    time.sleep(90)
    while True:
        rules = H.load_json(FILE, {"rules": {}, "warned": {}})
        use = _today_usage()
        for app, rule in rules["rules"].items():
            if not _applies(rule):
                continue
            mins = sum(s for a, s in use.items() if app in a.lower()) / 60
            key = f"{H.today()}:{app}"
            if mins >= rule["minutes"]:
                hit = False
                for pr in psutil.process_iter(["name"]):
                    if app in (pr.info["name"] or "").lower():
                        try:
                            pr.terminate(); hit = True
                        except Exception:
                            pass
                if hit:
                    H.say(f"[LIMIT] Tell the user kindly: that's your {rule['minutes']} minutes of {app} for today — I've closed it.")
            elif mins >= rule["minutes"] * 0.8 and rules["warned"].get(key) != "80":
                rules["warned"][key] = "80"; H.save_json(FILE, rules)
                H.say(f"[LIMIT] Tell the user: about {int(rule['minutes'] - mins)} minutes of {app} left today.")
        time.sleep(60)


H.on_ready(_watch)


def app_limits(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "list").lower()
    rules = H.load_json(FILE, {"rules": {}, "warned": {}})
    app = str(p.get("app") or "").lower().strip().replace(".exe", "")
    if act == "set":
        try:
            m = int(float(p.get("minutes")))
        except (TypeError, ValueError):
            return "How many minutes a day?"
        if not app:
            return "Which app? (use its program name, e.g. 'valorant', 'robloxplayerbeta', 'chrome')"
        rules["rules"][app] = {"minutes": m, "days": str(p.get("days") or "all").lower()}; H.save_json(FILE, rules)
        return f"Limit set: {m} minutes of {app} a day ({rules['rules'][app]['days']}). I'll warn you at 80%."
    if act == "remove":
        rules["rules"].pop(app, None); H.save_json(FILE, rules)
        return f"Removed the limit for {app}."
    use = _today_usage()
    if not rules["rules"]:
        return "No app limits set. Example: 'limit Valorant to 60 minutes on school days'."
    rows = [f"{a}: {int(sum(s for x, s in use.items() if a in x.lower()) / 60)} / {r['minutes']} min ({r['days']})" for a, r in rules["rules"].items()]
    H.show(player, "APP LIMITS", "\n".join(rows))
    return "Today: " + "; ".join(rows)


TOOL = {
    "name": "app_limits",
    "description": ("Self-set daily app time limits (uses screen time). action='set' (app program name, minutes, days "
                    "'all'/'weekdays'/'weekends'), 'remove' (app), 'list' (default, shows today's usage vs limits)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'set', 'remove' or 'list'."},
        "app": {"type": "STRING", "description": "Program name, e.g. 'valorant'."},
        "minutes": {"type": "NUMBER", "description": "Minutes per day."},
        "days": {"type": "STRING", "description": "'all', 'weekdays' or 'weekends'."}}, "required": []},
    "handler": app_limits,
}
