"""actions/orb_hand_control.py — Control the orb with your hands through the webcam.

  • Pinch (thumb + index finger) with ONE hand and move it → turns the orb.
  • Pinch with BOTH hands and pull them apart / push together → zooms in / out.
  • Let go (open your fingers) → the orb keeps spinning a little, then settles.
"""
import math
import threading
import time

_st = {"on": False, "stop": False}


def _pinch(hand) -> tuple | None:
    """(x, y) of the pinch point if this hand is pinching, else None."""
    lm = hand.landmark
    size = math.dist((lm[0].x, lm[0].y), (lm[9].x, lm[9].y)) or 1e-3   # wrist → middle knuckle
    gap = math.dist((lm[4].x, lm[4].y), (lm[8].x, lm[8].y))             # thumb tip ↔ index tip
    if gap / size < 0.33:
        return ((lm[4].x + lm[8].x) / 2, (lm[4].y + lm[8].y) / 2)
    return None


def _run(player) -> None:
    import cv2
    import mediapipe as mp
    from core import tool_bus
    hands = mp.solutions.hands.Hands(max_num_hands=2, min_detection_confidence=0.6, min_tracking_confidence=0.5)
    cap = cv2.VideoCapture(0)
    last_one, last_dist = None, None
    try:
        while not _st["stop"] and cap.isOpened():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05); continue
            frame = cv2.flip(frame, 1)                      # mirror, so it moves the way you do
            res = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            pinches = [pt for h in (res.multi_hand_landmarks or []) if (pt := _pinch(h))]
            if len(pinches) >= 2:                          # two-hand pinch → zoom
                d = math.dist(pinches[0], pinches[1])
                if last_dist:
                    ratio = max(0.85, min(1.18, d / last_dist))
                    if abs(ratio - 1) > 0.004:
                        tool_bus.emit("orb_control", {"zoom": ratio})
                last_dist, last_one = d, None
            elif len(pinches) == 1:                        # one-hand pinch → turn
                x, y = pinches[0]
                if last_one:
                    dx, dy = x - last_one[0], y - last_one[1]
                    if abs(dx) + abs(dy) > 0.002:
                        tool_bus.emit("orb_control", {"dyaw": dx * 6.0, "dpitch": dy * 6.0})
                last_one, last_dist = (x, y), None
            else:
                last_one = last_dist = None
            time.sleep(0.01)
    finally:
        cap.release(); hands.close()
        _st["on"] = False


def orb_hand_control(parameters: dict, player=None) -> str:
    action = str((parameters or {}).get("action") or "start").lower()
    if action == "stop":
        if not _st["on"]:
            return "Hand control isn't on."
        _st["stop"] = True
        return "Hand control off."
    if _st["on"]:
        return "Hand control is already on."
    try:
        import mediapipe as mp
        mp.solutions.hands
    except Exception:
        return "Hand control needs MediaPipe (python -m pip install mediapipe)."
    _st.update(on=True, stop=False)
    threading.Thread(target=_run, args=(player,), daemon=True, name="orb-hands").start()
    return ("Hand control on. Pinch with one hand and move to turn the orb; pinch with both hands and "
            "pull apart or push together to zoom. Say 'stop hand control' when done. "
            "(Gesture control can't run at the same time — they share the webcam.)")


TOOL = {
    "name": "orb_hand_control",
    "description": ("Control the orb with hand gestures through the webcam: one-hand pinch and move turns "
                    "it, two-hand pinch apart/together zooms. action='start' (default) or 'stop'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'start' or 'stop'."}}, "required": []},
    "handler": orb_hand_control,
}
