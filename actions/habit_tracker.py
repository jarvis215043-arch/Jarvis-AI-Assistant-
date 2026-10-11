"""actions/habit_tracker.py — Track daily habits with streaks (memory/habits.json)."""
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
FILE = H.mem_path("habits.json")


def _streak(days: list) -> int:
    done, d, n = set(days), date.today(), 0
    if d.isoformat() not in done:
        d -= timedelta(days=1)          # today not done yet → count up to yesterday
    while d.isoformat() in done:
        n += 1
        d -= timedelta(days=1)
    return n


def _board(data: dict) -> str:
    if not data:
        return "No habits yet."
    t = date.today().isoformat()
    lines = []
    for name, h in data.items():
        days = h.get("days", [])
        lines.append(f"{'☑' if t in days else '☐'} {name}  —  🔥 {_streak(days)}-day streak  (best {h.get('best', 0)})")
    return "\n".join(lines)


def habit_tracker(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "status").lower()
    name = str(p.get("habit") or "").strip().lower()
    data = H.load_json(FILE, {})
    if action == "add":
        if not name:
            return "Which habit should I track?"
        data.setdefault(name, {"days": [], "best": 0, "created": H.today()})
        H.save_json(FILE, data); H.show(player, "HABITS", _board(data))
        return f"Now tracking '{name}'. Tell me when you've done it each day."
    if action in ("done", "did"):
        match = next((k for k in data if name and (name in k or k in name)), None)
        if not match:
            return f"I'm not tracking '{name}'. Say 'track {name}' to add it."
        days = data[match]["days"]
        if H.today() not in days:
            days.append(H.today())
        s = _streak(days)
        data[match]["best"] = max(data[match].get("best", 0), s)
        H.save_json(FILE, data); H.show(player, "HABITS", _board(data))
        return f"Nice! '{match}' done today — {s}-day streak."
    if action == "remove":
        if name in data:
            data.pop(name); H.save_json(FILE, data)
            return f"Stopped tracking '{name}'."
        return f"I'm not tracking '{name}'."
    H.show(player, "HABITS", _board(data))
    if not data:
        return "You're not tracking any habits yet. Try: 'track drinking water'."
    left = [k for k, h in data.items() if H.today() not in h.get("days", [])]
    return ("Habits on screen. " + (f"Still to do today: {', '.join(left)}." if left else "All done today!"))


TOOL = {
    "name": "habit_tracker",
    "description": ("Daily habit tracker with streaks shown on the HUD. action='add' with habit; "
                    "'done' with habit when the user did it today; 'status' (default); 'remove'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'add', 'done', 'status' or 'remove'."},
        "habit": {"type": "STRING", "description": "Habit name, e.g. 'drink water', 'read 20 minutes'."}},
        "required": []},
    "handler": habit_tracker,
}
