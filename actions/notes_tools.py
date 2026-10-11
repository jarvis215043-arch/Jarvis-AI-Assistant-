"""actions/notes_tools.py — Voice memos (recorded, written out, searchable), an
email digest, and a private journal kept only on this PC."""
import threading
import time
import wave
from datetime import datetime

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
MEMOS = H.mem_path("memos.json")
JOURNAL_DIR = H.mem_path("journal/x").parent
_rec = {"on": False, "stop": False}


def _record(path: str, seconds: int) -> None:
    import numpy as np
    import sounddevice as sd
    frames = []
    with sd.InputStream(samplerate=16000, channels=1, dtype="int16", callback=lambda d, n, t, s: frames.append(d.copy())):
        t0 = time.monotonic()
        while not _rec["stop"] and time.monotonic() - t0 < seconds:
            time.sleep(0.1)
    audio = np.concatenate(frames) if frames else np.zeros((1, 1), "int16")
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(audio.tobytes())
    _rec["on"] = False
    try:
        text = H.ai_file("Write out exactly what is said in this voice memo. Only the words.", path)
    except Exception as e:
        text = f"(couldn't transcribe: {e})"
    memos = H.load_json(MEMOS, [])
    memos.append({"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "text": text, "audio": path})
    H.save_json(MEMOS, memos)
    H.say(f"[MEMO SAVED] Tell the user in one sentence that the memo is saved: \"{text[:120]}\"")


def notes_tools(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    if act == "memo_record":
        if _rec["on"]:
            return "Already recording — say 'stop the memo'."
        secs = max(5, min(int(float(p.get("seconds") or 60)), 600))
        path = str(H.documents_dir("Memos") / f"memo {datetime.now():%Y-%m-%d %H-%M-%S}.wav")
        _rec.update(on=True, stop=False)
        threading.Thread(target=_record, args=(path, secs), daemon=True).start()
        return f"Recording your memo now (up to {secs} seconds). Say 'stop the memo' when you're done."
    if act == "memo_stop":
        if not _rec["on"]:
            return "I'm not recording."
        _rec["stop"] = True
        return "Stopped — writing it out now."
    if act in ("memo_list", "memo_search"):
        memos = H.load_json(MEMOS, [])
        q = str(p.get("query") or "").lower()
        hits = [m for m in memos if q in m["text"].lower()] if q else memos[-15:]
        if not hits:
            return "No memos found."
        H.show(player, "VOICE MEMOS", "\n\n".join(f"{m['time']}\n{m['text']}" for m in hits[-15:]))
        return f"{len(hits)} memo(s) on screen. Latest: {hits[-1]['text'][:150]}"
    if act == "email_digest":
        try:
            from core import tool_bus
            raw = tool_bus.run_tool("gmail", {"action": "list", "max_results": 15}, timeout=60)
        except Exception as e:
            return f"I couldn't read your email: {e}"
        if "unread" not in raw.lower() and len(raw) < 40:
            return raw
        dig = H.ai_text("Summarise this inbox list for the user in a short digest: group by importance "
                        "(needs a reply / FYI / promotions), one line each, plain text.\n\n" + raw[:8000])
        H.show(player, "EMAIL DIGEST", dig)
        return "[DIGEST] On screen. Tell the user the most important 1-2 emails in two sentences:\n" + dig[:1000]
    if act == "journal_write":
        text = str(p.get("text") or "").strip()
        if not text:
            q = H.ai_text("Give one gentle, thoughtful journal prompt for a teenager's evening reflection. One sentence only.")
            return f"[JOURNAL] Ask the user this prompt, then save what they say with journal_write: {q}"
        f = JOURNAL_DIR / f"{datetime.now():%Y-%m-%d}.txt"
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now():%H:%M}] {text}\n\n")
        return "Saved to your journal (only on this PC)."
    if act == "journal_read":
        day = str(p.get("date") or H.today())
        f = JOURNAL_DIR / f"{day}.txt"
        if not f.exists():
            return f"No journal entry for {day}."
        H.show(player, f"JOURNAL — {day}", f.read_text(encoding="utf-8"))
        return f"Your journal for {day} is on screen."
    return "Notes: memo_record, memo_stop, memo_list, memo_search, email_digest, journal_write, journal_read."


TOOL = {
    "name": "notes_tools",
    "description": ("Voice memos: action='memo_record' (optional seconds), 'memo_stop', 'memo_list', 'memo_search' "
                    "(query). 'email_digest' summarises unread email. Private journal saved only on this PC: "
                    "'journal_write' (text; with no text it gives a prompt), 'journal_read' (date YYYY-MM-DD)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "seconds": {"type": "NUMBER", "description": "Max memo length."},
        "query": {"type": "STRING", "description": "Memo search words."},
        "text": {"type": "STRING", "description": "Journal entry text."},
        "date": {"type": "STRING", "description": "Journal date YYYY-MM-DD."}},
        "required": ["action"]},
    "handler": notes_tools,
}
