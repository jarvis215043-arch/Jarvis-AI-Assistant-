"""
actions/protocols.py — Protocols: your own named commands that run several
steps at once ("Activate gaming protocol" → opens Steam and Discord, sets the
volume...). Steps are plain sentences; the Task Agent carries them out, so a
protocol can use any JARVIS tool. Saved in config/protocols.json.
"""
import importlib.util
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Two ready-made examples, created the first time protocols are used.
_EXAMPLES = {
    "study": ["Turn on focus mode for 45 minutes", "Set the volume to 30",
              "Play lo-fi study music on YouTube"],
    "gaming": ["Turn off focus mode", "Open Steam", "Open Discord", "Set the volume to 60"],
}


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _file() -> Path:
    return _base_dir() / "config" / "protocols.json"


def _load() -> dict:
    p = _file()
    if not p.exists():
        data = {k: {"steps": v, "created": datetime.now().strftime("%Y-%m-%d")} for k, v in _EXAMPLES.items()}
        _save(data)
        return data
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict) -> None:
    p = _file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _clean_name(name: str) -> str:
    name = re.sub(r"\b(protocol|the|activate|run|start)\b", " ", (name or "").lower())
    return re.sub(r"\s+", " ", name).strip()


def _split_steps(raw) -> list[str]:
    if isinstance(raw, list):
        items = raw
    else:
        items = re.split(r"\n|;|,|\bthen\b|\band then\b", str(raw or ""))
    return [s.strip(" .-") for s in items if s and s.strip(" .-")]


def _agent():
    key = "actions.agent_task"
    if key in sys.modules:
        return sys.modules[key]
    path = _base_dir() / "actions" / "agent_task.py"
    spec = importlib.util.spec_from_file_location(key, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def _describe(name: str, steps: list[str]) -> str:
    return f"{name}: " + "; ".join(f"{i}. {s}" for i, s in enumerate(steps, 1))


def protocols(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "run").strip().lower()
    name = _clean_name(params.get("name") or "")
    data = _load()

    if action == "list":
        if not data:
            return "You don't have any protocols yet."
        text = "\n".join(_describe(n, v.get("steps", [])) for n, v in data.items())
        if player and hasattr(player, "show_content"):
            player.show_content("PROTOCOLS", text)
        return "Your protocols: " + ", ".join(data.keys()) + ". The steps are on screen."

    if not name:
        return "Which protocol? Tell me its name."

    if action in ("create", "save", "update", "edit"):
        steps = _split_steps(params.get("steps"))
        if not steps:
            return f"What should the {name} protocol do? Tell me the steps."
        data[name] = {"steps": steps, "created": datetime.now().strftime("%Y-%m-%d")}
        _save(data)
        return f"Saved the {name} protocol with {len(steps)} steps: {'; '.join(steps)}. Say 'activate {name} protocol' to run it."

    if action in ("delete", "remove"):
        if name not in data:
            return f"There's no protocol called {name}."
        data.pop(name)
        _save(data)
        return f"Deleted the {name} protocol."

    if name not in data:
        known = ", ".join(data.keys()) or "none yet"
        return f"There's no protocol called {name}. Your protocols: {known}."
    steps = data[name].get("steps", [])

    if action in ("show", "info"):
        return _describe(name, steps)

    # run
    goal = (f"Run the '{name}' protocol: do these steps in order — "
            + " ".join(f"({i}) {s}." for i, s in enumerate(steps, 1)))
    try:
        return _agent().start_task(goal, player, speak)
    except Exception as e:
        return f"I couldn't start the {name} protocol: {e}"


TOOL = {
    "name": "protocols",
    "description": (
        "Protocols = the user's own named multi-step commands, like 'activate gaming protocol' or "
        "'study protocol'. action='run' (default) with name; 'create' with name and steps (a list "
        "or a comma-separated sentence) to make or change one; 'list'; 'show' with name; 'delete' "
        "with name. Examples 'study' and 'gaming' exist from the start."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "'run' (default), 'create', 'list', 'show' or 'delete'."},
            "name":   {"type": "STRING", "description": "Protocol name, e.g. 'gaming'."},
            "steps":  {"type": "STRING", "description": "For create: the steps, separated by commas or 'then'."},
        },
        "required": [],
    },
    "handler": protocols,
}
