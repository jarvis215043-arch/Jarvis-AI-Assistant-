"""actions/learning_tools.py — Maths drill, essay coach, maths step checker,
smart flashcards (spaced repetition), reading buddy and science visualiser."""
import os
import random
import sys
import time
import webbrowser
from datetime import date, timedelta
from pathlib import Path

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
SRS = H.mem_path("flashcards_srs.json")
_drill = {"qs": [], "i": 0, "score": 0, "t0": 0.0, "kind": ""}
_read = {"chunks": [], "i": 0, "title": ""}
BOX_DAYS = [0, 1, 3, 7, 14, 30]     # Leitner boxes: when a card comes back


def _helper_mod(name):
    import importlib.util
    key = f"actions.{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, str(H.base_dir() / "actions" / f"{name}.py"))
    mod = importlib.util.module_from_spec(spec); sys.modules[key] = mod; spec.loader.exec_module(mod)
    return mod


def _text_source(p, player) -> str:
    t = str(p.get("text") or "").strip()
    if t:
        return t
    f = str(p.get("path") or getattr(player, "current_file", "") or "")
    if f and Path(f).exists():
        return _file_text(Path(f))
    try:
        import pyperclip
        return pyperclip.paste()
    except Exception:
        return ""


def _file_text(f: Path) -> str:
    if f.suffix.lower() == ".pdf":
        try:
            from PyPDF2 import PdfReader
            return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(f)).pages)
        except Exception:
            return ""
    if f.suffix.lower() == ".docx":
        from docx import Document
        return "\n".join(x.text for x in Document(str(f)).paragraphs)
    return f.read_text(encoding="utf-8", errors="replace")


def _drill_q():
    q = _drill["qs"][_drill["i"]]
    return f"[DRILL] Question {_drill['i'] + 1} of {len(_drill['qs'])}: ask the user '{q[0]}' and wait; then call learning_tools action='drill_answer' with their answer."


def learning_tools(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()

    # ── maths drill ──────────────────────────────────────────────────────────
    if act == "drill_start":
        kind = str(p.get("kind") or "tables").lower()
        n = max(5, min(int(float(p.get("count") or 10)), 30))
        qs = []
        for _ in range(n):
            if kind == "tables":
                a, b = random.randint(2, 15), random.randint(2, 12); qs.append((f"{a} times {b}", a * b))
            else:
                op = random.choice("+-×÷"); a, b = random.randint(12, 99), random.randint(2, 30)
                if op == "+": qs.append((f"{a} plus {b}", a + b))
                elif op == "-": qs.append((f"{a + b} minus {b}", a))
                elif op == "×": qs.append((f"{a} times {b % 12 + 2}", a * (b % 12 + 2)))
                else: c = b % 11 + 2; qs.append((f"{a * c} divided by {c}", a))
        _drill.update(qs=qs, i=0, score=0, t0=time.monotonic(), kind=kind)
        return "Drill started — answer as fast as you can! " + _drill_q()
    if act == "drill_answer":
        if not _drill["qs"]:
            return "No drill running."
        try:
            ans = int(float(str(p.get("answer") or "").strip()))
        except ValueError:
            return "[DRILL] Ask them to say just the number."
        q, right = _drill["qs"][_drill["i"]]
        ok = ans == right
        _drill["score"] += ok; _drill["i"] += 1
        msg = "Correct!" if ok else f"No — it's {right}."
        if _drill["i"] < len(_drill["qs"]):
            return f"[DRILL] Say '{msg}' then: " + _drill_q()
        secs = int(time.monotonic() - _drill["t0"]); n = len(_drill["qs"]); s = _drill["score"]
        hs = H.load_json(H.mem_path("drill_scores.json"), {})
        best = hs.get(_drill["kind"])
        new_best = best is None or (s, -secs) > (best["score"], -best["secs"])
        if new_best:
            hs[_drill["kind"]] = {"score": s, "secs": secs, "date": H.today()}; H.save_json(H.mem_path("drill_scores.json"), hs)
        _drill["qs"] = []
        return f"[DRILL OVER] Say: {msg} Done — {s} out of {n} in {secs} seconds.{' NEW HIGH SCORE!' if new_best else ''}"

    # ── essay coach (feedback only, never rewrites) ─────────────────────────
    if act == "essay_feedback":
        txt = _text_source(p, player)
        if len(txt.split()) < 40:
            return "Give me the essay: drop the file on the HUD, copy it to the clipboard, or paste it."
        fb = H.ai_text("You are a kind English teacher. Give feedback on this school essay WITHOUT rewriting it: "
                       "scores out of 10 for ideas, structure, language and grammar; 3 things done well; 3 specific "
                       "improvements with the line they refer to; spelling/grammar mistakes as 'wrong → right'. "
                       "Plain text.\n\nESSAY:\n" + txt[:12000])
        H.show(player, "ESSAY FEEDBACK", fb)
        return "[ESSAY] Feedback is on screen. Tell the user the overall scores and the top improvement in 2 sentences:\n" + fb[:1200]

    # ── maths step checker ───────────────────────────────────────────────────
    if act == "check_working":
        typed = str(p.get("text") or "").strip()
        prompt = ("Check this student's maths working line by line. For each line say ✓ or ✗; at the FIRST "
                  "mistake explain what went wrong and give a hint for fixing it (don't just give the final "
                  "answer). Plain text.")
        try:
            if typed:
                out = H.ai_text(prompt + "\n\nWORKING:\n" + typed)
            else:
                hh = _helper_mod("homework_helper")
                img = hh._screen_jpeg() if str(p.get("source") or "camera") == "screen" else hh._webcam_jpeg()
                out = H.ai_vision(prompt, [img])
        except Exception as e:
            return f"I couldn't check it: {e}"
        H.show(player, "MATHS CHECK", out)
        return "[CHECK] On screen. Tell the student where the first mistake is, kindly, in 2 sentences:\n" + out[:1200]

    # ── smart flashcards (spaced repetition) ─────────────────────────────────
    cards = H.load_json(SRS, [])
    if act == "card_add":
        f, b = str(p.get("front") or "").strip(), str(p.get("back") or "").strip()
        if not f or not b:
            return "Give me the front (question) and back (answer)."
        cards.append({"front": f, "back": b, "deck": p.get("deck") or "general", "box": 0, "due": H.today()}); H.save_json(SRS, cards)
        return f"Card added. {len(cards)} cards in total."
    if act == "cards_make":
        topic = str(p.get("deck") or p.get("text") or "").strip()
        if not topic:
            return "Which topic should I make cards for?"
        new = H.ai_json(f"Make 10 short study flashcards about {topic} for a school student. ONLY JSON: "
                        '[{"front": "...", "back": "..."}]') or []
        for c in new:
            if c.get("front"):
                cards.append({"front": c["front"], "back": c.get("back", ""), "deck": topic, "box": 0, "due": H.today()})
        H.save_json(SRS, cards)
        return f"Made {len(new)} cards about {topic}. Say 'review my flashcards' to start."
    if act == "cards_review":
        due = [c for c in cards if c["due"] <= H.today()]
        if not due:
            nxt = min((c["due"] for c in cards), default=None)
            return f"Nothing due today! Next review: {nxt}." if nxt else "No flashcards yet."
        c = due[0]
        return (f"[FLASHCARD] {len(due)} due. Ask: '{c['front']}'. After the user answers, tell them the answer "
                f"('{c['back']}') and call learning_tools action='card_result' with correct=true/false.")
    if act == "card_result":
        due = [c for c in cards if c["due"] <= H.today()]
        if not due:
            return "No card is waiting."
        c = due[0]
        ok = str(p.get("correct")).lower() in ("true", "1", "yes")
        c["box"] = min(c["box"] + 1, len(BOX_DAYS) - 1) if ok else 0
        c["due"] = (date.today() + timedelta(days=max(1, BOX_DAYS[c["box"]]) if ok else 0)).isoformat()
        if not ok:
            c["due"] = (date.today() + timedelta(days=1)).isoformat()
        H.save_json(SRS, cards)
        left = len([x for x in cards if x["due"] <= H.today()])
        return f"[FLASHCARD] {'Next card.' if left else 'All done for today!'} " + (learning_tools({"action": "cards_review"}, player) if left else "")

    # ── reading buddy ────────────────────────────────────────────────────────
    if act == "read_start":
        f = str(p.get("path") or getattr(player, "current_file", "") or "")
        if not f or not Path(f).exists():
            return "Drop the PDF or document onto the HUD first, then ask me to read it."
        text = _file_text(Path(f))
        if len(text) < 100:
            return "I couldn't get readable text from that file."
        paras, chunk, chunks = text.split("\n"), "", []
        for para in paras:
            chunk += para + "\n"
            if len(chunk) > 1100:
                chunks.append(chunk); chunk = ""
        if chunk.strip():
            chunks.append(chunk)
        _read.update(chunks=chunks, i=0, title=Path(f).name)
        act = "read_next"
    if act == "read_next":
        if not _read["chunks"]:
            return "Nothing to read — drop a file and say 'read this to me'."
        if _read["i"] >= len(_read["chunks"]):
            return "[READING] That's the end. Ask the user 2 questions about the whole text, then praise them."
        part = _read["chunks"][_read["i"]]; _read["i"] += 1
        return (f"[READING {_read['i']}/{len(_read['chunks'])}] Read this part aloud clearly, then ask ONE short "
                f"question about it and wait. When they're ready say 'next' to continue:\n{part}")

    # ── science visualiser (opens an interactive page) ───────────────────────
    if act == "visualise":
        topic = str(p.get("text") or "").strip()
        if not topic:
            return "What should I visualise? e.g. 'planets orbiting the sun', 'a pendulum', 'a simple circuit'."
        html = H.ai_text("Write ONE self-contained HTML file (inline CSS and JS, no external links) with an "
                         f"interactive, animated canvas simulation that teaches: {topic}. Dark background, orange "
                         "accents, sliders to change the key values, short labels explaining what's happening. "
                         "Return ONLY the HTML.")
        html = html.replace("```html", "").replace("```", "").strip()
        out = H.documents_dir("Science") / ("".join(ch for ch in topic if ch.isalnum() or ch == " ")[:40] + ".html")
        out.write_text(html, encoding="utf-8")
        webbrowser.open(out.as_uri())
        return f"Opened an interactive simulation of {topic} in your browser (saved in Documents, JARVIS, Science)."
    return "Learning tools: drill_start, drill_answer, essay_feedback, check_working, card_add, cards_make, cards_review, card_result, read_start, read_next, visualise."


TOOL = {
    "name": "learning_tools",
    "description": ("Study helpers. Maths drill: action='drill_start' (kind 'tables' or 'mental', count) then "
                    "'drill_answer' (answer). Essay feedback (no rewriting): 'essay_feedback' (text, or uploaded "
                    "file, or clipboard). Check maths working step by step: 'check_working' (text, or source "
                    "'camera'/'screen'). Spaced-repetition flashcards: 'card_add' (front, back, deck), 'cards_make' "
                    "(deck = topic), 'cards_review', 'card_result' (correct). Reading buddy for an uploaded "
                    "PDF/document: 'read_start', 'read_next'. Interactive science simulation in the browser: "
                    "'visualise' (text = topic)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "kind": {"type": "STRING", "description": "Drill kind: 'tables' or 'mental'."},
        "count": {"type": "NUMBER", "description": "Number of drill questions."},
        "answer": {"type": "STRING", "description": "The user's drill answer."},
        "text": {"type": "STRING", "description": "Essay text, maths working, or topic."},
        "path": {"type": "STRING", "description": "File path (optional)."},
        "source": {"type": "STRING", "description": "'camera' or 'screen'."},
        "front": {"type": "STRING", "description": "Flashcard question."},
        "back": {"type": "STRING", "description": "Flashcard answer."},
        "deck": {"type": "STRING", "description": "Deck / topic."},
        "correct": {"type": "BOOLEAN", "description": "Whether the flashcard answer was right."}},
        "required": ["action"]},
    "handler": learning_tools,
}
