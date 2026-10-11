"""actions/cricket_scores.py — Live cricket scores, and spoken alerts for a team
you follow (checks every 10 minutes during a match, stops when it's over)."""
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
_follow = {"team": "", "gen": 0, "last": ""}


def _score(team: str) -> str:
    return H.ai_search(f"Live or most recent cricket match score for {team} right now: teams, score, "
                       "overs, who is batting, and the result if finished. One or two short sentences. "
                       "If no match today, say 'NO MATCH' and when their next match is.")


def _watch(gen: int, team: str) -> None:
    end = time.monotonic() + 6 * 3600
    while _follow["gen"] == gen and time.monotonic() < end:
        try:
            s = _score(team)
            if "NO MATCH" in s.upper():
                H.say(f"[CRICKET] Tell the user briefly: {s}")
                break
            if s != _follow["last"]:
                _follow["last"] = s
                H.show(None, f"CRICKET — {team}", s)
                H.say(f"[CRICKET UPDATE] Tell the user in one short sentence: {s}")
                if any(w in s.lower() for w in ("won by", "match tied", "no result", "abandoned")):
                    break
        except Exception:
            pass
        time.sleep(600)
    if _follow["gen"] == gen:
        _follow["team"] = ""


def cricket_scores(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "score").lower()
    team = str(p.get("team") or "India").strip()
    if action == "follow":
        _follow["gen"] += 1
        _follow.update(team=team, last="")
        threading.Thread(target=_watch, args=(_follow["gen"], team), daemon=True).start()
        return f"Following {team} — I'll tell you score updates every 10 minutes during the match."
    if action == "unfollow":
        _follow["gen"] += 1
        _follow["team"] = ""
        return "Stopped cricket updates."
    try:
        s = _score(team)
    except Exception as e:
        return f"I couldn't get the score: {e}"
    H.show(player, f"CRICKET — {team}", s)
    return s


TOOL = {
    "name": "cricket_scores",
    "description": ("Cricket scores. action='score' (default) with team (default India); 'follow' with "
                    "team for spoken updates every 10 minutes during the match; 'unfollow'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'score', 'follow' or 'unfollow'."},
        "team": {"type": "STRING", "description": "Team or match, e.g. 'India', 'RCB', 'India vs Australia'."}},
        "required": []},
    "handler": cricket_scores,
}
