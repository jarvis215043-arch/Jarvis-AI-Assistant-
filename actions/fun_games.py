"""actions/fun_games.py — Quiz show for friends (scoreboard on the HUD), jokes &
riddles, rap/poem battle, air Pictionary (draw with your finger in front of the
webcam) and a chess coach that looks at the board on your screen."""
import random
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
_quiz = {"players": [], "scores": {}, "qs": [], "i": 0, "turn": 0, "topic": ""}
_riddle = {"answer": ""}
_pict = {"on": False, "stop": False, "guess": False}


def _board():
    H.show(None, f"QUIZ SHOW — {_quiz['topic']}", "\n".join(f"{n:<14} {s} pt{'s' if s != 1 else ''}"
           for n, s in sorted(_quiz["scores"].items(), key=lambda kv: -kv[1])))


def _ask():
    q = _quiz["qs"][_quiz["i"]]
    who = _quiz["players"][_quiz["turn"] % len(_quiz["players"])]
    opts = " | ".join(f"{chr(65 + k)}) {o}" for k, o in enumerate(q["options"]))
    return (f"[QUIZ SHOW] Like a game-show host, ask {who}: {q['q']} Options: {opts}. Wait for {who}'s answer, "
            "then call fun_games action='quiz_answer' with answer.")


def _pictionary() -> None:
    import cv2, numpy as np, mediapipe as mp
    hands = mp.solutions.hands.Hands(max_num_hands=1, min_detection_confidence=0.6)
    cap = cv2.VideoCapture(int(H.cfg().get("camera_index", 0)))
    canvas, last = None, None
    try:
        while not _pict["stop"] and cap.isOpened():
            ok, frame = cap.read()
            if not ok:
                continue
            frame = cv2.flip(frame, 1)
            if canvas is None:
                canvas = np.zeros_like(frame)
            res = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if res.multi_hand_landmarks:
                lm = res.multi_hand_landmarks[0].landmark
                h, w = frame.shape[:2]
                x, y = int(lm[8].x * w), int(lm[8].y * h)
                drawing = lm[8].y < lm[6].y and lm[12].y > lm[10].y      # only index finger up = pen down
                if drawing and last:
                    cv2.line(canvas, last, (x, y), (26, 122, 255), 8)
                last = (x, y) if drawing else None
                cv2.circle(frame, (x, y), 8, (26, 122, 255), -1)
            view = cv2.addWeighted(frame, 0.5, canvas, 1.0, 0)
            cv2.putText(view, "Index finger = draw | fist = lift | press G to let JARVIS guess, C = clear, Q = quit",
                        (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (26, 160, 255), 2)
            cv2.imshow("JARVIS Air Pictionary", view)
            k = cv2.waitKey(1) & 0xFF
            if k in (ord("q"), 27):
                break
            if k == ord("c"):
                canvas[:] = 0
            if k == ord("g") or _pict["guess"]:
                _pict["guess"] = False
                ok2, buf = cv2.imencode(".jpg", 255 - cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY))
                try:
                    g = H.ai_vision("This is a simple line drawing someone made in the air. What is it? "
                                    "Give your best guess in a few words, plus a second guess.", [buf.tobytes()])
                    H.say(f"[PICTIONARY] Say your guess playfully: {g}")
                except Exception:
                    pass
    finally:
        cap.release(); cv2.destroyAllWindows(); hands.close(); _pict["on"] = False


def fun_games(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    if act == "quiz_start":
        players = [x.strip() for x in str(p.get("players") or "Player 1").split(",") if x.strip()]
        topic = str(p.get("topic") or "general knowledge")
        n = max(3, min(int(float(p.get("rounds") or 3)), 8)) * len(players)
        qs = H.ai_json(f"Make {n} fun multiple-choice quiz questions about {topic} for school kids. ONLY JSON: "
                       '[{"q":"...","options":["..","..","..",".."],"answer":"A"}]') or []
        qs = [q for q in qs if isinstance(q, dict) and len(q.get("options", [])) == 4]
        if not qs:
            return "I couldn't make the quiz right now."
        _quiz.update(players=players, scores={x: 0 for x in players}, qs=qs, i=0, turn=0, topic=topic)
        _board()
        return f"[QUIZ SHOW] Welcome {', '.join(players)} enthusiastically to the {topic} quiz show! Then: " + _ask()
    if act == "quiz_answer":
        if not _quiz["qs"]:
            return "No quiz running."
        q = _quiz["qs"][_quiz["i"]]
        who = _quiz["players"][_quiz["turn"] % len(_quiz["players"])]
        a = str(p.get("answer") or "").strip().lower()
        right = "abcd".index(str(q["answer"]).strip()[:1].lower())
        ok = a[:1] == "abcd"[right] or q["options"][right].lower() in a
        if ok:
            _quiz["scores"][who] += 1
        _quiz["i"] += 1; _quiz["turn"] += 1; _board()
        verdict = f"{'Correct' if ok else 'Wrong'} — the answer is {q['options'][right]}."
        if _quiz["i"] >= len(_quiz["qs"]):
            win = max(_quiz["scores"].items(), key=lambda kv: kv[1])
            _quiz["qs"] = []
            return f"[QUIZ SHOW OVER] Say: {verdict} Final scores are on screen — {win[0]} wins with {win[1]}! Celebrate."
        return f"[QUIZ SHOW] Say: {verdict} Then: " + _ask()
    if act == "joke":
        return "[JOKE] " + H.ai_text("Tell one short, clean, genuinely funny joke for a teenager (puns welcome). Just the joke.")
    if act == "riddle":
        r = H.ai_json('Give one clever riddle for a teenager. ONLY JSON: {"riddle":"...","answer":"..."}') or {}
        _riddle["answer"] = r.get("answer", "")
        return f"[RIDDLE] Ask this riddle and let them guess (don't give the answer yet): {r.get('riddle')}"
    if act == "riddle_answer":
        return f"The answer was: {_riddle['answer'] or 'no riddle yet'}."
    if act == "rap_battle":
        topic = str(p.get("topic") or "who's the best AI")
        return (f"[RAP BATTLE] Start a friendly, clean rap battle with the user about '{topic}'. Rap ONE verse of "
                "4 rhyming lines, then challenge them to reply. Keep going verse by verse; rate their verses for "
                "rhyme and flow out of 10. Keep it fun — no insults about real people, no bad words.")
    if act == "poem_battle":
        topic = str(p.get("topic") or "the ocean")
        return f"[POEM BATTLE] Write a 4-line poem about '{topic}', then challenge the user to write one; compare kindly."
    if act == "pictionary":
        if _pict["on"]:
            return "Pictionary is already running — press G in its window for my guess."
        try:
            import mediapipe as mp; mp.solutions.hands
        except Exception:
            return "Air Pictionary needs MediaPipe (python -m pip install mediapipe)."
        _pict.update(on=True, stop=False, guess=False)
        threading.Thread(target=_pictionary, daemon=True).start()
        return "Air Pictionary started! Draw with just your index finger up, make a fist to lift the pen. Say 'guess' or press G when done."
    if act == "pictionary_guess":
        _pict["guess"] = True
        return "Looking at your drawing…"
    if act == "chess_coach":
        try:
            import pyautogui
            img = H.to_jpeg(pyautogui.screenshot(), 1600)
            tip = H.ai_vision("There is a chess game on this screen. Read the position carefully. Say whose move it "
                              "seems to be, the best move in plain words (e.g. 'knight from g1 to f3'), why, and one "
                              "thing to watch out for. If you can't see a board clearly, say so.", [img])
        except Exception as e:
            return f"I couldn't look at the board: {e}"
        H.show(player, "CHESS COACH", tip)
        return "[CHESS] Tell the user the suggested move and the reason in two sentences:\n" + tip[:900]
    return "Fun games: quiz_start, quiz_answer, joke, riddle, riddle_answer, rap_battle, poem_battle, pictionary, pictionary_guess, chess_coach."


TOOL = {
    "name": "fun_games",
    "description": ("Games and fun. Quiz show for friends: action='quiz_start' (players 'Rahul, Priya', topic, rounds) "
                    "then 'quiz_answer' (answer). 'joke'; 'riddle' then 'riddle_answer'; 'rap_battle' / 'poem_battle' "
                    "(topic). Air Pictionary with the webcam: 'pictionary', then 'pictionary_guess'. 'chess_coach' looks "
                    "at the chess board on screen and suggests a move."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "players": {"type": "STRING", "description": "Comma-separated player names."},
        "topic": {"type": "STRING", "description": "Quiz / battle topic."},
        "rounds": {"type": "NUMBER", "description": "Questions per player."},
        "answer": {"type": "STRING", "description": "Quiz answer."}},
        "required": ["action"]},
    "handler": fun_games,
}
