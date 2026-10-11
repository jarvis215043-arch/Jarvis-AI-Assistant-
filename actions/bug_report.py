"""actions/bug_report.py — "JARVIS, make a bug report" / "something went wrong" (2.6).
Builds one zip on the Desktop with the recent log, the tools JARVIS ran, a quick
self-test and your settings (keys hidden) — send that one file and the problem can
be found straight away. See core/bug_report.py for exactly what's inside."""
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


def bug_report(parameters: dict, player=None) -> str:
    what = str((parameters or {}).get("what") or (parameters or {}).get("problem") or "").strip()

    def _go():
        try:
            from core import bug_report as B, tool_bus
            path = B.build(what, tool_bus.declarations, lambda n, a: tool_bus.run_tool(n, a, timeout=15))
            B.reveal(path)
            H.log(player, f"SYS: Bug report saved: {path}")
            H.say(f"[BUG REPORT] Tell the user in one or two sentences: the bug report is saved on the Desktop as "
                  f"'{path.name}' (the folder is open). Ask them to glance through log.txt and then send that zip.")
        except Exception as e:
            H.say(f"[BUG REPORT] Tell the user the bug report couldn't be made: {e}. They can double-click "
                  "bug_report.bat in the Jarvis folder instead.")
    threading.Thread(target=_go, daemon=True, name="bug-report").start()
    return "Making the bug report — a few seconds. I'll say when it's on the Desktop."


TOOL = {
    "name": "bug_report",
    "description": ("Makes a bug report zip on the Desktop (recent log, tools run, quick self-test, settings with keys "
                    "hidden) for when something went wrong or JARVIS did the wrong thing. Use for 'make a bug report', "
                    "'something went wrong', 'that didn't work, report it'. what = what went wrong, in the user's words."),
    "parameters": {"type": "OBJECT", "properties": {
        "what": {"type": "STRING", "description": "What went wrong, in the user's words."}}, "required": []},
    "handler": bug_report,
}
