"""
actions/todo_list.py — A to-do list JARVIS keeps for you, shown on the HUD.
Saved in memory/todo.json so it survives restarts.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _file() -> Path:
    return _base_dir() / "memory" / "todo.json"


def load_items() -> list[dict]:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(items: list[dict]) -> None:
    p = _file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def open_items() -> list[str]:
    """Unfinished items — used by the morning briefing and night summary."""
    return [i["text"] for i in load_items() if not i.get("done")]


def _render(items: list[dict]) -> str:
    if not items:
        return "Your list is empty."
    lines = []
    for n, i in enumerate(items, 1):
        lines.append(f"{'☑' if i.get('done') else '☐'} {n}. {i['text']}")
    left = sum(1 for i in items if not i.get("done"))
    return "\n".join(lines) + f"\n\n{left} left to do."


def _show(player, items) -> None:
    if player and hasattr(player, "show_content"):
        try:
            player.show_content("TO-DO LIST", _render(items))
        except Exception:
            pass


def _find(items: list[dict], ref: str) -> int:
    """Index of the item matching a number ('2') or text ('science'), else -1."""
    ref = (ref or "").strip().lower()
    m = re.fullmatch(r"(?:number\s*)?(\d+)", ref)
    if m:
        k = int(m.group(1)) - 1
        return k if 0 <= k < len(items) else -1
    for k, i in enumerate(items):
        if ref and ref in i["text"].lower():
            return k
    return -1


def todo_list(parameters: dict, player=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "list").strip().lower()
    item = str(params.get("item") or "").strip()
    items = load_items()

    if action == "add":
        if not item:
            return "What should I add to your list?"
        new = [t.strip() for t in re.split(r",| and ", item) if t.strip()] if params.get("split") else [item]
        for t in new:
            items.append({"text": t, "done": False, "added": datetime.now().strftime("%Y-%m-%d")})
        _save(items); _show(player, items)
        left = sum(1 for i in items if not i.get('done'))
        return f"Added {', '.join(new)} to your list. {left} item{'s' if left != 1 else ''} to do."

    if action in ("done", "complete", "tick", "check"):
        k = _find(items, item)
        if k < 0:
            return f"I couldn't find '{item}' on your list."
        items[k]["done"] = True
        _save(items); _show(player, items)
        return f"Ticked off: {items[k]['text']}."

    if action in ("undone", "untick"):
        k = _find(items, item)
        if k < 0:
            return f"I couldn't find '{item}' on your list."
        items[k]["done"] = False
        _save(items); _show(player, items)
        return f"Marked '{items[k]['text']}' as not done."

    if action in ("remove", "delete"):
        k = _find(items, item)
        if k < 0:
            return f"I couldn't find '{item}' on your list."
        gone = items.pop(k)
        _save(items); _show(player, items)
        return f"Removed '{gone['text']}' from your list."

    if action == "clear_done":
        before = len(items)
        items = [i for i in items if not i.get("done")]
        _save(items); _show(player, items)
        return f"Cleared {before - len(items)} finished item(s)."

    if action == "clear_all":
        _save([]); _show(player, [])
        return "Your list is now empty."

    _show(player, items)
    todo = [i["text"] for i in items if not i.get("done")]
    if not todo:
        return "Nothing left on your list." if items else "Your list is empty."
    return f"You have {len(todo)} thing(s) to do: " + "; ".join(todo) + ". The list is on screen."


TOOL = {
    "name": "todo_list",
    "description": (
        "The user's to-do list, shown on the HUD. action='add' with item; 'list' (default); "
        "'done' with item (its text or number) to tick it off; 'undone'; 'remove' with item; "
        "'clear_done' removes finished items; 'clear_all' empties the list."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "'add', 'list', 'done', 'undone', 'remove', 'clear_done' or 'clear_all'."},
            "item":   {"type": "STRING", "description": "The item text, or its number on the list."},
            "split":  {"type": "BOOLEAN", "description": "For add: true to split 'a, b and c' into separate items."},
        },
        "required": [],
    },
    "handler": todo_list,
}
