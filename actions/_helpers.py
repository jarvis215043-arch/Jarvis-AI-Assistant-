"""
actions/_helpers.py — shared helpers for JARVIS tools (not a tool itself).
Paths, small JSON stores, settings, Gemini text/JSON/vision, HUD and speech.
"""
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

MODEL = "gemini-flash-latest"


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


# ── storage ───────────────────────────────────────────────────────────────────
def mem_path(name: str) -> Path:
    p = base_dir() / "memory" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_json(path: Path, default):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def cfg() -> dict:
    return load_json(base_dir() / "config" / "api_keys.json", {})


def save_cfg(key: str, value) -> None:
    p = base_dir() / "config" / "api_keys.json"
    data = load_json(p, {})
    data[key] = value
    save_json(p, data)


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def home_city() -> str:
    city = str(cfg().get("home_city") or "").strip()
    if city:
        return city
    ident = load_json(mem_path("long_term.json"), {}).get("identity", {})
    for k in ("city", "home_city", "location", "lives_in"):
        e = ident.get(k)
        v = (e.get("value", "") if isinstance(e, dict) else str(e or "")).strip()
        if v:
            return v
    return ""


# ── Gemini ────────────────────────────────────────────────────────────────────
def _client(timeout_ms: int = 60_000):
    from google import genai
    return genai.Client(api_key=cfg().get("gemini_api_key", ""), http_options={"timeout": timeout_ms})


def ai_text(prompt: str, json_mode: bool = False) -> str:
    from google.genai import types
    conf = types.GenerateContentConfig(response_mime_type="application/json") if json_mode else None
    r = _client().models.generate_content(model=MODEL, contents=prompt, config=conf)
    return (r.text or "").strip()


FAST_MODELS = ["gemini-flash-lite-latest", MODEL]


def ai_fast(prompt: str, json_mode: bool = False) -> str:
    """For simple text jobs (rewrite, define, caption…): the small, cheap, fast
    model first; the normal model only if that fails. Cheaper AND quicker."""
    from google.genai import types
    conf = types.GenerateContentConfig(response_mime_type="application/json") if json_mode else None
    last = None
    for model in FAST_MODELS:
        try:
            r = _client(30_000).models.generate_content(model=model, contents=prompt, config=conf)
            if (r.text or "").strip():
                return r.text.strip()
        except Exception as e:
            last = e
    raise RuntimeError(f"AI unavailable: {last}")


def ai_fast_json(prompt: str):
    raw = ai_fast(prompt, json_mode=True)
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"(\[.*\]|\{.*\})", raw, re.S)
        return json.loads(m.group(1)) if m else None


def clipboard_text() -> str:
    try:
        import pyperclip
        return (pyperclip.paste() or "").strip()
    except Exception:
        return ""


def to_clipboard(text: str) -> bool:
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def ai_json(prompt: str):
    raw = ai_text(prompt, json_mode=True)
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"(\[.*\]|\{.*\})", raw, re.S)
        return json.loads(m.group(1)) if m else None


def tinyfish_answer(question: str) -> str | None:
    """FREE search via TinyFish (if "tinyfish_api_key" is set) + the cheap fast
    model to answer from the results. None → caller falls back to Gemini search."""
    import os
    key = (cfg().get("tinyfish_api_key") or os.environ.get("TINYFISH_API_KEY") or "").strip()
    if not key:
        return None
    try:
        import requests
        q = re.split(r"(?<=[?.!])\s", question.strip().split("\n")[0])[0][:150]
        r = requests.get("https://api.search.tinyfish.ai", params={"query": q}, headers={"X-API-Key": key}, timeout=10)
        res = ((r.json() or {}).get("results") or []) if r.status_code == 200 else []
        if not res:
            return None
        ctx = "\n".join(f"[{i}] {x.get('title', '')} — {x.get('snippet', '')} ({x.get('site_name') or x.get('url', '')})"
                        for i, x in enumerate(res[:6], 1))
        ans = ai_fast(f"Today is {datetime.now():%d %B %Y}. Using ONLY these web search results, answer: {question}\n"
                      "If the results don't contain the answer, reply exactly NO_ANSWER.\n\nResults:\n" + ctx)
        return None if (not ans or "NO_ANSWER" in ans) else ans
    except Exception:
        return None


def ai_search(question: str) -> str:
    """Fresh web info: TinyFish (free) first if a key is set; otherwise, or if
    that fails, Gemini's Google Search grounding."""
    tf = tinyfish_answer(question)
    if tf:
        return tf
    from google.genai import types
    conf = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
    r = _client(30_000).models.generate_content(model=MODEL, contents=question, config=conf)
    return (r.text or "").strip()


def to_jpeg(img, max_side: int = 1280) -> bytes:
    """PIL image → JPEG bytes, resized so the longest side is max_side."""
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def ai_vision(prompt: str, images: list) -> str:
    """images: JPEG/PNG bytes. Returns Gemini's text answer."""
    from google.genai import types
    parts = [types.Part.from_bytes(data=b, mime_type="image/jpeg") for b in images]
    r = _client().models.generate_content(model=MODEL, contents=parts + [prompt])
    return (r.text or "").strip()


def ai_file(prompt: str, path: str) -> str:
    """Upload a file (audio, video, PDF) and ask about it."""
    c = _client(300_000)
    f = c.files.upload(file=str(path))
    import time
    for _ in range(60):                      # wait until the file is processed
        state = str(getattr(getattr(f, "state", None), "name", getattr(f, "state", "")))
        if "PROCESSING" not in state.upper():
            break
        time.sleep(2)
        f = c.files.get(name=f.name)
    r = c.models.generate_content(model=MODEL, contents=[f, prompt])
    return (r.text or "").strip()


# ── HUD / speech (via the tool bus) ───────────────────────────────────────────
def _bus():
    try:
        from core import tool_bus
        return tool_bus
    except Exception:
        return None


def show(player, title: str, text: str) -> None:
    if player is not None and hasattr(player, "show_content"):
        try:
            player.show_content(title, text)
            return
        except Exception:
            pass
    b = _bus()
    if b:
        b.show(title, text)


def log(player, text: str) -> None:
    print(text)
    if player is not None:
        try:
            player.write_log(text)
            return
        except Exception:
            pass
    b = _bus()
    if b:
        b.log(text)


def say(text: str) -> None:
    b = _bus()
    if b:
        b.say(text)


def on_ready(fn) -> None:
    b = _bus()
    if b:
        b.on_ready(fn)


def documents_dir(sub: str = "") -> Path:
    p = Path.home() / "Documents" / "JARVIS" / sub if sub else Path.home() / "Documents" / "JARVIS"
    p.mkdir(parents=True, exist_ok=True)
    return p
