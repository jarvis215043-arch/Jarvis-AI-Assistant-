"""actions/story_mode.py — Interactive adventure: JARVIS narrates, you choose
what happens next. Stories are kept family-friendly."""

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
_st = {"on": False, "genre": ""}


def story_mode(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "start").lower()
    if action == "stop":
        _st["on"] = False
        return "[STORY MODE — OFF] End the story with one short closing line and go back to normal."
    genre = str(p.get("genre") or "space adventure").strip()
    hero = str(p.get("hero") or "").strip()
    _st.update(on=True, genre=genre)
    H.show(player, "STORY MODE", f"Genre: {genre}\n\nListen, then choose what happens next.\nSay 'end the story' to stop.")
    return (f"[STORY MODE — ON: {genre}] You are now a storyteller running an interactive {genre} "
            f"adventure{' starring ' + hero if hero else ' where the user is the hero'}. Rules: tell the story "
            "in short, vivid parts (4-6 sentences), then stop and give exactly 3 numbered choices. Continue "
            "from whatever the user picks (or their own idea). Keep it exciting but family-friendly: no gore, "
            "nothing scary for kids. Add puzzles now and then. The story should reach an ending after about "
            "10 choices. If the user says 'end the story', call story_mode with action='stop'. Start now.")


TOOL = {
    "name": "story_mode",
    "description": ("Interactive choose-your-path adventure story. action='start' (default) with optional "
                    "genre (space, fantasy, mystery, superhero...) and hero; 'stop'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'start' or 'stop'."},
        "genre": {"type": "STRING", "description": "e.g. 'space adventure', 'mystery'."},
        "hero": {"type": "STRING", "description": "Optional hero name."}}, "required": []},
    "handler": story_mode,
}
