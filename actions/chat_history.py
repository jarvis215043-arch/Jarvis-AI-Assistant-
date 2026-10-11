"""
actions/chat_history.py — Look back at past conversations.
main.py writes every 'You:' and assistant line to memory/chat_history/<date>.txt;
this tool shows a day, searches all days, or saves a day as a file in Documents.
"""
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def history_dir() -> Path:
    return _base_dir() / "memory" / "chat_history"


def _parse_day(text: str) -> date | None:
    t = (text or "today").strip().lower()
    today = date.today()
    if t in ("", "today"):
        return today
    if t == "yesterday":
        return today - timedelta(days=1)
    m = re.fullmatch(r"(\d+)\s*days?\s*ago", t)
    if m:
        return today - timedelta(days=int(m.group(1)))
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %B %Y", "%d %b %Y", "%B %d %Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    return None


def _day_file(d: date) -> Path:
    return history_dir() / f"{d.isoformat()}.txt"


def _show(player, title, text) -> None:
    if player and hasattr(player, "show_content"):
        try:
            player.show_content(title, text[-4000:])
        except Exception:
            pass


def chat_history(parameters: dict, player=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "show").strip().lower()

    if action == "list":
        days = sorted(p.stem for p in history_dir().glob("*.txt"))
        if not days:
            return "No saved conversations yet — they start being saved from now on."
        return f"I have conversations saved for {len(days)} day(s), from {days[0]} to {days[-1]}."

    if action == "search":
        q = str(params.get("query") or "").strip().lower()
        if not q:
            return "What should I search for?"
        hits = []
        for p in sorted(history_dir().glob("*.txt"), reverse=True):
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if q in line.lower():
                    hits.append(f"{p.stem}  {line}")
                    if len(hits) >= 40:
                        break
            if len(hits) >= 40:
                break
        if not hits:
            return f"I couldn't find '{q}' in past conversations."
        _show(player, f"SEARCH — {q}", "\n".join(hits))
        return f"Found {len(hits)} line(s) mentioning '{q}'. Most recent: " + " | ".join(hits[:5])

    d = _parse_day(str(params.get("date") or "today"))
    if d is None:
        return "I didn't understand that date. Try 'yesterday' or a date like 2026-10-02."
    f = _day_file(d)
    if not f.exists():
        return f"There's no saved conversation for {d.strftime('%A %d %B %Y')}."
    text = f.read_text(encoding="utf-8", errors="replace")

    if action in ("export", "save"):
        docs = Path.home() / "Documents"
        docs.mkdir(exist_ok=True)
        out = docs / f"JARVIS chat {d.isoformat()}.txt"
        shutil.copy2(f, out)
        return f"Saved that conversation to {out}."

    _show(player, f"CHAT — {d.strftime('%a %d %b %Y')}", text)
    lines = text.splitlines()
    return (f"{d.strftime('%A %d %B')}: {len(lines)} lines of conversation, shown on screen. "
            "Here's the latest part:\n" + "\n".join(lines[-25:]))[:2500]


TOOL = {
    "name": "chat_history",
    "description": (
        "Past conversations with the user. action='show' (default) with date ('today', "
        "'yesterday', '3 days ago' or YYYY-MM-DD); 'search' with query to find when something "
        "was discussed; 'export' with date to save that day as a text file in Documents; 'list'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "'show' (default), 'search', 'export' or 'list'."},
            "date":   {"type": "STRING", "description": "'today', 'yesterday', 'N days ago' or YYYY-MM-DD."},
            "query":  {"type": "STRING", "description": "For search: words to look for."},
        },
        "required": [],
    },
    "handler": chat_history,
}
