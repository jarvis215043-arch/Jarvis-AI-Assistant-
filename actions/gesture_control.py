"""
actions/gesture_control.py — Hand gesture control via webcam using MediaPipe's
GestureRecognizer, plus custom motion gestures (swipe, pinch, zoom) and
two-hand combos, on top of the 7 built-in classified gestures.

Two modes:
  'gestures'      (default) — all discrete gestures + swipe + pinch + zoom + combos
  'volume_slider' — dedicated mode: hand height controls system volume directly
                    (mutually exclusive with 'gestures' — run one at a time)

NOTE: keeps the webcam open continuously while active. Stop gesture mode
before using JARVIS's "look at camera" vision feature.

KNOWN LIMITATION: with two hands visible, MediaPipe doesn't guarantee which
hand is "index 0" from frame to frame, so single-hand gestures can
occasionally flicker between your two hands if both are up.
"""
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False

try:
    import mediapipe as mp
    _MEDIAPIPE = True
except ImportError:
    _MEDIAPIPE = False

try:
    import pyautogui
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

_IS_WINDOWS = sys.platform == "win32"

try:
    if _IS_WINDOWS:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        _PYCAW = True
    else:
        _PYCAW = False
except ImportError:
    _PYCAW = False

try:
    if _IS_WINDOWS:
        import wmi
        _WMI = True
    else:
        _WMI = False
except ImportError:
    _WMI = False


_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
    "gesture_recognizer/float16/1/gesture_recognizer.task"
)

_CONFIDENCE_THRESHOLD     = 0.45   # overridden by Advanced Settings → Gesture sensitivity
_HOLD_FRAMES              = 3
_COOLDOWN_SECONDS         = 1.5
_PINCH_DISTANCE           = 0.06
_SWIPE_DISTANCE           = 0.22
_VERTICAL_SWIPE_DISTANCE  = 0.22
_SWIPE_WINDOW             = 0.5
_SWIPE_COOLDOWN           = 1.0
_ZOOM_DISTANCE_DELTA      = 0.12
_ZOOM_WINDOW              = 0.6
_LONG_HOLD_SECONDS        = 3.0

_state = {"active": False, "stop_flag": False}

# Signs whose action is disruptive (fist = MUTE, love-you = LOCK THE PC) only count when
# MediaPipe AND the hand's shape both clearly agree, the thumb isn't touching the index
# (a pinch), and the sign is held for half a second.
_RISKY = {"Closed_Fist", "ILoveYou"}
_RISKY_HOLD = 0.5


def _pc_sign(h: dict):
    g = h.get("g")
    if g in _RISKY and not (h.get("model") == g and h.get("geo") == g and h.get("pr", 0) >= 0.35
                            and h.get("score", 0) >= max(0.6, _CONFIDENCE_THRESHOLD)):
        return None
    return g
_lock = threading.Lock()


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _model_path() -> Path:
    return _base_dir() / "config" / "gesture_recognizer.task"


def _ensure_model(player=None) -> bool:
    path = _model_path()
    if path.exists():
        return True
    try:
        import requests
        _log("Downloading gesture recognition model (one-time, ~10 MB)...", player)
        resp = requests.get(_MODEL_URL, timeout=60)
        resp.raise_for_status()
        path.write_bytes(resp.content)
        return True
    except Exception as e:
        _log(f"Could not download the gesture model: {e}", player)
        return False


def _screenshot_dir() -> Path:
    out = _base_dir() / "gesture_screenshots"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _take_screenshot():
    if not _PYAUTOGUI:
        return
    img = pyautogui.screenshot()
    path = _screenshot_dir() / f"screenshot_{int(time.time())}.png"
    img.save(str(path))


def _lock_pc():
    try:
        if _IS_WINDOWS:
            pyautogui.hotkey("win", "l")
        elif sys.platform == "darwin":
            subprocess.run(["osascript", "-e",
                'tell application "System Events" to keystroke "q" using {control down, command down}'],
                check=False)
        else:
            subprocess.run(["loginctl", "lock-session"], check=False)
    except Exception as e:
        print(f"[GestureControl] Lock failed: {e}")


def _set_volume_absolute(level_0_to_1: float):
    """Windows only, via pycaw. Silently no-ops elsewhere."""
    if not (_IS_WINDOWS and _PYCAW):
        return
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(max(0.0, min(1.0, level_0_to_1)), None)
    except Exception as e:
        print(f"[GestureControl] Volume set failed: {e}")


def _set_brightness_relative(direction: str):
    """Windows laptop screens only — external monitors generally don't
    support this via WMI, so this quietly does nothing on a desktop rig."""
    if not _WMI:
        return
    try:
        c = wmi.WMI(namespace="wmi")
        methods = c.WmiMonitorBrightnessMethods()[0]
        current = c.WmiMonitorBrightness()[0].CurrentBrightness
        step = 10 if direction == "up" else -10
        new_level = max(0, min(100, current + step))
        methods.WmiSetBrightness(new_level, 0)
    except Exception as e:
        print(f"[GestureControl] Brightness change failed (likely an external monitor): {e}")


def _run_single_hand_action(gesture_name: str, player=None):
    try:
        if gesture_name == "Thumb_Up":
            pyautogui.press("volumeup")
        elif gesture_name == "Thumb_Down":
            pyautogui.press("volumedown")
        elif gesture_name == "Open_Palm":
            pyautogui.press("playpause")
        elif gesture_name == "Closed_Fist":
            pyautogui.press("volumemute")
        elif gesture_name == "Victory":
            _take_screenshot()
        elif gesture_name == "Pointing_Up":
            if player and hasattr(player, "request_say"):
                player.request_say("Please repeat your last response.")
        elif gesture_name == "ILoveYou":
            _lock_pc()
        else:
            return
        _log(f"Gesture: {gesture_name} triggered.", player)
    except Exception as e:
        _log(f"Gesture action failed ({gesture_name}): {e}", player)


def _trigger_pinch(player=None):
    try:
        pyautogui.click()
        _log("Gesture: Pinch → click.", player)
    except Exception as e:
        _log(f"Pinch action failed: {e}", player)


def _trigger_swipe(direction: str, player=None):
    try:
        pyautogui.press("nexttrack" if direction == "right" else "prevtrack")
        _log(f"Gesture: Swipe {direction} triggered.", player)
    except Exception as e:
        _log(f"Swipe action failed: {e}", player)


def _trigger_vertical_swipe(direction: str, player=None):
    try:
        _set_brightness_relative(direction)
        _log(f"Gesture: Vertical swipe {direction} → brightness {direction}.", player)
    except Exception as e:
        _log(f"Vertical swipe action failed: {e}", player)


def _trigger_zoom(direction: str, player=None):
    try:
        pyautogui.hotkey("ctrl", "+" if direction == "in" else "-")
        _log(f"Gesture: Zoom {direction} triggered.", player)
    except Exception as e:
        _log(f"Zoom action failed: {e}", player)


def _start_focus_mode(player=None):
    mod = sys.modules.get("actions.focus_mode")
    if mod and hasattr(mod, "focus_mode"):
        try:
            result = mod.focus_mode({"action": "start", "minutes": 25}, player=player)
            _log(f"Focus Mode result: {result}", player)
        except Exception as e:
            _log(f"Could not start Focus Mode: {e}", player)


_COMBO_ACTIONS = {
    frozenset({"Thumb_Up"}):                ("Focus Mode",               lambda p: _start_focus_mode(p)),
    frozenset({"Closed_Fist"}):             ("Task Manager",             lambda p: pyautogui.hotkey("ctrl", "shift", "esc")),
    frozenset({"Victory"}):                 ("File Explorer",            lambda p: pyautogui.hotkey("win", "e")),
    frozenset({"Thumb_Up", "Open_Palm"}):   ("Next virtual desktop",     lambda p: pyautogui.hotkey("ctrl", "win", "right")),
    frozenset({"Thumb_Down", "Open_Palm"}): ("Previous virtual desktop", lambda p: pyautogui.hotkey("ctrl", "win", "left")),
}


def _trigger_combo(gesture_a: str, gesture_b: str, player=None):
    key = frozenset({gesture_a, gesture_b})
    entry = _COMBO_ACTIONS.get(key)
    if entry is None:
        return
    label, action = entry
    try:
        action(player)
        _log(f"Two-hand combo: {label} triggered.", player)
    except Exception as e:
        _log(f"Combo action failed ({label}): {e}", player)


def _watch_gestures_loop(player):
    BaseOptions              = mp.tasks.BaseOptions
    GestureRecognizer        = mp.tasks.vision.GestureRecognizer
    GestureRecognizerOptions = mp.tasks.vision.GestureRecognizerOptions
    VisionRunningMode        = mp.tasks.vision.RunningMode

    options = GestureRecognizerOptions(
        base_options=BaseOptions(model_asset_path=str(_model_path())),
        running_mode=VisionRunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.4,
        min_hand_presence_confidence=0.4,
        min_tracking_confidence=0.4,
    )

    cap = cv2.VideoCapture(0)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    if not cap.isOpened():
        _log("Could not open the webcam for gesture control.", player)
        with _lock:
            _state["active"] = False
        return

    last_gesture = None
    hold_count = 0
    last_trigger_time = 0.0
    open_palm_start_time = None

    pinch_hold = 0
    last_pinch_time = 0.0

    combo_hold = 0
    last_combo_time = 0.0
    last_combo_key = None

    wrist_x_history: list[tuple[float, float]] = []
    wrist_y_history: list[tuple[float, float]] = []
    last_swipe_time = 0.0

    hand_distance_history: list[tuple[float, float]] = []
    last_zoom_time = 0.0

    start_time = time.monotonic()

    # Sensitivity (2.4): the sign is read by MediaPipe AND from the hand's shape, and voted
    # over the last few frames, so one flickering frame no longer cancels a held sign.
    global _CONFIDENCE_THRESHOLD
    from core import holo_gestures as HG
    try:
        from core.secure_config import read_config
        _cfg = read_config()
        _CONFIDENCE_THRESHOLD = max(0.1, min(0.9, float(_cfg.get("gesture_sensitivity", 0.4))))
    except Exception:
        pass
    HG.configure(_CONFIDENCE_THRESHOLD)
    if HG.apply_calibration():                            # measured on your hand (gesture calibration)
        _CONFIDENCE_THRESHOLD = HG.MIN_SCORE
    smoother = HG.SignSmoother(frames=5, need=3)
    risky_pending = None                                  # (sign, since) for mute / lock

    try:
        with GestureRecognizer.create_from_options(options) as recognizer:
            while True:
                with _lock:
                    if _state["stop_flag"]:
                        break
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                timestamp_ms = int((time.monotonic() - start_time) * 1000)
                now = time.monotonic()

                try:
                    result = recognizer.recognize_for_video(mp_image, timestamp_ms)
                except Exception:
                    continue

                num_hands_seen = len(result.hand_landmarks) if result.hand_landmarks else 0

                # ── Single-hand discrete gesture ──────────────────────────────
                infos = []
                for i, lms in enumerate(result.hand_landmarks or []):
                    top = result.gestures[i][0] if result.gestures and i < len(result.gestures) and result.gestures[i] else None
                    infos.append(HG.hand_info([(l.x, l.y) for l in lms],
                                              top.category_name if top else None, top.score if top else 0.0))
                frame_sign = next((_pc_sign(h) for h in infos if _pc_sign(h)), None) if num_hands_seen == 1 else \
                    (_pc_sign(infos[0]) if infos else None)
                steady = smoother.feed(frame_sign)
                top_name = smoother.current

                if steady in _RISKY:
                    risky_pending = (steady, now)             # mute / lock: wait until it's clearly held
                elif steady and (now - last_trigger_time) >= _COOLDOWN_SECONDS:
                    _run_single_hand_action(steady, player)
                    last_trigger_time = now
                if risky_pending:
                    if top_name != risky_pending[0]:
                        risky_pending = None
                    elif now - risky_pending[1] >= _RISKY_HOLD and (now - last_trigger_time) >= _COOLDOWN_SECONDS:
                        _run_single_hand_action(risky_pending[0], player)
                        last_trigger_time = now
                        risky_pending = None

                # ── Long-hold Open_Palm → stop gesture control ────────────────
                if top_name == "Open_Palm":
                    if open_palm_start_time is None:
                        open_palm_start_time = now
                    elif (now - open_palm_start_time) >= _LONG_HOLD_SECONDS:
                        _log("Gesture: Open palm held 3s → stopping gesture control.", player)
                        with _lock:
                            _state["stop_flag"] = True
                        break
                else:
                    open_palm_start_time = None

                # ── Pinch + horizontal/vertical swipe (hand index 0) ──────────
                if num_hands_seen >= 1:
                    lm = result.hand_landmarks[0]
                    if infos and infos[0]["pinch"]:               # thumb–index gap vs hand size, any distance from the camera
                        pinch_hold += 1
                    else:
                        pinch_hold = max(0, pinch_hold - 1)

                    if pinch_hold == _HOLD_FRAMES and (now - last_pinch_time) >= _COOLDOWN_SECONDS:
                        _trigger_pinch(player)
                        last_pinch_time = now

                    wrist_x, wrist_y = lm[0].x, lm[0].y
                    wrist_x_history.append((now, wrist_x))
                    wrist_y_history.append((now, wrist_y))
                    wrist_x_history[:] = [(t, x) for (t, x) in wrist_x_history if now - t <= _SWIPE_WINDOW]
                    wrist_y_history[:] = [(t, y) for (t, y) in wrist_y_history if now - t <= _SWIPE_WINDOW]

                    if wrist_x_history and (now - last_swipe_time) >= _SWIPE_COOLDOWN:
                        dx_swipe = wrist_x - wrist_x_history[0][1]
                        dy_swipe = wrist_y - wrist_y_history[0][1]
                        if abs(dx_swipe) >= _SWIPE_DISTANCE and abs(dx_swipe) >= abs(dy_swipe):
                            _trigger_swipe("right" if dx_swipe > 0 else "left", player)
                            last_swipe_time = now
                            wrist_x_history.clear(); wrist_y_history.clear()
                        elif abs(dy_swipe) >= _VERTICAL_SWIPE_DISTANCE:
                            _trigger_vertical_swipe("up" if dy_swipe < 0 else "down", player)
                            last_swipe_time = now
                            wrist_x_history.clear(); wrist_y_history.clear()

                # ── Two-hand: combos + zoom ────────────────────────────────────
                if num_hands_seen == 2:
                    lm0 = result.hand_landmarks[0][0]
                    lm1 = result.hand_landmarks[1][0]
                    hand_dist = ((lm0.x - lm1.x) ** 2 + (lm0.y - lm1.y) ** 2) ** 0.5
                    hand_distance_history.append((now, hand_dist))
                    hand_distance_history[:] = [(t, d) for (t, d) in hand_distance_history if now - t <= _ZOOM_WINDOW]

                    if hand_distance_history and (now - last_zoom_time) >= _SWIPE_COOLDOWN:
                        delta = hand_dist - hand_distance_history[0][1]
                        if delta >= _ZOOM_DISTANCE_DELTA:
                            _trigger_zoom("in", player)
                            last_zoom_time = now
                            hand_distance_history.clear()
                        elif delta <= -_ZOOM_DISTANCE_DELTA:
                            _trigger_zoom("out", player)
                            last_zoom_time = now
                            hand_distance_history.clear()

                    if len(result.gestures) == 2:
                        names = [_pc_sign(h) for h in infos if _pc_sign(h)]
                        combo_key = frozenset(names) if len(names) == 2 else None

                        if combo_key and combo_key in _COMBO_ACTIONS and combo_key == last_combo_key:
                            combo_hold += 1
                        else:
                            combo_hold = 1
                            last_combo_key = combo_key

                        if (combo_key and combo_hold == _HOLD_FRAMES
                                and (now - last_combo_time) >= 2.5):
                            gestures_list = list(combo_key)
                            a = gestures_list[0]
                            b = gestures_list[1] if len(gestures_list) > 1 else gestures_list[0]
                            _trigger_combo(a, b, player)
                            last_combo_time = now
                else:
                    combo_hold = 0
                    last_combo_key = None

                time.sleep(0.03)
    finally:
        cap.release()
        with _lock:
            _state["active"] = False
            _state["stop_flag"] = False


def _watch_volume_slider_loop(player):
    BaseOptions           = mp.tasks.BaseOptions
    HandLandmarker        = mp.tasks.vision.HandLandmarker
    HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
    VisionRunningMode     = mp.tasks.vision.RunningMode

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(_model_path())),
        running_mode=VisionRunningMode.VIDEO,
        num_hands=1,
    )

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        _log("Could not open the webcam for the volume slider.", player)
        with _lock:
            _state["active"] = False
        return

    start_time = time.monotonic()
    if not _PYCAW:
        _log("pycaw isn't available — volume slider needs it for smooth control.", player)

    try:
        with HandLandmarker.create_from_options(options) as landmarker:
            while True:
                with _lock:
                    if _state["stop_flag"]:
                        break
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                timestamp_ms = int((time.monotonic() - start_time) * 1000)

                try:
                    result = landmarker.detect_for_video(mp_image, timestamp_ms)
                except Exception:
                    continue

                if result.hand_landmarks:
                    wrist_y = result.hand_landmarks[0][0].y
                    volume_level = max(0.0, min(1.0, 1.0 - wrist_y))
                    if _PYCAW:
                        _set_volume_absolute(volume_level)

                time.sleep(0.05)
    finally:
        cap.release()
        with _lock:
            _state["active"] = False
            _state["stop_flag"] = False


def gesture_control(parameters: dict, player=None, session_memory=None) -> str:
    if not _CV2:
        return "Gesture control needs 'opencv-python' installed."
    if not _MEDIAPIPE:
        return "Gesture control needs 'mediapipe' installed."
    if not _PYAUTOGUI:
        return "Gesture control needs 'pyautogui' installed."

    params = parameters or {}
    action = (params.get("action") or "start").strip().lower()
    mode   = (params.get("mode") or "gestures").strip().lower()
    try:
        from core import gesture_modes
        gesture_modes.set_player(player)
    except Exception:
        gesture_modes = None

    if action == "stop":
        with _lock:
            if not _state["active"]:
                return "Gesture control isn't running, sir."
            _state["stop_flag"] = True
        msg = "Gesture control stopped, sir."
        _log(msg, player)
        return msg

    if action == "status":
        with _lock:
            active = _state["active"]
        return "Gesture control is active." if active else "Gesture control is off."

    # Holograms on screen → the user means HOLOGRAM hand control, not the computer.
    if mode not in ("computer", "pc", "system", "volume_slider") and player is not None:
        try:
            up = player.hologram_names() if hasattr(player, "hologram_names") else []
            holo = sys.modules.get("actions.suit_hologram")
            if up and holo is not None:
                with _lock:
                    if _state["active"]:
                        _state["stop_flag"] = True
                return holo.holograms({"action": "gestures_on"}, player)
        except Exception as e:
            _log(f"Couldn't hand over to hologram control: {e}", player)

    # PC mode asked for explicitly → hologram hand control lets go of the webcam first
    if gesture_modes is not None and gesture_modes.current() == "hologram":
        gesture_modes.stop_hologram()

    with _lock:
        if _state["active"]:
            return "Gesture control is already running, sir."

    if not _ensure_model(player):
        return "Sir, I couldn't set up gesture recognition — the model download failed."

    with _lock:
        _state["active"] = True
        _state["stop_flag"] = False

    if mode == "volume_slider":
        threading.Thread(target=_watch_volume_slider_loop, args=(player,), daemon=True).start()
        msg = "Volume slider mode on, sir — raise your hand higher for louder, lower for quieter."
    else:
        threading.Thread(target=_watch_gestures_loop, args=(player,), daemon=True).start()
        msg = (
            "Gesture control is on, sir. Thumbs up/down for volume, open palm for "
            "play/pause, fist to mute, victory sign for a screenshot, pointing up "
            "to repeat my last answer, love-you sign to lock the PC, swipe left or "
            "right to skip tracks, swipe up or down for brightness, pinch to click, "
            "spread your hands apart or together to zoom, and mixed two-hand combos "
            "for Task Manager, File Explorer, and switching desktops. Hold an open "
            "palm for 3 seconds to turn gesture control off."
        )
    _log(msg, player)
    return msg


def _log(message: str, player=None) -> None:
    print(f"[GestureControl] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass


TOOL = {
    "name": "gesture_control",
    "description": (
        "Webcam hand gestures that control the COMPUTER (volume, media, clicks) — not for holograms. "
        "Starts, stops, or checks it. "
        "mode='gestures' (default): thumbs up/down for volume, open palm for "
        "play/pause, fist to mute, victory for screenshot, pointing-up to repeat "
        "last response, love-you sign to lock PC, swipe left/right to skip tracks, "
        "swipe up/down for brightness, pinch to click, hands apart/together to "
        "zoom, two-hand combos for Task Manager/File Explorer/desktop switching, "
        "and a 3-second open-palm hold to stop. "
        "mode='volume_slider': hand height directly controls volume. "
        "action='start' (default), 'stop', or 'status'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "'start', 'stop', or 'status'. Defaults to 'start'."},
            "mode":   {"type": "STRING", "description": "'gestures' (default), 'volume_slider', or 'computer' (force PC control even while holograms are up)."}
        },
        "required": []
    },
    "handler": gesture_control,
}