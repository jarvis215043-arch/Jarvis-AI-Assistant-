"""
core/gesture_modes.py — The two hand-gesture modes, and only one at a time.

  HOLOGRAM mode   your hands move the holograms (actions/suit_hologram.py):
                  pinch = rotate, fist = move, thumbs = shape, two hands = size…
  PC mode         your hands control the computer (actions/gesture_control.py):
                  thumbs = volume, fist = mute, palm = play/pause, pinch = click…
  OFF

Both need the webcam, so switching to one always stops the other first. Switch by
voice ("hologram gesture mode", "PC gesture mode", "gestures off"), with the
buttons at the top of the hologram window's HAND CONTROLS panel, or with keys
in that window (G = hologram mode, P = PC mode, O = off).
"""
import sys
import threading
import time

_player = None
_lock = threading.Lock()
LABEL = {"hologram": "✋ HOLOGRAM", "pc": "🖥 PC", "off": "OFF"}


def set_player(p) -> None:
    """Remember the JARVIS window (tools call this) so the hologram window's buttons can switch modes."""
    global _player
    if p is not None:
        _player = p


def _holo():
    return sys.modules.get("actions.suit_hologram")


def _pc():
    return sys.modules.get("actions.gesture_control")


def current() -> str:
    h, g = _holo(), _pc()
    try:
        if h is not None and h._st.get("on"):
            return "hologram"
        if g is not None and g._state.get("active"):
            return "pc"
    except Exception:
        pass
    return "off"


def stop_hologram(wait: float = 3.0) -> bool:
    h = _holo()
    if h is None or not h._st.get("on"):
        return False
    h._st["stop"] = True
    t = time.monotonic()
    while h._st.get("on") and time.monotonic() - t < wait:   # until it has let go of the webcam
        time.sleep(0.05)
    return True


def stop_pc(wait: float = 3.0) -> bool:
    g = _pc()
    if g is None or not g._state.get("active"):
        return False
    try:
        with g._lock:
            g._state["stop_flag"] = True
    except Exception:
        g._state["stop_flag"] = True
    t = time.monotonic()
    while g._state.get("active") and time.monotonic() - t < wait:
        time.sleep(0.05)
    return True


def switch(mode: str, player=None) -> str:
    """mode: 'hologram' | 'pc' | 'off'. Blocking (≤ 3 s) — call from a worker thread, not the GUI."""
    mode = {"holo": "hologram", "holograms": "hologram", "computer": "pc", "system": "pc", "pc": "pc",
            "none": "off", "stop": "off"}.get(str(mode).lower().strip(), str(mode).lower().strip())
    p = player or _player
    with _lock:
        if mode == "hologram":
            stop_pc()
            h = _holo()
            if h is None or p is None:
                return "Hologram gestures aren't available."
            return h.holograms({"action": "gestures_on"}, p)
        if mode == "pc":
            stop_hologram()
            g = _pc()
            if g is None:
                return "PC gesture control isn't available."
            return g.gesture_control({"action": "start", "mode": "computer"}, p)
        if mode == "off":
            a, b = stop_hologram(), stop_pc()
            return "Hand gestures off." if (a or b) else "Hand gestures were already off."
    return "Gesture modes: hologram, pc or off."


def switch_async(mode: str) -> None:
    """For buttons / keys in the hologram window: switch without freezing the window."""
    def run():
        try:
            msg = switch(mode)
        except Exception as e:
            msg = f"Couldn't switch: {e}"
        print(f"[Gestures] {msg}")
        try:
            from core import tool_bus
            tool_bus.emit("hologram_control", {"feedback": {"hologram": "✋  HOLOGRAM GESTURE MODE",
                                                            "pc": "🖥  PC GESTURE MODE",
                                                            "off": "HAND GESTURES OFF"}.get(current(), msg[:40])})
        except Exception:
            pass
    threading.Thread(target=run, daemon=True, name="gesture-mode").start()
