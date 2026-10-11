"""actions/homework_helper.py — Hold a worksheet up to the webcam (or have it on
screen) and get step-by-step HINTS. Full worked answers only when asked."""
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


def _webcam_jpeg() -> bytes:
    import cv2
    idx = int(H.cfg().get("camera_index", 0))
    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if hasattr(cv2, "CAP_DSHOW") else cv2.VideoCapture(idx)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("the webcam is busy or not connected (close camera / gesture mode first)")
    try:
        for _ in range(12):            # let the camera adjust exposure
            cap.read(); time.sleep(0.05)
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("couldn't read from the webcam")
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return buf.tobytes()
    finally:
        cap.release()


def _screen_jpeg() -> bytes:
    import pyautogui
    return H.to_jpeg(pyautogui.screenshot(), 1600)


def homework_helper(parameters: dict, player=None) -> str:
    p = parameters or {}
    source = str(p.get("source") or "camera").lower()
    mode = str(p.get("mode") or "hints").lower()
    question = str(p.get("question") or "").strip()
    try:
        img = _screen_jpeg() if source == "screen" else _webcam_jpeg()
    except Exception as e:
        return f"I couldn't capture the {'screen' if source == 'screen' else 'webcam'}: {e}"
    if mode == "full":
        style = ("Solve it fully with clear numbered steps and the final answer, explaining each step "
                 "simply so the student learns the method.")
    else:
        style = ("Do NOT give the final answer. Give step-by-step HINTS: what the question is asking, the "
                 "idea or formula to use, and the first step to try. Ask the student to try the next step.")
    prompt = (f"This is a photo of a student's homework{(' — they ask: ' + question) if question else ''}. "
              "Read the question(s) carefully (if unreadable, say what to fix: hold it closer, more light). "
              f"{style} Plain text, no markdown, at most 12 short lines.")
    try:
        ans = H.ai_vision(prompt, [img])
    except Exception as e:
        return f"I couldn't read the homework: {e}"
    H.show(player, "HOMEWORK HELP — " + ("full answer" if mode == "full" else "hints"), ans)
    return "[HOMEWORK] It's on screen. Explain it to the student kindly in 2-4 sentences:\n" + ans[:2000]


TOOL = {
    "name": "homework_helper",
    "description": ("Homework help from the webcam (hold the worksheet up) or the screen. Gives "
                    "step-by-step hints by default; mode='full' only if the user asks for the full "
                    "worked answer. source='camera' (default) or 'screen'; optional question."),
    "parameters": {"type": "OBJECT", "properties": {
        "source": {"type": "STRING", "description": "'camera' or 'screen'."},
        "mode": {"type": "STRING", "description": "'hints' (default) or 'full'."},
        "question": {"type": "STRING", "description": "Optional: which question / what they're stuck on."}},
        "required": []},
    "handler": homework_helper,
}
