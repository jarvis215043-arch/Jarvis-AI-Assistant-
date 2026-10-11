"""
core/diagnostics.py — JARVIS self-test.

Checks, in about 30 seconds, everything that has ever broken JARVIS:
  • Python version and every library (required vs optional)
  • settings file readable (a missing comma used to stop JARVIS starting)
  • the Gemini key actually works, and the voice model still exists
    (preview models get renamed; Google also blocks under-18 / unverified accounts)
  • the TinyFish key (if set)
  • internet, microphone (with a live level), speakers, webcam, disk space
  • the files JARVIS needs (start-up sound, gesture model, instructions)
  • every tool: loads, has a valid description, and — for tools that have a
    harmless read-only action — actually runs it.
Nothing is changed and nothing is sent anywhere except one tiny test request to
Gemini and one to TinyFish.

Used by actions/diagnostics.py ("run diagnostics") and diagnostics.py /
diagnostics.bat (works even when JARVIS itself won't start).
"""
import importlib.util
import json
import shutil
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

OK, WARN, FAIL, INFO = "OK", "WARN", "FAIL", "INFO"
LIVE_MODEL = "models/gemini-3.1-flash-live-preview"

REQUIRED = ["PyQt6", "sounddevice", "numpy", "google.genai", "requests", "pyautogui", "pyperclip", "PIL", "psutil",
            "cv2", "mss"]
OPTIONAL = {"mediapipe": "gestures, hand control, workout coach", "OpenGL": "GPU orb (falls back to normal orb)",
            "matplotlib": "graph plotter", "serial": "Arduino features", "qrcode": "QR codes",
            "docx": "Word files / dictation", "PyPDF2": "PDF tools (or pypdf)", "openwakeword": "wake word",
            "googleapiclient": "Gmail / Calendar / Drive backup", "vosk": "offline mode", "pyttsx3": "offline mode",
            "tzdata": "world clock on Windows", "fastapi": "phone dashboard"}

# Tools with a harmless, read-only action → actually run it.
SAFE_CALLS = {
    "birthdays": {"action": "list"}, "protocols": {"action": "list"}, "chat_history": {"action": "list"},
    "demo_mode_control": {"action": "status"}, "demon_mode_control": {"action": "status"},
    "news_interests": {"action": "list"}, "python_tutor": {"action": "progress"}, "workout_coach": {"action": "history"},
    "security_watch": {"action": "status"}, "personality": {"mode": "status"}, "site_blocker": {"action": "status"},
    "app_limits": {"action": "list"}, "auto_backup": {"action": "status"}, "planner_plus": {"action": "countdowns"},
    "wellness": {"action": "reminders"}, "timers_alarms": {"action": "timer_list"},
    "desk_tools": {"action": "calculate", "expression": "6*7"}, "math_tools": {"action": "prime", "numbers": "97"},
    "world_clock": {"action": "time", "city": "London"}, "space_tracker": {"action": "moon"},
    "comms_plus": {"action": "scheduled"}, "recall": {"action": "search", "query": "test"},
    "hardware_control": {"action": "ports"}, "holograms": {"action": "colors"},
    "tool_usage": {"action": "disabled"}, "routing_test": {"action": "last"}, "gesture_calibration": {"action": "report"},
}
EXPECT = {"desk_tools": "42", "math_tools": "prime"}
NOT_A_FAILURE = ("isn't", "no ", "not ", "nothing", "none", "empty", "off", "never")


def _base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _has(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


def _with_timeout(fn, secs):
    """Run fn, giving up after secs (a stuck check must not freeze the self-test)."""
    ex = ThreadPoolExecutor(max_workers=1)
    try:
        return ex.submit(fn).result(timeout=secs)
    finally:
        ex.shutdown(wait=False)


class Report:
    def __init__(self):
        self.rows = []

    def add(self, status, area, name, detail=""):
        self.rows.append((status, area, name, str(detail)[:220]))

    def counts(self):
        return {s: sum(1 for r in self.rows if r[0] == s) for s in (OK, WARN, FAIL)}

    def text(self) -> str:
        c = self.counts()
        out = [f"JARVIS DIAGNOSTICS — {datetime.now():%d %b %Y %H:%M}",
               f"{c[OK]} OK · {c[WARN]} warnings · {c[FAIL]} problems", ""]
        order = {FAIL: 0, WARN: 1, INFO: 2, OK: 3}
        area = None
        for s, a, n, d in sorted(self.rows, key=lambda r: (r[1], order[r[0]])):
            if a != area:
                out.append(f"\n── {a} ──"); area = a
            mark = {"OK": "✓", "WARN": "!", "FAIL": "✗", "INFO": "·"}[s]
            out.append(f" {mark} {n}" + (f" — {d}" if d else ""))
        return "\n".join(out)

    def summary(self) -> str:
        c = self.counts()
        bad = [f"{n} ({d[:70]})" for s, a, n, d in self.rows if s == FAIL][:4]
        return (f"{c[OK]} checks OK, {c[WARN]} warnings, {c[FAIL]} problems."
                + (" Problems: " + "; ".join(bad) if bad else ""))


AQ_HELP = ('Keys starting with "AQ." (Google\'s new kind, the only kind AI Studio makes since May 2026) are refused by the live voice connection for some accounts. Fix: console.cloud.google.com -> new project -> enable "Gemini API" (Generative Language API) -> in AI Studio, API keys -> Import project -> Create key in that project -> paste it into JARVIS.')


def _live_test(key: str) -> None:
    """Opens (and closes) the same live voice connection JARVIS uses — raises if Google refuses it."""
    import asyncio
    from google import genai

    async def go():
        c = genai.Client(api_key=key, http_options={"api_version": "v1beta"})
        async with c.aio.live.connect(model=LIVE_MODEL, config={"response_modalities": ["AUDIO"]}):
            return True
    return asyncio.run(go())


def _gemini_error(e: Exception) -> str:
    t = str(e)
    if "invalid authentication credentials" in t or "ACCESS_TOKEN_TYPE_UNSUPPORTED" in t or "UNAUTHENTICATED" in t:
        return "Google refused this key for the voice connection. " + AQ_HELP
    if "PERMISSION_DENIED" in t or "403" in t:
        return ("Google blocked this key (PERMISSION_DENIED). Usual cause: the Google account is under 18 or not "
                "age-verified, or the region isn't supported. Make the key with an adult's verified account.")
    if "API_KEY_INVALID" in t or "API key not valid" in t:
        return "The key is wrong or was deleted — make a new one at aistudio.google.com."
    if "RESOURCE_EXHAUSTED" in t or "429" in t:
        return "The key works but hit its free-tier limit — wait a bit, or enable billing."
    return t[:180]


def run(cfg: dict, decls, run_tool, network: bool = True, hardware: bool = True) -> Report:
    """cfg = settings dict; decls() = tool declarations; run_tool(name, args) → str."""
    r = Report()
    base = _base()
    # ── System ──
    v = sys.version_info
    r.add(OK if v >= (3, 11) else FAIL, "System", f"Python {v.major}.{v.minor}.{v.micro}",
          "" if v >= (3, 11) else "JARVIS needs Python 3.11+ (3.13 recommended)")
    try:
        free = shutil.disk_usage(base).free / 1e9
        r.add(OK if free > 2 else WARN, "System", f"Disk space {free:.1f} GB free", "" if free > 2 else "less than 2 GB free")
    except Exception as e:
        r.add(WARN, "System", "Disk space", e)
    for m in REQUIRED:
        r.add(OK if _has(m) else FAIL, "Libraries", m, "" if _has(m) else "missing — run: python -m pip install -r requirements.txt")
    for m, what in OPTIONAL.items():
        if m == "PyPDF2" and not _has(m) and _has("pypdf"):
            r.add(OK, "Libraries", "pypdf", what); continue
        r.add(OK if _has(m) else WARN, "Libraries", m, "" if _has(m) else f"missing — needed for {what}")
    # ── Files & settings ──
    for rel, what in (("config/suit_up.mp3", "start-up sound"), ("config/gesture_recognizer.task", "gesture model"),
                      ("core/prompt.txt", "JARVIS's instructions"), ("config/jarvis.ico", "icon")):
        ok = (base / rel).exists()
        r.add(OK if ok else (FAIL if "prompt" in rel else WARN), "Files", rel, "" if ok else f"missing ({what})")
    f = base / "config" / "api_keys.json"
    if f.exists():
        try:
            json.loads(f.read_text(encoding="utf-8"))
            r.add(OK, "Settings", "api_keys.json is valid")
        except json.JSONDecodeError as e:
            r.add(FAIL, "Settings", "api_keys.json is broken",
                  f"line {e.lineno}, column {e.colno}: {e.msg} — fix it or use ⚙ → ADVANCED SETTINGS")
    elif (base / "config" / "api_keys.json.locked").exists():
        r.add(OK, "Settings", "Keys are locked (JARVIS is closed)")
    else:
        r.add(WARN, "Settings", "No settings yet", "JARVIS will ask for the Gemini key on first start")
    key = (cfg.get("gemini_api_key") or "").strip()
    r.add(OK if key else FAIL, "Keys", "Gemini key present", "" if key else "add it on the setup screen or Advanced Settings")
    r.add(OK if cfg.get("tinyfish_api_key") else INFO, "Keys", "TinyFish key",
          "set — free web search on" if cfg.get("tinyfish_api_key") else "not set (searches use Gemini — optional)")
    # ── Network ──
    if network:
        try:
            socket.create_connection(("1.1.1.1", 443), timeout=4).close()
            r.add(OK, "Network", "Internet")
            online = True
        except Exception:
            r.add(FAIL, "Network", "Internet", "offline — JARVIS needs internet (or use offline_jarvis.bat)")
            online = False
        if online and key and _has("google.genai"):
            try:
                from google import genai
                client = genai.Client(api_key=key, http_options={"timeout": 20_000})
                txt = _with_timeout(lambda: client.models.generate_content(
                    model="gemini-flash-lite-latest", contents="Reply with the word OK.").text, 25)
                r.add(OK, "Keys", "Gemini key works", (txt or "").strip()[:20])
                try:
                    _with_timeout(lambda: client.models.get(model=LIVE_MODEL), 20)
                    r.add(OK, "Keys", f"Voice model available ({LIVE_MODEL.split('/')[-1]})")
                except Exception as e:
                    r.add(FAIL, "Keys", "Voice model not found",
                          f"{LIVE_MODEL} may have been renamed/retired — update LIVE_MODEL in main.py ({str(e)[:80]})")
                try:                                    # the real thing: the live voice connection
                    _with_timeout(lambda: _live_test(key), 25)
                    r.add(OK, "Keys", "Voice connection accepts the key")
                except Exception as e:
                    r.add(FAIL, "Keys", "Voice connection refused the key", _gemini_error(e))
            except Exception as e:
                r.add(FAIL, "Keys", "Gemini key test", _gemini_error(e))
        if online and cfg.get("tinyfish_api_key"):
            try:
                import requests
                resp = requests.get("https://api.search.tinyfish.ai", params={"query": "weather today"},
                                    headers={"X-API-Key": cfg["tinyfish_api_key"]}, timeout=12)
                n = len((resp.json() or {}).get("results") or []) if resp.status_code == 200 else 0
                r.add(OK if n else FAIL, "Keys", "TinyFish key works" if n else "TinyFish key test",
                      f"{n} results" if n else f"HTTP {resp.status_code} — check the key")
            except Exception as e:
                r.add(WARN, "Keys", "TinyFish key test", e)
    # ── Hardware ──
    if hardware:
        try:
            import numpy as np
            import sounddevice as sd
            sd.query_devices(kind="input")
            rec = _with_timeout(lambda: (sd.rec(8000, samplerate=16000, channels=1, dtype="float32"), sd.wait())[0], 6)
            lvl = float(np.abs(rec).max())
            r.add(OK if lvl > 0.0005 else WARN, "Hardware", f"Microphone (level {lvl:.3f})",
                  "" if lvl > 0.0005 else "silent — check Windows privacy settings → Microphone, or ⚙ → AUDIO DEVICES")
        except Exception as e:
            r.add(FAIL, "Hardware", "Microphone", e)
        try:
            import sounddevice as sd
            sd.query_devices(kind="output")
            r.add(OK, "Hardware", "Speakers")
        except Exception as e:
            r.add(FAIL, "Hardware", "Speakers", e)
        try:
            import cv2
            idx = int(cfg.get("camera_index", 0))
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(idx)
            ok = cap.isOpened(); cap.release()
            r.add(OK if ok else WARN, "Hardware", f"Webcam {idx}", "" if ok else "not found (only needed for camera features)")
        except Exception as e:
            r.add(WARN, "Hardware", "Webcam", e)
    # ── Tools ──
    try:
        ds = list(decls())
    except Exception as e:
        r.add(FAIL, "Tools", "Loading tools", e)
        ds = []
    names = set()
    for d in ds:
        n = d.get("name", "?")
        problems = []
        if n in names:
            problems.append("duplicate name")
        names.add(n)
        if not str(d.get("description") or "").strip():
            problems.append("no description")
        params = d.get("parameters") or {}
        props = params.get("properties") or {}
        if params and str(params.get("type", "")).upper() != "OBJECT":
            problems.append("parameters type isn't OBJECT")
        for req in params.get("required") or []:
            if req not in props:
                problems.append(f"required '{req}' not defined")
        if problems:
            r.add(FAIL, "Tools", n, "; ".join(problems))
        elif n in SAFE_CALLS:
            try:
                res = str(_with_timeout(lambda: run_tool(n, SAFE_CALLS[n]), 25))
                low = res.lower()
                broke = any(w in low for w in ("error", "traceback", "exception", "failed")) and not any(
                    w in low for w in NOT_A_FAILURE)
                if n in EXPECT and EXPECT[n] not in low:
                    broke = True
                r.add(FAIL if broke else OK, "Tools", n, ("ran: " if not broke else "") + res.replace("\n", " ")[:90])
            except Exception as e:
                r.add(FAIL, "Tools", n, f"crashed: {e}")
        else:
            r.add(OK, "Tools", n, "loaded (not run — it would act on your PC)")
    r.add(OK if len(ds) >= 90 else WARN, "Tools", f"{len(ds)} tools loaded", "" if len(ds) >= 90 else "expected about 100")
    return r
