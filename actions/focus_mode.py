"""
actions/focus_mode.py — Closes distracting apps and keeps them closed for a set
duration. Runs a background thread; can be stopped early.

Reports APPS, not processes: Chrome alone runs 10+ processes, so "closed 13
apps" really meant "closed Chrome". It also remembers which apps it closed, so
"which apps did you close?" can be answered during or after a session.
"""
import os
import re
import threading
import time

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

# process-name prefix -> friendly name
_DEFAULT_BLOCKLIST = {
    "chrome": "Chrome",
    "discord": "Discord",
    "steam": "Steam",
    "spotify": "Spotify",
    "epicgameslauncher": "Epic Games Launcher",
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
}

# What people say -> the process name it actually runs as.
_ALIASES = {
    "vscode": "code", "visualstudiocode": "code", "edge": "msedge",
    "microsoftedge": "msedge", "epic": "epicgameslauncher",
    "epicgames": "epicgameslauncher", "roblox": "robloxplayer",
    "googlechrome": "chrome", "minecraft": "minecraft",
}

# Never touch these, whatever the user asks to block.
_PROTECTED = {"jarvis", "python", "pythonw", "explorer", "system", "svchost",
              "csrss", "winlogon", "lsass", "services", "dwm", "taskmgr"}

_state = {
    "active": False,
    "until": 0.0,
    "blocklist": {},        # prefix -> friendly name
    "closed": {},           # friendly name -> times closed this session
    "session": 0,           # bumps on every start so old watcher threads exit
}
_lock = threading.Lock()


def _protected_pids() -> set[int]:
    pids = {os.getpid()}
    try:
        me = psutil.Process()
        pids |= {p.pid for p in me.parents()}
        pids |= {p.pid for p in me.children(recursive=True)}
    except Exception:
        pass
    return pids


def _close_matching(blocklist: dict) -> set[str]:
    """Closes every process whose name starts with a blocked prefix.
    Returns the friendly names of the apps that were actually closed."""
    if not _PSUTIL or not blocklist:
        return set()
    skip = _protected_pids()
    victims, closed = [], set()
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            if proc.info["pid"] in skip:
                continue
            stem = (proc.info.get("name") or "").lower().removesuffix(".exe")
            if not stem or stem in _PROTECTED:
                continue
            for prefix, friendly in blocklist.items():
                if stem.startswith(prefix):
                    proc.terminate()          # polite close first
                    victims.append(proc)
                    closed.add(friendly)
                    break
        except Exception:
            continue

    # Force-kill anything that ignored the polite request.
    try:
        _, alive = psutil.wait_procs(victims, timeout=3)
        for p in alive:
            try:
                p.kill()
            except Exception:
                pass
    except Exception:
        pass
    return closed


def _record(closed: set[str]) -> None:
    with _lock:
        for name in closed:
            _state["closed"][name] = _state["closed"].get(name, 0) + 1


def _closed_list() -> str:
    names = sorted(_state["closed"])
    if not names:
        return "none of the blocked apps were open"
    return ", ".join(names)


def _watch_loop(session: int, player) -> None:
    while True:
        with _lock:
            if _state["session"] != session or not _state["active"]:
                return
            if time.monotonic() >= _state["until"]:
                _state["active"] = False
                summary = _closed_list()
                break
            blocklist = dict(_state["blocklist"])
        _record(_close_matching(blocklist))
        time.sleep(5)
    _log(f"Focus mode finished, sir. Apps I kept closed: {summary}.", player)


def _parse_apps(apps_raw: str) -> dict:
    custom = {}
    for a in re.split(r"[,/]| and ", apps_raw):
        a = a.strip().lower()
        if not a:
            continue
        prefix = re.sub(r"[^a-z0-9]", "", a)
        prefix = _ALIASES.get(prefix, prefix)
        if prefix and prefix not in _PROTECTED:
            custom[prefix] = a.title()
    return custom


def focus_mode(parameters: dict, player=None, session_memory=None) -> str:
    if not _PSUTIL:
        return "Focus mode needs the 'psutil' package installed — it's not available right now."

    params   = parameters or {}
    action   = (params.get("action") or "start").strip().lower()
    minutes  = params.get("minutes")
    apps_raw = (params.get("apps") or "").strip()

    if action == "stop":
        with _lock:
            was_active = _state["active"]
            _state["active"] = False
            _state["session"] += 1
            summary = _closed_list()
        msg = (f"Focus mode ended, sir. Apps I closed: {summary}."
               if was_active else f"Focus mode isn't running, sir. Last session I closed: {summary}.")
        _log(msg, player)
        return msg

    if action in ("status", "list", "apps"):
        with _lock:
            active = _state["active"]
            remaining = max(0, int(_state["until"] - time.monotonic()))
            summary = _closed_list()
            blocked = ", ".join(sorted(set(_state["blocklist"].values()))) or "none"
        if not active:
            return f"Focus mode is off. Last session I closed: {summary}."
        return (f"Focus mode is active — {remaining // 60} min {remaining % 60} s left. "
                f"Blocking: {blocked}. Closed so far: {summary}.")

    # ── start ──
    try:
        minutes = int(float(minutes)) if minutes else 25
    except (TypeError, ValueError):
        minutes = 25
    minutes = max(1, min(minutes, 240))

    blocklist = _parse_apps(apps_raw) if apps_raw else {}
    if not blocklist:
        blocklist = dict(_DEFAULT_BLOCKLIST)

    with _lock:
        _state["session"] += 1
        session = _state["session"]
        _state["active"] = True
        _state["until"] = time.monotonic() + minutes * 60
        _state["blocklist"] = blocklist
        _state["closed"] = {}

    closed_now = _close_matching(blocklist)
    _record(closed_now)
    threading.Thread(target=_watch_loop, args=(session, player), daemon=True).start()

    if closed_now:
        closed_txt = f"Closed {', '.join(sorted(closed_now))}"
    else:
        closed_txt = "None of the blocked apps were open"
    msg = (f"Focus mode on for {minutes} minute(s), sir. {closed_txt} — "
           f"I'll keep {', '.join(sorted(set(blocklist.values())))} shut until it ends.")
    _log(msg, player)
    return msg


def _log(message: str, player=None) -> None:
    print(f"[FocusMode] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass


TOOL = {
    "name": "focus_mode",
    "description": (
        "Starts, stops, or checks a focus session that closes distracting apps and "
        "keeps them closed for a set number of minutes. action='start' with minutes "
        "and optionally apps (comma-separated) to begin; 'stop' to end early; "
        "'status' for time left, which apps are blocked, and which apps were closed. "
        "Use 'status' when the user asks which apps you closed."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action":  {"type": "STRING", "description": "'start', 'stop', or 'status'. Defaults to 'start'."},
            "minutes": {"type": "NUMBER", "description": "How long to stay in focus mode (default 25)"},
            "apps":    {"type": "STRING", "description": "Comma-separated app names to block, e.g. 'chrome, discord'"}
        },
        "required": []
    },
    "handler": focus_mode,
}