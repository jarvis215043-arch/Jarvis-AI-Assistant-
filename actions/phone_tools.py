"""actions/phone_tools.py — Send a file/link/text to your phone (via your Telegram
bot), make a QR code, ring your Android phone loudly (find my phone), and show
the phone's battery. Ringing / battery need ADB (USB or wireless debugging)."""
import os
import shutil
import subprocess
import sys
import tempfile
import wave
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
NO_WIN = 0x08000000 if sys.platform == "win32" else 0


def _adb() -> str:
    c = H.cfg().get("adb_path")
    if c and Path(c).exists():
        return c
    local = H.base_dir() / "platform-tools" / ("adb.exe" if sys.platform == "win32" else "adb")
    if local.exists():
        return str(local)
    return shutil.which("adb") or ""


def _adb_run(*args, timeout=20) -> str:
    a = _adb()
    if not a:
        raise RuntimeError("ADB not found — install Android platform-tools")
    r = subprocess.run([a, *args], capture_output=True, text=True, timeout=timeout, creationflags=NO_WIN)
    return (r.stdout or "") + (r.stderr or "")


def _tg():
    import importlib.util
    key = "actions.telegram_bot"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, str(H.base_dir() / "actions" / "telegram_bot.py"))
    mod = importlib.util.module_from_spec(spec); sys.modules[key] = mod; spec.loader.exec_module(mod)
    return mod


def phone_tools(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    if act == "send":
        c = H.cfg()
        if not (c.get("telegram_token") and c.get("telegram_chat_id")):
            return "Set up the Telegram bot first (say 'set up Telegram'), then I can send things to your phone."
        f = str(p.get("path") or "").strip() or (str(getattr(player, "current_file", "") or "") if str(p.get("what") or "").lower() == "file" else "")
        if f and Path(f).exists():
            import requests
            with open(f, "rb") as fh:
                r = requests.post(f"https://api.telegram.org/bot{c['telegram_token']}/sendDocument",
                                  data={"chat_id": c["telegram_chat_id"]}, files={"document": fh}, timeout=120)
            return f"Sent {Path(f).name} to your phone." if r.ok else "Telegram didn't accept the file."
        text = str(p.get("text") or "").strip()
        if not text:
            try:
                import pyperclip; text = pyperclip.paste().strip()
            except Exception:
                pass
        if not text:
            return "What should I send? Give me text or a link, or drop a file on the HUD."
        return "Sent to your phone." if _tg().send(text) else "Couldn't send — check Telegram is paired."
    if act == "qr":
        text = str(p.get("text") or "").strip()
        if not text:
            try:
                import pyperclip; text = pyperclip.paste().strip()
            except Exception:
                pass
        if not text:
            return "What should the QR code contain?"
        import qrcode
        img = qrcode.make(text)
        out = H.documents_dir("QR") / "qr.png"
        img.save(out)
        if sys.platform == "win32":
            os.startfile(str(out))       # type: ignore[attr-defined]
        return "QR code is open — scan it with your phone's camera."
    if act == "find_phone":
        try:
            import numpy as np
            sr = 44100
            t = np.arange(int(sr * 0.25)) / sr
            beep = np.concatenate([np.sin(2 * np.pi * f * t) for f in (1400, 1800)] * 30)
            wav = Path(tempfile.gettempdir()) / "jarvis_find.wav"
            with wave.open(str(wav), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
                w.writeframes((beep * 30000).astype("int16").tobytes())
            if "device" not in _adb_run("devices").replace("List of devices attached", ""):
                return "No phone connected. Connect it by USB or turn on wireless debugging and pair it once."
            _adb_run("push", str(wav), "/sdcard/Download/jarvis_find.wav", timeout=40)
            _adb_run("shell", "cmd", "media_session", "volume", "--stream", "3", "--set", "15")
            _adb_run("shell", "am", "start", "-a", "android.intent.action.VIEW",
                     "-d", "file:///sdcard/Download/jarvis_find.wav", "-t", "audio/wav")
            return "Your phone should be beeping loudly now (about 15 seconds)."
        except Exception as e:
            return f"I couldn't ring your phone: {e}"
    if act == "battery":
        try:
            out = _adb_run("shell", "dumpsys", "battery")
        except Exception as e:
            return f"I couldn't reach your phone: {e}"
        lvl = next((l.split(":")[1].strip() for l in out.splitlines() if l.strip().startswith("level:")), None)
        st = next((l.split(":")[1].strip() for l in out.splitlines() if l.strip().startswith("status:")), "")
        if not lvl:
            return "No phone connected."
        return f"Your phone is at {lvl}%{' and charging' if st == '2' else ''}."
    return "Phone tools: send, qr, find_phone, battery."


TOOL = {
    "name": "phone_tools",
    "description": ("Phone helpers. 'send' sends text/a link (text, or the clipboard) or a file (path, or what='file' for the "
                    "file dropped on the HUD) to the user's phone via their Telegram bot; 'qr' shows a QR code (text or "
                    "clipboard); 'find_phone' makes their Android phone beep loudly; 'battery' tells the phone's battery level."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'send', 'qr', 'find_phone' or 'battery'."},
        "text": {"type": "STRING", "description": "Text or link."},
        "path": {"type": "STRING", "description": "File path to send."},
        "what": {"type": "STRING", "description": "'file' to send the uploaded file."}}, "required": ["action"]},
    "handler": phone_tools,
}
