"""actions/home_arduino.py — Home features through the Arduino (sketch:
arduino/jarvis_suit/jarvis_suit.ino): room sensors, plant care, door alert, TV/AC
remote (learns your remote's buttons), desk ambient lights that copy your screen's
colours, a gauntlet button that wakes JARVIS, and a wind-down mode.
Optional parts are switched on at the top of the sketch."""
import json
import sys
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
CFG = H.base_dir() / "config" / "home_arduino.json"
_amb = {"on": False}


def _hw():
    import importlib.util
    key = "actions.hardware_control"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, str(H.base_dir() / "actions" / "hardware_control.py"))
    mod = importlib.util.module_from_spec(spec); sys.modules[key] = mod; spec.loader.exec_module(mod)
    return mod


def _send(cmd: str) -> str:
    return _hw()._send(cmd)


def _cfg():
    return H.load_json(CFG, {"plant_watch": False, "plant_dry": 550, "door_alert": False, "button": False, "ir": {}})


def _sensors() -> dict:
    r = _send("SENSORS")
    out = {}
    for part in r.replace("OK SENSORS", "").split():
        if "=" in part:
            k, v = part.split("=", 1)
            try:
                out[k] = float(v)
            except ValueError:
                pass
    return out


def _bus_ui():
    try:
        from core import tool_bus
        return tool_bus._ui
    except Exception:
        return None


def _watch() -> None:
    time.sleep(30)
    last_plant, last_door, tick = 0.0, None, 0
    while True:
        c = _cfg()
        try:
            if c.get("door_alert"):
                r = _send("DOOR")
                is_open = r.strip().endswith("1")
                if last_door is not None and is_open and not last_door:
                    H.say("[DOOR] Tell the user briefly: your room door just opened.")
                    try:
                        tg = sys.modules.get("actions.telegram_bot")
                        tg and tg.send("🚪 JARVIS: your room door just opened.")
                    except Exception:
                        pass
                last_door = is_open
            if c.get("button") and _send("BUTTON").strip().endswith("1"):
                ui = _bus_ui()
                if ui is not None and getattr(ui, "muted", False):
                    ui.set_muted(False)
                H.say("[GAUNTLET] The user pressed their gauntlet button. Say only: 'Yes, sir?'")
            if c.get("plant_watch") and tick % 600 == 0 and time.monotonic() - last_plant > 6 * 3600:
                soil = _sensors().get("soil")
                if soil is not None and soil >= c.get("plant_dry", 550):
                    last_plant = time.monotonic()
                    H.say("[PLANT] Tell the user in one friendly sentence: your plant's soil is dry — time to water it.")
        except Exception:
            pass
        tick += 1
        time.sleep(0.4 if c.get("button") else 1.0)


H.on_ready(_watch)


def _ambient_loop() -> None:
    import mss, numpy as np
    last = None
    with mss.mss() as sct:
        mon = sct.monitors[1]
        while _amb["on"]:
            try:
                img = np.asarray(sct.grab(mon))[::24, ::24, :3]           # small sample, BGRA → BGR
                b, g, r = (int(x) for x in img.reshape(-1, 3).mean(0))
                cur = (r, g, b)
                if last is None or sum(abs(a - b) for a, b in zip(cur, last)) > 18:
                    _send(f"STRIP {r} {g} {b}"); last = cur
            except Exception:
                pass
            time.sleep(0.25)


def home_arduino(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    c = _cfg()
    try:
        import serial  # noqa: F401
    except ImportError:
        return "Home features need pyserial: python -m pip install pyserial"
    try:
        if act == "sensors":
            s = _sensors()
            if not s:
                return "No sensor data — check the Arduino is connected and the sensors are switched on in the sketch."
            parts = []
            if "t" in s: parts.append(f"{s['t']:.1f}°C")
            if "h" in s: parts.append(f"humidity {s['h']:.0f}%")
            if "light" in s: parts.append(f"light {int(s['light'] / 10.23)}%")
            if "soil" in s: parts.append(f"soil {'dry' if s['soil'] >= c['plant_dry'] else 'moist'}")
            if "door" in s: parts.append(f"door {'open' if s['door'] else 'closed'}")
            H.show(player, "ROOM SENSORS", "\n".join(parts))
            return "Room: " + ", ".join(parts) + "."
        if act in ("plant_on", "plant_off"):
            c["plant_watch"] = act == "plant_on"; H.save_json(CFG, c)
            return "I'll tell you when your plant needs water." if c["plant_watch"] else "Plant reminders off."
        if act == "plant_calibrate":
            soil = _sensors().get("soil")
            if soil is None:
                return "No soil sensor reading."
            c["plant_dry"] = int(soil) - 15; H.save_json(CFG, c)
            return f"Calibrated: anything drier than now ({int(soil)}) counts as 'needs water'. Do this when the soil is just starting to feel dry."
        if act in ("door_on", "door_off"):
            c["door_alert"] = act == "door_on"; H.save_json(CFG, c)
            return "Door alert on." if c["door_alert"] else "Door alert off."
        if act in ("button_on", "button_off"):
            c["button"] = act == "button_on"; H.save_json(CFG, c)
            return "Gauntlet button active: press it to wake me." if c["button"] else "Gauntlet button off."
        if act == "remote_learn":
            name = str(p.get("name") or "").lower().strip()
            if not name:
                return "What should I call this button? e.g. 'tv power'."
            r = _send("IR LEARN")                 # the Arduino waits up to 8 s for a remote press
            parts = r.split()
            if len(parts) >= 5 and parts[0] == "OK":
                c["ir"][name] = parts[2:5]; H.save_json(CFG, c)
                return f"Learned '{name}'. Say 'press {name}' any time."
            return "I didn't catch a signal. Point your remote at the IR receiver and press the button within 8 seconds."
        if act == "remote_press":
            name = str(p.get("name") or "").lower().strip()
            code = c["ir"].get(name)
            if not code:
                return f"I haven't learned '{name}'. Learned: {', '.join(c['ir']) or 'none yet'}."
            r = _send("IR SEND " + " ".join(code))
            return f"Pressed {name}." if r.startswith("OK") else "The Arduino didn't confirm."
        if act == "ambient_on":
            if not _amb["on"]:
                _amb["on"] = True
                threading.Thread(target=_ambient_loop, daemon=True).start()
            return "Desk lights now follow your screen's colours."
        if act == "ambient_off":
            _amb["on"] = False
            _send("STRIP 0 0 0")
            return "Desk ambient lights off."
        if act == "wind_down":
            from core import tool_bus
            done = []
            for tool, args, label in (("smart_lights", {"action": "scene", "value": "night"}, "lights dimmed"),
                                      ("music_control", {"action": "play", "query": "rain sounds for sleeping"}, "rain sounds on"),
                                      ("hardware_control", {"action": "send", "command": "reactor idle"}, "reactor low")):
                r = tool_bus.run_tool(tool, args, timeout=30)
                if not any(w in r.lower() for w in ("couldn't", "no ", "failed", "not ")):
                    done.append(label)
            if p.get("time"):
                tool_bus.run_tool("timers_alarms", {"action": "alarm_set", "time": p.get("time")}, timeout=10)
                done.append(f"alarm {p.get('time')}")
            return f"[WIND DOWN] Wish the user a calm good night in one sentence. Done: {', '.join(done) or 'music only'}."
    except Exception as e:
        return f"Couldn't reach the Arduino: {e}"
    return "Home: sensors, plant_on/off, plant_calibrate, door_on/off, button_on/off, remote_learn, remote_press, ambient_on/off, wind_down."


TOOL = {
    "name": "home_arduino",
    "description": ("Home features via the Arduino. 'sensors' (temperature, humidity, light, soil, door); plant care "
                    "'plant_on'/'plant_off', 'plant_calibrate'; 'door_on'/'door_off' (alert when the door opens); TV/AC "
                    "remote: 'remote_learn' (name, e.g. 'tv power') then 'remote_press' (name); 'ambient_on'/'ambient_off' "
                    "(LED strip copies the screen's colours); 'button_on'/'button_off' (gauntlet button wakes JARVIS); "
                    "'wind_down' (night lights, rain sounds, optional alarm time)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "name": {"type": "STRING", "description": "Remote button name."},
        "time": {"type": "STRING", "description": "Alarm time for wind_down."}}, "required": ["action"]},
    "handler": home_arduino,
}
