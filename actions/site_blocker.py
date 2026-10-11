"""actions/site_blocker.py — Blocks distracting websites while you focus: if a
blocked site is in the front browser tab, JARVIS closes that tab and reminds you.
Turns on/off by voice, and automatically during focus mode / Pomodoro if 'auto' is on."""
import sys
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
STATE = H.mem_path("site_blocker.json")
BROWSERS = ("chrome", "msedge", "firefox", "brave", "opera")
DEFAULT_SITES = ["youtube", "instagram", "facebook", "reddit", "tiktok", "netflix", "twitter", "x.com", "discord"]
_st = {"until": 0.0}


def _front():
    if sys.platform != "win32":
        return "", ""
    import ctypes, psutil
    u = ctypes.windll.user32
    h = u.GetForegroundWindow()
    n = u.GetWindowTextLengthW(h); buf = ctypes.create_unicode_buffer(n + 1); u.GetWindowTextW(h, buf, n + 1)
    pid = ctypes.c_ulong(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    try:
        name = psutil.Process(pid.value).name().lower()
    except Exception:
        name = ""
    return buf.value.lower(), name


def _active() -> bool:
    if time.monotonic() < _st["until"]:
        return True
    if not H.load_json(STATE, {}).get("auto", False):
        return False
    for mod in ("actions.focus_mode", "actions.pomodoro"):
        m = sys.modules.get(mod)
        try:
            if mod.endswith("focus_mode") and m and getattr(m, "_state", {}).get("active"):
                return True
            if mod.endswith("pomodoro") and m and m._st.get("on") and m._st.get("phase") == "work":
                return True
        except Exception:
            pass
    return False


def _watch() -> None:
    last = 0.0
    while True:
        try:
            if _active():
                sites = H.load_json(STATE, {}).get("sites") or DEFAULT_SITES
                title, proc = _front()
                if any(b in proc for b in BROWSERS) and any(s in title for s in sites):
                    import pyautogui
                    pyautogui.hotkey("ctrl", "w")
                    if time.monotonic() - last > 20:
                        last = time.monotonic()
                        H.say("[BLOCKED] Say in one short, friendly sentence: that site is blocked while you focus — back to work!")
        except Exception:
            pass
        time.sleep(1.5)


H.on_ready(_watch)


def site_blocker(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "on").lower()
    st = H.load_json(STATE, {})
    if act == "on":
        mins = max(1, min(int(float(p.get("minutes") or 60)), 600))
        _st["until"] = time.monotonic() + mins * 60
        return f"Website blocker on for {mins} minutes. Blocked: {', '.join(st.get('sites') or DEFAULT_SITES)}."
    if act == "off":
        _st["until"] = 0.0
        return "Website blocker off."
    if act in ("auto_on", "auto_off"):
        st["auto"] = act == "auto_on"; H.save_json(STATE, st)
        return "The blocker now turns on automatically during focus mode and Pomodoro work blocks." if st["auto"] else "Automatic blocking off."
    if act in ("add", "remove"):
        site = str(p.get("site") or "").lower().strip()
        sites = st.get("sites") or list(DEFAULT_SITES)
        if act == "add" and site and site not in sites:
            sites.append(site)
        if act == "remove":
            sites = [x for x in sites if x != site]
        st["sites"] = sites; H.save_json(STATE, st)
        return f"Blocked sites: {', '.join(sites)}."
    return f"Blocker is {'ON' if _active() else 'off'}. Blocked sites: {', '.join(st.get('sites') or DEFAULT_SITES)}."


TOOL = {
    "name": "site_blocker",
    "description": ("Blocks distracting websites (closes the tab). action='on' (minutes), 'off', 'auto_on' "
                    "(block automatically during focus mode / Pomodoro), 'auto_off', 'add' / 'remove' (site), 'status'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "minutes": {"type": "NUMBER", "description": "How long to block."},
        "site": {"type": "STRING", "description": "Site name, e.g. 'youtube'."}}, "required": []},
    "handler": site_blocker,
}
