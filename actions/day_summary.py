"""
actions/day_summary.py — Night summary ("wrap up my day"): what you talked
about today, what's still on your to-do list, and tomorrow's calendar.
"""
import importlib.util
import sys
from datetime import date, timedelta
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _load(name: str):
    key = f"actions.{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, str(_base_dir() / "actions" / f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def _today_topics() -> str:
    f = _base_dir() / "memory" / "chat_history" / f"{date.today().isoformat()}.txt"
    if not f.exists():
        return ""
    text = f.read_text(encoding="utf-8", errors="replace")[-12000:]
    if len(text) < 80:
        return ""
    try:
        return _load("_ai_text").ask(
            "Here is today's conversation log between a user and their assistant. List the 3-5 "
            "main things the user did or asked about today, as short plain bullet points "
            "starting with '- '. No intro.\n\n" + text).strip()
    except Exception:
        return ""


def _tomorrow_calendar() -> str:
    try:
        from core import tool_bus
    except Exception:
        return ""
    if not (_base_dir() / "config" / "google_calendar_token.json").exists():
        return ""   # not logged in to Calendar here — don't pop a login window at night
    tmr = (date.today() + timedelta(days=1)).isoformat()
    r = tool_bus.run_tool("google_calendar", {"action": "list", "date": tmr}, timeout=30)
    return r.replace(" sir.", "").strip()


def day_summary(parameters: dict, player=None) -> str:
    topics = _today_topics()
    try:
        todos = _load("todo_list").open_items()
    except Exception:
        todos = []
    cal = _tomorrow_calendar()

    parts = [f"WRAP-UP — {date.today().strftime('%A %d %B')}", ""]
    parts += ["Today:", topics or "- (nothing saved from today's conversations yet)", ""]
    parts += ["Still to do:"] + ([f"☐ {t}" for t in todos] or ["- nothing, all done!"]) + [""]
    parts += ["Tomorrow:", cal or "- calendar not connected on this PC, or nothing scheduled"]
    text = "\n".join(parts)
    if player and hasattr(player, "show_content"):
        try:
            player.show_content("DAY SUMMARY", text)
        except Exception:
            pass
    return ("[DAY SUMMARY] Give the user a warm 3-4 sentence wrap-up of their day from this, then "
            "wish them good night. It's also on screen.\n" + text)


TOOL = {
    "name": "day_summary",
    "description": (
        "Night summary / 'wrap up my day': today's main activities (from the chat log), unfinished "
        "to-do items and tomorrow's calendar, shown on screen. Use for 'wrap up my day', 'how was "
        "my day', 'what's on tomorrow and what's left to do'."
    ),
    "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    "handler": day_summary,
}
