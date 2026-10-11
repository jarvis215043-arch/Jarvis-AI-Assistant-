"""actions/birthdays.py — Remember birthdays and remind you the day before and
on the day (checked a minute after JARVIS starts, then every few hours)."""
import time
from datetime import date, datetime

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
FILE = H.mem_path("birthdays.json")
_FMTS = ("%d %B", "%d %b", "%B %d", "%b %d", "%d-%m", "%d/%m", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y")


def _parse(text: str):
    t = (text or "").strip()
    for f in _FMTS:
        try:
            d = datetime.strptime(t, f)
            return d.month, d.day
        except ValueError:
            pass
    return None


def _days_until(m: int, d: int) -> int:
    t = date.today()
    try:
        nxt = date(t.year, m, d)
    except ValueError:                      # 29 Feb in a non-leap year
        nxt = date(t.year, 3, 1)
    if nxt < t:
        nxt = nxt.replace(year=t.year + 1)
    return (nxt - t).days


def _upcoming(data: dict, within: int):
    out = []
    for name, v in data.items():
        n = _days_until(v["m"], v["d"])
        if n <= within:
            out.append((n, name))
    return sorted(out)


def _watch() -> None:
    time.sleep(60)
    while True:
        data = H.load_json(FILE, {})
        st = H.load_json(H.mem_path("birthdays_notified.json"), {})
        for n, name in _upcoming(data, 1):
            key = f"{H.today()}:{name}"
            if key not in st:
                st[key] = 1
                when = "TODAY" if n == 0 else "tomorrow"
                H.say(f"[REMINDER] Tell the user in one short sentence that it's {name}'s birthday {when}.")
        H.save_json(H.mem_path("birthdays_notified.json"), st)
        time.sleep(3 * 3600)


H.on_ready(_watch)


def birthdays(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "upcoming").lower()
    name = str(p.get("name") or "").strip()
    data = H.load_json(FILE, {})
    if action == "add":
        md = _parse(str(p.get("date") or ""))
        if not name or not md:
            return "Tell me the name and the date, like 'Rahul, 14 March'."
        data[name] = {"m": md[0], "d": md[1]}
        H.save_json(FILE, data)
        return f"Saved {name}'s birthday ({date(2000, md[0], md[1]).strftime('%d %B')}). I'll remind you the day before."
    if action == "remove":
        if name in data:
            data.pop(name); H.save_json(FILE, data)
            return f"Removed {name}'s birthday."
        return f"I don't have a birthday saved for {name}."
    rows = _upcoming(data, 366 if action == "list" else int(p.get("days") or 30))
    if not rows:
        return "No birthdays coming up." if data else "No birthdays saved yet."
    text = "\n".join(f"{'TODAY' if n == 0 else ('tomorrow' if n == 1 else f'in {n} days')} — {nm} "
                     f"({date(2000, data[nm]['m'], data[nm]['d']).strftime('%d %b')})" for n, nm in rows)
    H.show(player, "BIRTHDAYS", text)
    return "Upcoming birthdays: " + "; ".join(text.splitlines()[:5])


TOOL = {
    "name": "birthdays",
    "description": ("Birthday reminders (reminds the day before and on the day). action='add' with name "
                    "and date (e.g. '14 March'); 'upcoming' (default, next 30 days, optional days); "
                    "'list' all; 'remove' with name."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'add', 'upcoming', 'list' or 'remove'."},
        "name": {"type": "STRING", "description": "Person's name."},
        "date": {"type": "STRING", "description": "Birthday, e.g. '14 March' or '14-03'."},
        "days": {"type": "NUMBER", "description": "For upcoming: how many days ahead."}},
        "required": []},
    "handler": birthdays,
}
