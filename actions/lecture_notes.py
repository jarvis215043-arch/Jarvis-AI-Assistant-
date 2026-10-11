"""actions/lecture_notes.py — Records a class or video through the microphone
(or uses an audio/video file you uploaded), then makes notes: summary, key
points and a short quiz. Notes are saved in Documents/JARVIS/Notes."""
import threading
import time
import wave
from datetime import datetime
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
_rec = {"on": False, "stop": False, "file": "", "started": 0.0, "max_min": 90}
RATE = 16000


def _record(path: str) -> None:
    import numpy as np
    import sounddevice as sd
    frames = []
    def cb(indata, n, t, status):
        frames.append(indata.copy())
    with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", callback=cb):
        while not _rec["stop"] and time.monotonic() - _rec["started"] < _rec["max_min"] * 60:
            time.sleep(0.2)
    audio = np.concatenate(frames) if frames else np.zeros((1, 1), dtype="int16")
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(audio.tobytes())
    _rec["on"] = False
    if not _rec["stop"]:                       # hit the time limit by itself
        threading.Thread(target=_make_notes, args=(path, "the recorded class", None), daemon=True).start()


def _make_notes(path: str, title: str, player) -> str:
    H.log(player, "SYS: Making notes — this can take a minute for long recordings…")
    prompt = ("Make study notes from this recording. Plain text with these parts: TITLE (one line), "
              "SUMMARY (4-6 sentences), KEY POINTS (numbered), IMPORTANT TERMS (term — meaning), "
              "QUICK QUIZ (3 questions with answers at the end).")
    try:
        notes = H.ai_file(prompt, path)
    except Exception as e:
        H.say(f"[NOTES] Tell the user the notes couldn't be made: {e}")
        return f"I couldn't make notes: {e}"
    out = H.documents_dir("Notes") / f"Notes {datetime.now():%Y-%m-%d %H-%M}.txt"
    out.write_text(notes, encoding="utf-8")
    H.show(player, "LECTURE NOTES", notes)
    H.say(f"[NOTES READY] Tell the user in one or two sentences that notes for {title} are on screen and "
          f"saved in Documents, JARVIS, Notes. Mention the main topic: {notes[:300]}")
    return "Notes made."


def lecture_notes(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "start").lower()
    if action == "start":
        if _rec["on"]:
            return "I'm already recording. Say 'stop recording' when the class ends."
        try:
            mx = max(1, min(int(float(p.get("max_minutes") or 90)), 180))
        except (TypeError, ValueError):
            mx = 90
        path = str(H.documents_dir("Notes") / f"Recording {datetime.now():%Y-%m-%d %H-%M}.wav")
        _rec.update(on=True, stop=False, file=path, started=time.monotonic(), max_min=mx)
        threading.Thread(target=_record, args=(path,), daemon=True).start()
        return (f"Recording through the microphone (up to {mx} minutes). Put the speaker near the mic, "
                "and say 'stop recording' when it's over — I'll make the notes.")
    if action == "stop":
        if not _rec["on"]:
            return "I'm not recording."
        _rec["stop"] = True
        path = _rec["file"]
        def later():
            for _ in range(50):
                if not _rec["on"]:
                    break
                time.sleep(0.2)
            _make_notes(path, "the class", player)
        threading.Thread(target=later, daemon=True).start()
        mins = int((time.monotonic() - _rec["started"]) / 60)
        return f"Stopped after about {mins} minute(s). Making your notes now — I'll tell you when they're ready."
    if action == "file":
        f = str(p.get("path") or "").strip() or str(getattr(player, "current_file", "") or "")
        if not f or not Path(f).exists():
            return "Drop the audio or video file onto the JARVIS window first, then ask me again."
        threading.Thread(target=_make_notes, args=(f, Path(f).name, player), daemon=True).start()
        return f"Making notes from {Path(f).name} — I'll tell you when they're ready."
    if action == "status":
        if not _rec["on"]:
            return "Not recording."
        return f"Recording for {int((time.monotonic() - _rec['started']) / 60)} minute(s) so far."
    return "Lecture notes can: start, stop, status, or file."


TOOL = {
    "name": "lecture_notes",
    "description": ("Records a class/video with the microphone and turns it into study notes (summary, "
                    "key points, terms, quiz) saved in Documents/JARVIS/Notes. action='start' (optional "
                    "max_minutes), 'stop' (makes the notes), 'status', or 'file' to make notes from an "
                    "uploaded audio/video file (path optional)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'start', 'stop', 'status' or 'file'."},
        "max_minutes": {"type": "NUMBER", "description": "Recording limit (default 90)."},
        "path": {"type": "STRING", "description": "For file: path of the audio/video file."}},
        "required": []},
    "handler": lecture_notes,
}
