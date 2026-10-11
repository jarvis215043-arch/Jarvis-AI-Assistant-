"""actions/language_tutor.py — Practise speaking a language with gentle
corrections. Mistakes are saved so you can review them later."""

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
FILE = H.mem_path("language_mistakes.json")
_st = {"on": False, "lang": ""}


def language_tutor(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "start").lower()
    data = H.load_json(FILE, {})
    if action == "mistake":
        lang = _st["lang"] or str(p.get("language") or "general")
        data.setdefault(lang, []).append({"wrong": p.get("wrong", ""), "right": p.get("right", ""), "date": H.today()})
        data[lang] = data[lang][-200:]
        H.save_json(FILE, data)
        return "noted"
    if action == "review":
        lang = str(p.get("language") or _st["lang"] or "").strip()
        rows = data.get(lang, []) if lang else [m for v in data.values() for m in v]
        if not rows:
            return "No mistakes saved yet — practise first!"
        H.show(player, f"MISTAKES TO REVIEW{(' — ' + lang) if lang else ''}",
               "\n".join(f"✗ {m['wrong']}\n✓ {m['right']}" for m in rows[-20:]))
        return f"{len(rows)} saved corrections; the latest are on screen. Want to practise them?"
    if action == "stop":
        _st["on"] = False
        return "[LANGUAGE TUTOR — OFF] Finish with one encouraging sentence in English and summarise 1-2 things to practise."
    lang = str(p.get("language") or "").strip()
    if not lang:
        return "Which language? For example Hindi, Marathi, French or Spanish."
    level = str(p.get("level") or "beginner").strip()
    topic = str(p.get("topic") or "everyday conversation").strip()
    _st.update(on=True, lang=lang)
    H.show(player, "LANGUAGE TUTOR", f"{lang} — {level}\nTopic: {topic}\n\nSay 'stop language practice' to finish.")
    return (f"[LANGUAGE TUTOR — ON: {lang}, {level}] You are a friendly {lang} tutor. Hold a spoken "
            f"conversation about {topic} in simple {lang} suited to a {level}. After each user reply: if "
            "there's a mistake, gently give the correct sentence and a very short reason in English, then "
            f"call language_tutor with action='mistake', wrong=<their words>, right=<corrected>. Then continue "
            f"in {lang} with a short question. Praise good sentences. If the user is stuck, give a hint in "
            "English. If they say 'stop language practice', call language_tutor with action='stop'. Start now "
            f"with a greeting and an easy question in {lang}.")


TOOL = {
    "name": "language_tutor",
    "description": ("Spoken language practice with gentle corrections. action='start' with language "
                    "(and optional level, topic); 'mistake' (internal: wrong, right) to save a correction; "
                    "'review' lists saved corrections; 'stop'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'start', 'mistake', 'review' or 'stop'."},
        "language": {"type": "STRING", "description": "e.g. 'French', 'Hindi', 'Marathi'."},
        "level": {"type": "STRING", "description": "'beginner', 'intermediate' or 'advanced'."},
        "topic": {"type": "STRING", "description": "Conversation topic, e.g. 'school', 'food'."},
        "wrong": {"type": "STRING", "description": "For mistake: what the user said."},
        "right": {"type": "STRING", "description": "For mistake: the corrected version."}},
        "required": []},
    "handler": language_tutor,
}
