"""
actions/demon_mode_control.py — Turns Demon Mode on, off, or reports its status.
Demon Mode = JARVIS gives complete, all-out answers (full lists, full explanations,
extra details and next steps). It never makes actions do more than asked.
The switch itself lives in core/demon_mode.py.
"""
import importlib.util
import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_demon_mode_module():
    key = "jarvis_ext_demon_mode"
    if key in sys.modules:
        return sys.modules[key]
    path = _base_dir() / "core" / "demon_mode.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(key, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        sys.modules.pop(key, None)
        print(f"[DemonMode] demon_mode.py failed to load: {e}")
        return None
    return mod


def demon_mode_control(parameters: dict, player=None, session_memory=None) -> str:
    action = ((parameters or {}).get("action") or "on").strip().lower()
    dm = _get_demon_mode_module()
    if dm is None:
        path = _base_dir() / "core" / "demon_mode.py"
        return f"I couldn't load the demon mode module, sir — expected it at {path}."

    if action in ("status", "check"):
        if dm.is_demon_mode():
            since = dm.demon_since()
            return (f"Demon mode is on{f' since {since}' if since else ''}, sir — "
                    "every answer is complete and detailed.\n\n" + dm.RULES)
        return "Demon mode is off, sir — answers are normal length."

    if action in ("off", "disable", "stop", "end"):
        if not dm.is_demon_mode():
            return "Demon mode was already off, sir."
        dm.set_demon_mode(False)
        msg = "Demon mode off, sir — back to normal-length answers."
        _log(msg, player)
        return msg + " [DEMON MODE — OFF] Go back to normal answer length from now on."

    if dm.is_demon_mode():
        return "Demon mode is already on, sir.\n\n" + dm.RULES
    dm.set_demon_mode(True)
    msg = "Demon mode on, sir — from now on you get the complete picture, every time."
    _log(msg, player)
    # The rules go back to the model in this tool result, so they apply to the
    # very next answer (main.py also adds them on every reconnect).
    return msg + "\n\n" + dm.RULES


def _log(message: str, player=None) -> None:
    print(f"[DemonMode] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass


TOOL = {
    "name": "demon_mode_control",
    "description": (
        "Turns DEMON mode (with an N) on or off, or checks it. Demon mode = complete, "
        "all-out answers: full lists, full explanations, extra details and next steps. "
        "Use when the user says 'turn on demon mode', 'demon mode off', 'is demon mode on?'. "
        "NOT the same as demo_mode_control (DEMO mode blocks calls/emails for a presentation) — "
        "if you can't tell which one the user said, ask."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "'on', 'off', or 'status'. Defaults to 'on'."}
        },
        "required": []
    },
    "handler": demon_mode_control,
}