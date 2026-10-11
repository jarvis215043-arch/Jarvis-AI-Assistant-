"""
core/boot_screen.py — The first window you see when you open JARVIS.

A small orange HUD loads up ("INITIALISING CORE… LOADING MODULES… CHECKING
MICROPHONE…") and then says CLAP TWICE TO START. A double clap (or Enter, if
the microphone isn't working) closes it and the PIN screen opens next.
Esc or the ✕ closes JARVIS.

Drawing uses tkinter (like the PIN screen). The timing logic lives in BootState
so it can be tested without a screen.
"""
import json
import math
import sys
import time
from pathlib import Path

ORANGE, ORANGE_DIM, DARK = "#ff7a1a", "#7a3a0c", "#1a0c03"
STEPS = [("INITIALISING CORE", 0.55), ("LOADING MODULES", 0.6),
         ("CHECKING MICROPHONE", 0.5), ("SYSTEMS READY", 0.45)]


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _cfg() -> dict:
    try:
        return json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


class BootState:
    """Loading → waiting for claps → done. Pure logic, no drawing."""

    def __init__(self, now: float):
        self.t0 = now
        self.total = sum(d for _, d in STEPS)
        self.claps = 0                 # 0, 1 (first clap heard) or 2 (double clap)
        self.done_at = None
        self.mic_ok = True

    def progress(self, now: float) -> float:
        return max(0.0, min(1.0, (now - self.t0) / self.total))

    def step_text(self, now: float) -> str:
        t = now - self.t0
        for text, dur in STEPS:
            if t < dur:
                return text
            t -= dur
        return STEPS[-1][0]

    def ready(self, now: float) -> bool:
        return self.progress(now) >= 1.0

    def on_clap(self, first_heard: bool, double: bool, now: float) -> None:
        if not self.ready(now) or self.done_at is not None:
            return
        if double:
            self.claps, self.done_at = 2, now
        elif first_heard:
            self.claps = 1
        else:
            self.claps = 0

    def start_now(self, now: float) -> None:     # Enter / click fallback
        if self.ready(now) and self.done_at is None:
            self.claps, self.done_at = 2, now

    def finished(self, now: float) -> bool:
        return self.done_at is not None and now - self.done_at > 0.6


def wait_for_double_clap() -> bool:
    """Shows the boot HUD. Returns True to continue to the PIN screen, False if
    the user closed it."""
    import tkinter as tk
    cfg = _cfg()
    name = str(cfg.get("assistant_name") or "JARVIS").upper()
    state = BootState(time.monotonic())
    level = {"v": 0.0}
    detector, stream = None, None

    try:
        import sounddevice as sd
        from core.clap import ClapDetector
        detector = ClapDetector(16000, threshold=float(cfg.get("clap_threshold", 0.30)))
        flags = {"double": False}

        def cb(indata, frames, t, status):
            level["v"] = max(level["v"] * 0.85, float(abs(indata).max()) / 32768)
            if detector.feed(indata):
                flags["double"] = True
        stream = sd.InputStream(samplerate=16000, channels=1, dtype="int16", blocksize=800, callback=cb)
        stream.start()
    except Exception as e:
        print(f"[Boot] Microphone unavailable ({e}) — press Enter to start instead.")
        state.mic_ok = False
        flags = {"double": False}

    root = tk.Tk()
    root.title(name)
    root.configure(bg="black")
    root.overrideredirect(True)
    W, H = 600, 380
    x = (root.winfo_screenwidth() - W) // 2
    y = (root.winfo_screenheight() - H) // 2
    root.geometry(f"{W}x{H}+{x}+{y}")
    root.attributes("-topmost", True)
    cv = tk.Canvas(root, width=W, height=H, bg="black", highlightthickness=0)
    cv.pack()
    result = {"go": False}

    def close(go: bool):
        result["go"] = go
        try:
            if stream is not None:
                stream.stop(); stream.close()
        except Exception:
            pass
        root.destroy()

    root.bind("<Escape>", lambda e: close(False))
    root.bind("<Return>", lambda e: state.start_now(time.monotonic()))
    root.bind("<space>", lambda e: state.start_now(time.monotonic()))
    root.focus_force()

    def draw():
        now = time.monotonic()
        if flags["double"]:
            flags["double"] = False
            state.on_clap(True, True, now)
        elif detector is not None:
            state.on_clap(detector.first is not None, False, now)
        if state.finished(now):
            close(True)
            return
        cv.delete("all")
        t = now - state.t0
        cv.create_rectangle(2, 2, W - 2, H - 2, outline=ORANGE_DIM, width=2)
        for cx, cy in ((14, 14), (W - 14, 14), (14, H - 14), (W - 14, H - 14)):     # corner marks
            cv.create_rectangle(cx - 4, cy - 4, cx + 4, cy + 4, outline=ORANGE, width=1)
        cv.create_text(W - 22, 18, text="✕", fill=ORANGE_DIM, font=("Segoe UI", 11), tags="x")
        cv.tag_bind("x", "<Button-1>", lambda e: close(False))

        # spinning arc rings (left), brighter while ready
        rcx, rcy = 140, 190
        glow = 1.0 if state.ready(now) else 0.6
        for i, (r, spd, ext, w) in enumerate(((78, 90, 110, 3), (62, -140, 80, 2), (46, 200, 60, 2), (30, -260, 140, 1))):
            start = (t * spd) % 360
            col = ORANGE if (i % 2 == 0 or glow == 1.0) else ORANGE_DIM
            for k in range(2):
                cv.create_arc(rcx - r, rcy - r, rcx + r, rcy + r, start=start + k * 180, extent=ext,
                              style="arc", outline=col, width=w)
        core = 10 + 3 * math.sin(t * 4) + (6 if state.claps else 0)
        cv.create_oval(rcx - core, rcy - core, rcx + core, rcy + core, fill="#ffd2a8", outline=ORANGE)

        # title + status
        cv.create_text(395, 70, text=name, fill=ORANGE, font=("Segoe UI", 26, "bold"))
        cv.create_text(395, 100, text="PERSONAL AI SYSTEM", fill=ORANGE_DIM, font=("Consolas", 9))
        if not state.ready(now):
            p = state.progress(now)
            cv.create_text(395, 175, text=state.step_text(now) + "." * (int(t * 3) % 4),
                           fill=ORANGE, font=("Consolas", 11, "bold"))
            cv.create_rectangle(270, 200, 520, 212, outline=ORANGE_DIM)
            cv.create_rectangle(272, 202, 272 + 246 * p, 210, fill=ORANGE, outline="")
            cv.create_text(395, 228, text=f"{int(p * 100)}%", fill=ORANGE_DIM, font=("Consolas", 9))
        elif state.done_at is not None:
            cv.create_text(395, 190, text="STARTING…", fill="#ffe2c4", font=("Segoe UI", 18, "bold"))
        else:
            pulse = 0.5 + 0.5 * math.sin(t * 3.2)
            shade = "#ff%02x%02x" % (int(122 + 80 * pulse), int(26 + 90 * pulse))
            cv.create_text(395, 168, text="👏  CLAP TWICE", fill=shade, font=("Segoe UI", 22, "bold"))
            cv.create_text(395, 198, text="TO START " + name, fill=ORANGE, font=("Segoe UI", 12, "bold"))
            for k in range(2):                           # clap indicators
                fx = 375 + k * 40
                cv.create_oval(fx - 8, 222, fx + 8, 238, outline=ORANGE,
                               fill=ORANGE if state.claps > k else "")
            if state.mic_ok:                             # live microphone level
                lv = min(1.0, level["v"] * 2.2)
                cv.create_rectangle(300, 258, 490, 264, outline=ORANGE_DIM)
                cv.create_rectangle(301, 259, 301 + 188 * lv, 263, fill=ORANGE, outline="")
                cv.create_text(395, 278, text="MIC", fill=ORANGE_DIM, font=("Consolas", 8))
            else:
                cv.create_text(395, 268, text="Microphone not found", fill="#ff4d4d", font=("Consolas", 9))
        cv.create_text(W / 2, H - 22, text="Enter = start without clapping   ·   Esc = exit",
                       fill=ORANGE_DIM, font=("Consolas", 8))
        root.after(33, draw)

    draw()
    root.mainloop()
    # Break the links between the window and its callbacks and clean up NOW, on
    # this (main) thread — tkinter objects cleaned up later from another thread
    # crash the program ("Tcl_AsyncDelete: async handler deleted by the wrong thread").
    go = result["go"]
    root = cv = None
    import gc
    gc.collect()
    return go
