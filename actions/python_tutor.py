"""actions/python_tutor.py — Short Python lessons with an exercise each. You
write the answer in Documents/JARVIS/Python/lesson_N.py and JARVIS runs and
checks it. Progress is saved."""
import subprocess
import sys

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
LESSONS = ["print and variables", "input and simple maths", "if / elif / else", "for loops and range",
           "while loops", "lists", "functions", "strings and f-strings", "dictionaries",
           "a mini project: number guessing game"]
FILE = H.mem_path("python_tutor.json")


def _folder():
    return H.documents_dir("Python")


def python_tutor(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "lesson").lower()
    st = H.load_json(FILE, {"done": [], "current": 1})
    if action == "progress":
        done = sorted(set(st["done"]))
        H.show(player, "PYTHON PROGRESS", "\n".join(f"{'✓' if i in done else '○'} {i}. {t}" for i, t in enumerate(LESSONS, 1)))
        return f"You've finished {len(done)} of {len(LESSONS)} lessons."
    try:
        n = int(float(p.get("number") or st.get("current", 1)))
    except (TypeError, ValueError):
        n = st.get("current", 1)
    n = max(1, min(n, len(LESSONS)))
    path = _folder() / f"lesson_{n}.py"
    if action == "lesson":
        text = H.ai_text(f"Teach Python lesson {n}: '{LESSONS[n - 1]}' to a beginner school student. Plain "
                         "text, no markdown: a 6-10 line explanation, one short example program, then one "
                         "EXERCISE with exact expected output. Keep it fun.")
        if not path.exists():
            path.write_text(f"# Lesson {n}: {LESSONS[n - 1]}\n# Write your answer below, save, then say 'check my Python'.\n\n", encoding="utf-8")
        st["current"] = n; H.save_json(FILE, st)
        H.show(player, f"PYTHON LESSON {n} — {LESSONS[n - 1]}", text + f"\n\nWrite your answer in:\n{path}")
        return (f"[PYTHON LESSON {n}] It's on screen. Explain the main idea in 2-3 sentences and read the exercise. "
                f"Tell them to write the answer in Documents, JARVIS, Python, lesson_{n}.py, then say 'check my Python'.")
    if action == "check":
        if not path.exists() or len(path.read_text(encoding="utf-8").strip().splitlines()) < 3:
            return f"Write your answer in {path} first."
        code = path.read_text(encoding="utf-8")
        try:
            r = subprocess.run([sys.executable if not getattr(sys, "frozen", False) else "python", str(path)],
                               capture_output=True, text=True, timeout=10, input="5\n3\n")
            out = (r.stdout + r.stderr)[-1500:]
        except Exception as e:
            out = f"(couldn't run it: {e})"
        verdict = H.ai_text(f"A beginner wrote this for the exercise of lesson '{LESSONS[n - 1]}'.\nCODE:\n{code}\n"
                            f"OUTPUT WHEN RUN:\n{out}\nStart with PASS or TRY AGAIN. Then 2-4 kind sentences: what's "
                            "good, and if needed one hint (don't write the full solution).")
        if verdict.upper().startswith("PASS") and n not in st["done"]:
            st["done"].append(n); st["current"] = min(n + 1, len(LESSONS)); H.save_json(FILE, st)
        H.show(player, f"PYTHON CHECK — lesson {n}", f"Output:\n{out}\n\n{verdict}")
        return "[PYTHON CHECK] Tell the student kindly: " + verdict[:800]
    return "Python tutor can: lesson, check or progress."


TOOL = {
    "name": "python_tutor",
    "description": ("Python lessons for beginners (10 lessons). action='lesson' (current, or number); "
                    "'check' runs and checks the student's answer file; 'progress'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'lesson', 'check' or 'progress'."},
        "number": {"type": "NUMBER", "description": "Lesson number 1-10."}}, "required": []},
    "handler": python_tutor,
}
