"""actions/pomodoro.py — Pomodoro study timer: work blocks with spoken break
reminders, and focus mode switched on during work blocks."""
import threading
import time

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
_st = {"on": False, "phase": "", "ends": 0.0, "round": 0, "rounds": 0, "gen": 0, "focus": False}


def _focus(on: bool, minutes: int) -> None:
    try:
        from core import tool_bus
        tool_bus.run_tool("focus_mode", {"action": "start", "minutes": minutes} if on else {"action": "stop"}, timeout=20)
    except Exception:
        pass


def _loop(gen: int, work: int, brk: int, rounds: int, use_focus: bool) -> None:
    for r in range(1, rounds + 1):
        if _st["gen"] != gen:
            return
        _st.update(phase="work", round=r, ends=time.monotonic() + work * 60)
        if use_focus:
            _focus(True, work)
        H.show(None, "POMODORO", f"Round {r} of {rounds}: WORK for {work} minutes")
        if r > 1:
            H.say(f"[POMODORO] Tell the user in one short sentence: break's over, round {r} of {rounds} — {work} minutes of focus starting now.")
        while time.monotonic() < _st["ends"]:
            if _st["gen"] != gen:
                return
            time.sleep(1)
        if use_focus:
            _focus(False, 0)
        if r == rounds:
            break
        _st.update(phase="break", ends=time.monotonic() + brk * 60)
        H.show(None, "POMODORO", f"Round {r} done. BREAK for {brk} minutes")
        H.say(f"[POMODORO] Tell the user in one short sentence: great work, round {r} done — take a {brk}-minute break.")
        while time.monotonic() < _st["ends"]:
            if _st["gen"] != gen:
                return
            time.sleep(1)
    if _st["gen"] == gen:
        _st["on"] = False
        H.show(None, "POMODORO", f"All {rounds} rounds finished!")
        H.say(f"[POMODORO] Tell the user: all {rounds} study rounds are finished — well done!")


def pomodoro(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "start").lower()
    if action == "stop":
        if not _st["on"]:
            return "No Pomodoro timer is running."
        _st["gen"] += 1
        _st["on"] = False
        if _st["focus"]:
            _focus(False, 0)
        return "Pomodoro stopped."
    if action == "status":
        if not _st["on"]:
            return "No Pomodoro timer is running."
        left = max(0, int(_st["ends"] - time.monotonic()))
        return f"Round {_st['round']} of {_st['rounds']}, {_st['phase']}: {left // 60} min {left % 60} s left."
    def num(k, d, lo, hi):
        try:
            return max(lo, min(int(float(p.get(k) or d)), hi))
        except (TypeError, ValueError):
            return d
    work, brk, rounds = num("work_minutes", 25, 1, 120), num("break_minutes", 5, 1, 60), num("rounds", 4, 1, 12)
    use_focus = str(p.get("focus", "true")).lower() not in ("false", "no", "0")
    _st["gen"] += 1
    _st.update(on=True, rounds=rounds, focus=use_focus)
    threading.Thread(target=_loop, args=(_st["gen"], work, brk, rounds, use_focus), daemon=True).start()
    mins = lambda n: f"{n} minute{'s' if n != 1 else ''}"
    return (f"Pomodoro started: {rounds} round{'s' if rounds != 1 else ''} of {mins(work)} work and {mins(brk)} break"
            f"{', with focus mode during work' if use_focus else ''}. I'll tell you when to take breaks.")


TOOL = {
    "name": "pomodoro",
    "description": ("Pomodoro study timer: work blocks with spoken break reminders; focus mode runs "
                    "during work blocks. action='start' (default) with optional work_minutes (25), "
                    "break_minutes (5), rounds (4), focus (true/false); 'status'; 'stop'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'start', 'status' or 'stop'."},
        "work_minutes": {"type": "NUMBER", "description": "Minutes per work block (default 25)."},
        "break_minutes": {"type": "NUMBER", "description": "Minutes per break (default 5)."},
        "rounds": {"type": "NUMBER", "description": "Number of work blocks (default 4)."},
        "focus": {"type": "BOOLEAN", "description": "Use focus mode during work (default true)."}},
        "required": []},
    "handler": pomodoro,
}
