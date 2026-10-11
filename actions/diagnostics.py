"""actions/diagnostics.py — "Run diagnostics" / "check yourself": the JARVIS
self-test (core/diagnostics.py). Report on the HUD + Documents/JARVIS/diagnostics.txt."""
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


def diagnostics(parameters: dict, player=None) -> str:
    quick = str((parameters or {}).get("action") or "full").lower() == "quick"

    def _go():
        try:
            from core import diagnostics as D, tool_bus
            rep = D.run(H.cfg(), tool_bus.declarations, lambda n, a: tool_bus.run_tool(n, a, timeout=20),
                        network=not quick, hardware=not quick)
            text = rep.text()
            (H.documents_dir() / "diagnostics.txt").write_text(text, encoding="utf-8")
            H.show(player, "DIAGNOSTICS", text)
            H.say("[DIAGNOSTICS] Tell the user the result in one or two sentences (full report is on the HUD and in "
                  "Documents, JARVIS, diagnostics.txt): " + rep.summary())
        except Exception as e:
            H.say(f"[DIAGNOSTICS] Tell the user the self-test itself failed: {e}")
    threading.Thread(target=_go, daemon=True, name="diagnostics").start()
    return "Running the self-test — about 30 seconds. I'll tell you the result."


TOOL = {
    "name": "diagnostics",
    "description": ("JARVIS self-test: checks libraries, settings, the Gemini/TinyFish keys, internet, mic, speakers, webcam "
                    "and every tool. action='full' (default) or 'quick' (no network/hardware). Use for 'run diagnostics', "
                    "'check yourself', 'is everything working?'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'full' or 'quick'."}}, "required": []},
    "handler": diagnostics,
}
