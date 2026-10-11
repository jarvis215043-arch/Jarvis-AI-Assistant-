"""
actions/agent_task.py — the Task Agent.

Handles requests that need several steps or several tools in a row, e.g.
"check tomorrow's weather, and if it rains remind me at 7 AM and put it in my
calendar". It plans with Gemini, runs JARVIS's own tools one after another
(through core/tool_bus, so demo mode and CONFIRM buttons still apply), shows
progress on the HUD, and tells you the result when it's finished.

It works in the background, so you can keep talking while it runs.
"""
import json
import sys
import threading
import time
from pathlib import Path

MODEL = "gemini-flash-latest"
MAX_STEPS = 10
STEP_TIMEOUT = 90.0

# Tools the agent must not use on its own: itself (no loops), safety switches,
# and conversation modes that only make sense when you ask for them directly.
_EXCLUDED = {"agent_task", "protocols", "demo_mode_control", "demon_mode_control",
             "interpreter_mode", "study_mode"}

_state = {"running": False, "goal": "", "steps": [], "cancel": False, "started": 0.0}
_lock = threading.Lock()


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _api_key() -> str:
    try:
        return json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")).get("gemini_api_key", "")
    except Exception:
        return ""


def _tool_bus():
    try:
        from core import tool_bus
        return tool_bus
    except Exception:
        return None


def _log(msg: str, player=None) -> None:
    print(f"[TaskAgent] {msg}")
    if player:
        try:
            player.write_log(f"SYS: {msg}")
        except Exception:
            pass


def _show(player, goal: str, steps: list, footer: str = "") -> None:
    if not (player and hasattr(player, "show_content")):
        return
    lines = [f"Goal: {goal}", ""]
    for i, s in enumerate(steps, 1):
        lines.append(f"{'✓' if s['ok'] else '✗'} {i}. {s['label']}")
        if s.get("note"):
            lines.append(f"     {s['note'][:160]}")
    if footer:
        lines += ["", footer]
    try:
        player.show_content("TASK AGENT", "\n".join(lines))
    except Exception:
        pass


def _pick_tools(goal: str, decls: list, client) -> set | None:
    """Cheap first step: a small model picks the few tools this goal needs, so each
    agent step sends ~8 tool descriptions instead of all ~77 (much cheaper/faster)."""
    import re as _re
    cat = "\n".join(f"{d['name']}: {str(d.get('description', ''))[:110]}" for d in decls
                    if isinstance(d, dict) and d.get("name") not in _EXCLUDED)
    prompt = (f"Goal: {goal}\n\nTools:\n{cat}\n\nList the names of the tools needed for this goal (at most 8), "
              "comma-separated, nothing else.")
    for model in ("gemini-flash-lite-latest", MODEL):
        try:
            txt = client.models.generate_content(model=model, contents=prompt).text or ""
            names = {n.strip() for n in _re.split(r"[,\s]+", txt) if n.strip()}
            known = {d["name"] for d in decls if isinstance(d, dict)}
            picked = names & known
            if picked:
                return picked
        except Exception:
            continue
    return None


def _function_declarations(types, only: set | None = None):
    """Converts JARVIS tool declarations into Gemini ones, skipping any that
    don't convert cleanly (one odd tool must not break the whole agent)."""
    bus = _tool_bus()
    out = []
    for d in (bus.declarations() if bus else []):
        if not isinstance(d, dict) or d.get("name") in _EXCLUDED or d.get("name") == "more_tools":
            continue
        if only is not None and d.get("name") not in only:
            continue
        try:
            kw = {"name": d["name"], "description": str(d.get("description", ""))[:1000]}
            params = d.get("parameters")
            if isinstance(params, dict) and params.get("properties"):
                kw["parameters"] = params
            out.append(types.FunctionDeclaration(**kw))
        except Exception as e:
            print(f"[TaskAgent] skipped tool {d.get('name')}: {e}")
    return out


SYSTEM = (
    "You are the task agent inside JARVIS, a personal assistant on a Windows PC. "
    "You get one goal from the user and complete it by calling tools, one step at a time. "
    "Rules:\n"
    "- Plan briefly, then act. Use the fewest tool calls that fully complete the goal.\n"
    "- Read each tool result before the next step; adapt if something failed.\n"
    "- Only do what the goal asks. Never delete files, send messages or emails, make calls, "
    "or change system power settings unless the goal explicitly asks for exactly that.\n"
    "- If a tool says something needs CONFIRM on screen, or is blocked by demo mode, accept "
    "that and mention it in your summary — never try to work around it.\n"
    "- Today is {today}.\n"
    "- When finished, reply with a short plain-text summary (max 4 sentences) of what you "
    "did and the key results. No markdown."
)


def _run(goal: str, player, speak) -> None:
    steps = _state["steps"]
    try:
        from google import genai
        from google.genai import types
    except Exception as e:
        _finish(goal, player, speak, f"I couldn't start the task agent: {e}", failed=True)
        return

    key = _api_key()
    bus = _tool_bus()
    if not key or bus is None or not bus.available():
        _finish(goal, player, speak, "The task agent isn't ready — no API key or tools available.", failed=True)
        return

    client = genai.Client(api_key=key, http_options={"timeout": 60_000})
    picked = _pick_tools(goal, bus.declarations(), client)
    decls = _function_declarations(types, picked)
    if not decls:                                   # pick failed → fall back to every tool
        decls = _function_declarations(types)
    if picked:
        _log(f"Task tools: {', '.join(sorted(picked))}", player)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM.format(today=time.strftime("%A %d %B %Y, %I:%M %p")),
        tools=[types.Tool(function_declarations=decls)] if decls else None,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
    )
    contents = [types.Content(role="user", parts=[types.Part(text=f"Goal: {goal}")])]
    summary = ""

    for _ in range(MAX_STEPS):
        if _state["cancel"]:
            _finish(goal, player, speak, "Task cancelled.", failed=True)
            return
        try:
            resp = client.models.generate_content(model=MODEL, contents=contents, config=config)
        except Exception as e:
            _finish(goal, player, speak, f"The task stopped: Gemini error — {e}", failed=True)
            return

        calls = list(resp.function_calls or [])
        if not calls:
            summary = (resp.text or "").strip() or "Done."
            break

        if resp.candidates and resp.candidates[0].content:
            contents.append(resp.candidates[0].content)
        reply_parts = []
        for fc in calls:
            if _state["cancel"]:
                break
            args = dict(fc.args or {})
            label = f"{fc.name}({', '.join(f'{k}={v}' for k, v in args.items())[:120]})"
            _log(f"Task step {len(steps) + 1}: {label}", player)
            if fc.name in _EXCLUDED:
                result = "That tool can't be used inside a task."
            else:
                result = bus.run_tool(fc.name, args, timeout=STEP_TIMEOUT)
            ok = not any(w in result.lower() for w in ("failed", "error", "couldn't", "could not", "not available", "skipped"))
            steps.append({"label": label, "ok": ok, "note": result})
            _show(player, goal, steps, "Working…")
            reply_parts.append(types.Part.from_function_response(
                name=fc.name, response={"result": result[:4000]}))
        contents.append(types.Content(role="user", parts=reply_parts))
    else:
        summary = f"I stopped after {MAX_STEPS} steps; the task may be incomplete."

    _finish(goal, player, speak, summary)


def _finish(goal: str, player, speak, summary: str, failed: bool = False) -> None:
    steps = list(_state["steps"])
    with _lock:
        _state["running"] = False
    _show(player, goal, steps, ("✗ " if failed else "✓ ") + summary)
    _log(f"Task {'stopped' if failed else 'finished'}: {summary[:120]}", player)
    if speak:
        try:
            speak(f"[TASK {'STOPPED' if failed else 'COMPLETE'}] The background task \"{goal}\" "
                  f"has {'stopped' if failed else 'finished'}. Result: {summary} "
                  "Tell the user in one or two short sentences. Do not call agent_task again for this.")
        except Exception:
            pass


def start_task(goal: str, player=None, speak=None) -> str:
    """Starts a background task. Also used by actions/protocols.py."""
    goal = (goal or "").strip()
    if not goal:
        return "Tell me what the task is."
    with _lock:
        if _state["running"]:
            return f"I'm still working on another task: \"{_state['goal']}\". Say 'cancel the task' to stop it."
        _state.update(running=True, goal=goal, steps=[], cancel=False, started=time.monotonic())
    _show(player, goal, [], "Starting…")
    _log(f"Task started: {goal}", player)
    threading.Thread(target=_run, args=(goal, player, speak), daemon=True, name="task-agent").start()
    return (f"[TASK STARTED] Working on it in the background: \"{goal}\". Tell the user in ONE short "
            "sentence that you've started and will report back when it's done. Progress shows on screen.")


def agent_task(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "start").strip().lower()
    if action == "cancel":
        if not _state["running"]:
            return "No task is running."
        _state["cancel"] = True
        return "Cancelling the task after the current step."
    if action == "status":
        if not _state["running"]:
            return "No task is running."
        done = len(_state["steps"])
        secs = int(time.monotonic() - _state["started"])
        return f"Working on \"{_state['goal']}\": {done} step(s) done so far, {secs} seconds in."
    return start_task(params.get("goal") or params.get("task") or "", player, speak)


TOOL = {
    "name": "agent_task",
    "description": (
        "Task Agent: completes requests that need SEVERAL steps or several different tools in a "
        "row (e.g. 'check tomorrow's weather and if it rains set a reminder and add it to my "
        "calendar', 'find the 3 biggest files on my desktop and tell me their sizes'). Runs in the "
        "background and reports back when done. Do NOT use it for a single simple action — call "
        "that tool directly. action='start' (default) with goal = the full request in one sentence; "
        "action='status' or 'cancel' for a running task."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "'start' (default), 'status' or 'cancel'."},
            "goal":   {"type": "STRING", "description": "The complete multi-step request, in one sentence, with every detail the user gave."},
        },
        "required": [],
    },
    "handler": agent_task,
}
