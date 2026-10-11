"""
core/demo_mode.py — The on/off switch for Demo Mode.

While demo mode is on, the tools that affect real people are blocked:
making phone calls, sending/replying to email, and creating or deleting
calendar events. Everything else (reading email, checking the calendar,
search, apps, focus mode...) works normally. Handy when showing Jarvis
to a class so nobody gets called or emailed by accident.

Used by actions/demo_mode_control.py, actions/phone_control.py,
plugins/gmail.py and plugins/google_calendar.py. They all load this file
under the same name, so they all share one switch.

The setting is saved to config/demo_mode.json, so if Jarvis crashes and
restarts in the middle of a demo, demo mode stays on.
"""
import json
import sys
import threading
from datetime import datetime
from pathlib import Path

_lock = threading.Lock()
_state = {"on": None, "since": None}   # None = not loaded from disk yet


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _state_file() -> Path:
    return _base_dir() / "config" / "demo_mode.json"


def _load() -> None:
    """Reads the saved setting once. Missing or broken file = demo mode off."""
    if _state["on"] is not None:
        return
    try:
        data = json.loads(_state_file().read_text(encoding="utf-8"))
        _state["on"] = bool(data.get("on", False))
        _state["since"] = data.get("since")
    except Exception:
        _state["on"] = False
        _state["since"] = None


def _save() -> None:
    try:
        path = _state_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"on": _state["on"], "since": _state["since"]}),
                        encoding="utf-8")
    except Exception as e:
        print(f"[DemoMode] Couldn't save setting (still applied for this run): {e}")


def is_demo_mode() -> bool:
    """True while demo mode is on."""
    with _lock:
        _load()
        return bool(_state["on"])


def set_demo_mode(on: bool) -> None:
    """Turns demo mode on (True) or off (False) and remembers it."""
    with _lock:
        _load()
        on = bool(on)
        if on and not _state["on"]:
            _state["since"] = datetime.now().strftime("%I:%M %p").lstrip("0")
        if not on:
            _state["since"] = None
        _state["on"] = on
        _save()
    print(f"[DemoMode] Demo mode {'ON' if on else 'OFF'}")


def demo_since() -> str | None:
    """The time demo mode was turned on (e.g. '9:05 PM'), or None if it's off."""
    with _lock:
        _load()
        return _state["since"] if _state["on"] else None