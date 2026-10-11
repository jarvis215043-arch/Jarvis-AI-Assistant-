"""
actions/hardware_control.py — Control real hardware through an Arduino on USB:
lights, the suit's motorized faceplate (servo), a chest 'arc reactor' LED, a fan.

Works with the sketch in arduino/jarvis_suit/jarvis_suit.ino. JARVIS finds the
Arduino automatically, sends one command per line (e.g. 'FACE OPEN') and reads
the Arduino's 'OK ...' reply. Needs the pyserial package (in requirements.txt).
"""
import json
import sys
import threading
import time
from pathlib import Path

BAUD = 9600
# What you say → what the Arduino receives
_COMMANDS = {
    "lights on": "LIGHTS ON", "lights off": "LIGHTS OFF",
    "eyes on": "LIGHTS ON", "eyes off": "LIGHTS OFF",
    "faceplate open": "FACE OPEN", "open faceplate": "FACE OPEN", "open the faceplate": "FACE OPEN",
    "faceplate close": "FACE CLOSE", "close faceplate": "FACE CLOSE", "close the faceplate": "FACE CLOSE",
    "reactor on": "REACTOR ON", "reactor off": "REACTOR OFF", "reactor pulse": "REACTOR PULSE",
    "fan on": "FAN ON", "fan off": "FAN OFF",
    "suit up": "SUIT UP", "power down": "POWER DOWN", "status": "STATUS",
    "reactor glow": "REACTOR GLOW", "reactor idle": "REACTOR IDLE",
}

_ser = None
_lock = threading.Lock()


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _cfg_file() -> Path:
    return _base_dir() / "config" / "hardware.json"


def _saved_port() -> str:
    try:
        return json.loads(_cfg_file().read_text(encoding="utf-8")).get("port", "")
    except Exception:
        return ""


def _save_port(port: str) -> None:
    p = _cfg_file()
    data = {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    data["port"] = port
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


def _ports():
    from serial.tools import list_ports
    return list(list_ports.comports())


def _guess_port() -> str:
    saved = _saved_port()
    ports = _ports()
    names = [p.device for p in ports]
    if saved and saved in names:
        return saved
    for p in ports:
        desc = f"{p.description} {p.manufacturer or ''}".lower()
        if any(k in desc for k in ("arduino", "ch340", "ch341", "usb-serial", "usb serial", "cp210", "ftdi")):
            return p.device
    return names[0] if len(names) == 1 else ""


def _connect(port: str = ""):
    global _ser
    import serial
    if _ser is not None and _ser.is_open and (not port or _ser.port == port):
        return _ser
    port = port or _guess_port()
    if not port:
        raise RuntimeError("no Arduino found — plug it in with a USB cable")
    if _ser is not None:
        try:
            _ser.close()
        except Exception:
            pass
    _ser = serial.Serial(port, BAUD, timeout=1.5)
    time.sleep(2.0)                 # most Arduinos reset when the port opens
    _ser.reset_input_buffer()
    _save_port(port)
    return _ser


def _send(command: str) -> str:
    with _lock:
        ser = _connect()
        ser.write((command.strip().upper() + "\n").encode("ascii", "ignore"))
        ser.flush()
        reply = ser.readline().decode("ascii", "ignore").strip()
    return reply


# ── Reactor lamp: the LED ring pulses while JARVIS speaks ─────────────────────
def _lamp_on() -> bool:
    try:
        return bool(json.loads(_cfg_file().read_text(encoding="utf-8")).get("lamp_sync"))
    except Exception:
        return False


def _set_lamp(on: bool) -> None:
    data = {}
    try:
        data = json.loads(_cfg_file().read_text(encoding="utf-8"))
    except Exception:
        pass
    data["lamp_sync"] = on
    _cfg_file().parent.mkdir(parents=True, exist_ok=True)
    _cfg_file().write_text(json.dumps(data), encoding="utf-8")


def _on_speaking(speaking) -> None:
    if not _lamp_on():
        return
    def _go():
        try:
            _send("REACTOR GLOW" if speaking else "REACTOR IDLE")
        except Exception:
            pass
    threading.Thread(target=_go, daemon=True).start()


try:
    from core import tool_bus as _bus
    _bus.subscribe("speaking", _on_speaking)
except Exception:
    pass


def hardware_control(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "send").strip().lower()

    if action in ("lamp_on", "lamp_off"):
        _set_lamp(action == "lamp_on")
        return ("Reactor lamp on — it'll glow and pulse whenever I speak." if action == "lamp_on"
                else "Reactor lamp sync off.")

    try:
        import serial  # noqa: F401
    except ImportError:
        return "Hardware control needs pyserial: run  python -m pip install pyserial  then restart JARVIS."

    if action in ("ports", "list", "scan"):
        ports = _ports()
        if not ports:
            return "No USB serial devices found. Plug the Arduino in with a data USB cable."
        return "Found: " + "; ".join(f"{x.device} ({x.description})" for x in ports)

    if action == "connect":
        try:
            ser = _connect(str(p.get("port") or ""))
            return f"Connected to the Arduino on {ser.port}."
        except Exception as e:
            return f"Couldn't connect: {e}"

    raw = str(p.get("command") or "").strip()
    if not raw:
        return "What should I do? For example: lights on, open faceplate, reactor on."
    cmd = _COMMANDS.get(raw.lower(), raw.upper())
    try:
        reply = _send(cmd)
    except Exception as e:
        return f"Couldn't reach the Arduino: {e}"
    if reply.startswith("OK"):
        return f"Done — {raw}."
    if reply.startswith("ERR"):
        return f"The Arduino didn't understand '{cmd}'. It knows: {', '.join(sorted(set(_COMMANDS.values())))}."
    return f"Sent '{cmd}' but the Arduino didn't reply. Check it's running the jarvis_suit sketch."


TOOL = {
    "name": "hardware_control",
    "description": (
        "Controls real hardware via an Arduino on USB (the user's suit/props): lights or eyes "
        "on/off, open/close the faceplate, reactor on/off/pulse, fan on/off, 'suit up' (everything "
        "on + faceplate closes), 'power down'. action='send' (default) with command in plain words; "
        "'ports' lists USB devices; 'connect' with optional port like COM3; 'lamp_on'/'lamp_off' makes the "
        "reactor LED ring glow and pulse whenever JARVIS speaks."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action":  {"type": "STRING", "description": "'send' (default), 'ports', 'connect', 'lamp_on' or 'lamp_off'."},
            "command": {"type": "STRING", "description": "e.g. 'lights on', 'open faceplate', 'reactor pulse', 'suit up'."},
            "port":    {"type": "STRING", "description": "For connect: e.g. 'COM3'. Usually found automatically."},
        },
        "required": [],
    },
    "handler": hardware_control,
}
