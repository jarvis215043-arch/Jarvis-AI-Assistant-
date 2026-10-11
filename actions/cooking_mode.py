"""actions/cooking_mode.py — Hands-free recipes: one step at a time by voice
('next', 'repeat', 'back', 'ingredients'), with timers for timed steps."""

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
_r = {"title": "", "ingredients": [], "steps": [], "i": -1}


def _show(player):
    if not _r["steps"]:
        return
    lines = [f"{'▶ ' if k == _r['i'] else '  '}{k + 1}. {s['text']}" for k, s in enumerate(_r["steps"])]
    H.show(player, f"COOKING — {_r['title']}", "Ingredients: " + ", ".join(_r["ingredients"]) + "\n\n" + "\n".join(lines))


def _step(player) -> str:
    s = _r["steps"][_r["i"]]
    _show(player)
    t = f" This step takes about {s['minutes']} minutes — offer to start a timer (cooking_mode action='timer')." if s.get("minutes") else ""
    return f"[COOKING] Step {_r['i'] + 1} of {len(_r['steps'])}: read it clearly: {s['text']}.{t} Then wait for 'next'."


def cooking_mode(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "start").lower()
    if act == "start":
        dish = str(p.get("dish") or "").strip()
        if not dish:
            return "What are we cooking?"
        serves = p.get("serves") or 2
        r = H.ai_json(f"A simple, safe recipe for {dish} for {serves} people, suitable for a teenager cooking at home "
                      "(say when an adult should help with sharp knives or hot oil). ONLY JSON: "
                      '{"title":"...","ingredients":["200 g ..."],"steps":[{"text":"...","minutes":0}]}') or {}
        if not r.get("steps"):
            return "I couldn't get that recipe — try another dish."
        _r.update(title=r.get("title", dish), ingredients=r.get("ingredients", []), steps=r["steps"], i=-1)
        _show(player)
        return (f"[COOKING] Recipe for {_r['title']} is on screen. Read the ingredients list "
                f"({', '.join(_r['ingredients'])}) and ask if they're ready; when they say 'next', give step 1.")
    if not _r["steps"]:
        return "No recipe open — say 'cook <dish>'."
    if act == "next":
        if _r["i"] + 1 >= len(_r["steps"]):
            return "[COOKING] That was the last step — tell them to enjoy their food!"
        _r["i"] += 1
        return _step(player)
    if act in ("repeat", "again"):
        return _step(player) if _r["i"] >= 0 else "We haven't started the steps yet — say 'next'."
    if act in ("back", "previous"):
        _r["i"] = max(0, _r["i"] - 1)
        return _step(player)
    if act == "ingredients":
        return "Ingredients: " + ", ".join(_r["ingredients"])
    if act == "timer":
        s = _r["steps"][max(0, _r["i"])]
        mins = s.get("minutes") or p.get("minutes")
        if not mins:
            return "This step doesn't have a time. How many minutes?"
        from core import tool_bus
        return tool_bus.run_tool("timers_alarms", {"action": "timer_start", "minutes": mins, "name": f"step {_r['i'] + 1}"})
    if act == "stop":
        _r["steps"] = []
        return "Cooking mode closed. Enjoy!"
    return "Cooking: start (dish), next, repeat, back, ingredients, timer, stop."


TOOL = {
    "name": "cooking_mode",
    "description": ("Hands-free recipes. action='start' (dish, optional serves); then 'next', 'repeat', 'back', "
                    "'ingredients', 'timer' (for the current step), 'stop'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "dish": {"type": "STRING", "description": "What to cook."},
        "serves": {"type": "NUMBER", "description": "Number of people."},
        "minutes": {"type": "NUMBER", "description": "Timer minutes."}}, "required": []},
    "handler": cooking_mode,
}
