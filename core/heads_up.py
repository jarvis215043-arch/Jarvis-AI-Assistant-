"""
core/heads_up.py — Keeps JARVIS's unprompted heads-ups useful, not annoying (2.6).

Background features speak with a tag, e.g. "[RAIN ALERT] Tell the user…". The
OPTIONAL ones below share one daily limit and stay quiet at night:
    meeting heads-ups, rain, disk space, word of the day, news
Never limited (you asked for them, or they matter right now): alarms, timers,
reminders, battery, security, pomodoro, backups, updates, cricket matches you
follow, and everything you ask.

Settings (⚙ → 🛠 ADVANCED SETTINGS → HEADS-UPS):
    heads_up_max      most optional heads-ups per day (default 6, 0 = none)
    heads_up_quiet    quiet hours, e.g. "22-7" (default) — "" = never quiet
A held-back heads-up still appears in the HUD log, so nothing is lost.
"""
import json
import re
import sys
import threading
import time
from pathlib import Path

BUDGETED = {"MEETING", "RAIN ALERT", "RAIN", "DISK", "WORD OF THE DAY", "NEWS"}
_lock = threading.Lock()
_TAG = re.compile(r"^\s*\[([A-Z][A-Z _-]*)\]")


def _base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _cfg() -> dict:
    try:
        from core.secure_config import read_config
        return read_config()
    except Exception:
        return {}


def tag_of(text: str) -> str | None:
    m = _TAG.match(str(text or ""))
    return m.group(1).strip() if m else None


def quiet_now(spec: str | None = None, hour: int | None = None) -> bool:
    spec = _cfg().get("heads_up_quiet", "22-7") if spec is None else spec
    m = re.match(r"^\s*(\d{1,2})\s*[-–to]+\s*(\d{1,2})\s*$", str(spec or ""))
    if not m:
        return False
    a, b = int(m.group(1)) % 24, int(m.group(2)) % 24
    h = time.localtime().tm_hour if hour is None else hour
    return (a <= h < b) if a < b else (h >= a or h < b)


def _state_path() -> Path:
    p = _base() / "memory" / "heads_up.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def allow(text: str, now_hour: int | None = None) -> bool:
    """True = say it. Counts it against today's limit if it's an optional heads-up."""
    tag = tag_of(text)
    if tag not in BUDGETED:
        return True
    c = _cfg()
    if quiet_now(c.get("heads_up_quiet", "22-7"), now_hour):
        return False
    try:
        limit = int(c.get("heads_up_max", 6))
    except (TypeError, ValueError):
        limit = 6
    today = time.strftime("%Y-%m-%d")
    with _lock:
        p = _state_path()
        try:
            st = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            st = {}
        if st.get("day") != today:
            st = {"day": today, "n": 0, "said": []}
        if st["n"] >= limit:
            return False
        st["n"] += 1
        st["said"] = (st.get("said") or [])[-20:] + [f"{time.strftime('%H:%M')} {tag}"]
        p.write_text(json.dumps(st), encoding="utf-8")
    return True


def today_status() -> dict:
    try:
        st = json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:
        st = {}
    if st.get("day") != time.strftime("%Y-%m-%d"):
        st = {"n": 0, "said": []}
    return st
