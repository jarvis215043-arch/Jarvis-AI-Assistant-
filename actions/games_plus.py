"""actions/games_plus.py — Voice games: tic-tac-toe (JARVIS never loses),
hangman, number guessing, rock-paper-scissors, 20 questions, would-you-rather,
word chain and a daily trivia streak. Game logic runs locally."""
import random

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
STREAK = H.mem_path("trivia_streak.json")
WORDS = ["galaxy", "volcano", "penguin", "robotics", "satellite", "chemistry", "pyramid", "keyboard", "dinosaur",
         "hurricane", "telescope", "algorithm", "orchestra", "microscope", "rainforest", "electricity", "astronaut"]
_g = {"ttt": None, "hang": None, "num": None, "rps": [0, 0, 0], "chain": None, "trivia": None}
LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def _win(b):
    for a, c, d in LINES:
        if b[a] != " " and b[a] == b[c] == b[d]:
            return b[a]
    return "draw" if " " not in b else None


def _minimax(b, me):
    w = _win(b)
    if w == "O": return 1, None
    if w == "X": return -1, None
    if w == "draw": return 0, None
    best = (-2, None) if me == "O" else (2, None)
    for i in range(9):
        if b[i] == " ":
            b[i] = me
            s, _ = _minimax(b, "X" if me == "O" else "O")
            b[i] = " "
            if (me == "O" and s > best[0]) or (me == "X" and s < best[0]):
                best = (s, i)
    return best


def _board(b):
    c = [b[i] if b[i] != " " else str(i + 1) for i in range(9)]
    return f" {c[0]} | {c[1]} | {c[2]}\n---+---+---\n {c[3]} | {c[4]} | {c[5]}\n---+---+---\n {c[6]} | {c[7]} | {c[8]}"


def games_plus(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    move = str(p.get("move") or "").strip().lower()
    # ── tic-tac-toe ──
    if act == "tictactoe":
        _g["ttt"] = [" "] * 9
        H.show(player, "TIC-TAC-TOE (you are X)", _board(_g["ttt"]))
        return "[GAME] Tic-tac-toe started — the user is X and goes first. Ask them for a square 1 to 9 (board on screen)."
    if act == "ttt_move":
        b = _g["ttt"]
        if not b:
            return "No game running — say 'play tic-tac-toe'."
        try:
            i = int(move) - 1
            assert 0 <= i < 9 and b[i] == " "
        except Exception:
            return "[GAME] That square isn't free — ask for another number 1 to 9."
        b[i] = "X"
        w = _win(b)
        if not w:
            _, j = _minimax(b, "O"); b[j] = "O"; w = _win(b)
        H.show(player, "TIC-TAC-TOE (you are X)", _board(b))
        if w:
            _g["ttt"] = None
            return {"X": "[GAME] They WON — congratulate them!", "O": "[GAME] JARVIS won — be a good sport, offer a rematch.",
                    "draw": "[GAME] It's a draw — offer a rematch."}[w]
        return f"[GAME] JARVIS took square {j + 1}. Ask for their next square."
    # ── hangman ──
    if act == "hangman":
        topic = str(p.get("topic") or "").strip()
        word = (H.ai_fast(f"Give ONE single common English word (6-10 letters, no spaces) related to {topic}. Just the word.").strip().lower()
                if topic else random.choice(WORDS))
        word = "".join(ch for ch in word if ch.isalpha()) or random.choice(WORDS)
        _g["hang"] = {"word": word, "guessed": set(), "lives": 6}
        shown = " ".join("_" for _ in word)
        H.show(player, "HANGMAN", f"{shown}\n\nLives: 6")
        return f"[GAME] Hangman started: a {len(word)}-letter word{' about ' + topic if topic else ''}, 6 lives. Ask for a letter."
    if act == "hang_guess":
        h = _g["hang"]
        if not h:
            return "No hangman game — say 'play hangman'."
        ch = move[:1]
        if not ch.isalpha():
            return "[GAME] Ask for a single letter."
        if ch in h["guessed"]:
            return f"[GAME] '{ch}' was already guessed."
        h["guessed"].add(ch)
        if ch not in h["word"]:
            h["lives"] -= 1
        shown = " ".join(c if c in h["guessed"] else "_" for c in h["word"])
        H.show(player, "HANGMAN", f"{shown}\n\nLives: {h['lives']}   Tried: {' '.join(sorted(h['guessed']))}")
        if "_" not in shown:
            _g["hang"] = None; return f"[GAME] They got it: {h['word'].upper()}! Celebrate."
        if h["lives"] <= 0:
            _g["hang"] = None; return f"[GAME] Out of lives — the word was {h['word'].upper()}. Offer another round."
        return f"[GAME] {'Yes' if ch in h['word'] else 'No'} — {shown.replace(' ', '')} with {h['lives']} lives left. Ask for the next letter."
    # ── number guessing ──
    if act == "number":
        hi = int(float(p.get("move") or 100)) if move.isdigit() else 100
        _g["num"] = {"n": random.randint(1, hi), "tries": 0, "hi": hi}
        return f"[GAME] I'm thinking of a number from 1 to {hi}. Ask them to guess."
    if act == "num_guess":
        g = _g["num"]
        if not g:
            return "No game — say 'number guessing game'."
        try:
            x = int(float(move))
        except ValueError:
            return "[GAME] Ask for a number."
        g["tries"] += 1
        if x == g["n"]:
            _g["num"] = None; return f"[GAME] Correct! It was {x}, found in {g['tries']} tries."
        return f"[GAME] {'Higher' if x < g['n'] else 'Lower'}! (try {g['tries']})"
    # ── rock paper scissors ──
    if act == "rps":
        opts = ["rock", "paper", "scissors"]
        me = next((o for o in opts if o in move), None)
        if not me:
            return "[GAME] Rock, paper or scissors?"
        ai = random.choice(opts)
        r = 0 if me == ai else (1 if (opts.index(me) - opts.index(ai)) % 3 == 1 else 2)
        _g["rps"][r] += 1
        res = ["Draw", "You win", "I win"][r]
        return f"I chose {ai}. {res}! Score — you {_g['rps'][1]}, me {_g['rps'][2]}, draws {_g['rps'][0]}."
    # ── conversation games ──
    if act == "twenty_questions":
        return ("[GAME] 20 Questions: the user thinks of something; YOU ask up to 20 yes/no questions, one at a time, counting "
                "them, and try to guess it. Be playful. Start by asking them to think of something and say 'ready'.")
    if act == "would_you_rather":
        q = H.ai_fast("One fun, kid-friendly 'Would you rather' question with two creative options. Just the question.")
        return f"[GAME] Ask: {q} Then react to their answer and say what you'd pick."
    if act == "word_chain":
        _g["chain"] = {"used": set(), "last": ""}
        w = random.choice(WORDS); _g["chain"]["used"].add(w); _g["chain"]["last"] = w
        return f"[GAME] Word chain: each word must start with the last letter of the previous one, no repeats. JARVIS starts: '{w}'. Their word must start with '{w[-1]}'."
    if act == "chain_word":
        c = _g["chain"]
        if not c:
            return "No word chain game — say 'play word chain'."
        w = "".join(ch for ch in move if ch.isalpha())
        if not w:
            return "[GAME] Say a word."
        if w[0] != c["last"][-1]:
            _g["chain"] = None; return f"[GAME] Oops — '{w}' doesn't start with '{c['last'][-1]}'. Game over! Offer a rematch."
        if w in c["used"]:
            _g["chain"] = None; return f"[GAME] '{w}' was already used — game over! Offer a rematch."
        c["used"].add(w)
        reply = H.ai_fast(f"Give one common English noun starting with '{w[-1]}', not any of: {', '.join(c['used'])}. Just the word.").strip().lower()
        reply = "".join(ch for ch in reply if ch.isalpha())
        c["used"].add(reply); c["last"] = reply or w
        return f"[GAME] Good! JARVIS says '{reply}'. Their next word must start with '{(reply or w)[-1]}'."
    # ── daily trivia streak ──
    if act == "trivia":
        q = H.ai_fast_json('One interesting general-knowledge trivia question for a teenager. ONLY JSON: {"q":"...","options":["..","..","..",".."],"answer":"A"}') or {}
        if not q.get("options"):
            return "I couldn't get a question right now."
        _g["trivia"] = q
        s = H.load_json(STREAK, {"streak": 0, "best": 0})
        return (f"[TRIVIA] Current streak: {s['streak']}. Ask: {q['q']} Options: "
                + " | ".join(f"{chr(65 + i)}) {o}" for i, o in enumerate(q["options"])) + ". Then call games_plus action='trivia_answer'.")
    if act == "trivia_answer":
        q = _g["trivia"]
        if not q:
            return "No trivia question — say 'daily trivia'."
        right = "ABCD".index(str(q["answer"]).strip()[:1].upper())
        ok = move[:1].upper() == "ABCD"[right] or q["options"][right].lower() in move
        s = H.load_json(STREAK, {"streak": 0, "best": 0})
        s["streak"] = s["streak"] + 1 if ok else 0; s["best"] = max(s["best"], s["streak"]); H.save_json(STREAK, s)
        _g["trivia"] = None
        return f"[TRIVIA] {'Correct!' if ok else 'Not quite — it was ' + q['options'][right] + '.'} Streak: {s['streak']} (best {s['best']})."
    return "Games: tictactoe, ttt_move, hangman, hang_guess, number, num_guess, rps, twenty_questions, would_you_rather, word_chain, chain_word, trivia, trivia_answer."


TOOL = {
    "name": "games_plus",
    "description": ("Voice games. Start: action='tictactoe','hangman' (optional topic),'number','word_chain','trivia',"
                    "'twenty_questions','would_you_rather'. Moves (move = the user's answer): 'ttt_move' (square 1-9),"
                    "'hang_guess' (letter),'num_guess' (number),'chain_word' (word),'trivia_answer' (A-D),'rps' (rock/paper/scissors)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "move": {"type": "STRING", "description": "The user's move / guess / answer."},
        "topic": {"type": "STRING", "description": "Hangman topic."}}, "required": ["action"]},
    "handler": games_plus,
}
