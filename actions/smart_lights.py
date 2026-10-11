"""actions/smart_lights.py — Controls smart bulbs on your Wi-Fi.

Works out of the box with WiZ bulbs (Philips WiZ / many Indian brands built on
WiZ): JARVIS finds them on your network by itself — no account or key needed.
Also works with Home Assistant if you use it (set ha_url and ha_token in
config/api_keys.json) — that covers most other brands."""
import json
import socket
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
LIGHTS = H.base_dir() / "config" / "lights.json"
PORT = 38899
SCENES = {   # WiZ pilot params
    "movie": {"dimming": 15, "temp": 2200},
    "study": {"dimming": 100, "temp": 5000},
    "relax": {"dimming": 40, "temp": 2700},
    "night": {"dimming": 10, "r": 255, "g": 80, "b": 0},
    "party": {"dimming": 100, "sceneId": 4},
    "focus": {"dimming": 90, "temp": 6000},
}
COLORS = {"red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255), "purple": (160, 0, 255),
          "pink": (255, 60, 150), "orange": (255, 120, 0), "yellow": (255, 210, 0), "cyan": (0, 212, 255),
          "white": None, "warm white": None}


def _wiz_send(ip: str, method: str, params: dict) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(1.0)
    try:
        s.sendto(json.dumps({"method": method, "params": params}).encode(), (ip, PORT))
        s.recvfrom(1024)
        return True
    except Exception:
        return False
    finally:
        s.close()


def _discover() -> list:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1); s.settimeout(0.5)
    found = set()
    try:
        for _ in range(3):
            s.sendto(b'{"method":"getPilot","params":{}}', ("255.255.255.255", PORT))
            end = time.time() + 1.5
            while time.time() < end:
                try:
                    _, addr = s.recvfrom(1024)
                    found.add(addr[0])
                except socket.timeout:
                    break
    finally:
        s.close()
    ips = sorted(found)
    H.save_json(LIGHTS, {"wiz": ips})
    return ips


def _ha(service: str, data: dict) -> bool:
    c = H.cfg()
    if not (c.get("ha_url") and c.get("ha_token")):
        return False
    import requests
    r = requests.post(f"{c['ha_url'].rstrip('/')}/api/services/light/{service}",
                      headers={"Authorization": f"Bearer {c['ha_token']}"},
                      json={"entity_id": "all", **data}, timeout=8)
    return r.ok


def smart_lights(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "on").lower()
    if action == "discover":
        ips = _discover()
        return f"Found {len(ips)} WiZ light(s)." if ips else "No WiZ lights found. Make sure they're set up in the WiZ app and on the same Wi-Fi as this PC."
    bulbs = H.load_json(LIGHTS, {}).get("wiz") or _discover()
    params, ha_service, ha_data = {}, "turn_on", {}
    if action == "off":
        params, ha_service = {"state": False}, "turn_off"
    elif action == "brightness":
        try:
            b = max(10, min(int(float(p.get("value") or 50)), 100))
        except (TypeError, ValueError):
            b = 50
        params, ha_data = {"state": True, "dimming": b}, {"brightness_pct": b}
    elif action == "color":
        name = str(p.get("value") or "white").lower()
        rgb = COLORS.get(name, COLORS["white"]) if name in COLORS else None
        if name not in COLORS:
            return f"I know these colours: {', '.join(COLORS)}."
        params = {"state": True, **({"r": rgb[0], "g": rgb[1], "b": rgb[2]} if rgb else {"temp": 2700 if 'warm' in name else 4500})}
        ha_data = {"rgb_color": list(rgb)} if rgb else {"color_temp_kelvin": 2700 if 'warm' in name else 4500}
    elif action == "scene":
        name = str(p.get("value") or "").lower()
        if name not in SCENES:
            return f"Scenes: {', '.join(SCENES)}."
        params = {"state": True, **SCENES[name]}
        ha_data = {"brightness_pct": SCENES[name].get("dimming", 80)}
    else:
        params = {"state": True}
    ok = sum(_wiz_send(ip, "setPilot", params) for ip in bulbs)
    ha_ok = False
    try:
        ha_ok = _ha(ha_service, ha_data)
    except Exception:
        pass
    if not ok and not ha_ok:
        return ("I couldn't reach any lights. For WiZ bulbs, make sure they're on the same Wi-Fi and say "
                "'find my lights'. For other brands, connect them through Home Assistant.")
    what = {"off": "off", "on": "on", "brightness": f"at {p.get('value')}%", "color": str(p.get('value')),
            "scene": f"{p.get('value')} mode"}.get(action, action)
    return f"Lights {what}" + (f" ({ok} bulb{'s' if ok != 1 else ''})." if ok else ".")


TOOL = {
    "name": "smart_lights",
    "description": ("Controls Wi-Fi smart bulbs (WiZ automatically, others via Home Assistant). action='on', "
                    "'off', 'brightness' with value 10-100, 'color' with value (red, blue, cyan, warm white...), "
                    "'scene' with value (movie, study, relax, night, party, focus), 'discover' to find bulbs."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'on', 'off', 'brightness', 'color', 'scene' or 'discover'."},
        "value": {"type": "STRING", "description": "Brightness %, colour name or scene name."}}, "required": []},
    "handler": smart_lights,
}
