"""
actions/screen_ocr.py — Extracts the actual text on screen (real, quotable text,
not a description like the screen_process vision tool).

Two engines, tried in this order:
  1. Tesseract OCR — free and offline, but has to be installed on the PC.
     Found automatically in the usual install folders, or set 'tesseract_path'
     in config/api_keys.json.
  2. Gemini — used automatically when Tesseract isn't installed (or finds no
     text). Needs nothing extra: it uses the gemini_api_key Jarvis already has.
     Also reads Hindi/Marathi and handwriting better than Tesseract.

Can read the whole screen or just the active window.
"""
import io
import json
import os
import shutil
import sys
from pathlib import Path

import pyautogui

MAX_CHARS = 4000
GEMINI_MODEL = "gemini-flash-latest"
GEMINI_TIMEOUT_MS = 30_000


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _config() -> dict:
    try:
        return json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Screenshot ────────────────────────────────────────────────────────────────

def _grab(area: str):
    """Screenshot of the whole screen, or only the active window if asked."""
    if area == "window":
        try:
            win = pyautogui.getActiveWindow()
            if win and win.width > 50 and win.height > 50:
                left, top = max(0, win.left), max(0, win.top)
                return pyautogui.screenshot(region=(left, top, win.width, win.height)), "the active window"
        except Exception:
            pass  # fall back to the full screen
    return pyautogui.screenshot(), "the screen"


# ── Engine 1: Tesseract ───────────────────────────────────────────────────────

def _find_tesseract() -> str | None:
    """Config path first, then PATH, then the usual Windows install folders."""
    custom = str(_config().get("tesseract_path", "")).strip().strip('"')
    candidates = [custom] if custom else []
    on_path = shutil.which("tesseract")
    if on_path:
        candidates.append(on_path)
    candidates += [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        str(_base_dir() / "Tesseract-OCR" / "tesseract.exe"),   # copied next to Jarvis
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return None


def _ocr_tesseract(img) -> str | None:
    """Returns text, or None if Tesseract isn't available."""
    exe = _find_tesseract()
    if not exe:
        return None
    try:
        import pytesseract
    except ImportError:
        return None
    pytesseract.pytesseract.tesseract_cmd = exe

    # Screen text is small: 2x upscale + grayscale makes Tesseract far more accurate.
    from PIL import Image
    prepared = img.convert("L")
    prepared = prepared.resize((prepared.width * 2, prepared.height * 2), Image.LANCZOS)

    lang = str(_config().get("tesseract_lang", "eng")).strip() or "eng"
    try:
        return pytesseract.image_to_string(prepared, lang=lang).strip()
    except pytesseract.TesseractError:
        # Asked for a language pack that isn't installed — retry in English.
        return pytesseract.image_to_string(prepared, lang="eng").strip()


# ── Engine 2: Gemini ──────────────────────────────────────────────────────────

def _ocr_gemini(img) -> str:
    from google import genai
    from google.genai import types

    key = _config().get("gemini_api_key", "")
    if not key:
        raise RuntimeError("no gemini_api_key in config/api_keys.json")

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    client = genai.Client(api_key=key, http_options={"timeout": GEMINI_TIMEOUT_MS})
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png"),
            "Transcribe ALL readable text in this screenshot exactly as written, top to "
            "bottom, keeping line breaks and the original language. Skip icons, taskbar "
            "clock and window-control buttons. Output only the text, no commentary. "
            "If there is no readable text, output exactly: NO_TEXT",
        ],
    )
    text = (response.text or "").strip()
    return "" if text == "NO_TEXT" else text


# ── Tool ──────────────────────────────────────────────────────────────────────

def read_screen(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    area = str(params.get("area") or "screen").strip().lower()

    try:
        img, where = _grab(area)
    except Exception as e:
        msg = f"Sir, I couldn't take a screenshot: {e}"
        _log(msg, player)
        return msg

    text, engine, tess_error = None, "", ""
    try:
        text = _ocr_tesseract(img)
        engine = "Tesseract"
    except Exception as e:
        tess_error = str(e)
        text = None

    if not text:  # not installed, failed, or found nothing → let Gemini try
        try:
            text = _ocr_gemini(img)
            engine = "Gemini"
        except Exception as e:
            detail = f" (Tesseract: {tess_error})" if tess_error else ""
            msg = f"Sir, I couldn't read {where}: {e}{detail}"
            _log(msg, player)
            return msg

    if not text:
        msg = f"I don't see any readable text on {where}, sir."
        _log(msg, player)
        return msg

    _log(f"Read {len(text)} characters from {where} ({engine}).", player)
    _show(player, "Screen text", text)

    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n[trimmed — the full text is on the HUD]"
    return f"Text on {where}:\n{text}"


def _log(message: str, player=None) -> None:
    print(f"[ScreenOCR] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass


def _show(player, title: str, text: str) -> None:
    """Puts the full text in the HUD's content panel so it can be copied."""
    if player and hasattr(player, "show_content"):
        try:
            player.show_content(title, text)
        except Exception:
            pass


TOOL = {
    "name": "read_screen",
    "description": (
        "Extracts the actual text currently visible on screen — use for 'read this "
        "to me', 'summarize what's on screen', 'what does this say'. Different from "
        "screen_process (vision): this gets real text you can quote or summarize "
        "precisely, not a visual description. Use area='window' when the user means "
        "just the app/window they're looking at."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "area": {"type": "STRING", "description": "'screen' (default, everything) or 'window' (only the active window)."}
        },
        "required": [],
    },
    "handler": read_screen,
}