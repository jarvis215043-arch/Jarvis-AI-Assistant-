"""actions/music_creative.py — Instrument tuner (listens through the mic and
names the note), metronome, name generator, original song lyrics, comic-strip
scripts and drawing prompts."""
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
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_met = {"on": False}


def _pitch(seconds: float = 2.0):
    import numpy as np
    import sounddevice as sd
    sr = 22050
    rec = sd.rec(int(sr * seconds), samplerate=sr, channels=1, dtype="float32"); sd.wait()
    x = rec[:, 0]
    if np.abs(x).max() < 0.02:
        return None
    x = x * np.hanning(len(x))
    ac = np.correlate(x[:8192], x[:8192], "full")[8191:]          # autocorrelation pitch
    lo, hi = int(sr / 1200), int(sr / 60)
    k = lo + int(np.argmax(ac[lo:hi]))
    return sr / k if ac[k] > 0.2 * ac[0] else None


def _click(freq: float, sr: int = 44100):
    import numpy as np
    t = np.arange(int(sr * 0.04)) / sr
    return (np.sin(2 * np.pi * freq * t) * np.exp(-t * 90) * 0.6).astype("float32")


def _metronome(bpm: int, beats: int):
    import sounddevice as sd
    hi, lo = _click(1600), _click(1000)
    n, t0 = 0, time.monotonic()
    while _met["on"]:
        sd.play(hi if n % beats == 0 else lo, 44100)
        n += 1
        time.sleep(max(0, t0 + n * 60 / bpm - time.monotonic()))


def music_creative(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    topic = str(p.get("topic") or "").strip()
    if act == "tune":
        try:
            f = _pitch()
        except Exception as e:
            return f"I couldn't use the microphone: {e}"
        if not f:
            return "I couldn't hear a clear note — play one string/note loudly, close to the mic, and ask again."
        n = 12 * math.log2(f / 440.0) + 57
        near = round(n); cents = (n - near) * 100
        name = NOTES[near % 12] + str(near // 12)
        how = "in tune ✓" if abs(cents) < 6 else ("a bit sharp — loosen slightly" if cents > 0 else "a bit flat — tighten slightly")
        return f"That's {name} ({f:.1f} Hz), {cents:+.0f} cents — {how}."
    if act == "metronome":
        bpm = max(30, min(int(float(p.get("bpm") or 90)), 240))
        beats = max(1, min(int(float(p.get("beats") or 4)), 12))
        _met["on"] = False; time.sleep(0.1); _met["on"] = True
        threading.Thread(target=_metronome, args=(bpm, beats), daemon=True).start()
        return f"Metronome at {bpm} BPM, {beats} beats per bar. Say 'stop the metronome' to stop."
    if act == "metronome_stop":
        _met["on"] = False
        return "Metronome stopped."
    prompts = {
        "names":   f"Give 10 creative names for {topic or 'a gaming username'}. One per line, no explanations.",
        "lyrics":  f"Write ORIGINAL song lyrics (not copied or based on any existing song) about {topic or 'chasing dreams'}: "
                   "2 verses, a catchy chorus, a bridge. Label the parts.",
        "comic":   f"Write a funny 4-panel comic strip script about {topic or 'a robot learning to cook'}: for each panel, "
                   "a short scene description and the speech bubbles.",
        "drawing": f"Give one fun, specific drawing challenge{(' about ' + topic) if topic else ''} with 3 details to include and a time limit.",
    }
    if act not in prompts:
        return "Music & creative: tune, metronome (bpm, beats), metronome_stop, names, lyrics, comic, drawing (topic)."
    out = H.ai_fast(prompts[act])
    H.show(player, act.upper() + (f" — {topic}" if topic else ""), out)
    H.to_clipboard(out)
    return f"[{act.upper()}] On screen and copied. Share the highlight in one or two sentences:\n" + out[:900]


TOOL = {
    "name": "music_creative",
    "description": ("Music & creativity. 'tune' (listens to one note through the mic and says if it's in tune); 'metronome' "
                    "(bpm, beats), 'metronome_stop'; 'names' (topic: pet, team, character, username…); 'lyrics' (topic; original "
                    "only); 'comic' (topic; 4-panel script); 'drawing' (drawing challenge)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "topic": {"type": "STRING", "description": "What it's about."},
        "bpm": {"type": "NUMBER", "description": "Metronome speed."},
        "beats": {"type": "NUMBER", "description": "Beats per bar."}}, "required": ["action"]},
    "handler": music_creative,
}
