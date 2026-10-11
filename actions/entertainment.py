"""actions/entertainment.py — Mood DJ, a movie/anime watchlist with suggestions,
a sound board, and your Steam game stats."""
import math
import os
import re
import threading
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
WATCH = H.mem_path("watchlist.json")
MOODS = {"study": "lofi hip hop beats to study", "focus": "deep focus instrumental music", "gaming": "epic gaming music mix",
         "chill": "chill evening music mix", "happy": "happy upbeat songs", "workout": "workout motivation music",
         "sleep": "rain sounds for sleeping", "sad": "calm comforting songs", "party": "party hits mix", "hype": "hype music mix"}
SOUNDS = ("applause", "drumroll", "tada", "airhorn", "beep", "suit up", "laser", "sad trombone")


def _synth_raw(name: str):
    import numpy as np
    sr = 44100
    t = lambda s: np.arange(int(sr * s)) / sr
    if name == "applause":
        x = np.random.default_rng().normal(0, 1, int(sr * 2.5))
        env = np.minimum(1, np.arange(len(x)) / (sr * 0.3)) * np.exp(-np.arange(len(x)) / (sr * 1.6))
        clap = (np.random.default_rng().random(len(x)) > 0.9985).astype(float)
        x = np.convolve(clap, np.exp(-np.arange(400) / 60), "same") * 0.6 + x * 0.25
        return x * env, sr
    if name == "drumroll":
        tt = t(2.2); x = np.random.default_rng().normal(0, 1, len(tt)) * (0.5 + 0.5 * np.sin(2 * np.pi * 24 * tt) ** 2)
        x[-int(sr * 0.25):] *= 3; return x * 0.35, sr
    if name in ("tada", "suit up"):
        out = []
        for f, d in ((523, 0.12), (659, 0.12), (784, 0.12), (1047, 0.6)):
            tt = t(d); out.append(np.sin(2 * np.pi * f * tt) * np.exp(-tt * 3) + 0.4 * np.sin(4 * np.pi * f * tt) * np.exp(-tt * 5))
        return np.concatenate(out) * 0.4, sr
    if name == "airhorn":
        tt = t(1.2); return np.sign(np.sin(2 * np.pi * 440 * tt)) * 0.25 * np.minimum(1, tt * 20), sr
    if name == "laser":
        tt = t(0.5); return np.sin(2 * np.pi * (1800 - 1500 * tt / 0.5) * tt) * np.exp(-tt * 5) * 0.5, sr
    if name == "sad trombone":
        out = []
        for f in (392, 370, 349):
            tt = t(0.45); out.append(np.sin(2 * np.pi * f * tt) * 0.4)
        tt = t(1.0); out.append(np.sin(2 * np.pi * (330 + 6 * np.sin(2 * np.pi * 6 * tt)) * tt) * 0.4 * np.exp(-tt))
        return np.concatenate(out), sr
    tt = t(0.25); return np.sin(2 * np.pi * 880 * tt) * 0.4, sr


def _synth(name: str):
    """Sound effect, scaled so its loudest point is at a safe level (no clipping)."""
    import numpy as np
    x, sr = _synth_raw(name)
    peak = float(np.max(np.abs(x))) or 1.0
    return x / peak * 0.8, sr


def _steam_dir():
    for p in (Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Steam", Path("C:/Program Files/Steam")):
        if p.exists():
            return p
    return None


def entertainment(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    if act == "mood_dj":
        mood = str(p.get("mood") or "chill").lower()
        query = next((q for k, q in MOODS.items() if k in mood), f"{mood} music mix")
        try:
            from core import tool_bus
            r = tool_bus.run_tool("music_control", {"action": "play", "query": query}, timeout=40)
        except Exception as e:
            r = f"couldn't start music: {e}"
        return f"Mood DJ: playing '{query}'. {r}"
    wl = H.load_json(WATCH, {"to_watch": [], "watched": []})
    if act == "watch_add":
        t = str(p.get("title") or "").strip()
        if t and t not in wl["to_watch"]:
            wl["to_watch"].append(t); H.save_json(WATCH, wl)
        return f"Added {t}. Your watchlist has {len(wl['to_watch'])}."
    if act == "watched":
        t = str(p.get("title") or "").strip()
        wl["to_watch"] = [x for x in wl["to_watch"] if x.lower() != t.lower()]
        wl["watched"].append({"title": t, "rating": p.get("rating"), "date": H.today()}); H.save_json(WATCH, wl)
        return f"Marked {t} as watched."
    if act == "watch_list":
        if not wl["to_watch"]:
            return "Your watchlist is empty."
        H.show(player, "WATCHLIST", "\n".join(f"• {x}" for x in wl["to_watch"]))
        return "To watch: " + ", ".join(wl["to_watch"])
    if act == "recommend":
        kind = str(p.get("kind") or "movie or anime")
        seen = ", ".join(f"{w['title']} ({w.get('rating') or '?'}/10)" for w in wl["watched"][-15:]) or "nothing yet"
        rec = H.ai_text(f"Suggest 5 {kind} titles suitable for a teenager (age-appropriate ratings). They've watched: "
                        f"{seen}. Avoid those. One line each: title — why they'd like it.")
        H.show(player, "RECOMMENDATIONS", rec)
        return "[RECOMMEND] On screen. Mention the top 2 in one sentence:\n" + rec[:800]
    if act == "sound":
        name = str(p.get("name") or "applause").lower()
        name = next((s for s in SOUNDS if s in name or name in s), "beep")
        def _play():
            try:
                import sounddevice as sd
                x, sr = _synth(name); sd.play(x.astype("float32"), sr); sd.wait()
            except Exception:
                pass
        threading.Thread(target=_play, daemon=True).start()
        return f"🔊 {name}!"
    if act == "game_stats":
        steam = _steam_dir()
        if not steam:
            return "I couldn't find Steam on this PC."
        names = {}
        libs = [steam / "steamapps"]
        vdf = steam / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            for x in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(errors="ignore")):
                libs.append(Path(x.replace("\\\\", "\\")) / "steamapps")
        for lib in libs:
            for m in lib.glob("appmanifest_*.acf"):
                txt = m.read_text(errors="ignore")
                a, n = re.search(r'"appid"\s+"(\d+)"', txt), re.search(r'"name"\s+"([^"]+)"', txt)
                if a and n:
                    names[a.group(1)] = n.group(1)
        play = {}
        for cfg in (steam / "userdata").glob("*/config/localconfig.vdf"):
            txt = cfg.read_text(errors="ignore")
            for appid, block in re.findall(r'"(\d+)"\s*\{([^{}]*"Playtime"[^{}]*)\}', txt):
                mins = re.search(r'"Playtime"\s+"(\d+)"', block)
                if mins:
                    play[appid] = max(play.get(appid, 0), int(mins.group(1)))
        rows = sorted(((names.get(a, f"App {a}"), m) for a, m in play.items() if m > 0), key=lambda x: -x[1])
        if not rows:
            return f"You have {len(names)} Steam games installed, but I couldn't find playtime yet."
        H.show(player, "STEAM PLAYTIME", "\n".join(f"{n:<34} {m // 60} h {m % 60} min" for n, m in rows[:20]))
        tot = sum(m for _, m in rows)
        return f"Your most-played: {rows[0][0]} ({rows[0][1] // 60} hours). Total {tot // 60} hours across {len(rows)} games."
    return "Entertainment: mood_dj, watch_add, watched, watch_list, recommend, sound, game_stats."


TOOL = {
    "name": "entertainment",
    "description": ("'mood_dj' (mood: study, focus, gaming, chill, happy, workout, sleep, party...) plays fitting "
                    "music; watchlist: 'watch_add' (title), 'watched' (title, rating), 'watch_list', 'recommend' "
                    "(kind: movie/anime/series); 'sound' (name: applause, drumroll, tada, airhorn, laser, sad "
                    "trombone, beep); 'game_stats' shows Steam playtime."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "mood": {"type": "STRING", "description": "Mood or activity."},
        "title": {"type": "STRING", "description": "Movie/anime title."},
        "rating": {"type": "NUMBER", "description": "Your rating out of 10."},
        "kind": {"type": "STRING", "description": "movie, anime or series."},
        "name": {"type": "STRING", "description": "Sound effect name."}},
        "required": ["action"]},
    "handler": entertainment,
}
