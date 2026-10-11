"""actions/more_tools.py — Lean mode: keeps JARVIS fast and cheap.

The voice model only carries the everyday tools in full. Every other tool is
listed in ONE short catalog (this tool's description, built by main.py). When
the user wants one of them, the voice model calls more_tools(tool, request) and
a small, cheap, fast model reads just that ONE tool's full description and fills
in the details. Repeat calls can pass args directly and skip that step.
Turn it off with  "lean_mode": false  in config/api_keys.json."""
import json
import re
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
ROUTER_MODELS = ["gemini-flash-lite-latest", "gemini-flash-latest"]

# Tools the voice model always has in full (everything else goes through here).
CORE_TOOLS = {
    "open_app", "web_search", "weather_report", "computer_settings", "computer_control", "browser_control",
    "file_controller", "youtube_video", "reminder", "send_message", "make_phone_call", "focus_mode",
    "music_control", "todo_list", "timers_alarms", "mic_control", "demo_mode_control", "demon_mode_control",
    "agent_task", "protocols", "read_screen", "more_tools",
}


def core_names() -> set:
    extra = H.cfg().get("core_tools")
    return CORE_TOOLS | set(extra) if isinstance(extra, list) else CORE_TOOLS


def _short(desc: str, n: int = 95) -> str:
    first = re.split(r"(?<=[.!?])\s|\.\s", str(desc or "").strip())[0]
    first = re.sub(r"\s+", " ", first).strip().rstrip(".")
    return first if len(first) <= n else first[: n - 1].rstrip() + "…"


def catalog_declaration(extended: list) -> dict:
    """The more_tools declaration main.py sends: a one-line catalog of every other tool."""
    lines = "\n".join(f"- {d['name']}: {_short(d.get('description', ''))}" for d in sorted(extended, key=lambda d: d["name"]))
    return {
        "name": "more_tools",
        "description": ("Runs any JARVIS tool that is NOT in your function list. Call it with tool = the exact name below "
                        "and request = what the user wants, in one sentence with every detail they gave. If a previous "
                        "result showed 'args used', you may pass args (a JSON string) instead of request for the same "
                        "tool — that's faster. Catalog:\n" + lines),
        "parameters": {"type": "OBJECT", "properties": {
            "tool": {"type": "STRING", "description": "Exact tool name from the catalog."},
            "request": {"type": "STRING", "description": "What the user wants, in one full sentence."},
            "args": {"type": "STRING", "description": "Optional: exact arguments as a JSON object string."}},
            "required": ["tool"]},
    }


def _find(name: str):
    from core import tool_bus
    decls = {d["name"]: d for d in tool_bus.declarations()}
    n = (name or "").strip().lower().replace(" ", "_")
    if n in decls:
        return decls[n]
    near = [k for k in decls if n and (n in k or k in n)]
    return decls[near[0]] if len(near) == 1 else None


def _fill_args(decl: dict, request: str) -> dict:
    """Ask a small, cheap model to turn the request into this one tool's arguments."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=H.cfg().get("gemini_api_key", ""), http_options={"timeout": 30_000})
    params = decl.get("parameters") if (decl.get("parameters") or {}).get("properties") else None
    fd = types.FunctionDeclaration(name=decl["name"], description=str(decl.get("description", ""))[:2000],
                                   **({"parameters": params} if params else {}))
    cfg = types.GenerateContentConfig(
        system_instruction=(f"Today is {time.strftime('%A %d %B %Y, %H:%M')}. Call the function with the arguments "
                            "that best match the user's request. Use only values the user gave or obvious defaults."),
        tools=[types.Tool(function_declarations=[fd])],
        tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
            mode="ANY", allowed_function_names=[decl["name"]])),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.0,
    )
    last = None
    for model in ROUTER_MODELS:
        try:
            r = client.models.generate_content(model=model, contents=f"User request: {request}", config=cfg)
            calls = list(r.function_calls or [])
            if calls:
                return dict(calls[0].args or {})
        except Exception as e:
            last = e
    raise RuntimeError(f"couldn't work out the details ({last})")


def more_tools(parameters: dict, player=None, speak=None) -> str:
    p = parameters or {}
    name, request, raw = str(p.get("tool") or ""), str(p.get("request") or "").strip(), p.get("args")
    decl = _find(name)
    if decl is None:
        return f"There's no tool called '{name}'. Pick an exact name from the more_tools catalog."
    if decl["name"] in ("more_tools",):
        return "Pick a different tool."
    try:
        from core import tool_bus, tool_prefs
        if decl["name"] in tool_prefs.disabled({d["name"] for d in tool_bus.declarations()}):
            return (f"The {decl['name']} tool is switched off. Tell the user they can say "
                    f"'turn the {decl['name']} tool back on' (tool_usage action='enable').")
    except Exception:
        pass
    args = None
    if raw:
        try:
            args = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except Exception:
            args = None
    if args is None:
        if not request:
            return f"Tell me what the user wants from {decl['name']} (request)."
        try:
            args = _fill_args(decl, request)
        except Exception as e:
            return f"I couldn't run {decl['name']}: {e}"
    from core import tool_bus
    result = tool_bus.run_tool(decl["name"], args, timeout=85)
    return f"{result}\n(args used for {decl['name']}: {json.dumps(args, ensure_ascii=False)})"


TOOL = {   # main.py replaces this description with the live catalog in lean mode
    "name": "more_tools",
    "description": "Runs any JARVIS tool that isn't in your function list (lean mode).",
    "parameters": {"type": "OBJECT", "properties": {
        "tool": {"type": "STRING", "description": "Exact tool name."},
        "request": {"type": "STRING", "description": "What the user wants."},
        "args": {"type": "STRING", "description": "Optional JSON arguments."}}, "required": ["tool"]},
    "handler": more_tools,
}
