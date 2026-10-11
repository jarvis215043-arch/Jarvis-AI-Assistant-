"""
actions/study_mode.py — Study Mode: quizzes, flashcards and step-by-step
explanations, shown on the HUD. Remembers which topics you got wrong
(memory/study.json) so 'what should I revise?' has a real answer.
"""
import importlib.util
import json
import re
import sys
from datetime import datetime
from pathlib import Path

_quiz = {"topic": "", "questions": [], "i": 0, "score": 0, "wrong": []}


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _ai():
    key = "actions._ai_text"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, str(_base_dir() / "actions" / "_ai_text.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def _stats_file() -> Path:
    return _base_dir() / "memory" / "study.json"


def _stats() -> dict:
    try:
        d = json.loads(_stats_file().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_stats(d: dict) -> None:
    p = _stats_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def _show(player, title, text) -> None:
    if player and hasattr(player, "show_content"):
        try:
            player.show_content(title, text)
        except Exception:
            pass


def _question_text(q: dict, n: int, total: int) -> str:
    opts = "\n".join(f"  {chr(65 + k)}) {o}" for k, o in enumerate(q["options"]))
    return f"Question {n} of {total}:\n{q['q']}\n{opts}"


def _ask_current(player) -> str:
    q = _quiz["questions"][_quiz["i"]]
    text = _question_text(q, _quiz["i"] + 1, len(_quiz["questions"]))
    _show(player, f"QUIZ — {_quiz['topic']}", text + f"\n\nScore: {_quiz['score']}/{_quiz['i']}")
    return ("[QUIZ] Read this question and its options aloud, then wait for the user's answer and "
            "call study_mode with action='answer' and their answer:\n" + text)


def _start_quiz(topic: str, count: int, level: str, player) -> str:
    data = _ai().ask_json(
        f"Make a {count}-question multiple-choice quiz on: {topic}. Level: {level}. "
        "Each question has exactly 4 options and one correct answer. Return ONLY JSON: "
        '[{"q": "question", "options": ["..","..","..",".."], "answer": "A", '
        '"subtopic": "2-4 word subtopic", "explain": "one-sentence reason"}]')
    qs = [q for q in (data or []) if isinstance(q, dict) and len(q.get("options", [])) == 4
          and str(q.get("answer", "")).strip()[:1].upper() in "ABCD"]
    if not qs:
        return "I couldn't make that quiz right now — try again in a moment."
    _quiz.update(topic=topic, questions=qs[:count], i=0, score=0, wrong=[])
    return _ask_current(player)


def _match(answer: str, q: dict) -> int:
    """Which option (0-3) the user picked, or -1."""
    a = (answer or "").strip().lower()
    m = re.match(r"^\(?([abcd])\)?(\b|[.):]|$)", a) or re.search(r"\b(?:option|answer)\s*([abcd])\b", a)
    if m:
        return "abcd".index(m.group(1))
    for k, o in enumerate(q["options"]):
        if a and (a in o.lower() or o.lower() in a):
            return k
    return -1


def _answer(answer: str, player) -> str:
    if not _quiz["questions"]:
        return "There's no quiz running. Say 'quiz me on <topic>' to start one."
    q = _quiz["questions"][_quiz["i"]]
    picked = _match(answer, q)
    if picked < 0:
        return "[QUIZ] I couldn't tell which option that was. Ask the user to say A, B, C or D."
    right = "ABCD".index(str(q["answer"]).strip()[:1].upper())
    correct = picked == right
    if correct:
        _quiz["score"] += 1
        verdict = "Correct!"
    else:
        _quiz["wrong"].append(q.get("subtopic") or _quiz["topic"])
        verdict = f"Not quite — the answer is {'ABCD'[right]}) {q['options'][right]}."
    verdict += f" {q.get('explain', '')}"
    _quiz["i"] += 1

    if _quiz["i"] < len(_quiz["questions"]):
        return f"[QUIZ] Tell the user: {verdict} Then: " + _ask_current(player)

    total, score = len(_quiz["questions"]), _quiz["score"]
    stats = _stats()
    weak = stats.setdefault("weak_topics", {})
    for t in _quiz["wrong"]:
        weak[t] = weak.get(t, 0) + 1
    stats.setdefault("quizzes", []).append({"topic": _quiz["topic"], "score": score, "total": total,
                                            "date": datetime.now().strftime("%Y-%m-%d")})
    stats["quizzes"] = stats["quizzes"][-50:]
    _save_stats(stats)
    revise = ", ".join(sorted(set(_quiz["wrong"]))) or "nothing — perfect!"
    _show(player, f"QUIZ — {_quiz['topic']}", f"Finished!\nScore: {score}/{total}\nRevise: {revise}")
    _quiz["questions"] = []
    return (f"[QUIZ OVER] Tell the user: {verdict} The quiz is finished — they scored {score} out of "
            f"{total}. Topics to revise: {revise}. Be encouraging.")


def study_mode(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "quiz").strip().lower()
    topic = str(p.get("topic") or "").strip()
    level = str(p.get("level") or "school level").strip()
    try:
        count = max(3, min(int(float(p.get("count") or 5)), 15))
    except (TypeError, ValueError):
        count = 5

    if action == "answer":
        return _answer(str(p.get("answer") or ""), player)

    if action == "stop":
        if not _quiz["questions"]:
            return "No quiz is running."
        s, n = _quiz["score"], _quiz["i"]
        _quiz["questions"] = []
        return f"Quiz stopped. Score so far: {s} out of {n}."

    if action in ("review", "revise", "weak"):
        weak = _stats().get("weak_topics", {})
        if not weak:
            return "No weak topics recorded yet — take a quiz first."
        top = sorted(weak.items(), key=lambda kv: -kv[1])[:6]
        text = "\n".join(f"• {t}  (missed {n}×)" for t, n in top)
        _show(player, "TOPICS TO REVISE", text)
        return "Topics you've missed most: " + ", ".join(t for t, _ in top) + ". Want a quiz on the first one?"

    if not topic:
        return "Which topic? For example: 'quiz me on the nervous system'."

    if action == "quiz":
        return _start_quiz(topic, count, level, player)

    if action == "flashcards":
        data = _ai().ask_json(
            f"Make {count + 3} study flashcards on: {topic} ({level}). Return ONLY JSON: "
            '[{"front": "short question or term", "back": "short answer"}]')
        cards = [c for c in (data or []) if isinstance(c, dict) and c.get("front")]
        if not cards:
            return "I couldn't make flashcards right now — try again."
        text = "\n\n".join(f"{n}. {c['front']}\n   → {c.get('back', '')}" for n, c in enumerate(cards, 1))
        _show(player, f"FLASHCARDS — {topic}", text)
        return f"Made {len(cards)} flashcards on {topic}; they're on screen. First one: {cards[0]['front']}"

    if action == "explain":
        text = _ai().ask(
            f"Explain {topic} step by step for a student ({level}). Use 4-7 numbered steps, simple "
            "words, one everyday example, and end with a one-line summary. Plain text, no markdown.")
        if not text.strip():
            return "I couldn't write that explanation right now."
        _show(player, f"EXPLAINED — {topic}", text)
        return "[EXPLANATION] It's on screen. Say the key idea in 2-3 sentences:\n" + text[:1500]

    return "Study mode can: quiz, answer, flashcards, explain, review or stop."


TOOL = {
    "name": "study_mode",
    "description": (
        "Study Mode for schoolwork. action='quiz' with topic (and optional count, level) starts a "
        "multiple-choice quiz; after the user answers aloud call action='answer' with their answer; "
        "'flashcards' with topic; 'explain' with topic for a step-by-step explanation on screen; "
        "'review' lists the topics they get wrong most; 'stop' ends a quiz."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "'quiz' (default), 'answer', 'flashcards', 'explain', 'review' or 'stop'."},
            "topic":  {"type": "STRING", "description": "Subject or topic, e.g. 'the nervous system'."},
            "answer": {"type": "STRING", "description": "For action='answer': what the user said (e.g. 'B' or the option text)."},
            "count":  {"type": "NUMBER", "description": "Number of quiz questions (default 5, max 15)."},
            "level":  {"type": "STRING", "description": "e.g. 'class 8', 'beginner'. Default: school level."},
        },
        "required": [],
    },
    "handler": study_mode,
}
