"""actions/security_watch.py — Watches the webcam while you're away. If someone
appears, it takes a photo (Documents/JARVIS/Security) and alerts you — on your
phone too, if the Telegram bot is set up."""
import sys
import threading
import time
from datetime import datetime

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
_st = {"armed": False, "gen": 0, "alerts": 0}


def _tg():
    import importlib.util
    key = "actions.telegram_bot"
    if key in sys.modules:
        return sys.modules[key]
    try:
        spec = importlib.util.spec_from_file_location(key, str(H.base_dir() / "actions" / "telegram_bot.py"))
        mod = importlib.util.module_from_spec(spec); sys.modules[key] = mod; spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _watch(gen: int, delay: int) -> None:
    import cv2
    time.sleep(delay)                        # time to leave the room
    if _st["gen"] != gen:
        return
    cap = cv2.VideoCapture(int(H.cfg().get("camera_index", 0)))
    if not cap.isOpened():
        H.say("[SECURITY] Tell the user: I couldn't open the webcam, so security watch is NOT running.")
        _st["armed"] = False
        return
    H.log(None, "SYS: Security watch armed.")
    prev, last_alert = None, 0.0
    try:
        while _st["gen"] == gen:
            ok, frame = cap.read()
            if not ok:
                time.sleep(1); continue
            g = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)
            if prev is not None:
                diff = cv2.threshold(cv2.absdiff(prev, g), 25, 255, cv2.THRESH_BINARY)[1]
                changed = cv2.countNonZero(diff) / diff.size
                if changed > 0.04 and time.monotonic() - last_alert > 60:
                    last_alert = time.monotonic()
                    _st["alerts"] += 1
                    out = H.documents_dir("Security") / f"motion {datetime.now():%Y-%m-%d %H-%M-%S}.jpg"
                    cv2.imwrite(str(out), frame)
                    H.log(None, f"SYS: ⚠ Motion detected — photo saved: {out.name}")
                    tg = _tg()
                    if tg:
                        tg.send_photo(str(out), f"⚠ JARVIS security: movement at {datetime.now():%H:%M}")
                    H.say("[SECURITY] Say firmly: 'Motion detected. This computer is being monitored and a photo has been taken.'")
            prev = g
            time.sleep(0.5)
    finally:
        cap.release()


def security_watch(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "arm").lower()
    if action in ("disarm", "stop", "off"):
        if not _st["armed"]:
            return "Security watch isn't on."
        _st["gen"] += 1; _st["armed"] = False
        return f"Security watch off. {_st['alerts']} alert(s) while it was on — photos are in Documents, JARVIS, Security."
    if action == "status":
        return f"Security watch is {'ON' if _st['armed'] else 'off'}. {_st['alerts']} alert(s) so far."
    try:
        import cv2  # noqa: F401
    except ImportError:
        return "Security watch needs OpenCV (python -m pip install opencv-python), so it is NOT armed."
    try:
        delay = max(5, min(int(float(p.get("delay_seconds") or 30)), 600))
    except (TypeError, ValueError):
        delay = 30
    _st["gen"] += 1
    _st.update(armed=True, alerts=0)
    threading.Thread(target=_watch, args=(_st["gen"], delay), daemon=True).start()
    phone = " and to your phone" if H.cfg().get("telegram_chat_id") else ""
    return (f"Security watch arms in {delay} seconds — leave the room now. Any movement takes a photo and "
            f"alerts here{phone}. Note: the webcam can't be used for anything else while it's on.")


TOOL = {
    "name": "security_watch",
    "description": ("Webcam motion alarm while the user is away: saves a photo, warns out loud and sends it "
                    "to their phone if Telegram is set up. action='arm' (default, optional delay_seconds to "
                    "leave the room); 'disarm'; 'status'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'arm', 'disarm' or 'status'."},
        "delay_seconds": {"type": "NUMBER", "description": "Seconds before it starts watching (default 30)."}},
        "required": []},
    "handler": security_watch,
}
