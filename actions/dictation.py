"""actions/dictation.py — Speak an essay and JARVIS writes it into a formatted
Word document (title, headings, paragraphs), saved in Documents/JARVIS."""
import os
import sys
from datetime import datetime

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
_doc = {"on": False, "title": "", "blocks": []}   # blocks: (style, text)


def dictation(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "start").lower()
    text = str(p.get("text") or "").strip()
    if action == "start":
        _doc.update(on=True, title=str(p.get("title") or "My essay").strip(), blocks=[])
        H.show(player, "DICTATION", f"Title: {_doc['title']}\n\nSpeak your essay. Say 'new heading …' for a heading,\n'finish the document' when done.")
        return ("[DICTATION — ON] The user will now speak an essay. For EVERY sentence or group of sentences "
                "they say, call dictation with action='add' and text = exactly their words, cleaned up "
                "(punctuation, capitals; remove 'um'). If they say 'new heading X', call action='heading' with "
                "text=X. If they say 'new paragraph', call action='paragraph'. If they say 'delete that', call "
                "action='undo'. When they say 'finish the document' (or 'save it'), call action='finish'. Don't "
                "chat in between — just say 'Got it' briefly. Tell them you're ready.")
    if not _doc["on"] and action != "finish":
        return "Dictation isn't running. Say 'start dictation' first."
    if action == "add":
        if not text:
            return "Nothing to add."
        if _doc["blocks"] and _doc["blocks"][-1][0] == "p":
            _doc["blocks"][-1] = ("p", _doc["blocks"][-1][1] + " " + text)
        else:
            _doc["blocks"].append(("p", text))
    elif action == "paragraph":
        _doc["blocks"].append(("p", ""))
    elif action == "heading":
        _doc["blocks"].append(("h", text or "Heading"))
    elif action == "undo":
        if _doc["blocks"]:
            _doc["blocks"].pop()
    elif action == "finish":
        return _finish(player, bool(p.get("polish", True)))
    preview = "\n\n".join(("## " + t) if s == "h" else t for s, t in _doc["blocks"] if t)
    H.show(player, f"DICTATION — {_doc['title']}", preview[-3500:] or "(empty)")
    return "Got it."


def _finish(player, polish: bool) -> str:
    from docx import Document
    blocks = [(s, t) for s, t in _doc["blocks"] if t.strip()]
    if not blocks:
        _doc["on"] = False
        return "The document is empty, so I didn't save anything."
    if polish:
        try:
            fixed = H.ai_json("Fix only spelling, grammar and punctuation in these essay blocks; keep the "
                              "author's words and meaning. Return ONLY a JSON list of strings, same count and "
                              "order:\n" + json_dumps([t for _, t in blocks]))
            if isinstance(fixed, list) and len(fixed) == len(blocks):
                blocks = [(s, str(f)) for (s, _), f in zip(blocks, fixed)]
        except Exception:
            pass
    d = Document()
    d.add_heading(_doc["title"], 0)
    for s, t in blocks:
        d.add_heading(t, 1) if s == "h" else d.add_paragraph(t)
    safe = "".join(c for c in _doc["title"] if c.isalnum() or c in " -_")[:60] or "Essay"
    out = H.documents_dir() / f"{safe} {datetime.now():%Y-%m-%d %H-%M}.docx"
    d.save(out)
    _doc["on"] = False
    if sys.platform == "win32":
        try:
            os.startfile(str(out))   # type: ignore[attr-defined]
        except Exception:
            pass
    words = sum(len(t.split()) for _, t in blocks)
    return f"[DICTATION — OFF] Saved '{_doc['title']}' ({words} words) to {out} and opened it in Word. Tell the user."


def json_dumps(x):
    import json
    return json.dumps(x, ensure_ascii=False)


TOOL = {
    "name": "dictation",
    "description": ("Dictate an essay into a formatted Word document. action='start' with optional title; "
                    "then 'add' with text for each spoken sentence(s), 'heading' with text, 'paragraph', "
                    "'undo'; 'finish' saves it (spell-checked) in Documents/JARVIS and opens it."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'start', 'add', 'heading', 'paragraph', 'undo' or 'finish'."},
        "title": {"type": "STRING", "description": "For start: document title."},
        "text": {"type": "STRING", "description": "For add/heading: the words."},
        "polish": {"type": "BOOLEAN", "description": "For finish: fix spelling and grammar (default true)."}},
        "required": []},
    "handler": dictation,
}
