"""actions/world_clock.py — The time in any city, and converting a time between
cities ("3 pm in Gurugram is what in New York?")."""
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
ZONES = {"india": "Asia/Kolkata", "delhi": "Asia/Kolkata", "gurugram": "Asia/Kolkata", "gurgaon": "Asia/Kolkata",
         "mumbai": "Asia/Kolkata", "nashik": "Asia/Kolkata", "bangalore": "Asia/Kolkata", "kolkata": "Asia/Kolkata",
         "london": "Europe/London", "uk": "Europe/London", "paris": "Europe/Paris", "berlin": "Europe/Berlin",
         "dubai": "Asia/Dubai", "singapore": "Asia/Singapore", "tokyo": "Asia/Tokyo", "japan": "Asia/Tokyo",
         "beijing": "Asia/Shanghai", "china": "Asia/Shanghai", "hong kong": "Asia/Hong_Kong", "sydney": "Australia/Sydney",
         "melbourne": "Australia/Melbourne", "new york": "America/New_York", "usa": "America/New_York",
         "washington": "America/New_York", "toronto": "America/Toronto", "chicago": "America/Chicago",
         "los angeles": "America/Los_Angeles", "san francisco": "America/Los_Angeles", "california": "America/Los_Angeles",
         "brazil": "America/Sao_Paulo", "sao paulo": "America/Sao_Paulo", "buenos aires": "America/Argentina/Buenos_Aires",
         "hanoi": "Asia/Ho_Chi_Minh", "ho chi minh": "Asia/Ho_Chi_Minh", "vietnam": "Asia/Ho_Chi_Minh",
         "manila": "Asia/Manila", "dhaka": "Asia/Dhaka", "bangladesh": "Asia/Dhaka", "nairobi": "Africa/Nairobi",
         "johannesburg": "Africa/Johannesburg", "cairo": "Africa/Cairo", "moscow": "Europe/Moscow"}


def _zone(name: str):
    from zoneinfo import ZoneInfo
    n = (name or "").lower().strip()
    if not n or n in ("here", "local", "my time"):
        return None
    key = ZONES.get(n) or next((v for k, v in ZONES.items() if k in n), None)
    if not key:
        key = H.ai_text(f"Give ONLY the IANA time zone name for '{name}' (e.g. Europe/London).").strip().split()[0]
    return ZoneInfo(key)


def world_clock(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "time").lower()
    try:
        if act == "time":
            places = [x.strip() for x in str(p.get("city") or "").split(",") if x.strip()]
            if not places:
                return "Which city?"
            out = []
            for pl in places:
                z = _zone(pl)
                now = datetime.now(z) if z else datetime.now()
                out.append(f"{pl.title()}: {now:%I:%M %p, %a}".replace(" 0", " "))
            return "; ".join(out)
        if act == "convert":
            t = str(p.get("time") or "").strip().lower()
            fz, tz = _zone(str(p.get("from_city") or "")), _zone(str(p.get("to_city") or ""))
            base = None
            for f in ("%I %p", "%I:%M %p", "%H:%M", "%I%p", "%I:%M%p"):
                try:
                    base = datetime.strptime(t, f); break
                except ValueError:
                    pass
            if base is None:
                return "What time? e.g. '3 pm'."
            today = datetime.now(fz) if fz else datetime.now().astimezone()
            src = today.replace(hour=base.hour, minute=base.minute, second=0, microsecond=0)
            dst = src.astimezone(tz) if tz else src.astimezone()
            day = "" if dst.date() == src.date() else (" (next day)" if dst.date() > src.date() else " (previous day)")
            return f"{base:%I:%M %p} in {p.get('from_city') or 'your time'} is {dst:%I:%M %p}{day} in {p.get('to_city') or 'your time'}."
    except Exception as e:
        return f"I couldn't work out that time zone: {e}"
    return "World clock: time (city, or several separated by commas), convert (time, from_city, to_city)."


TOOL = {
    "name": "world_clock",
    "description": ("World times. action='time' (city, or 'London, Tokyo'); 'convert' (time like '3 pm', from_city, "
                    "to_city — either can be empty for the user's own time)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'time' or 'convert'."},
        "city": {"type": "STRING", "description": "City or cities."},
        "time": {"type": "STRING", "description": "Time to convert."},
        "from_city": {"type": "STRING", "description": "From city."},
        "to_city": {"type": "STRING", "description": "To city."}}, "required": []},
    "handler": world_clock,
}
