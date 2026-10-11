"""actions/school_planner.py — Exam planner, school timetable, doubt log and word
of the day. Everything is saved on this PC (memory/school.json)."""
import random
import time
from datetime import date, datetime, timedelta

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
FILE = H.mem_path("school.json")
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _data():
    d = H.load_json(FILE, {})
    for k, v in (("exams", []), ("timetable", {}), ("doubts", []), ("words", [])):
        d.setdefault(k, v)
    return d


def _parse_date(text: str):
    t = (text or "").strip()
    for f in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %B %Y", "%d %b %Y", "%d %B", "%d %b", "%B %d"):
        try:
            d = datetime.strptime(t, f).date()
            if "%Y" not in f:
                d = d.replace(year=date.today().year)
                if d < date.today():
                    d = d.replace(year=d.year + 1)
            return d
        except ValueError:
            pass
    return None


def _word_today(d: dict) -> dict:
    today = H.today()
    if d["words"] and d["words"][-1].get("date") == today:
        return d["words"][-1]
    known = ", ".join(w["word"] for w in d["words"][-60:])
    w = H.ai_json("Pick one useful, interesting English word for a school student (age 11-15) to learn. "
                  f"Not any of: {known or 'none'}. Return ONLY JSON: "
                  '{"word": "...", "meaning": "simple meaning", "example": "a sentence using it"}') or {}
    if w.get("word"):
        w["date"] = today
        d["words"].append(w); d["words"] = d["words"][-120:]
        H.save_json(FILE, d)
    return w


def _watch_word() -> None:
    time.sleep(150)
    while True:
        d = _data()
        if d.get("word_alert", True) and datetime.now().hour >= 7 and d.get("word_said") != H.today():
            try:
                w = _word_today(d)
                if w.get("word"):
                    d = _data(); d["word_said"] = H.today(); H.save_json(FILE, d)
                    H.say(f"[WORD OF THE DAY] In one or two short sentences tell the user today's word: "
                          f"{w['word']} — {w['meaning']}. Example: {w['example']}")
            except Exception:
                pass
        time.sleep(1800)


H.on_ready(_watch_word)


def school_planner(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    d = _data()

    # ── exams ────────────────────────────────────────────────────────────────
    if act == "exam_add":
        sub, dt = str(p.get("subject") or "").strip(), _parse_date(str(p.get("date") or ""))
        if not sub or not dt:
            return "Tell me the subject and the date, like 'Science on 14 March'."
        d["exams"] = [e for e in d["exams"] if e["subject"].lower() != sub.lower()] + [{"subject": sub, "date": dt.isoformat()}]
        H.save_json(FILE, d)
        return f"Added {sub} on {dt:%d %B} — {(dt - date.today()).days} days to go."
    if act == "exam_remove":
        sub = str(p.get("subject") or "").lower()
        d["exams"] = [e for e in d["exams"] if e["subject"].lower() != sub]; H.save_json(FILE, d)
        return "Removed."
    if act in ("exam_list", "countdown"):
        up = sorted((e for e in d["exams"] if e["date"] >= H.today()), key=lambda e: e["date"])
        if not up:
            return "No upcoming exams saved. Say 'Maths exam on 12 March' to add one."
        rows = [f"{e['subject']:<16} {date.fromisoformat(e['date']):%a %d %b}   in {(date.fromisoformat(e['date']) - date.today()).days} days" for e in up]
        H.show(player, "EXAM COUNTDOWN", "\n".join(rows))
        return "Upcoming exams: " + "; ".join(rows[:5])
    if act == "exam_plan":
        up = sorted((e for e in d["exams"] if e["date"] >= H.today()), key=lambda e: e["date"])
        if not up:
            return "Add your exams first, then I'll make the plan."
        hours = p.get("hours_per_day") or 2
        plan = H.ai_text(f"Today is {date.today():%A %d %B %Y}. A school student has these exams: "
                         + "; ".join(f"{e['subject']} on {e['date']}" for e in up)
                         + f". They can study about {hours} hours a day. Make a day-by-day revision timetable "
                         "from today until the last exam: more time for nearer exams, a short review the day "
                         "before each exam, one lighter day a week, breaks. Plain text, one line per day.")
        out = H.documents_dir() / "Revision plan.txt"
        out.write_text(plan, encoding="utf-8")
        H.show(player, "REVISION PLAN", plan)
        return f"[PLAN] Your revision plan is on screen and saved as Documents, JARVIS, Revision plan. Summarise the next 2 days in one sentence:\n{plan[:800]}"

    # ── timetable ────────────────────────────────────────────────────────────
    if act == "timetable_set":
        day = str(p.get("day") or "").lower()
        if day not in DAYS:
            return "Which day? (Monday to Sunday)"
        periods = []
        for part in str(p.get("periods") or "").split(","):
            bits = part.strip().split(" ", 1)
            if len(bits) == 2 and ":" in bits[0]:
                periods.append([bits[0].zfill(5), bits[1].strip()])
        if not periods:
            return "Tell me the periods like: 8:00 Maths, 8:45 English, 9:30 Science."
        d["timetable"][day] = sorted(periods); H.save_json(FILE, d)
        return f"Saved {day.title()}: " + ", ".join(f"{t} {s}" for t, s in d["timetable"][day])
    if act in ("next_class", "today"):
        today = DAYS[date.today().weekday()]
        periods = d["timetable"].get(today, [])
        if not periods:
            return f"No timetable saved for {today.title()}."
        now = datetime.now().strftime("%H:%M")
        if act == "today":
            return f"{today.title()}: " + ", ".join(f"{t} {s}" for t, s in periods)
        nxt = next(((t, s) for t, s in periods if t > now), None)
        return f"Next: {nxt[1]} at {nxt[0]}." if nxt else "No more classes today."
    if act == "pack":
        tm = DAYS[(date.today().weekday() + 1) % 7]
        subs = sorted({s for _, s in d["timetable"].get(tm, [])})
        return f"Tomorrow ({tm.title()}) you have: {', '.join(subs)}. Pack those books." if subs else f"No timetable saved for {tm.title()}."

    # ── doubts ───────────────────────────────────────────────────────────────
    if act == "doubt_add":
        q = str(p.get("text") or "").strip()
        if not q:
            return "What's the doubt?"
        d["doubts"].append({"text": q, "subject": p.get("subject", ""), "date": H.today(), "done": False}); H.save_json(FILE, d)
        return f"Saved your doubt. You have {sum(not x['done'] for x in d['doubts'])} to ask."
    if act == "doubt_list":
        open_ = [x for x in d["doubts"] if not x["done"]]
        if not open_:
            return "No doubts saved."
        H.show(player, "DOUBTS TO ASK", "\n".join(f"{i}. [{x.get('subject') or '-'}] {x['text']}" for i, x in enumerate(open_, 1)))
        return f"{len(open_)} doubts to ask; they're on screen."
    if act == "doubt_done":
        open_ = [x for x in d["doubts"] if not x["done"]]
        try:
            open_[int(float(p.get("number") or 1)) - 1]["done"] = True
        except Exception:
            return "Which number?"
        H.save_json(FILE, d)
        return "Marked as asked."

    # ── word of the day ──────────────────────────────────────────────────────
    if act == "word":
        w = _word_today(d)
        return f"Today's word: {w.get('word')} — {w.get('meaning')}. Example: {w.get('example')}" if w.get("word") else "I couldn't get a word right now."
    if act == "word_quiz":
        words = d["words"][-7:]
        if len(words) < 2:
            return "Not enough words yet — come back after a few days of words."
        w = random.choice(words)
        others = [x["meaning"] for x in words if x is not w][:3]
        opts = others + [w["meaning"]]; random.shuffle(opts)
        return (f"[WORD QUIZ] Ask the user: what does '{w['word']}' mean? Read these options: "
                + " | ".join(f"{chr(65 + i)}) {o}" for i, o in enumerate(opts))
                + f". The correct answer is {chr(65 + opts.index(w['meaning']))}. Tell them if they're right.")
    if act in ("word_on", "word_off"):
        d["word_alert"] = act == "word_on"; H.save_json(FILE, d)
        return f"Word of the day announcements {'on' if act == 'word_on' else 'off'}."
    return "School planner: exam_add, exam_list, exam_plan, exam_remove, timetable_set, next_class, today, pack, doubt_add, doubt_list, doubt_done, word, word_quiz."


TOOL = {
    "name": "school_planner",
    "description": ("School organiser. Exams: action='exam_add' (subject, date), 'exam_list' (countdown), "
                    "'exam_plan' (revision timetable, optional hours_per_day), 'exam_remove'. Timetable: "
                    "'timetable_set' (day, periods like '8:00 Maths, 8:45 English'), 'next_class', 'today', "
                    "'pack' (what to pack for tomorrow). Doubts to ask the teacher: 'doubt_add' (text, subject), "
                    "'doubt_list', 'doubt_done' (number). Word of the day: 'word', 'word_quiz', 'word_on'/'word_off'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "subject": {"type": "STRING", "description": "Subject name."},
        "date": {"type": "STRING", "description": "Exam date, e.g. '14 March'."},
        "day": {"type": "STRING", "description": "Weekday for timetable_set."},
        "periods": {"type": "STRING", "description": "e.g. '8:00 Maths, 8:45 English'."},
        "text": {"type": "STRING", "description": "The doubt."},
        "number": {"type": "NUMBER", "description": "Doubt number."},
        "hours_per_day": {"type": "NUMBER", "description": "Study hours per day for the plan."}},
        "required": ["action"]},
    "handler": school_planner,
}
