"""actions/comms_plus.py — Schedule a message for later, wish writer, email
templates, a private contacts book, translate-then-send, group messages and
reply suggestions. Drafts go to the HUD and the clipboard; sending uses the
normal send_message tool (so demo mode still blocks it)."""
import time
from datetime import datetime, timedelta

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
SCHED = H.mem_path("scheduled_messages.json")
CONTACTS = H.mem_path("contacts.json")
TEMPLATES = {"leave": "a polite leave application to a school teacher/principal",
             "teacher": "a respectful email to a teacher asking a question",
             "complaint": "a polite complaint email to customer support",
             "thanks": "a thank-you email",
             "request": "a polite request email",
             "apology": "a sincere apology message"}


def _watch() -> None:
    time.sleep(30)
    while True:
        items = H.load_json(SCHED, [])
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        changed = False
        for m in items:
            if not m.get("sent") and m["when"] <= now:
                try:
                    from core import tool_bus
                    r = tool_bus.run_tool("send_message", {"receiver": m["to"], "message_text": m["text"],
                                                           "platform": m.get("platform") or "whatsapp"}, timeout=90)
                    m["sent"] = True; m["result"] = r[:120]; changed = True
                    H.say(f"[SCHEDULED] Tell the user briefly: I sent your scheduled message to {m['to']}.")
                except Exception as e:
                    m["result"] = str(e)
        if changed:
            H.save_json(SCHED, items[-100:])
        time.sleep(30)


H.on_ready(_watch)


def _when(text: str):
    t = (text or "").strip().lower()
    now = datetime.now()
    for f in ("%Y-%m-%d %H:%M", "%H:%M", "%I:%M %p", "%I %p", "%I:%M%p", "%I%p"):
        try:
            d = datetime.strptime(t.replace("tomorrow", "").strip(), f)
            if f.startswith("%Y"):
                return d
            d = now.replace(hour=d.hour, minute=d.minute, second=0, microsecond=0)
            if "tomorrow" in t or d <= now:
                d += timedelta(days=1)
            return d
        except ValueError:
            continue
    return None


def comms_plus(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    text = str(p.get("text") or "").strip()
    to = str(p.get("to") or "").strip()
    if act == "schedule":
        w = _when(str(p.get("time") or ""))
        if not (w and to and text):
            return "Tell me who to send it to, the message, and the time (e.g. 'tomorrow 9 am')."
        items = H.load_json(SCHED, [])
        items.append({"to": to, "text": text, "when": w.strftime("%Y-%m-%d %H:%M"), "platform": p.get("platform") or "whatsapp"})
        H.save_json(SCHED, items)
        return f"Scheduled for {w:%a %d %b, %I:%M %p}: '{text}' to {to}. Keep the PC on with JARVIS running."
    if act == "scheduled":
        items = [m for m in H.load_json(SCHED, []) if not m.get("sent")]
        return ("Scheduled: " + "; ".join(f"{m['when']} → {m['to']}: {m['text'][:40]}" for m in items)) if items else "Nothing scheduled."
    if act == "cancel_scheduled":
        items = H.load_json(SCHED, [])
        keep = [m for m in items if m.get("sent") or (to and to.lower() not in m["to"].lower())]
        H.save_json(SCHED, keep)
        return f"Cancelled {len(items) - len(keep)} scheduled message(s)."
    if act == "contact_add":
        name = str(p.get("name") or to).strip()
        if not name:
            return "Whose details?"
        c = H.load_json(CONTACTS, {})
        c[name] = {k: v for k, v in (("phone", p.get("phone")), ("email", p.get("email")), ("note", p.get("note"))) if v}
        H.save_json(CONTACTS, c)
        return f"Saved {name} in your contacts (only on this PC)."
    if act == "contact_find":
        q = str(p.get("name") or to).lower()
        c = H.load_json(CONTACTS, {})
        hits = {k: v for k, v in c.items() if q in k.lower()}
        if not hits:
            return f"No contact matching '{q}'."
        return "; ".join(f"{k}: " + ", ".join(f"{a} {b}" for a, b in v.items()) for k, v in hits.items())
    drafts = {
        "wish":    f"Write a warm, short {p.get('occasion') or 'birthday'} wish for {to or 'a friend'}{(' — ' + text) if text else ''}. Add 1-2 emojis.",
        "email":   f"Write {TEMPLATES.get(str(p.get('kind') or '').lower(), 'a polite email')}{(' about: ' + text) if text else ''}. "
                   "Include a subject line. Fill in what's known; leave [brackets] for anything missing.",
        "group":   f"Write a friendly group message for: {text or 'inviting friends to my birthday'}. Short, clear, with the key details.",
        "replies": f"Suggest 3 different short replies (friendly, neutral, polite-no) to this message:\n{text or H.clipboard_text()}",
        "translate": f"Translate this message into {p.get('language') or 'English'}, keeping the tone. Only the translation:\n{text}",
    }
    if act not in drafts:
        return "Comms: schedule, scheduled, cancel_scheduled, wish, email, group, replies, translate, contact_add, contact_find."
    if act == "translate" and not text:
        return "What message should I translate?"
    out = H.ai_fast(drafts[act])
    H.show(player, act.upper(), out)
    H.to_clipboard(out)
    if act == "translate" and to:
        from core import tool_bus
        r = tool_bus.run_tool("send_message", {"receiver": to, "message_text": out, "platform": p.get("platform") or "whatsapp"}, timeout=90)
        return f"Translated and sent: {out[:200]} ({r[:80]})"
    return f"[DRAFT] On screen and copied to the clipboard — read it to the user if short:\n{out[:900]}"


TOOL = {
    "name": "comms_plus",
    "description": ("Messages & email. 'schedule' (to, text, time, platform) sends a message later; 'scheduled'; 'cancel_scheduled' "
                    "(to); drafts copied to clipboard: 'wish' (to, occasion), 'email' (kind leave/teacher/complaint/thanks/request/"
                    "apology, text), 'group' (text), 'replies' (text or clipboard), 'translate' (text, language, optional to = also "
                    "send); private contacts: 'contact_add' (name, phone, email, note), 'contact_find' (name)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "to": {"type": "STRING", "description": "Person / contact."},
        "text": {"type": "STRING", "description": "Message or details."},
        "time": {"type": "STRING", "description": "When to send."},
        "platform": {"type": "STRING", "description": "whatsapp or telegram."},
        "occasion": {"type": "STRING", "description": "Birthday, Diwali, exam, …"},
        "kind": {"type": "STRING", "description": "Email template kind."},
        "language": {"type": "STRING", "description": "Translate to."},
        "name": {"type": "STRING", "description": "Contact name."},
        "phone": {"type": "STRING", "description": "Contact phone."},
        "email": {"type": "STRING", "description": "Contact email."},
        "note": {"type": "STRING", "description": "Contact note."}}, "required": ["action"]},
    "handler": comms_plus,
}
