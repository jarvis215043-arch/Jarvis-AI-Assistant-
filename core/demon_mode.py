"""
core/demon_mode.py — The on/off switch for Demon Mode.

Demon Mode makes JARVIS go all out on every answer: complete lists instead of a
few examples, the full explanation instead of a summary, plus the extra details
and next steps you would probably ask for anyway.

It only changes how much JARVIS TELLS you. Actions that change things (files,
settings, messages, calls, calendar) still do exactly what you asked — never
extra — and still ask for confirmation where they did before.

Used by actions/demon_mode_control.py (the voice switch) and main.py (which adds
the Demon Mode rules to JARVIS's instructions every time it connects, so the mode
survives reconnects and restarts). The setting lives in config/demon_mode.json and
is read fresh every time, so every part of JARVIS always sees the same value.
"""
import json
import sys
from datetime import datetime
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _state_file() -> Path:
    return _base_dir() / "config" / "demon_mode.json"


def _read() -> dict:
    try:
        data = json.loads(_state_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def is_demon_mode() -> bool:
    """True while Demon Mode is on."""
    return bool(_read().get("on", False))


def demon_since() -> str | None:
    """When Demon Mode was turned on (e.g. '9:05 PM'), or None if it's off."""
    data = _read()
    return data.get("since") if data.get("on") else None


def set_demon_mode(on: bool) -> None:
    """Turns Demon Mode on (True) or off (False) and remembers it."""
    on = bool(on)
    data = {"on": on, "since": datetime.now().strftime("%I:%M %p").lstrip("0") if on else None}
    try:
        path = _state_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception as e:
        print(f"[DemonMode] Couldn't save setting: {e}")
    print(f"[DemonMode] Demon mode {'ON' if on else 'OFF'}")


# The rules JARVIS follows while Demon Mode is on. main.py puts these in the
# system instructions; the voice switch also hands them over the moment the mode
# is turned on, so they apply to the very next answer.
RULES = (
    "[DEMON MODE — ON]\n"
    "The user has switched on Demon Mode. Until they turn it off:\n"
    "- Give COMPLETE answers. When asked for a list, give every item — never a sample, "
    "never 'some examples include' or 'and more'. When asked to explain, cover every part.\n"
    "- Go beyond the question: add the related details, numbers, dates, pros and cons, and "
    "the next useful step the user would likely ask for next.\n"
    "- Use tools to the fullest: web_search with mode 'research' for questions of fact; "
    "ask tools for the maximum number of results; read every relevant result before answering.\n"
    "- Long answers are fine. For anything longer than a few sentences, also put the full "
    "answer on screen and speak the key points in order.\n"
    "- SAFETY: 'more' applies to INFORMATION only. Actions that change things (files, settings, "
    "apps, messages, emails, calls, calendar, purchases) do exactly what was asked — nothing "
    "extra — and keep every confirmation step. Demo mode rules still apply.\n"
)