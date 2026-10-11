"""actions/mic_control.py — Mute or unmute the microphone by voice.
While muted JARVIS hears nothing, so to unmute: clap twice, press F4, or click
the microphone button."""


def mic_control(parameters: dict, player=None) -> str:
    action = str((parameters or {}).get("action") or "mute").strip().lower()
    if player is None or not hasattr(player, "set_muted"):
        return "I can't control the microphone from here."
    if action in ("unmute", "on"):
        player.set_muted(False)
        return "Microphone back on."
    if action == "status":
        return "The microphone is muted." if getattr(player, "muted", False) else "The microphone is on."
    player.set_muted(True)
    return ("[MUTED] Say in one short sentence: 'Muted. Clap twice or press F4 when you need me.' "
            "You won't hear anything until then.")


TOOL = {
    "name": "mic_control",
    "description": ("Mutes the user's microphone so JARVIS stops listening ('mute yourself', 'stop "
                    "listening', 'mute the mic'). action='mute' (default), 'unmute' (typed), 'status'. "
                    "To unmute by voice the user claps twice."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'mute', 'unmute' or 'status'."}}, "required": []},
    "handler": mic_control,
}
