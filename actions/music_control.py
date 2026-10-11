"""
actions/music_control.py — Music by voice: play/pause, next, previous, volume,
mute (works with Spotify, YouTube, any player via the keyboard media keys), and
'play <song>' (Spotify search if Spotify is installed, otherwise YouTube).
"""
import os
import shutil
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path

_KEYS = {
    "play_pause": "playpause", "pause": "playpause", "resume": "playpause", "play": None,
    "next": "nexttrack", "skip": "nexttrack", "previous": "prevtrack", "back": "prevtrack",
    "volume_up": "volumeup", "louder": "volumeup", "volume_down": "volumedown",
    "quieter": "volumedown", "mute": "volumemute", "unmute": "volumemute",
}


def _spotify_installed() -> bool:
    if sys.platform != "win32":
        return bool(shutil.which("spotify"))
    candidates = [Path(os.environ.get("APPDATA", "")) / "Spotify" / "Spotify.exe",
                  Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "Spotify.exe"]
    return any(p.exists() for p in candidates)


def _press(key: str, times: int = 1) -> None:
    import pyautogui
    for _ in range(max(1, times)):
        pyautogui.press(key)
        time.sleep(0.05)


def music_control(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "play_pause").strip().lower().replace(" ", "_")
    query = str(p.get("query") or "").strip()
    app = str(p.get("app") or "").strip().lower()

    if action == "play" and query:
        if app == "youtube" or (app != "spotify" and not _spotify_installed()):
            try:
                from core import tool_bus
                if tool_bus.available():
                    return tool_bus.run_tool("youtube_video", {"action": "play", "query": query})
            except Exception:
                pass
            webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(query))
            return f"Opened YouTube results for {query}."
        try:
            os.startfile("spotify:search:" + urllib.parse.quote(query))   # type: ignore[attr-defined]
            return f"Opened Spotify search for {query} — the top result is on screen; say 'play' if it doesn't start."
        except Exception as e:
            return f"I couldn't open Spotify: {e}"

    if action == "play" and not query:
        action = "play_pause"

    key = _KEYS.get(action)
    if not key:
        return "Music control can: play <song>, play_pause, next, previous, volume_up, volume_down, mute."
    try:
        steps = int(float(p.get("steps") or (5 if "volume" in action or action in ("louder", "quieter") else 1)))
    except (TypeError, ValueError):
        steps = 1
    try:
        _press(key, steps)
    except Exception as e:
        return f"I couldn't send the media key: {e}"
    names = {"playpause": "Toggled play/pause", "nexttrack": "Skipped to the next track",
             "prevtrack": "Went back a track", "volumeup": "Turned the volume up",
             "volumedown": "Turned the volume down", "volumemute": "Toggled mute"}
    return names[key] + "."


TOOL = {
    "name": "music_control",
    "description": (
        "Music by voice for Spotify, YouTube or any player. action='play' with query plays a song "
        "or playlist (Spotify if installed, else YouTube; app='spotify' or 'youtube' to choose); "
        "'play_pause', 'next', 'previous', 'volume_up', 'volume_down' (optional steps), 'mute'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "'play', 'play_pause', 'next', 'previous', 'volume_up', 'volume_down' or 'mute'."},
            "query":  {"type": "STRING", "description": "For play: song, artist or playlist."},
            "app":    {"type": "STRING", "description": "Optional: 'spotify' or 'youtube'."},
            "steps":  {"type": "NUMBER", "description": "For volume: how many steps (default 5)."},
        },
        "required": [],
    },
    "handler": music_control,
}
