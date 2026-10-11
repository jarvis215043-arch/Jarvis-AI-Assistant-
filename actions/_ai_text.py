"""
actions/_ai_text.py — tiny helper so tools can ask Gemini for text or JSON.
Uses core/text_generation.py (retries, quota handling, Ollama backup) when it's
there, otherwise calls Gemini directly. Not a tool itself (no TOOL dict).
"""
import importlib.util
import json
import re
import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _text_generation():
    key = "jarvis_ext_text_generation"
    if key in sys.modules:
        return sys.modules[key]
    path = _base_dir() / "core" / "text_generation.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(key, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(key, None)
        return None
    return mod


def ask(prompt: str, json_mode: bool = False) -> str:
    tg = _text_generation()
    if tg is not None:
        return tg.generate_text(prompt, json_mode=json_mode)
    from google import genai
    from google.genai import types
    key = json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))["gemini_api_key"]
    client = genai.Client(api_key=key, http_options={"timeout": 60_000})
    cfg = types.GenerateContentConfig(response_mime_type="application/json") if json_mode else None
    return client.models.generate_content(model="gemini-flash-latest", contents=prompt, config=cfg).text or ""


def ask_json(prompt: str):
    raw = ask(prompt, json_mode=True).strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"(\[.*\]|\{.*\})", raw, re.S)
        return json.loads(m.group(1)) if m else None
