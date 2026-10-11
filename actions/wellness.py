"""actions/wellness.py — Water, stretch, 20-20-20 eye and screen-break
reminders (spoken, only while JARVIS isn't muted), a guided breathing exercise,
a sleep-cycle calculator, a private mood check-in and an exercise log."""
import time
from datetime import datetime, timedelta

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
CFG = H.mem_path("wellness.json")
REM = {"water": ("💧 time for a glass of water", 60), "stretch": ("🧘 stand up and stretch for a minute", 45),
       "eyes": ("👀 20-20-20: look at something 20 feet away for 20 seconds", 20), "break": ("⏸ take a 5-minute screen break", 50)}


def _cfg():
    c = H.load_json(CFG, {})
    c.setdefault("on", {}); c.setdefault("mood", []); c.setdefault("exercise", [])
    return c


def _watch() -> None:
    last = {}
    time.sleep(120)
    while True:
        c = _cfg()
        now = time.monotonic()
        quiet = 23 <= datetime.now().hour or datetime.now().hour < 7
        for k, (msg, default) in REM.items():
            mins = c["on"].get(k)
            if not mins or quiet:
                continue
            if now - last.setdefault(k, now) >= mins * 60:
                last[k] = now
                try:
                    from core import tool_bus
                    if tool_bus.is_speaking_busy():
                        continue
                except Exception:
                    pass
                H.say(f"[REMINDER] Say only, briefly and warmly: {msg}.")
        time.sleep(30)


H.on_ready(_watch)


def wellness(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    c = _cfg()
    if act in ("remind_on", "remind_off"):
        kind = str(p.get("kind") or "").lower()
        kind = next((k for k in REM if k in kind), None)
        if not kind:
            return "Which reminder? water, stretch, eyes or break."
        if act == "remind_off":
            c["on"].pop(kind, None); H.save_json(CFG, c)
            return f"{kind.title()} reminders off."
        mins = int(float(p.get("minutes") or REM[kind][1]))
        c["on"][kind] = max(5, mins); H.save_json(CFG, c)
        return f"{kind.title()} reminders every {c['on'][kind]} minutes (quiet from 11 pm to 7 am)."
    if act == "reminders":
        return ("Reminders: " + ", ".join(f"{k} every {m} min" for k, m in c["on"].items())) if c["on"] else "No reminders on."
    if act == "breathe":
        rounds = max(2, min(int(float(p.get("minutes") or 4)), 8))
        return (f"[BREATHING] Guide a calm box-breathing exercise, {rounds} rounds. Each round say slowly: 'Breathe in… 2… 3… 4. "
                "Hold… 2… 3… 4. Breathe out… 2… 3… 4. Hold… 2… 3… 4.' Speak calmly with pauses, then end gently.")
    if act == "sleep":
        wake = str(p.get("time") or "").strip()
        cyc = timedelta(minutes=90); fall = timedelta(minutes=15)
        if wake:
            try:
                w = datetime.strptime(wake.lower().replace(".", ":"), "%I:%M %p")
            except ValueError:
                try:
                    w = datetime.strptime(wake, "%H:%M")
                except ValueError:
                    return "What time do you need to wake up? e.g. 6:30 am."
            beds = [(w - fall - cyc * n).strftime("%I:%M %p").lstrip("0") for n in (6, 5)]
            return f"To wake at {w:%I:%M %p} feeling fresh, go to sleep at {beds[0]} (9 h) or {beds[1]} (7.5 h)."
        now = datetime.now()
        wakes = [(now + fall + cyc * n).strftime("%I:%M %p").lstrip("0") for n in (5, 6)]
        return f"If you sleep now, wake up at {wakes[0]} or {wakes[1]} — the end of a sleep cycle."
    if act == "mood":
        m = str(p.get("text") or "").strip()
        if not m:
            return "[MOOD] Ask the user gently how they're feeling today (1-10 and a word), then save it with wellness action='mood'."
        c["mood"].append({"date": H.today(), "mood": m}); c["mood"] = c["mood"][-365:]; H.save_json(CFG, c)
        return "[MOOD] Saved (only on this PC). Respond kindly in one or two sentences to how they feel."
    if act == "mood_history":
        rows = c["mood"][-14:]
        H.show(player, "MOOD (last 2 weeks)", "\n".join(f"{r['date']}  {r['mood']}" for r in rows) or "nothing yet")
        return f"{len(rows)} check-ins on screen."
    if act == "exercise_add":
        what = str(p.get("text") or "").strip()
        if not what:
            return "What exercise did you do? e.g. '20 push-ups' or '30 min cycling'."
        c["exercise"].append({"date": H.today(), "what": what}); H.save_json(CFG, c)
        week = [e for e in c["exercise"] if e["date"] >= (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")]
        return f"Logged. That's {len(week)} workout{'s' if len(week) != 1 else ''} this week 💪"
    if act == "exercise_log":
        rows = c["exercise"][-15:]
        H.show(player, "EXERCISE LOG", "\n".join(f"{r['date']}  {r['what']}" for r in rows) or "nothing yet")
        return f"{len(rows)} recent workouts on screen."
    return "Wellness: remind_on/remind_off (kind water/stretch/eyes/break, minutes), reminders, breathe, sleep (time), mood, mood_history, exercise_add, exercise_log."


TOOL = {
    "name": "wellness",
    "description": ("Wellbeing. 'remind_on'/'remind_off' (kind water/stretch/eyes/break, minutes); 'reminders'; 'breathe' (guided "
                    "breathing); 'sleep' (time = wake-up time → when to sleep; empty → when to wake); 'mood' (text; private check-in); "
                    "'mood_history'; 'exercise_add' (text), 'exercise_log'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "kind": {"type": "STRING", "description": "water, stretch, eyes or break."},
        "minutes": {"type": "NUMBER", "description": "Reminder interval / breathing rounds."},
        "time": {"type": "STRING", "description": "Wake-up time."},
        "text": {"type": "STRING", "description": "Mood or exercise text."}}, "required": ["action"]},
    "handler": wellness,
}
