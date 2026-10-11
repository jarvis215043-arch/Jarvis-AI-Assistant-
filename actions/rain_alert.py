"""actions/rain_alert.py — Warns you in the morning if it's likely to rain today
(checks once a day after 6 AM while JARVIS is running). Needs your city."""
import time
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
STATE = H.mem_path("rain_alert.json")


def _check(city: str) -> tuple[bool, str]:
    ans = H.ai_search(f"Will it rain today in {city}? Answer starting with YES or NO, then the "
                      "chance of rain and the time it's most likely, in one short sentence.")
    return ans.strip().upper().startswith("YES"), ans


def _watch() -> None:
    time.sleep(90)
    while True:
        st = H.load_json(STATE, {})
        city = H.home_city()
        if st.get("enabled", True) and city and datetime.now().hour >= 6 and st.get("last") != H.today():
            try:
                rain, ans = _check(city)
                st["last"] = H.today(); H.save_json(STATE, st)
                if rain:
                    H.say(f"[RAIN ALERT] Tell the user in one short sentence: {ans} Suggest taking an umbrella.")
            except Exception:
                pass
        time.sleep(1800)


H.on_ready(_watch)


def rain_alert(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "check").lower()
    st = H.load_json(STATE, {})
    if action == "set_city":
        city = str(p.get("city") or "").strip()
        if not city:
            return "Which city?"
        H.save_cfg("home_city", city)
        return f"Got it — your city is {city}. Weather in the morning briefing and rain alerts will use it."
    if action in ("on", "off"):
        st["enabled"] = action == "on"; H.save_json(STATE, st)
        return f"Rain alerts {'on' if action == 'on' else 'off'}."
    city = str(p.get("city") or "").strip() or H.home_city()
    if not city:
        return "Which city should I check? Say 'set my city to Gurugram'."
    try:
        rain, ans = _check(city)
    except Exception as e:
        return f"I couldn't check the weather: {e}"
    return ans


TOOL = {
    "name": "rain_alert",
    "description": ("Rain alerts: a morning warning if it'll rain. action='check' (default, optional "
                    "city); 'set_city' with city (also used by the morning briefing weather); 'on'/'off'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'check', 'set_city', 'on' or 'off'."},
        "city": {"type": "STRING", "description": "City name, e.g. Gurugram."}}, "required": []},
    "handler": rain_alert,
}
