"""actions/workout_coach.py — Counts squats, push-ups and bicep curls with the
webcam (MediaPipe body tracking), shows a camera window with the count, and
cheers you on. Close the window or say 'stop workout' to finish."""
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
EXERCISES = {  # joints (left side ids in MediaPipe Pose), down angle, up angle
    "squats":  ((23, 25, 27), 100, 160),   # hip-knee-ankle
    "pushups": ((11, 13, 15), 90, 155),    # shoulder-elbow-wrist
    "curls":   ((11, 13, 15), 50, 150),
}
_st = {"on": False, "stop": False, "count": 0, "ex": "", "goal": 0}


def _angle(a, b, c) -> float:
    ab = (a.x - b.x, a.y - b.y); cb = (c.x - b.x, c.y - b.y)
    dot = ab[0] * cb[0] + ab[1] * cb[1]
    n = math.hypot(*ab) * math.hypot(*cb) or 1e-6
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / n))))


def _run(ex: str, goal: int) -> None:
    import cv2
    import mediapipe as mp
    (j1, j2, j3), down_a, up_a = EXERCISES[ex]
    pose = mp.solutions.pose.Pose(min_detection_confidence=0.6, min_tracking_confidence=0.6)
    cap = cv2.VideoCapture(int(H.cfg().get("camera_index", 0)))
    stage, last_said = "up", 0
    try:
        while not _st["stop"] and cap.isOpened():
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.flip(frame, 1)
            res = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if res.pose_landmarks:
                lm = res.pose_landmarks.landmark
                ang = _angle(lm[j1], lm[j2], lm[j3])
                if ang < down_a and stage == "up":
                    stage = "down"
                elif ang > up_a and stage == "down":
                    stage = "up"
                    _st["count"] += 1
                    c = _st["count"]
                    if goal and c >= goal:
                        H.say(f"[WORKOUT] Tell the user enthusiastically in one sentence: {goal} {ex} done — goal reached!")
                        _st["stop"] = True
                    elif c % 5 == 0 and c != last_said:
                        last_said = c
                        H.say(f"[WORKOUT] Say only: '{c}! Keep going!'")
                mp.solutions.drawing_utils.draw_landmarks(frame, res.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS)
            cv2.putText(frame, f"{ex.upper()}: {_st['count']}" + (f" / {goal}" if goal else ""), (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 212, 255), 3)
            cv2.imshow("JARVIS Workout (press Q to stop)", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    finally:
        cap.release(); cv2.destroyAllWindows(); pose.close()
        _st["on"] = False
        log = H.load_json(H.mem_path("workouts.json"), [])
        log.append({"date": H.today(), "exercise": ex, "reps": _st["count"]})
        H.save_json(H.mem_path("workouts.json"), log[-300:])


def workout_coach(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "start").lower()
    if action == "stop":
        if not _st["on"]:
            return "No workout running."
        _st["stop"] = True
        return f"Workout stopped — {_st['count']} {_st['ex']}. Nice job!"
    if action == "history":
        log = H.load_json(H.mem_path("workouts.json"), [])
        if not log:
            return "No workouts recorded yet."
        H.show(player, "WORKOUTS", "\n".join(f"{w['date']}  {w['exercise']}: {w['reps']}" for w in log[-15:]))
        return f"{len(log)} workouts recorded; the latest are on screen."
    ex = str(p.get("exercise") or "squats").lower().replace("-", "").replace(" ", "")
    ex = {"squat": "squats", "pushup": "pushups", "curl": "curls", "bicepcurls": "curls"}.get(ex, ex)
    if ex not in EXERCISES:
        return "I can count squats, push-ups or bicep curls."
    if _st["on"]:
        return "A workout is already running."
    try:
        import mediapipe as mp
        mp.solutions.pose
    except Exception:
        return "Workout coach needs MediaPipe body tracking (python -m pip install mediapipe)."
    try:
        goal = max(0, int(float(p.get("goal") or 0)))
    except (TypeError, ValueError):
        goal = 0
    _st.update(on=True, stop=False, count=0, ex=ex, goal=goal)
    threading.Thread(target=_run, args=(ex, goal), daemon=True).start()
    side = "side-on to the camera" if ex in ("squats", "pushups") else "facing the camera, left arm visible"
    return f"Workout started: {ex}{f', goal {goal}' if goal else ''}. Stand {side} so your whole body is in view. I'll count!"


TOOL = {
    "name": "workout_coach",
    "description": ("Counts exercise reps with the webcam: squats, pushups or curls. action='start' with "
                    "exercise and optional goal; 'stop'; 'history'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'start', 'stop' or 'history'."},
        "exercise": {"type": "STRING", "description": "'squats', 'pushups' or 'curls'."},
        "goal": {"type": "NUMBER", "description": "Target number of reps."}}, "required": []},
    "handler": workout_coach,
}
