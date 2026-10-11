"""actions/telegram_bot.py — Message JARVIS from your phone through your own
Telegram bot. Only YOUR paired Telegram chat is answered; everyone else is
ignored. Messages are handled by the Task Agent (so demo mode and the on-screen
CONFIRM buttons still apply on the PC).

Setup: in Telegram, message @BotFather → /newbot → copy the token. Then tell
JARVIS: "set up Telegram" and paste the token in the COMMAND INPUT box, and send
the pairing code it shows to your new bot from your phone."""
import random
import re
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
API = "https://api.telegram.org/bot{token}/{method}"
_pair = {"code": "", "until": 0.0}
_poll = {"gen": 0}


def _call(token: str, method: str, **params):
    import requests
    r = requests.post(API.format(token=token, method=method), json=params, timeout=40)
    return r.json()


def send(text: str) -> bool:
    """Send a message to the paired chat (used by security_watch too)."""
    c = H.cfg()
    if not (c.get("telegram_token") and c.get("telegram_chat_id")):
        return False
    try:
        _call(c["telegram_token"], "sendMessage", chat_id=c["telegram_chat_id"], text=text[:4000])
        return True
    except Exception:
        return False


def send_photo(path: str, caption: str = "") -> bool:
    c = H.cfg()
    if not (c.get("telegram_token") and c.get("telegram_chat_id")):
        return False
    try:
        import requests
        with open(path, "rb") as fh:
            requests.post(API.format(token=c["telegram_token"], method="sendPhoto"),
                          data={"chat_id": c["telegram_chat_id"], "caption": caption[:900]},
                          files={"photo": fh}, timeout=60)
        return True
    except Exception:
        return False


def _agent():
    import importlib.util
    key = "actions.agent_task"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, str(H.base_dir() / "actions" / "agent_task.py"))
    mod = importlib.util.module_from_spec(spec); sys.modules[key] = mod; spec.loader.exec_module(mod)
    return mod


def _handle(token: str, chat_id: int, text: str) -> None:
    text = text.strip()
    if text in ("/start", "/help"):
        _call(token, "sendMessage", chat_id=chat_id, text="JARVIS here. Ask me anything or give me a task, e.g. 'what's on my calendar today?' or 'add milk to my to-do list'.")
        return
    H.log(None, f"SYS: Telegram: {text[:80]}")
    def reply(msg: str):
        m = re.search(r"Result: (.*?)(?: Tell the user|$)", msg, re.S)
        _call(token, "sendMessage", chat_id=chat_id, text=(m.group(1) if m else msg)[:4000])
    started = _agent().start_task(f"(Request sent from the user's phone via Telegram) {text}", None, reply)
    if not started.startswith("[TASK STARTED]"):
        _call(token, "sendMessage", chat_id=chat_id, text=started)
    else:
        _call(token, "sendChatAction", chat_id=chat_id, action="typing")


def _loop(gen: int) -> None:
    offset = None
    while _poll["gen"] == gen:
        c = H.cfg()
        token = c.get("telegram_token")
        if not token:
            return
        try:
            res = _call(token, "getUpdates", timeout=25, **({"offset": offset} if offset else {}))
        except Exception:
            time.sleep(10); continue
        for u in res.get("result", []):
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            chat_id, text = (msg.get("chat") or {}).get("id"), msg.get("text") or ""
            if not chat_id or not text:
                continue
            paired = H.cfg().get("telegram_chat_id")
            if paired and chat_id == paired:
                threading.Thread(target=_handle, args=(token, chat_id, text), daemon=True).start()
            elif text.startswith("/pair") and _pair["code"] and time.monotonic() < _pair["until"] and _pair["code"] in text:
                H.save_cfg("telegram_chat_id", chat_id)
                _pair["code"] = ""
                _call(token, "sendMessage", chat_id=chat_id, text="✅ Paired! You can now message JARVIS here.")
                H.say("[TELEGRAM] Tell the user in one sentence that their phone is now paired with JARVIS on Telegram.")
            # anyone else: ignored on purpose


def _start_polling() -> None:
    if H.cfg().get("telegram_token"):
        _poll["gen"] += 1
        threading.Thread(target=_loop, args=(_poll["gen"],), daemon=True, name="telegram").start()


H.on_ready(_start_polling)


def telegram_bot(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "status").lower()
    if action == "setup":
        token = str(p.get("token") or "").strip()
        if not re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,}", token):
            return ("To set up: in Telegram, message @BotFather, send /newbot, choose a name, and copy the token "
                    "it gives you. Then type 'set up Telegram with token <paste it>' in the COMMAND INPUT box.")
        H.save_cfg("telegram_token", token)
        H.save_cfg("telegram_chat_id", "")
        _pair.update(code=f"{random.randint(0, 999999):06d}", until=time.monotonic() + 600)
        _start_polling()
        H.show(player, "TELEGRAM PAIRING", f"On your phone, open your new bot and send:\n\n/pair {_pair['code']}\n\n(valid for 10 minutes)")
        return f"Token saved. On your phone, send '/pair {_pair['code']}' to your new bot within 10 minutes. The code is on screen."
    if action == "test":
        return "Sent a test message to your phone." if send("👋 Test message from JARVIS.") else "Telegram isn't set up and paired yet."
    if action == "off":
        _poll["gen"] += 1
        H.save_cfg("telegram_token", ""); H.save_cfg("telegram_chat_id", "")
        return "Telegram disconnected. (You can also delete the bot in @BotFather.)"
    c = H.cfg()
    if not c.get("telegram_token"):
        return "Telegram isn't set up. Say 'set up Telegram' for the steps."
    return "Telegram is connected and paired with your phone." if c.get("telegram_chat_id") else "Telegram bot is set up but no phone is paired yet."


TOOL = {
    "name": "telegram_bot",
    "description": ("Control JARVIS from the user's phone via their own Telegram bot. action='setup' with "
                    "token (from @BotFather) then pair with the code shown; 'status' (default); 'test' sends "
                    "a test message; 'off' disconnects."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'setup', 'status', 'test' or 'off'."},
        "token": {"type": "STRING", "description": "For setup: the bot token from @BotFather."}}, "required": []},
    "handler": telegram_bot,
}
