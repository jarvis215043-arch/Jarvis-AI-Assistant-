"""
actions/phone_control.py — Places (and ends) phone calls on an Android phone
connected to this PC via USB-C, using ADB (Android Debug Bridge).

ONE-TIME PHONE SETUP:
  1. Settings → About phone → tap "Build number" 7x to unlock Developer Options.
  2. Settings → Developer options → enable "USB debugging".
  3. Plug in via a USB-C DATA cable (not charge-only) and tap "Allow" on the
     "Allow USB debugging?" prompt that appears on the phone.

ONE-TIME PC SETUP:
  - Install Android platform-tools and make sure `adb` is on PATH, or set
    "adb_path" in config/api_keys.json to its full path.
"""
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

from core import confirm as confirm_gate


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _config() -> dict:
    try:
        return json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _adb_path() -> str:
    return _config().get("adb_path", "adb")


def _get_demo_mode_module():
    key = "jarvis_ext_demo_mode"
    if key in sys.modules:
        return sys.modules[key]
    path = _base_dir() / "core" / "demo_mode.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(key, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def _run_adb(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run([_adb_path(), *args], capture_output=True, text=True, timeout=timeout)


def _device_ready() -> tuple[bool, str]:
    try:
        result = _run_adb(["devices"])
    except FileNotFoundError:
        return False, "ADB is not installed or not on PATH. Install Android platform-tools first."
    except Exception as e:
        return False, f"Could not run adb: {e}"

    lines = [l.strip() for l in result.stdout.splitlines()[1:] if l.strip()]
    if not lines:
        return False, "No phone detected. Plug it in via USB-C and enable USB debugging."
    for line in lines:
        if line.endswith("unauthorized"):
            return False, "Phone detected but not authorized — check the phone screen and tap Allow."
        if line.endswith("offline"):
            return False, "Phone shows as offline — try unplugging and replugging the cable."
    if any(line.endswith("device") for line in lines):
        return True, ""
    return False, "Phone connection state unclear — run 'adb devices' manually to check."


_DIGITS_RE = re.compile(r"[^\d+]")


def _clean_number(number: str) -> str:
    return _DIGITS_RE.sub("", number.strip())


def _lookup_contact_number(name: str) -> str | None:
    try:
        result = _run_adb([
            "shell", "content", "query",
            "--uri", "content://com.android.contacts/data/phones",
            "--projection", "display_name:data1",
            "--where", f"display_name LIKE '%{name}%' AND mimetype='vnd.android.cursor.item/phone_v2'",
        ])
    except Exception:
        return None

    out = result.stdout
    if not out or "No result found" in out:
        return None
    match = re.search(r"data1=([+\d\-\s()]+)", out)
    return _clean_number(match.group(1)) if match else None


def make_phone_call(parameters: dict, player=None, session_memory=None) -> str:
    params       = parameters or {}
    contact_name = (params.get("contact_name") or "").strip()
    phone_number = (params.get("phone_number") or "").strip()
    action       = (params.get("action") or "call").strip().lower()

    if action == "hang_up":
        try:
            _run_adb(["shell", "input", "keyevent", "KEYCODE_ENDCALL"])
        except Exception as e:
            msg = f"Could not end the call: {e}"
            _log(msg, player)
            return msg
        msg = "Call ended, sir."
        _log(msg, player)
        return msg

    # Demo mode only guards actually PLACING a call — hanging up is safe/reversible.
    dm = _get_demo_mode_module()
    if dm and dm.is_demo_mode():
        msg = "Calling is disabled while demo mode is on, sir."
        _log(msg, player)
        return msg

    ready, err = _device_ready()
    if not ready:
        _log(err, player)
        return err

    if not phone_number and contact_name:
        phone_number = _lookup_contact_number(contact_name) or ""
        if not phone_number:
            msg = f"I couldn't find a number for {contact_name}, sir. Please give me the number directly."
            _log(msg, player)
            return msg

    if not phone_number:
        msg = "Sir, I need a contact name or phone number to call."
        _log(msg, player)
        return msg

    number = _clean_number(phone_number)
    if not number:
        msg = "That doesn't look like a valid phone number, sir."
        _log(msg, player)
        return msg

    who = contact_name or number

    def _place_call() -> str:
        try:
            result = _run_adb(["shell", "am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{number}"])
        except Exception as e:
            return f"Could not place the call: {e}"
        if result.returncode != 0:
            return f"The phone rejected the call request: {result.stderr.strip()[:150]}"
        return f"Calling {who} now, sir."

    return confirm_gate.request(
        key=f"call:{number}",
        title=f"Call {who}?",
        detail=f"JARVIS wants to dial {number} on your phone.",
        run=_place_call,
    )


def _log(message: str, player=None) -> None:
    print(f"[PhoneControl] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass


TOOL = {
    "name": "make_phone_call",
    "description": (
        "Places or ends a phone call on the user's Android phone via USB-C/ADB. "
        "Placing a call requires the user to confirm on the HUD first — you will "
        "get back [CONFIRMATION_PENDING]. Use action='hang_up' to end a call instantly, no confirmation needed."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "contact_name": {"type": "STRING", "description": "Contact name as saved on the phone"},
            "phone_number": {"type": "STRING", "description": "Phone number, if no contact name given"},
            "action": {"type": "STRING", "description": "'call' or 'hang_up'. Defaults to 'call'."}
        },
        "required": []
    },
    "handler": make_phone_call,
}