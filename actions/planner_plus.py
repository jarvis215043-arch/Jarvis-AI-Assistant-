"""actions/planner_plus.py — Day planner, decision helper, priority matrix, goals
with milestones, event countdowns, sticky notes, routines (step-by-step
checklists) and a weekly review. Saved in memory/planner.json."""
import time
from datetime import date, datetime, timedelta

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
FILE = H.mem_path("planner.json")
_run = {"name": "", "i": 0}


def _d():
    d = H.load_json(FILE, {})
    for k, v in (("goals", {}), ("countdowns", {}), ("notes", []), ("routines", {})):
        d.setdefault(k, v)
    return d


def _items(text) -> list:
    import re
    return [x.strip(" .") for x in re.split(r",|;|\n|\bthen\b", str(text or "")) if x.strip(" .")]


def planner_plus(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    d = _d()
    name = str(p.get("name") or "").strip()
    text = str(p.get("text") or "").strip()
    if act == "day_plan":
        todos = []
        try:
            todos = [i["text"] for i in H.load_json(H.mem_path("todo.json"), []) if not i.get("done")]
        except Exception:
            pass
        plan = H.ai_fast(f"Make a realistic time-blocked plan for the rest of today (it's {datetime.now():%H:%M}, {date.today():%A}). "
                         f"Things to fit in: {text or 'nothing specific'}; to-do list: {', '.join(todos) or 'empty'}. Include short "
                         "breaks, a meal, and stop by 10 pm. One line per block: 'HH:MM–HH:MM  task'.")
        H.show(player, "TODAY'S PLAN", plan)
        return "[PLAN] On screen. Say the next 2 blocks in one sentence:\n" + plan[:900]
    if act == "decide":
        opts = _items(text)
        out = H.ai_fast(f"Help a teenager decide between: {', '.join(opts) or text}. Context: {p.get('details') or 'none'}. "
                        "For each option: 2 pros, 2 cons. Then a clear suggestion and the one question that would change it.")
        H.show(player, "DECISION HELPER", out)
        return "[DECIDE] On screen. Give the suggestion in one sentence:\n" + out[:1000]
    if act == "prioritise":
        tasks = _items(text) or [i["text"] for i in H.load_json(H.mem_path("todo.json"), []) if not i.get("done")]
        if not tasks:
            return "Which tasks should I sort?"
        out = H.ai_fast("Sort these tasks into an Eisenhower matrix (DO NOW: urgent+important, PLAN: important not urgent, "
                        "QUICK/ASK FOR HELP: urgent not important, LATER: neither). Short headings with the tasks under each:\n"
                        + "\n".join(tasks))
        H.show(player, "PRIORITIES", out)
        return "[PRIORITIES] On screen. Say what to do first in one sentence:\n" + out[:900]
    if act == "goal_add":
        if not name:
            return "What's the goal?"
        steps = _items(text) or _items(H.ai_fast(f"Break the goal '{name}' into 5 small milestones, comma-separated, no numbering."))
        d["goals"][name] = {"steps": [{"text": s, "done": False} for s in steps], "created": H.today()}
        H.save_json(FILE, d)
        return f"Goal '{name}' saved with {len(steps)} milestones: " + "; ".join(steps)
    if act == "goal_done":
        g = d["goals"].get(name)
        if not g:
            return f"No goal called '{name}'."
        nxt = next((s for s in g["steps"] if not s["done"]), None)
        if nxt:
            nxt["done"] = True
        H.save_json(FILE, d)
        left = [s["text"] for s in g["steps"] if not s["done"]]
        return f"Ticked '{nxt['text'] if nxt else '-'}'. " + (f"Next: {left[0]}." if left else "Goal complete! 🎉")
    if act == "goals":
        if not d["goals"]:
            return "No goals yet."
        rows = [f"{n}: {sum(s['done'] for s in g['steps'])}/{len(g['steps'])} — next: {next((s['text'] for s in g['steps'] if not s['done']), 'done!')}"
                for n, g in d["goals"].items()]
        H.show(player, "GOALS", "\n".join(rows))
        return "; ".join(rows)
    if act == "countdown_add":
        try:
            when = datetime.strptime(str(p.get("date") or ""), "%Y-%m-%d").date()
        except ValueError:
            try:
                when = datetime.strptime(str(p.get("date") or "") + f" {date.today().year}", "%d %B %Y").date()
                if when < date.today():
                    when = when.replace(year=when.year + 1)
            except ValueError:
                return "Which date? e.g. '25 December' or 2026-12-25."
        d["countdowns"][name or "event"] = when.isoformat(); H.save_json(FILE, d)
        return f"{(when - date.today()).days} days until {name or 'the event'}."
    if act == "countdowns":
        rows = sorted(((date.fromisoformat(v) - date.today()).days, k) for k, v in d["countdowns"].items() if v >= H.today())
        if not rows:
            return "No countdowns."
        H.show(player, "COUNTDOWNS", "\n".join(f"{n:>4} days  {k}" for n, k in rows))
        return "; ".join(f"{k} in {n} days" for n, k in rows)
    if act == "note_add":
        if not text:
            return "What should the note say?"
        d["notes"].append({"text": text, "time": datetime.now().strftime("%d %b %H:%M")}); H.save_json(FILE, d)
        H.show(player, "STICKY NOTES", "\n".join(f"📌 {n['text']}" for n in d["notes"][-12:]))
        return "Stuck on the HUD."
    if act == "notes":
        H.show(player, "STICKY NOTES", "\n".join(f"{i}. 📌 {n['text']}" for i, n in enumerate(d["notes"], 1)) or "none")
        return f"{len(d['notes'])} sticky notes on screen."
    if act == "note_remove":
        try:
            d["notes"].pop(int(float(p.get("number") or 0)) - 1); H.save_json(FILE, d); return "Removed."
        except Exception:
            return "Which note number?"
    if act == "routine_save":
        steps = _items(text)
        if not name or not steps:
            return "Give the routine a name and its steps (comma-separated)."
        d["routines"][name.lower()] = steps; H.save_json(FILE, d)
        return f"Saved the '{name}' routine ({len(steps)} steps). Say 'start my {name} routine'."
    if act == "routine_start":
        steps = d["routines"].get(name.lower())
        if not steps:
            return f"No routine called '{name}'. Saved: {', '.join(d['routines']) or 'none'}."
        _run.update(name=name.lower(), i=0)
        return f"[ROUTINE] Step 1 of {len(steps)}: {steps[0]}. Say 'next' (planner_plus action='routine_next') when done."
    if act == "routine_next":
        steps = d["routines"].get(_run["name"], [])
        _run["i"] += 1
        if _run["i"] >= len(steps):
            return "[ROUTINE] All steps done — great job!"
        return f"[ROUTINE] Step {_run['i'] + 1} of {len(steps)}: {steps[_run['i']]}."
    if act == "weekly_review":
        since = (date.today() - timedelta(days=7)).isoformat()
        facts = []
        st_ = H.load_json(H.mem_path("screen_time.json"), {})
        mins = sum(sum(v.values()) for k, v in st_.items() if k >= since) // 60
        if mins: facts.append(f"screen time {mins // 60} h {mins % 60} min")
        todos = H.load_json(H.mem_path("todo.json"), [])
        facts.append(f"to-dos done {sum(1 for i in todos if i.get('done'))}, open {sum(1 for i in todos if not i.get('done'))}")
        hab = H.load_json(H.mem_path("habits.json"), {})
        if hab: facts.append("habits: " + ", ".join(f"{k} {sum(1 for x in v.get('days', []) if x >= since)}/7" for k, v in hab.items()))
        q = H.load_json(H.mem_path("study.json"), {}).get("quizzes", [])
        wk = [x for x in q if x.get("date", "") >= since]
        if wk: facts.append(f"quizzes {len(wk)}, avg {sum(x['score'] for x in wk) / max(1, sum(x['total'] for x in wk)) * 100:.0f}%")
        out = H.ai_fast("Write a short, encouraging weekly review for a student from these facts, with one thing that went well "
                        "and one small goal for next week:\n" + "\n".join(facts))
        H.show(player, "WEEKLY REVIEW", "\n".join(facts) + "\n\n" + out)
        return "[REVIEW] On screen. Summarise in two sentences:\n" + out[:800]
    return "Planner: day_plan, decide, prioritise, goal_add, goal_done, goals, countdown_add, countdowns, note_add, notes, note_remove, routine_save, routine_start, routine_next, weekly_review."


TOOL = {
    "name": "planner_plus",
    "description": ("Planning. action='day_plan' (text = things to fit in); 'decide' (text = options, details); 'prioritise' "
                    "(text = tasks, else the to-do list); goals: 'goal_add' (name, optional text = milestones), 'goal_done' (name), "
                    "'goals'; 'countdown_add' (name, date), 'countdowns'; sticky notes: 'note_add' (text), 'notes', 'note_remove' "
                    "(number); routines: 'routine_save' (name, text = steps), 'routine_start' (name), 'routine_next'; 'weekly_review'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "name": {"type": "STRING", "description": "Goal / countdown / routine name."},
        "text": {"type": "STRING", "description": "Options, tasks, steps or note text."},
        "date": {"type": "STRING", "description": "Countdown date."},
        "details": {"type": "STRING", "description": "Extra context."},
        "number": {"type": "NUMBER", "description": "Note number."}}, "required": ["action"]},
    "handler": planner_plus,
}
