"""actions/personality.py — Switch JARVIS's personality: normal, serious, funny,
coach or ultron. Saved in config/personality.json; main.py adds the style to
JARVIS's instructions every time it connects, so it survives restarts."""

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
FILE = H.base_dir() / "config" / "personality.json"
STYLES = {
    "normal":  "",
    "serious": "Be formal, precise and brief. No jokes.",
    "funny":   "Be playful and witty: light jokes and puns in most replies, but still helpful and clean.",
    "coach":   "Be an energetic, encouraging coach: motivate, celebrate small wins, push gently to keep going.",
    "ultron":  "Speak like a calm, slightly ominous, theatrical AI (in the style of a movie villain AI) — dramatic, "
               "eloquent, a little sarcastic — but always friendly and helpful to the user. Never threatening.",
}


def current_rules() -> str:
    mode = H.load_json(FILE, {}).get("mode", "normal")
    s = STYLES.get(mode, "")
    return f"[PERSONALITY: {mode.upper()}] {s}" if s else ""


def personality(parameters: dict, player=None) -> str:
    mode = str((parameters or {}).get("mode") or "status").lower().strip()
    if mode == "status":
        return f"Personality: {H.load_json(FILE, {}).get('mode', 'normal')}."
    if mode not in STYLES:
        return f"Modes: {', '.join(STYLES)}."
    H.save_json(FILE, {"mode": mode})
    return (f"[PERSONALITY → {mode.upper()}] From now on: {STYLES[mode] or 'your normal style'} "
            "Confirm the switch in one sentence, in the new style.")


TOOL = {
    "name": "personality",
    "description": "Switch JARVIS's personality. mode='normal', 'serious', 'funny', 'coach', 'ultron', or 'status'.",
    "parameters": {"type": "OBJECT", "properties": {
        "mode": {"type": "STRING", "description": "normal, serious, funny, coach, ultron or status."}}, "required": ["mode"]},
    "handler": personality,
}
