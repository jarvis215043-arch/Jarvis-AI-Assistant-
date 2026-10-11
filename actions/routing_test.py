"""actions/routing_test.py — "JARVIS, test your tool routing" (2.6).
Checks that everyday phrases go to the right tool (see core/routing_test.py).
action='quick' (default, 40 phrases, ≈3 US cents) or 'full' (all ≈140, ≈10–15 US cents);
'last' shows the previous result. Runs in the background (1–3 minutes)."""
import json
import threading


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
_st = {"running": False}


def live_declarations() -> list:
    """Exactly what the voice model gets (lean mode + switched-off tools applied)."""
    from core import tool_bus
    fn = getattr(tool_bus, "live_declarations", None)
    if callable(fn):
        return list(fn())
    decls = tool_bus.declarations()
    try:
        from actions import more_tools as MT
        core = MT.core_names()
        keep = [d for d in decls if d["name"] in core and d["name"] != "more_tools"]
        return keep + [MT.catalog_declaration([d for d in decls if d["name"] not in core])]
    except Exception:
        return decls


def routing_test(parameters: dict, player=None) -> str:
    from core import routing_test as RT, run_log
    act = str((parameters or {}).get("action") or "quick").lower()
    last_txt = run_log.log_dir() / "routing_last.txt"
    if act in ("last", "report", "result"):
        if not last_txt.exists():
            return "The routing test hasn't been run yet — say 'test your tool routing'."
        H.show(player, "TOOL ROUTING TEST", last_txt.read_text(encoding="utf-8"))
        return "The last routing test result is on screen."
    if _st["running"]:
        return "The routing test is already running."
    key = H.cfg().get("gemini_api_key", "")
    if not key:
        return "The routing test needs the Gemini key."

    def _go():
        _st["running"] = True
        try:
            from actions import more_tools as MT
            decls = live_declarations()
            names = {d["name"] for d in decls}
            inner = set()
            for d in decls:                                   # tools reachable through the more_tools catalog
                if d["name"] == "more_tools":
                    import re
                    inner |= set(re.findall(r"^- ([a-z0-9_]+):", d.get("description", ""), re.M))
            cases = RT.pick_cases(act != "full", names | inner)
            system = (H.base_dir() / "core" / "prompt.txt").read_text(encoding="utf-8", errors="replace")
            ask = RT.gemini_asker(decls, system, key, list(getattr(MT, "ROUTER_MODELS", ["gemini-flash-lite-latest"])))
            res = RT.run(ask, cases, workers=4)
            text = RT.report_text(res)
            last_txt.write_text(text, encoding="utf-8")
            (run_log.log_dir() / "routing_last.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
            H.show(player, "TOOL ROUTING TEST", text)
            tested = res["total"] - len(res["errors"])
            H.say(f"[ROUTING TEST] Tell the user in one or two sentences: {res['passed']} of {tested} test phrases went "
                  f"to the right tool" + (f"; {len(res['failures'])} went to the wrong one — the list is on screen, and "
                                          "they can send it to get the tool descriptions fixed" if res["failures"] else "")
                  + (f"; {len(res['errors'])} couldn't be tested" if res["errors"] else "") + ".")
        except Exception as e:
            H.say(f"[ROUTING TEST] Tell the user the routing test couldn't run: {e}")
        finally:
            _st["running"] = False
    threading.Thread(target=_go, daemon=True, name="routing-test").start()
    n = 40 if act != "full" else len(__import__("core.routing_test", fromlist=["CASES"]).CASES)
    return f"Testing {n} phrases against my tool list in the background — about {1 if n <= 40 else 3} minute(s)."


TOOL = {
    "name": "routing_test",
    "description": ("Self-check that everyday requests go to the right JARVIS tool. action='quick' (default, 40 phrases), "
                    "'full' (all phrases), 'last' (show the previous result). Use for 'test your tool routing'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "quick | full | last"}}, "required": []},
    "handler": routing_test,
}
