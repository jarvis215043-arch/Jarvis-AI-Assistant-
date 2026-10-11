"""actions/translate_window.py — Reads the text in the window you're looking at
(or the whole screen) and shows it translated on the HUD."""

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


def _grab(area: str):
    import pyautogui
    if area != "screen":
        try:
            w = pyautogui.getActiveWindow()
            if w and w.width > 80 and w.height > 80:
                return pyautogui.screenshot(region=(max(0, w.left), max(0, w.top), w.width, w.height))
        except Exception:
            pass
    return pyautogui.screenshot()


def translate_window(parameters: dict, player=None) -> str:
    p = parameters or {}
    lang = str(p.get("language") or "English").strip()
    area = str(p.get("area") or "window").lower()
    try:
        img = H.to_jpeg(_grab(area), 1800)
    except Exception as e:
        return f"I couldn't capture the {area}: {e}"
    try:
        out = H.ai_vision(f"Read all the meaningful text in this screenshot (ignore menus, buttons and the "
                          f"taskbar) and translate it into {lang}. Keep the paragraph structure. Output only the "
                          f"translation. If it's already in {lang}, say so in one line.", [img])
    except Exception as e:
        return f"I couldn't translate it: {e}"
    H.show(player, f"TRANSLATED → {lang}", out)
    return f"[TRANSLATION] It's on screen. Tell the user in one sentence what the text is about:\n{out[:1500]}"


TOOL = {
    "name": "translate_window",
    "description": ("Translates the text in the active window (or area='screen' for everything) into a "
                    "language (default English) and shows it on the HUD."),
    "parameters": {"type": "OBJECT", "properties": {
        "language": {"type": "STRING", "description": "Target language, e.g. 'English', 'Hindi'."},
        "area": {"type": "STRING", "description": "'window' (default) or 'screen'."}}, "required": []},
    "handler": translate_window,
}
