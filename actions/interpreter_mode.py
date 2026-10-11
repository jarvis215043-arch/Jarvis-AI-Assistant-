"""
actions/interpreter_mode.py — Interpreter Mode: JARVIS translates live between
two people speaking different languages (e.g. English ⇄ Marathi) until you say
'stop interpreter mode'.
"""

_state = {"on": False, "a": "", "b": ""}


def interpreter_mode(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "start").strip().lower()

    if action == "stop":
        if not _state["on"]:
            return "Interpreter mode isn't on."
        _state["on"] = False
        if player:
            try:
                player.write_log("SYS: Interpreter mode off.")
            except Exception:
                pass
        return ("[INTERPRETER MODE — OFF] Stop translating. Go back to being a normal assistant "
                "and confirm in one short sentence.")

    if action == "status":
        return (f"Interpreter mode is on: {_state['a']} ⇄ {_state['b']}." if _state["on"]
                else "Interpreter mode is off.")

    a = str(p.get("language_a") or "English").strip()
    b = str(p.get("language_b") or "").strip()
    if not b:
        return "Which two languages? For example: English and Marathi."
    _state.update(on=True, a=a, b=b)
    if player:
        try:
            player.write_log(f"SYS: Interpreter mode — {a} ⇄ {b}. Say 'stop interpreter mode' to end.")
            player.show_content("INTERPRETER MODE", f"{a}  ⇄  {b}\n\nSpeak normally. JARVIS repeats what "
                                f"you say in the other language.\nSay 'stop interpreter mode' to finish.")
        except Exception:
            pass
    return (f"[INTERPRETER MODE — ON: {a} ⇄ {b}] From now on you are a live interpreter. For EVERY "
            f"thing you hear: if it is in {a}, say it in {b}; if it is in {b}, say it in {a}. Say only "
            "the translation — no greetings, no comments, no answers to questions (translate the "
            "question instead), keep the speaker's tone. The ONLY exception: if someone clearly says "
            "'stop interpreter mode', call interpreter_mode with action='stop'. Now say, in both "
            "languages, one short sentence that interpreter mode is ready.")


TOOL = {
    "name": "interpreter_mode",
    "description": (
        "Interpreter Mode: live translation between two people speaking different languages. "
        "action='start' with language_a and language_b (e.g. English and Marathi); 'stop' when the "
        "user says 'stop interpreter mode'; 'status'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action":     {"type": "STRING", "description": "'start' (default), 'stop' or 'status'."},
            "language_a": {"type": "STRING", "description": "First language (default English)."},
            "language_b": {"type": "STRING", "description": "Second language, e.g. Marathi."},
        },
        "required": [],
    },
    "handler": interpreter_mode,
}
