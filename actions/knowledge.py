"""actions/knowledge.py — 10 quick-knowledge features: definitions, synonyms,
word origins, fun facts, on this day, quote of the day, country / element /
animal facts, and explain-like-I'm-5. Uses the small, fast model; 'on this day'
uses live search."""
from datetime import date

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
JOBS = {
    "define":    "Define '{q}' simply for a school student: meaning, part of speech, one example sentence.",
    "synonyms":  "Give 8 synonyms and 5 antonyms for '{q}', grouped, one line each.",
    "origin":    "Explain where the word '{q}' comes from (its etymology) in 2-3 simple sentences.",
    "fun_fact":  "Tell one surprising, true fun fact{about} in 2 sentences, suitable for a teenager.",
    "quote":     "Give one inspiring quote by a real, well-known person (with their name) and one line on what it means.",
    "country":   "Give quick facts about {q}: capital, population (approx.), languages, currency, 3 interesting facts.",
    "element":   "Give quick facts about the chemical element {q}: symbol, atomic number, group, state, 3 uses, 1 fun fact.",
    "animal":    "Give quick facts about the {q}: habitat, diet, size, lifespan, 3 amazing facts.",
    "eli5":      "Explain '{q}' like I'm 5 years old, in 4-5 short sentences with one everyday comparison.",
}


def knowledge(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    q = str(p.get("query") or "").strip()
    try:
        if act == "on_this_day":
            out = H.ai_search(f"Notable events that happened on {date.today():%B %d} in history (different years). "
                              "5 short lines: year — event. Include one Indian event if there is one.")
        elif act in JOBS:
            if act in ("define", "synonyms", "origin", "country", "element", "animal", "eli5") and not q:
                return "About what?"
            out = H.ai_fast(JOBS[act].format(q=q, about=f" about {q}" if q else ""))
        else:
            return "Knowledge: define, synonyms, origin, fun_fact, on_this_day, quote, country, element, animal, eli5."
    except Exception as e:
        return f"I couldn't look that up: {e}"
    H.show(player, act.replace("_", " ").upper() + (f" — {q}" if q else ""), out)
    return out[:1500]


TOOL = {
    "name": "knowledge",
    "description": ("Quick knowledge. action='define','synonyms','origin' (word origin),'eli5' (explain like I'm 5),"
                    "'country','element','animal' (all with query); 'fun_fact' (optional query topic),'quote','on_this_day'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "query": {"type": "STRING", "description": "The word, country, element, animal or concept."}}, "required": ["action"]},
    "handler": knowledge,
}
