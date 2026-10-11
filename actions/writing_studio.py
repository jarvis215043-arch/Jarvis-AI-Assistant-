"""actions/writing_studio.py — 14 writing helpers. Works on text you give, the
text on your clipboard, or the file dropped on the HUD. The result appears on
the HUD and is copied to your clipboard, ready to paste. Uses the small, fast model."""
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
NEEDS_TEXT = {"summarise", "formal", "casual", "grammar", "shorten", "expand", "translate", "email_reply", "bullets_to_text"}
JOBS = {
    "summarise":    "Summarise this in 3-5 short bullet points a student can read quickly:\n{text}",
    "formal":       "Rewrite this in a polite, formal tone. Keep the meaning:\n{text}",
    "casual":       "Rewrite this in a friendly, casual tone. Keep the meaning:\n{text}",
    "grammar":      "Fix spelling, grammar and punctuation only. Keep the writer's words and style. Return just the fixed text:\n{text}",
    "shorten":      "Make this about half as long, keeping every key point:\n{text}",
    "expand":       "Expand this into a fuller, well-structured version (about twice as long), same voice:\n{text}",
    "translate":    "Translate this into {lang}. Return only the translation:\n{text}",
    "email_reply":  "Write a short, polite reply to this email/message{extra}. Return only the reply:\n{text}",
    "bullets_to_text": "Turn these notes/bullets into smooth, connected paragraphs:\n{text}",
    "caption":      "Write 3 short, catchy social-media captions (with 1-2 emojis each) for: {topic}",
    "hashtags":     "Give 12 relevant hashtags for a post about: {topic}. One line, space-separated.",
    "titles":       "Give 6 catchy titles for: {topic}. One per line.",
    "poem":         "Write a short original poem (8-12 lines) about: {topic}{extra}",
    "speech":       "Write a {length} speech for a school student about: {topic}{extra}. Clear opening, 3 points, strong ending.",
    "thank_you":    "Write a warm, short thank-you note to {topic}{extra}.",
}


def writing_studio(parameters: dict, player=None) -> str:
    p = parameters or {}
    job = str(p.get("action") or "").lower().replace(" ", "_").replace("summarize", "summarise")
    if job not in JOBS:
        return "Writing studio: " + ", ".join(JOBS) + "."
    text = str(p.get("text") or "").strip()
    if job in NEEDS_TEXT and not text:
        f = str(getattr(player, "current_file", "") or "")
        if f and Path(f).suffix.lower() in (".txt", ".md") and Path(f).exists():
            text = Path(f).read_text(encoding="utf-8", errors="replace")
        else:
            text = H.clipboard_text()
    if job in NEEDS_TEXT and not text:
        return "Copy the text first (or type it / drop a .txt file on the HUD), then ask again."
    topic = str(p.get("topic") or text or "").strip()
    if job not in NEEDS_TEXT and not topic:
        return "What's it about?"
    extra = str(p.get("details") or "").strip()
    prompt = JOBS[job].format(text=text[:12000], topic=topic[:500], lang=p.get("language") or "English",
                              length=p.get("length") or "2-minute", extra=(" — " + extra) if extra else "")
    try:
        out = H.ai_fast(prompt)
    except Exception as e:
        return f"I couldn't do that right now: {e}"
    H.show(player, f"WRITING — {job.replace('_', ' ').upper()}", out)
    copied = H.to_clipboard(out)
    return (f"[WRITING] Done — it's on screen{' and copied to the clipboard' if copied else ''}. "
            "Tell the user in one sentence; read it aloud only if it's short:\n" + out[:1500])


TOOL = {
    "name": "writing_studio",
    "description": ("Writing helpers; result shown on the HUD and copied to the clipboard. On text (text, else clipboard): "
                    "action='summarise','formal','casual','grammar','shorten','expand','translate' (language),"
                    "'email_reply' (details),'bullets_to_text'. From a topic: 'caption','hashtags','titles','poem',"
                    "'speech' (length),'thank_you' (topic = who/what for)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "text": {"type": "STRING", "description": "Text to work on (optional — clipboard is used otherwise)."},
        "topic": {"type": "STRING", "description": "Topic for captions/poems/speeches etc."},
        "language": {"type": "STRING", "description": "Target language for translate."},
        "length": {"type": "STRING", "description": "Speech length, e.g. '2-minute'."},
        "details": {"type": "STRING", "description": "Extra instructions."}}, "required": ["action"]},
    "handler": writing_studio,
}
