"""actions/gesture_calibration.py — Tune hand gestures to YOUR hand, light and camera (2.6).

"JARVIS, calibrate my gestures" → the hologram window walks you through 9 short
steps (about 50 seconds): open palm, fist, thumbs up, thumbs down, peace sign,
love-you sign, point up, pinch, and a relaxed hand. For each it records ~2.5 s of
what the webcam really sees, then works out:
  • the lowest MediaPipe confidence worth trusting for YOUR hand (min_score),
  • where YOUR pinch ends and an open hand begins (pinch_in / pinch_out),
and checks how often each sign is recognised with those settings. The result is
saved to config/gesture_calibration.json and used by hologram AND PC gesture
modes from then on (it overrides the Gesture sensitivity setting).

  "calibrate my gestures"      → action='start'
  "how good are my gestures?"  → action='report'  (last result, on screen)
  "reset gesture calibration"  → action='reset'   (back to the defaults)
"""
import json
import threading
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
_st = {"running": False, "stop": False}

STEPS = [
    ("Open_Palm", "✋  OPEN PALM", "Hold your open hand up, fingers apart, palm to the camera."),
    ("Closed_Fist", "✊  FIST", "Make a fist."),
    ("Thumb_Up", "👍  THUMBS UP", "Fist sideways, thumb pointing straight up."),
    ("Thumb_Down", "👎  THUMBS DOWN", "Thumb pointing straight down."),
    ("Victory", "✌  PEACE SIGN", "Index and middle finger up, the rest folded."),
    ("ILoveYou", "🤟  LOVE-YOU SIGN", "Thumb, index and little finger out."),
    ("Pointing_Up", "☝  POINT UP", "Only your index finger up."),
    ("pinch", "🤏  PINCH", "Touch your thumb and index fingertips together and keep them touching."),
    ("relaxed", "🖐  RELAXED HAND", "Let your hand hang loose in view — not a sign. Move it a little."),
]
SIGNS = [k for k, _, _ in STEPS if k not in ("pinch", "relaxed")]
FALSE_ALARM = {"Closed_Fist", "ILoveYou", "Thumb_Up", "Thumb_Down", "Victory", "Pointing_Up"}
READY, RECORD = 2.5, 2.5
TIPS = {"Thumb_Up": "turn your fist sideways and point the thumb straight up, clear of the knuckles",
        "Thumb_Down": "point the thumb straight down, below the fist",
        "Closed_Fist": "curl all four fingers in tightly",
        "Victory": "spread the two fingers into a clear V; fold the others",
        "ILoveYou": "keep the middle and ring fingers folded down",
        "Pointing_Up": "point straight up and fold the other fingers",
        "Open_Palm": "spread your fingers and face the palm to the camera"}


def _pct(vals, q):
    if not vals:
        return None
    v = sorted(vals)
    i = min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))
    return v[i]


def analyse(samples: dict) -> dict:
    """samples: {step: [frame or None, ...]}, frame = {"lm": 21 (x,y), "model": str|None, "score": float}.
    Pure function (no camera) → the thresholds + per-sign results."""
    from core import holo_gestures as G
    shapes = {k: [(f, G.hand_shape(f["lm"])) for f in v if f] for k, v in samples.items()}
    seen = {k: (sum(1 for f in v if f) / len(v) if v else 0.0) for k, v in samples.items()}
    notes = []
    # ── pinch: where your pinch ends and everything else begins ──
    P = [s["pinch_ratio"] for _, s in shapes.get("pinch", [])]
    N = [s["pinch_ratio"] for k, rows in shapes.items() if k != "pinch" for _, s in rows]
    a, b = _pct(P, 0.90), _pct(N, 0.05)
    if a is None or b is None:
        pin, pout = G.PINCH_IN, G.PINCH_OUT
        notes.append("Not enough pinch frames to tune the pinch — kept the default.")
    elif a < b:
        pin = max(0.10, min(0.50, a + 0.35 * (b - a)))
        pout = max(pin + 0.05, min(0.65, a + 0.70 * (b - a)))
    else:
        pin = max(0.10, min(0.40, (a + b) / 2)); pout = pin + 0.08
        notes.append("Your pinch and your other signs overlap — touch the fingertips firmly when you pinch.")
    # ── trust level: the min_score that gets most signs right with the fewest false alarms ──
    saved = (G.MIN_SCORE, G.PINCH_IN, G.PINCH_OUT, G.TIGHT_PINCH)
    best = None
    try:
        G.PINCH_IN, G.PINCH_OUT, G.TIGHT_PINCH = pin, pout, min(0.18, pin * 0.75)
        for t in [x / 100 for x in range(25, 65, 5)]:
            G.MIN_SCORE = t
            acc = {}
            for sign in SIGNS:
                rows = samples.get(sign) or []
                frames = [f for f in rows if f]
                acc[sign] = (sum(1 for f in frames if G.hand_info(f["lm"], f.get("model"), f.get("score", 0))["g"] == sign)
                             / len(frames)) if frames else 0.0
            pinch_ok = [G.hand_info(f["lm"], f.get("model"), f.get("score", 0))["pinch"]
                        for f in (samples.get("pinch") or []) if f]
            false = [G.hand_info(f["lm"], f.get("model"), f.get("score", 0))["g"] in FALSE_ALARM
                     for f in (samples.get("relaxed") or []) if f]
            fr = sum(false) / len(false) if false else 0.0
            score = sum(acc.values()) / max(1, len(acc)) - 2.0 * fr
            # better score wins; near-ties go to the setting closest to the tested default (0.45)
            if best is None or score > best[0] + 0.01 or (abs(score - best[0]) <= 0.01 and abs(t - 0.45) < abs(best[1] - 0.45)):
                best = (score, t, dict(acc), (sum(pinch_ok) / len(pinch_ok)) if pinch_ok else 0.0, fr)
    finally:
        G.MIN_SCORE, G.PINCH_IN, G.PINCH_OUT, G.TIGHT_PINCH = saved
    _, t, acc, pinch_rate, fr = best
    alone = {}
    for sign in SIGNS:
        frames = [f for f in (samples.get(sign) or []) if f]
        alone[sign] = (sum(1 for f in frames if f.get("model") == sign and f.get("score", 0) >= 0.5) / len(frames)) if frames else 0.0
    for sign in SIGNS:
        if seen.get(sign, 0) < 0.6:
            notes.append(f"{sign.replace('_', ' ')}: your hand was often out of view or not found — more light, closer.")
        elif acc[sign] < 0.7:
            notes.append(f"{sign.replace('_', ' ')}: recognised {acc[sign]:.0%} — {TIPS.get(sign, 'hold it steadier')}.")
    if fr > 0.15:
        notes.append(f"A relaxed hand looked like a sign {fr:.0%} of the time — keep your hand down when you're not signing.")
    return {"min_score": round(t, 2), "pinch_in": round(pin, 3), "pinch_out": round(pout, 3),
            "recognised": {k: round(v, 2) for k, v in acc.items()}, "camera_alone": {k: round(v, 2) for k, v in alone.items()},
            "pinch_recognised": round(pinch_rate, 2), "relaxed_false_alarm": round(fr, 2),
            "hand_seen": {k: round(v, 2) for k, v in seen.items()}, "notes": notes,
            "date": time.strftime("%Y-%m-%d %H:%M")}


def report_text(r: dict) -> str:
    names = {"Open_Palm": "Open palm", "Closed_Fist": "Fist", "Thumb_Up": "Thumbs up", "Thumb_Down": "Thumbs down",
             "Victory": "Peace sign", "ILoveYou": "Love-you", "Pointing_Up": "Point up"}
    lines = [f"Calibrated {r.get('date', '')}", "",
             f"{'Sign':14} {'now':>5}   {'camera alone':>12}"]
    for k in SIGNS:
        lines.append(f"{names[k]:14} {r['recognised'].get(k, 0):>5.0%}   {r['camera_alone'].get(k, 0):>12.0%}")
    lines += [f"{'Pinch':14} {r.get('pinch_recognised', 0):>5.0%}", "",
              f"Relaxed hand mistaken for a sign: {r.get('relaxed_false_alarm', 0):.0%}",
              f"Settings: trust MediaPipe from {r['min_score']:.2f} · pinch starts below {r['pinch_in']:.2f}, "
              f"ends above {r['pinch_out']:.2f}"]
    if r.get("notes"):
        lines += ["", "Tips:"] + [f" • {n}" for n in r["notes"]]
    lines += ["", "'Camera alone' = MediaPipe by itself; 'now' = with JARVIS's hand-shape check, smoothing and your settings."]
    return "\n".join(lines)


def _camera_frames():
    """Yields [(landmarks, gesture, score), ...] per webcam frame (mirrored)."""
    import cv2
    import mediapipe as mp
    from actions import suit_hologram as SH
    model = SH._model_file()
    if model is None:
        raise RuntimeError("the gesture model (config/gesture_recognizer.task) is missing and couldn't be downloaded")
    V = mp.tasks.vision
    recog = V.GestureRecognizer.create_from_options(V.GestureRecognizerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model)), running_mode=V.RunningMode.VIDEO, num_hands=1,
        min_hand_detection_confidence=0.4, min_hand_presence_confidence=0.4, min_tracking_confidence=0.4))
    cap = cv2.VideoCapture(int(H.cfg().get("camera_index", 0)))
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    if not cap.isOpened():
        recog.close()
        raise RuntimeError("couldn't open the webcam")
    t0, last = time.monotonic(), -1
    try:
        while not _st["stop"]:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.03); continue
            rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
            ts = max(last + 1, int((time.monotonic() - t0) * 1000)); last = ts
            try:
                res = recog.recognize_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
            except Exception:
                continue
            out = []
            for i, lms in enumerate(res.hand_landmarks or []):
                top = res.gestures[i][0] if res.gestures and i < len(res.gestures) and res.gestures[i] else None
                out.append(([(l.x, l.y) for l in lms], top.category_name if top else None, top.score if top else 0.0))
            yield out
    finally:
        cap.release()
        try:
            recog.close()
        except Exception:
            pass


def run_session(player=None, frames=None, ready: float = READY, record: float = RECORD) -> dict:
    """The guided session. frames: a frame generator (tests pass a fake one)."""
    from core import tool_bus, holo_gestures as G
    emit = lambda d: tool_bus.emit("hologram_control", d)
    frames = frames or _camera_frames()
    samples = {}
    try:
        for n, (key, title, sub) in enumerate(STEPS, 1):
            t_end = time.monotonic() + ready
            while time.monotonic() < t_end and not _st["stop"]:     # get ready (camera keeps running)
                hands = next(frames)
                emit({"banner": {"title": f"{n}/{len(STEPS)}  {title}", "sub": f"Get ready… {sub}",
                                 "p": 1 - (t_end - time.monotonic()) / ready},
                      "cursors": [(h[0][9][0], h[0][9][1], "hand") for h in hands]})
            rows = []
            t_end = time.monotonic() + record
            while time.monotonic() < t_end and not _st["stop"]:     # record
                hands = next(frames)
                rows.append({"lm": hands[0][0], "model": hands[0][1], "score": hands[0][2]} if hands else None)
                emit({"banner": {"title": f"{n}/{len(STEPS)}  {title}", "sub": "Hold it… " + sub,
                                 "p": 1 - (t_end - time.monotonic()) / record},
                      "cursors": [(h[0][9][0], h[0][9][1], "hand") for h in hands]})
            samples[key] = rows
            if _st["stop"]:
                raise RuntimeError("stopped")
    finally:
        emit({"banner": None, "cursors": []})
        try:
            frames.close()
        except Exception:
            pass
    result = analyse(samples)
    G.calibration_path().write_text(json.dumps(result, indent=2), encoding="utf-8")
    G.apply_calibration()
    return result


def gesture_calibration(parameters: dict, player=None) -> str:
    from core import holo_gestures as G
    act = str((parameters or {}).get("action") or "start").lower()
    if act in ("report", "status", "show"):
        try:
            r = json.loads(G.calibration_path().read_text(encoding="utf-8"))
        except Exception:
            return "Gestures haven't been calibrated yet — say 'calibrate my gestures'."
        H.show(player, "GESTURE CALIBRATION", report_text(r))
        return "Your gesture calibration results are on screen."
    if act in ("reset", "clear", "default"):
        try:
            G.calibration_path().unlink()
        except FileNotFoundError:
            pass
        return "Gesture calibration cleared — the default settings apply from the next time hand control starts."
    if act in ("stop", "cancel"):
        _st["stop"] = True
        return "Stopping the calibration."
    if _st["running"]:
        return "The calibration is already running — follow the steps in the hologram window."
    try:
        import cv2  # noqa: F401
        import mediapipe  # noqa: F401
    except Exception:
        return "Calibration needs MediaPipe and OpenCV (python -m pip install mediapipe opencv-python)."

    def _go():
        _st.update(running=True, stop=False)
        before = "off"
        try:
            from core import gesture_modes
            before = gesture_modes.current()
            gesture_modes.switch("off", player)                       # free the webcam
            player and player.hologram({"op": "open"})
            r = run_session(player)
            H.show(player, "GESTURE CALIBRATION", report_text(r))
            weak = [k.replace("_", " ").lower() for k, v in r["recognised"].items() if v < 0.7]
            H.say("[CALIBRATION] Tell the user in two short sentences: gesture calibration is done and saved"
                  + (f"; these signs are still weak: {', '.join(weak)} (tips are on screen)" if weak
                     else "; every sign was recognised well") + ".")
            if before in ("hologram", "pc"):
                gesture_modes.switch(before, player)                  # back to what was running
        except Exception as e:
            H.say(f"[CALIBRATION] Tell the user the gesture calibration didn't finish: {e}.")
        finally:
            _st["running"] = False
    threading.Thread(target=_go, daemon=True, name="gesture-calibration").start()
    return ("Starting gesture calibration — about 50 seconds. Follow the big instructions in the hologram window: "
            "9 signs, a few seconds each.")


TOOL = {
    "name": "gesture_calibration",
    "description": ("Tunes hand-gesture recognition to the user's own hand, light and webcam (≈50 s guided session in "
                    "the hologram window). action='start' (default, 'calibrate my gestures'), 'report' (last result), "
                    "'reset' (back to defaults), 'stop'. Use when gestures are missed or misread."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "start | report | reset | stop"}}, "required": []},
    "handler": gesture_calibration,
}
