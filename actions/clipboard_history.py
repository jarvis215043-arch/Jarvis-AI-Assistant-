"""actions/clipboard_history.py — Remembers what you copy (this session only,
kept in memory, never written to disk — copied passwords stay private)."""
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
_items: list = []      # newest last: {"t": "HH:MM", "text": "..."}
MAX = 200


def _watch() -> None:
    try:
        import pyperclip
    except Exception:
        return
    last = None
    while True:
        try:
            cur = pyperclip.paste()
            if cur and cur != last and cur.strip():
                last = cur
                if not _items or _items[-1]["text"] != cur:
                    _items.append({"t": time.strftime("%H:%M"), "text": cur[:5000]})
                    del _items[:-MAX]
        except Exception:
            pass
        time.sleep(1.5)


H.on_ready(_watch)


def clipboard_history(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "list").lower()
    if action == "search":
        q = str(p.get("query") or "").lower().strip()
        hits = [(i, it) for i, it in enumerate(_items) if q and q in it["text"].lower()]
        if not hits:
            return f"Nothing you copied this session contains '{q}'."
        H.show(player, f"CLIPBOARD — {q}", "\n\n".join(f"#{i + 1} [{it['t']}] {it['text'][:300]}" for i, it in hits[-15:]))
        return f"Found {len(hits)} match(es); they're on screen. Say 'copy number N' to put one back."
    if action in ("copy", "restore"):
        try:
            n = int(float(p.get("number") or 0))
            text = _items[n - 1]["text"]
        except Exception:
            return "Which number? Check the list on screen."
        import pyperclip
        pyperclip.copy(text)
        return f"Copied #{n} back to your clipboard."
    if action == "clear":
        _items.clear()
        return "Clipboard history cleared."
    if not _items:
        return "Nothing copied yet this session."
    H.show(player, "CLIPBOARD HISTORY", "\n\n".join(f"#{i + 1} [{it['t']}] {it['text'][:200]}"
                                                     for i, it in list(enumerate(_items))[-20:]))
    return f"{len(_items)} things copied this session; the latest 20 are on screen."


TOOL = {
    "name": "clipboard_history",
    "description": ("History of everything copied this session. action='list' (default); 'search' with "
                    "query; 'copy' with number to put an old item back on the clipboard; 'clear'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'list', 'search', 'copy' or 'clear'."},
        "query": {"type": "STRING", "description": "Text to search for."},
        "number": {"type": "NUMBER", "description": "Item number from the list."}},
        "required": []},
    "handler": clipboard_history,
}
