"""actions/heads_up.py — JARVIS speaks first when it matters (2.6).

NEW: a heads-up ~10 minutes before each Google Calendar event ("Maths class
starts in 10 minutes"). The existing rain, battery and disk warnings keep working.
All optional heads-ups share one daily limit and quiet hours (core/heads_up.py),
so JARVIS never chatters.

  "heads-up status"                    → action='status' (today's count, settings)
  "turn heads-ups off / on"            → action='off' / 'on'   (meeting heads-ups)
  "only 3 heads-ups a day"             → action='limit' (number)
  "quiet hours 21 to 8"                → action='quiet' (hours like '21-8', or 'none')
  "warn me 15 minutes before meetings" → action='minutes' (number)
Only runs if Google Calendar is already connected (it never opens a sign-in by itself).
"""
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
STATE = H.mem_path("heads_up_meetings.json")
_cache = {"t": 0.0, "events": []}


def _calendar():
    import sys
    return sys.modules.get("plugins.google_calendar")


def _events_today(cal) -> list:
    """Today's timed events, refreshed every 10 minutes (one small API call)."""
    if time.monotonic() - _cache["t"] > 600 or not _cache["events"]:
        if not cal._token_path().exists():                  # not connected → never trigger a sign-in
            return []
        service = cal._get_service()
        _cache["events"] = [e for e in cal._events_on(service, date.today(), 1) if "dateTime" in (e.get("start") or {})]
        _cache["t"] = time.monotonic()
    return _cache["events"]


def due_meetings(events: list, now: datetime, minutes: int, announced: set) -> list:
    """(key, title, minutes away, location) for events starting within `minutes` and not yet announced."""
    out = []
    for e in events:
        try:
            start = datetime.fromisoformat(e["start"]["dateTime"].replace("Z", "+00:00"))
        except Exception:
            continue
        now_cmp = now if now.tzinfo else now.astimezone()
        mins = (start - now_cmp.astimezone(start.tzinfo)).total_seconds() / 60
        key = f"{e.get('id', '')}|{e['start']['dateTime']}"
        if 0 < mins <= minutes and key not in announced:
            out.append((key, (e.get("summary") or "An event").strip(), max(1, round(mins)), (e.get("location") or "").strip()))
    return out


def _watch() -> None:
    time.sleep(90)
    while True:
        try:
            cfg = H.cfg()
            cal = _calendar()
            if cfg.get("meeting_heads_up", True) and cal is not None:
                st = H.load_json(STATE, {})
                if st.get("day") != H.today():
                    st = {"day": H.today(), "said": []}
                minutes = int(cfg.get("meeting_heads_up_minutes", 10) or 10)
                for key, title, mins, loc in due_meetings(_events_today(cal), datetime.now().astimezone(),
                                                          minutes, set(st["said"])):
                    st["said"].append(key); H.save_json(STATE, st)
                    H.say(f"[MEETING] Tell the user in one short sentence: '{title}' starts in {mins} minutes"
                          + (f" ({loc})" if loc else "") + ".")
        except Exception as e:
            print(f"[Heads-up] calendar check skipped: {e}")
        time.sleep(45)


H.on_ready(_watch)


def heads_up(parameters: dict, player=None) -> str:
    from core import heads_up as HU
    p = parameters or {}
    act = str(p.get("action") or "status").lower().strip()
    val = str(p.get("value") or "").strip()
    cfg = H.cfg()
    if act in ("off", "on"):
        H.save_cfg("meeting_heads_up", act == "on")
        return f"Meeting heads-ups {'on' if act == 'on' else 'off'}."
    if act == "limit":
        try:
            n = max(0, min(30, int(float(val))))
        except ValueError:
            return "How many optional heads-ups a day? (a number; 0 = none)"
        H.save_cfg("heads_up_max", n)
        return f"At most {n} optional heads-ups a day now." if n else "Optional heads-ups are off (0 a day)."
    if act == "quiet":
        spec = "" if val.lower() in ("none", "off", "no", "") else val.replace(" to ", "-").replace(" ", "")
        import re
        if spec and not re.fullmatch(r"\d{1,2}-\d{1,2}", spec):
            return "Give quiet hours like '22-7' (10 pm to 7 am), or 'none'."
        H.save_cfg("heads_up_quiet", spec)
        return f"Quiet hours set to {spec}." if spec else "No quiet hours — heads-ups can come any time."
    if act == "minutes":
        try:
            m = max(1, min(120, int(float(val))))
        except ValueError:
            return "How many minutes before a meeting?"
        H.save_cfg("meeting_heads_up_minutes", m)
        return f"I'll give a heads-up {m} minutes before each calendar event."
    st = HU.today_status()
    cal = _calendar()
    connected = cal is not None and cal._token_path().exists()
    lines = [f"Meeting heads-ups: {'on' if cfg.get('meeting_heads_up', True) else 'off'} "
             f"({cfg.get('meeting_heads_up_minutes', 10)} min before) — calendar "
             f"{'connected' if connected else 'NOT connected (say “what is on my calendar” once to connect)'}",
             f"Optional heads-ups today: {st.get('n', 0)} of {cfg.get('heads_up_max', 6)}",
             f"Quiet hours: {cfg.get('heads_up_quiet', '22-7') or 'none'}",
             "", "Today: " + (", ".join(st.get("said") or []) or "none yet")]
    H.show(player, "HEADS-UPS", "\n".join(lines))
    return lines[0] + ". " + lines[1] + "."


TOOL = {
    "name": "heads_up",
    "description": ("JARVIS's unprompted heads-ups: before calendar events, rain, disk… with a daily limit and quiet hours. "
                    "action='status' (default), 'on'/'off' (meeting heads-ups), 'limit' (value = most per day), "
                    "'quiet' (value like '22-7' or 'none'), 'minutes' (value = minutes before a meeting)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "status | on | off | limit | quiet | minutes"},
        "value": {"type": "STRING", "description": "Number or hours for limit / quiet / minutes."}}, "required": []},
    "handler": heads_up,
}
