"""actions/suit_hologram.py — the "holograms" tool.

Create holograms from 140 built-in shapes (sphere, DNA, galaxy, atom, reactor core,
rocket, tree, chess king, the armour suit…), any word as text ("text:HELLO"), or
ANYTHING else — JARVIS designs it from simple parts. Up to 9 at once; remove them
one by one or all; colour them from the colour wheel (red, vermilion, orange,
amber, yellow, chartreuse, green, teal, blue, violet, purple, magenta, plus cyan,
white, gray) with colour relationships (analogous, complementary, triadic, split
complementary, square, monochromatic, warm, cool, grayscale, rainbow) or a mood
("calm" → blue, "energetic" → red…). Explode / assemble / spin, and control
EVERY hologram with your hands through the webcam (2.3): rotate, move, resize,
explode, select, flick through shapes, change colour and scheme, remove —
see GESTURE_HELP below and core/holo_gestures.py."""
import math
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
_st = {"on": False, "stop": False, "engine": ""}


def _free_webcam() -> None:
    """Gesture control and orb hand control use the same webcam — pause them."""
    import sys
    gc = sys.modules.get("actions.gesture_control")
    if gc is not None and getattr(gc, "_state", {}).get("active"):
        try:
            with gc._lock:
                gc._state["stop_flag"] = True
        except Exception:
            gc._state["stop_flag"] = True
    oh = sys.modules.get("actions.orb_hand_control")
    if oh is not None and getattr(oh, "_st", {}).get("on"):
        oh._st["stop"] = True
    for _ in range(30):                                   # up to 3 s for them to let go
        busy = (gc is not None and gc._state.get("active")) or (oh is not None and oh._st.get("on"))
        if not busy:
            break
        time.sleep(0.1)


def _model_file():
    """MediaPipe's gesture model (config/gesture_recognizer.task, ~8 MB, shared with
    gesture control). Downloaded once if it isn't there."""
    from pathlib import Path
    import sys
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    path = base / "config" / "gesture_recognizer.task"
    if not path.exists():
        try:
            import requests
            r = requests.get("https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
                             "gesture_recognizer/float16/1/gesture_recognizer.task", timeout=60)
            r.raise_for_status()
            path.write_bytes(r.content)
        except Exception as e:
            print(f"[Holograms] couldn't download the gesture model: {e}")
            return None
    return path


def _hands_loop(player=None):
    """Webcam → MediaPipe → core/holo_gestures.py → hologram window."""
    import cv2
    import mediapipe as mp
    from core import tool_bus
    from core import holo_gestures as HG
    from core.holo_gestures import HoloGestureEngine, hand_info
    cfg = H.cfg()
    HG.configure(cfg.get("gesture_sensitivity", 0.4), cfg.get("gesture_hold", 0.3))
    if HG.apply_calibration():                            # measured on your hand → wins over the setting
        print(f"[Holograms] using your gesture calibration (min score {HG.MIN_SCORE:.2f}, pinch {HG.PINCH_IN:.2f})")
    engine = HoloGestureEngine()
    _free_webcam()
    cap = cv2.VideoCapture(int(cfg.get("camera_index", 0)))
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)               # always the newest frame — no lag
        cap.set(cv2.CAP_PROP_FPS, 30)
    except Exception:
        pass
    recog = legacy = None
    try:
        model = _model_file()
        if model is not None:                             # full gestures (thumbs, victory, palm…)
            V = mp.tasks.vision
            recog = V.GestureRecognizer.create_from_options(V.GestureRecognizerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
                running_mode=V.RunningMode.VIDEO, num_hands=2,      # low thresholds: find hands easily,
                min_hand_detection_confidence=0.4,                    # core/holo_gestures.py filters the signs
                min_hand_presence_confidence=0.4, min_tracking_confidence=0.4))
            _st["engine"] = "full"
        else:                                             # no model → signs from the hand's shape only
            legacy = mp.solutions.hands.Hands(max_num_hands=2, min_detection_confidence=0.4, min_tracking_confidence=0.4)
            _st["engine"] = "shape"
    except Exception as e:
        print(f"[Holograms] gesture model unavailable ({e}) — reading signs from hand shape only")
        try:
            legacy = mp.solutions.hands.Hands(max_num_hands=2, min_detection_confidence=0.4, min_tracking_confidence=0.4)
            _st["engine"] = "shape"
        except Exception as e2:
            print(f"[Holograms] hand tracking unavailable: {e2}")
            cap.release(); _st["on"] = False
            if player is not None:
                player.hologram({"op": "gestures", "on": False})
            return
    if not cap.isOpened():
        print("[Holograms] couldn't open the webcam")
        for r in (recog, legacy):
            try:
                r.close()
            except Exception:
                pass
        _st["on"] = False
        if player is not None:
            player.hologram({"op": "gestures", "on": False})
        return
    t0 = time.monotonic()
    last_ts = -1
    try:
        while not _st["stop"] and cap.isOpened():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05); continue
            rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)     # mirrored: move right = right
            hands = []
            if recog is not None:
                ts = int((time.monotonic() - t0) * 1000)
                if ts <= last_ts:
                    ts = last_ts + 1
                last_ts = ts
                try:
                    res = recog.recognize_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
                except Exception:
                    continue
                for i, lms in enumerate(res.hand_landmarks or []):
                    top = res.gestures[i][0] if res.gestures and i < len(res.gestures) and res.gestures[i] else None
                    hands.append(hand_info([(l.x, l.y) for l in lms],
                                           top.category_name if top else None, top.score if top else 0.0))
            else:
                res = legacy.process(rgb)
                for hl in (res.multi_hand_landmarks or []):
                    hands.append(hand_info([(l.x, l.y) for l in hl.landmark], None))
            hands.sort(key=lambda h: h["palm"][0])                         # stable left → right order
            for cmd in engine.update(hands):
                tool_bus.emit("hologram_control", cmd)
            time.sleep(0.005)
    finally:
        cap.release()
        for r in (recog, legacy):
            try:
                r.close()
            except Exception:
                pass
        _st["on"] = False
        try:
            tool_bus.emit("hologram_control", {"cursors": [], "mode": ""})
            if player is not None:
                player.hologram({"op": "gestures", "on": False})
        except Exception:
            pass


GESTURE_HELP = ("ONE HAND\n"
                "  Pinch + move ........ rotate\n"
                "  Fist over a hologram  grab THAT one · move = move · pull closer = bigger, push away = smaller · open hand = drop\n"
                "  Swipe open palm ..... select next / previous hologram\n"
                "  Hold palm still 1 s . spin on / off\n"
                "  Point up ............ select all <-> back to one\n"
                "  Thumb up / down ..... next / previous shape (hold to flick through all 140)\n"
                "  Victory (peace) ..... next colour on the colour wheel\n"
                "  Love-you sign ....... next colour scheme\n"
                "TWO HANDS\n"
                "  Pinch both, pull apart / together ... bigger / smaller\n"
                "  Open both, pull apart / together .... explode / reassemble\n"
                "  Both thumbs down for 1 s ............ remove it\n\n"
                "Gestures act on the SELECTED hologram (brackets around it), or on all when none is.\n"
                "Mouse: click = select, drag = rotate, scroll = size. Keys: arrows, C, S, Space, Del, R.\n\n"
                "TWO MODES (only one at a time): HOLOGRAM = hands move holograms · PC = hands control the computer.\n"
                "Say 'hologram gesture mode' / 'PC gesture mode' / 'gestures off', or use the buttons at the top of\n"
                "the HAND CONTROLS panel in the hologram window (keys G = hologram, P = PC, O = off, H = hide panel).")


def _colors(p: dict):
    from core import holo_shapes as HS
    text = f"{p.get('color') or ''} {p.get('scheme') or ''}".strip()
    base = HS.color_name(str(p.get("color") or "")) or HS.color_name(text) or "cyan"
    scheme = HS.scheme_name(str(p.get("scheme") or text))
    return base, scheme, HS.palette(base, scheme)


def holograms(parameters: dict, player=None) -> str:
    from core import holo_shapes as HS
    p = parameters or {}
    act = str(p.get("action") or "create").lower()
    if player is None or not hasattr(player, "hologram"):
        return "Holograms need the JARVIS window."
    try:
        from core import gesture_modes
        gesture_modes.set_player(player)
    except Exception:
        gesture_modes = None
    if act in ("gesture_mode", "mode", "hand_mode"):             # hologram | pc | off
        if gesture_modes is None:
            return "Gesture modes aren't available."
        return gesture_modes.switch(str(p.get("target") or p.get("mode") or "hologram"), player)
    if act == "shapes":
        groups = HS.CATEGORIES
        H.show(player, f"HOLOGRAM SHAPES ({len(HS.names())} + text + anything)",
               "\n\n".join(f"{g}:\n  " + ", ".join(v) for g, v in groups.items())
               + "\n\nAlso: text:YOURWORD — and anything else, which I design from parts.")
        return f"{len(HS.names())} built-in shapes are on screen — plus any word as text, and anything else I can design."
    if act == "colors":
        H.show(player, "HOLOGRAM COLOURS",
               "Colour wheel: " + ", ".join(HS.WHEEL) + ", plus cyan, white, gray.\n\nRelationships: "
               + ", ".join(HS.SCHEMES) + "\n\nMoods: calm/trust → blue · energy/passion → red · nature/growth → green · "
               "joy/sunshine → yellow · warm/creative → orange · royal/mysterious → purple")
        return "The colour wheel, colour relationships and moods are on screen."
    if act == "list":
        cur = player.hologram_names() if hasattr(player, "hologram_names") else []
        return ("Holograms up now: " + ", ".join(cur)) if cur else "No holograms are up."
    if act == "create":
        shape = str(p.get("shape") or "suit").strip()
        base, scheme, pal = _colors(p)
        key = HS.resolve(shape)
        import re as _re
        plain = _re.sub(r"^(an?|the|some)\s+", "", shape.strip().lower())[:24]
        cmd = {"op": "add", "name": key or plain, "shape": key, "palette": pal, "scheme": scheme, "base": base}
        if key is None:                                   # anything else → JARVIS designs it from parts
            try:
                parts = H.ai_fast_json(HS.CUSTOM_PROMPT.format(what=shape[:80]))
                parts = parts if isinstance(parts, list) else (parts or {}).get("parts", [])
                HS.from_primitives(parts)                 # check it builds before sending
                cmd["primitives"] = parts
            except Exception as e:
                return f"I couldn't design a '{shape}' hologram ({e}). Try a built-in shape — say 'list hologram shapes'."
        player.hologram(cmd)
        label = cmd["name"].replace("text:", "'") + ("'" if cmd["name"].startswith("text:") else "")
        what = ("custom-designed " if key is None else "") + label
        col = base if scheme == "single" else f"{base}, {scheme}"
        return f"Creating {'an' if what[0] in 'aeiou' else 'a'} {what} hologram in {col}."
    if act == "remove":
        target = str(p.get("target") or "last")
        player.hologram({"op": "remove", "target": target})
        return "Removing all holograms." if target.lower() in ("all", "everything") else f"Removing {target}."
    if act == "color":
        base, scheme, pal = _colors(p)
        player.hologram({"op": "color", "target": str(p.get("target") or "all"), "palette": pal, "scheme": scheme, "base": base})
        return f"Recoloured to {base}" + (f" ({scheme}: " + ", ".join(pal) + ")" if scheme != "single" else "") + "."
    if act in ("select", "focus", "pick"):
        target = str(p.get("target") or "all")
        player.hologram({"op": "select", "target": target})
        return ("All holograms selected." if target.lower() in ("all", "none", "everything")
                else f"Selected {target} — gestures and the mouse now move just that one.")
    if act in ("gestures", "gesture_help", "help"):
        H.show(player, "HOLOGRAM GESTURES", GESTURE_HELP)
        return "The hologram gestures are on screen." + ("" if _st["on"] else " Say 'hologram gestures on' to start.")
    if act in ("gestures_on", "hands_on"):
        if _st["on"]:
            return "Hand control for the holograms is already on."
        try:
            import cv2  # noqa: F401
            import mediapipe  # noqa: F401
        except Exception:
            return "Hand control needs MediaPipe and OpenCV (python -m pip install mediapipe opencv-python)."
        was_pc = gesture_modes is not None and gesture_modes.current() == "pc"
        player.hologram("show")
        player.hologram({"op": "gestures", "on": True})
        _st.update(on=True, stop=False)
        threading.Thread(target=_hands_loop, args=(player,), daemon=True, name="holo-hands").start()
        return ("HOLOGRAM gesture mode on — your hands now move the holograms, not the computer. Pinch and move to "
                "rotate, fist to move, swipe your palm to pick one, thumbs up or down to change shape, peace sign "
                "for the next colour, two pinches to resize, two open palms to explode. The controls are listed in "
                "the hologram window." + (" PC gesture control is paused — say 'PC gesture mode' to switch back."
                                          if was_pc else ""))
    if act in ("gestures_off", "hands_off"):
        _st["stop"] = True
        player.hologram({"op": "gestures", "on": False})
        return "Hologram gesture mode off. (Say 'PC gesture mode' to control the computer with your hands.)"
    if act == "close":
        _st["stop"] = True
    if act not in ("show", "explode", "assemble", "spin", "stop_spin", "reset", "close"):
        return "Holograms: create, remove, color, select, list, shapes, colors, gestures, show, explode, assemble, spin, stop_spin, reset, close, gestures_on, gestures_off."
    player.hologram(act)
    return {"show": "Holograms up.", "explode": "Exploding them.", "assemble": "Reassembling.", "spin": "Spinning.",
            "stop_spin": "Holding still.", "reset": "View reset.", "close": "Closing all holograms."}[act]


TOOL = {
    "name": "holograms",
    "description": ("Holograms + hologram HAND-GESTURE control (webcam): create, remove, recolour, gestures_on. "
                    "action='gesture_mode' with target 'hologram' | 'pc' | 'off' switches which one the hands control "
                    "(holograms or the computer) — only one at a time. "
                    "3D particle holograms (up to 9 at once). action='create' (shape: any of 140 built-ins like sphere, dna, lorenz attractor, robot, eiffel tower, jellyfish, "
                    "galaxy, atom, reactor core, rocket, tree, suit… or 'text:WORD' or ANYTHING else, which is designed from "
                    "parts; color: red, vermilion, orange, amber, yellow, chartreuse, green, teal, blue, violet, purple, "
                    "magenta, cyan, white, gray, or a mood; scheme: analogous, complementary, triadic, split complementary, "
                    "square, monochromatic, warm, cool, grayscale, rainbow); 'remove' (target: name, number, 'last' or 'all'); "
                    "'color' (target, color, scheme); 'select' (target — gestures/mouse then act on just that one; 'all' = every one); "
                    "'list' (what's up now); 'shapes' (show all shapes); 'colors'; 'gestures' (show the hand-gesture list); "
                    "'explode', 'assemble', 'spin', 'stop_spin', 'reset', 'close' (remove all); "
                    "'gestures_on'/'gestures_off' (webcam hand control of every hologram: rotate, move, resize, explode, "
                    "select, change shape/colour/scheme, remove)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above (default 'create')."},
        "shape": {"type": "STRING", "description": "Shape to create."},
        "color": {"type": "STRING", "description": "Colour name or mood."},
        "scheme": {"type": "STRING", "description": "Colour relationship."},
        "target": {"type": "STRING", "description": "Which hologram: name, number (1 = first), 'last', 'selected' or 'all'."}},
        "required": []},
    "handler": holograms,
}
