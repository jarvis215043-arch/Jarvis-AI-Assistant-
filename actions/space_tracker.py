"""actions/space_tracker.py — Moon phase (worked out on this PC), where the ISS is
right now, when you can see it from your city, and upcoming rocket launches."""
import math
from datetime import datetime, timezone

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
PHASES = ["New moon 🌑", "Waxing crescent 🌒", "First quarter 🌓", "Waxing gibbous 🌔",
          "Full moon 🌕", "Waning gibbous 🌖", "Last quarter 🌗", "Waning crescent 🌘"]


def moon(now=None):
    now = now or datetime.now(timezone.utc)
    ref = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)          # a known new moon
    age = ((now - ref).total_seconds() / 86400) % 29.530588853
    illum = (1 - math.cos(2 * math.pi * age / 29.530588853)) / 2
    return PHASES[int((age / 29.530588853) * 8 + 0.5) % 8], age, illum


def space_tracker(parameters: dict, player=None) -> str:
    act = str((parameters or {}).get("action") or "moon").lower()
    if act == "moon":
        name, age, illum = moon()
        days_full = (14.77 - age) % 29.53
        return f"{name} — {illum * 100:.0f}% lit. Next full moon in about {days_full:.0f} days."
    if act == "iss_now":
        try:
            import requests
            d = requests.get("http://api.open-notify.org/iss-now.json", timeout=10).json()["iss_position"]
            lat, lon = float(d["latitude"]), float(d["longitude"])
        except Exception as e:
            return f"I couldn't reach the ISS tracker: {e}"
        where = H.ai_text(f"In under 12 words, what is roughly below latitude {lat:.1f}, longitude {lon:.1f}? (ocean, country or region)")
        return f"The ISS is over {where.strip().rstrip('.')} right now ({lat:.1f}°, {lon:.1f}°), moving at about 28,000 km/h."
    if act == "iss_pass":
        city = H.home_city()
        if not city:
            return "Tell me your city first (say 'my city is Gurugram')."
        return H.ai_search(f"Next visible ISS passes over {city} in the coming days (date, time, direction, brightness). Short list.")
    if act == "launches":
        r = H.ai_search("Upcoming rocket launches in the next two weeks worldwide: date, rocket, mission, launch site. Short list, include ISRO if any.")
        H.show(player, "UPCOMING LAUNCHES", r)
        return "[LAUNCHES] On screen. Mention the next 2 launches in one sentence:\n" + r[:900]
    return "Space: moon, iss_now, iss_pass, launches."


TOOL = {
    "name": "space_tracker",
    "description": "Space info. action='moon' (phase), 'iss_now' (where the ISS is), 'iss_pass' (when to see it from the user's city), 'launches'.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'moon', 'iss_now', 'iss_pass' or 'launches'."}}, "required": []},
    "handler": space_tracker,
}
