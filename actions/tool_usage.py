"""actions/tool_usage.py — Which tools you actually use, and switching off the rest (2.6).

JARVIS writes one line per tool it runs to memory/logs/tools.jsonl (on this PC
only). From that:
  "which tools do I use most?"           → action='report'
  "what tools have I never used?"        → action='unused'
  "switch off the tools I don't use"     → action='prune'  (needs 14+ days of history;
                                            asks to CONFIRM; safety tools are never switched off)
  "turn the games tool back on"          → action='enable' (target, or 'all')
  "switch off the cricket tool"          → action='disable' (target)
  "which tools are switched off?"        → action='disabled'
Switched-off tools aren't sent to the voice model — every turn gets cheaper and
JARVIS has fewer wrong tools to pick from. Nothing is deleted.
"""
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
MIN_DAYS = 14
# Background / safety tools: used rarely or automatically, never pruned.
KEEP = {"more_tools", "tool_usage", "bug_report", "diagnostics", "jarvis_update", "mic_control", "demo_mode_control",
        "demon_mode_control", "system_alerts", "rain_alert", "birthdays", "auto_backup", "heads_up", "reminder",
        "timers_alarms", "security_watch", "gesture_calibration", "routing_test", "github_save", "personality", "agent_task",
        "protocols", "open_app", "web_search", "weather_report", "computer_settings", "computer_control",
        "browser_control", "file_controller", "send_message", "make_phone_call", "read_screen", "todo_list"}


def _all_tools() -> list[str]:
    try:
        from core import tool_bus
        return sorted({d["name"] for d in tool_bus.declarations()})
    except Exception:
        return []


def _set_list(key: str, values) -> None:
    H.save_cfg(key, sorted(set(values)))


def _match(target: str, names: list[str]) -> list[str]:
    """'the cricket tool' → cricket_scores; 'games' → games_plus / fun_games (asks which)."""
    import re
    t = re.sub(r"[^a-z0-9]+", "_", (target or "").lower()).strip("_")
    t = re.sub(r"^(the|my)_", "", t)
    t = re.sub(r"_(tool|tools|feature|one)$", "", t)
    if not t:
        return []
    if t in names:
        return [t]
    hit = [n for n in names if t in n or n in t]
    if hit:
        return hit
    words = [w for w in t.split("_") if len(w) > 2]
    return [n for n in names if any(w in n for w in words)]


def tool_usage(parameters: dict, player=None) -> str:
    from core import run_log, tool_prefs
    p = parameters or {}
    act = str(p.get("action") or "report").lower().strip()
    names = _all_tools()
    counts, days = run_log.usage_counts()
    off = tool_prefs.disabled(names)
    cfg = H.cfg()

    if act in ("report", "top", "most"):
        if not counts:
            return "I haven't recorded any tool use yet — it starts counting from JARVIS 2.6."
        top = sorted(counts.items(), key=lambda kv: -kv[1])
        lines = [f"{n:24} {c:5}×" for n, c in top[:30]]
        H.show(player, f"TOOLS YOU USE ({days:.0f} days of history)", "\n".join(lines)
               + f"\n\n{len([n for n in names if n not in counts])} of {len(names)} tools never used so far."
               + (f"\nSwitched off: {', '.join(sorted(off))}" if off else ""))
        return ("Most used: " + ", ".join(f"{n} ({c})" for n, c in top[:5])
                + f". That's from {days:.0f} days of history; the full list is on screen.")

    unused = [n for n in names if n not in counts and n not in off]
    if act in ("unused", "never", "never_used"):
        H.show(player, f"NEVER USED IN {days:.0f} DAYS ({len(unused)})", ", ".join(unused) or "—")
        return f"{len(unused)} tools haven't been used in {days:.0f} days of history — they're on screen."

    if act in ("prune", "switch_off_unused", "clean"):
        if days < MIN_DAYS:
            return (f"I only have {days:.0f} days of history — wait until at least {MIN_DAYS} days so I don't switch "
                    "off something you use now and then.")
        cand = [n for n in unused if n not in KEEP]
        if not cand:
            return "Nothing to switch off — you've used everything that isn't a safety tool."
        if str(p.get("confirm") or "").lower() not in ("yes", "true", "1"):
            H.show(player, "SWITCH OFF THESE UNUSED TOOLS?", ", ".join(cand)
                   + "\n\nSay 'yes, switch them off' to confirm. Nothing is deleted; 'turn X back on' restores any.")
            return (f"{len(cand)} tools haven't been used in {days:.0f} days — the list is on screen. Ask the user "
                    "to confirm; then call tool_usage again with action='prune' and confirm='yes'.")
        _set_list("disabled_tools", list(cfg.get("disabled_tools") or []) + cand)
        return (f"Switched off {len(cand)} unused tools. Each turn is now lighter. They come back the moment you say "
                "'turn the … tool back on'. JARVIS applies this on its next restart.")

    if act in ("disable", "off", "switch_off"):
        hit = [n for n in _match(str(p.get("target") or ""), names) if n not in tool_prefs.NEVER_DISABLE]
        if len(hit) != 1:
            return ("Which tool? " + (", ".join(hit[:8]) if hit else "I couldn't find that tool name.")
                    + " Say 'which tools are there' for the list.")
        _set_list("disabled_tools", list(cfg.get("disabled_tools") or []) + hit)
        _set_list("enabled_tools", [x for x in (cfg.get("enabled_tools") or []) if x not in hit])
        return f"Switched off {hit[0]} (from the next restart). Say 'turn {hit[0]} back on' to undo."

    if act in ("enable", "on", "switch_on", "restore"):
        target = str(p.get("target") or "").strip().lower()
        if target in ("all", "everything"):
            back = sorted(off)
            _set_list("disabled_tools", [])
            _set_list("enabled_tools", list(cfg.get("enabled_tools") or []) + [n for n in back if n in tool_prefs.DEFAULT_OFF_IF])
            return f"All tools are back on ({len(back)} restored) from the next restart."
        hit = _match(target, sorted(set(names) | off))
        if len(hit) != 1:
            return "Which tool? " + (", ".join(hit[:8]) if hit else "I couldn't find that tool name.")
        _set_list("disabled_tools", [x for x in (cfg.get("disabled_tools") or []) if x != hit[0]])
        _set_list("enabled_tools", list(cfg.get("enabled_tools") or []) + hit)
        return f"{hit[0]} is back on from the next restart."

    if act in ("disabled", "list_off", "switched_off"):
        return ("Switched off: " + ", ".join(sorted(off))) if off else "No tools are switched off."

    return "tool_usage: report, unused, prune, disable (target), enable (target or 'all'), disabled."


TOOL = {
    "name": "tool_usage",
    "description": ("Which JARVIS tools the user actually uses, and switching tools off/on. action='report' (most used), "
                    "'unused' (never used), 'prune' (switch off all unused tools — show the list, then confirm='yes'), "
                    "'disable' / 'enable' (target = tool name, or 'all' for enable), 'disabled' (list switched-off tools)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "report | unused | prune | disable | enable | disabled"},
        "target": {"type": "STRING", "description": "Tool name for disable/enable, or 'all'."},
        "confirm": {"type": "STRING", "description": "'yes' once the user confirmed a prune."}},
        "required": []},
    "handler": tool_usage,
}
