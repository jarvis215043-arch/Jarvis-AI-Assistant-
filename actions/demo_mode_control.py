"""
actions/demo_mode_control.py — Turns Demo Mode on, off, or reports its status.
Demo mode blocks: making phone calls, sending/replying to Gmail, and creating or
deleting calendar events. Reading email, checking your calendar, and every other
tool still work normally. The switch itself lives in core/demo_mode.py.
"""
import importlib.util
import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_demo_mode_module():
    key = "jarvis_ext_demo_mode"
    if key in sys.modules:
        return sys.modules[key]
    path = _base_dir() / "core" / "demo_mode.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(key, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        sys.modules.pop(key, None)
        print(f"[DemoMode] demo_mode.py failed to load: {e}")
        return None
    return mod


def demo_mode_control(parameters: dict, player=None, session_memory=None) -> str:
    action = ((parameters or {}).get("action") or "on").strip().lower()
    dm = _get_demo_mode_module()
    if dm is None:
        path = _base_dir() / "core" / "demo_mode.py"
        return f"I couldn't load the demo mode module, sir — expected it at {path}."

    if action in ("status", "check", "is it on"):
        if dm.is_demo_mode():
            since = dm.demo_since()
            return (f"Demo mode is on{f' since {since}' if since else ''}, sir — "
                    "calls, sending email and changing the calendar are blocked.")
        return "Demo mode is off, sir — everything works normally."

    if action in ("off", "disable", "stop", "end"):
        if not dm.is_demo_mode():
            return "Demo mode was already off, sir."
        dm.set_demo_mode(False)
        msg = "Demo mode off, sir — calls, email, and calendar are back to normal."
    else:
        if dm.is_demo_mode():
            return "Demo mode is already on, sir."
        dm.set_demo_mode(True)
        msg = ("Demo mode on, sir — calls, sending email, and changing calendar events "
               "are disabled until you turn it off.")

    _log(msg, player)
    return msg


def _log(message: str, player=None) -> None:
    print(f"[DemoMode] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass


TOOL = {
    "name": "demo_mode_control",
    "description": (
        "Turns Demo Mode on or off, or checks it. When on, calls, sending/replying to "
        "email, and creating or deleting calendar events are politely refused instead "
        "of actually happening — everything else still works normally. Use when the "
        "user says 'turn on demo mode', 'demo mode off', or 'is demo mode on?'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "'on', 'off', or 'status'. Defaults to 'on'."}
        },
        "required": []
    },
    "handler": demo_mode_control,
}