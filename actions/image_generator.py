"""
actions/image_generator.py — High-quality image generation (and editing).

WHY THE OLD IMAGES LOOKED BAD
  They came from a free public service (Pollinations) using a model name it no
  longer offers, at 1024×1024, from the one-line description the voice model
  passed in.

NOW
  1. Your short request is first turned into a detailed art prompt (subject,
     style, lighting, composition, detail) by the small, cheap model — unless
     you say "exactly" / "literally".
  2. The picture is made by Google's Nano Banana image models on YOUR Gemini key,
     best model first, at 2K. Google has two API styles (the new "Interactions"
     and the classic generate_content); both are tried, and the first model +
     style that works on your key is remembered so later images are instant.
  3. The shape is picked from your words: wallpaper → 16:9, phone wallpaper /
     story → 9:16, portrait/poster → 3:4, otherwise square.
  4. "Edit the last image: make it night-time" edits the previous picture.
  5. If Gemini images aren't available on your key (some need billing), it falls
     back to an improved free Pollinations request — and says so.
  Settings (⚙ → Advanced Settings or config/api_keys.json):
    "image_provider": "auto" | "gemini" | "pollinations" | "openai"
    "image_model": force one Gemini model id      "image_size": "1K" | "2K" | "4K"
Images are saved in Pictures/JARVIS and opened.
"""
import base64
import json
import os
import random
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

GEMINI_MODELS = ["gemini-nano-banana-2.1", "gemini-3.1-flash-image", "gemini-3-pro-image",
                 "gemini-3-pro-image-preview", "gemini-2.5-flash-image"]
SHAPES = {"16:9": (1792, 1024), "9:16": (1024, 1792), "3:4": (1152, 1536), "4:3": (1536, 1152), "1:1": (1280, 1280)}
_last = {"path": None}


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _config() -> dict:
    try:
        return json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _state_file() -> Path:
    return _base_dir() / "memory" / "image_model.json"


def _output_dir() -> Path:
    out = Path.home() / "Pictures" / "JARVIS"
    try:
        out.mkdir(parents=True, exist_ok=True)
        return out
    except Exception:
        out = _base_dir() / "generated_images"
        out.mkdir(parents=True, exist_ok=True)
        return out


def _open_file(path: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))                      # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as e:
        print(f"[ImageGenerator] Could not open {path}: {e}")


def _say(player, text: str) -> None:
    """Spoken update. request_say injects text into the conversation, so it's
    labelled as a status line for JARVIS to relay — not something the user said."""
    if player and hasattr(player, "request_say"):
        try:
            player.request_say(f"[IMAGE STATUS — tell the user this in one short sentence, nothing else] {text}")
        except Exception:
            pass


def _log(message: str, player=None) -> None:
    print(f"[ImageGenerator] {message}")
    if player:
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass


def pick_shape(request: str) -> str:
    t = (request or "").lower()
    if any(w in t for w in ("phone wallpaper", "mobile wallpaper", "lock screen", "story", "reel", "vertical", "9:16")):
        return "9:16"
    if any(w in t for w in ("wallpaper", "desktop", "landscape", "banner", "thumbnail", "cinematic", "16:9", "widescreen")):
        return "16:9"
    if any(w in t for w in ("portrait", "poster", "book cover", "3:4")):
        return "3:4"
    return "1:1"


def _client(timeout_ms=120_000):
    from google import genai
    return genai.Client(api_key=_config().get("gemini_api_key", ""), http_options={"timeout": timeout_ms})


def improve_prompt(request: str) -> str:
    """Short request → detailed image prompt (cheap model). Keeps the user's intent."""
    t = request.lower()
    if any(w in t for w in ("exactly", "literally", "as written")):
        return request
    try:
        c = _client(30_000)
        rule = ("Rewrite this image request as ONE detailed prompt for an image generator (60-110 words): keep the "
                "subject and any style the user asked for; add composition, lighting, colours, mood, materials and fine "
                "detail; if no style is given, choose the most fitting (photorealistic, cinematic, illustration…). "
                "Any text that must appear goes in quotes. No real people's likenesses, nothing unsafe. "
                "Return only the prompt.\n\nRequest: " + request)
        for model in ("gemini-flash-lite-latest", "gemini-flash-latest"):
            try:
                out = (c.models.generate_content(model=model, contents=rule).text or "").strip()
                if len(out) > len(request):
                    return out
            except Exception:
                continue
    except Exception:
        pass
    return request


def _image_bytes_from_interaction(it) -> bytes | None:
    img = getattr(it, "output_image", None)
    data = getattr(img, "data", None) if img is not None else None
    if data:
        return base64.b64decode(data) if isinstance(data, str) else bytes(data)
    for o in getattr(it, "outputs", None) or []:
        d = getattr(o, "data", None)
        if d and "image" in str(getattr(o, "mime_type", "") or getattr(o, "type", "")):
            return base64.b64decode(d) if isinstance(d, str) else bytes(d)
    return None


def _image_bytes_from_response(r) -> bytes | None:
    for cand in getattr(r, "candidates", None) or []:
        for part in getattr(getattr(cand, "content", None), "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                d = inline.data
                return base64.b64decode(d) if isinstance(d, str) else bytes(d)
    return None


def _gemini_try(model: str, style: str, prompt: str, shape: str, size: str, edit_from: Path | None):
    """One attempt with one model + one API style. Returns image bytes or raises."""
    c = _client()
    if style == "interactions":
        if edit_from is not None or not hasattr(c, "interactions"):
            raise RuntimeError("interactions API not available here")
        it = c.interactions.create(model=model, input=prompt,
                                   response_format={"type": "image", "aspect_ratio": shape, "image_size": size})
        b = _image_bytes_from_interaction(it)
        if not b:
            raise RuntimeError("no image in the reply")
        return b
    from google.genai import types
    contents = prompt
    if edit_from is not None:
        from PIL import Image
        contents = [Image.open(edit_from), prompt]
    last = None
    for ic in ({"aspect_ratio": shape, "image_size": size}, {"aspect_ratio": shape}, None):
        try:
            cfg = types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"],
                                              **({"image_config": types.ImageConfig(**ic)} if ic else {}))
            r = c.models.generate_content(model=model, contents=contents, config=cfg)
            b = _image_bytes_from_response(r)
            if b:
                return b
            last = RuntimeError("no image in the reply (the request may have been declined)")
        except TypeError as e:            # older library: this ImageConfig option doesn't exist
            last = e
            continue
    raise last or RuntimeError("no image")


def _gemini(prompt: str, shape: str, edit_from: Path | None = None) -> tuple[bytes, str]:
    cfg = _config()
    size = str(cfg.get("image_size") or "2K").upper()
    forced = (cfg.get("image_model") or "").strip()
    try:
        remembered = json.loads(_state_file().read_text(encoding="utf-8"))
    except Exception:
        remembered = {}
    combos = []
    if remembered.get("model"):
        combos.append((remembered["model"], remembered.get("style", "classic")))
    for m in ([forced] if forced else GEMINI_MODELS):
        for st in ("interactions", "classic"):
            if (m, st) not in combos:
                combos.append((m, st))
    errors = []
    for model, style in combos:
        try:
            b = _gemini_try(model, style, prompt, shape, size, edit_from)
            if remembered.get("model") != model or remembered.get("style") != style:
                _state_file().parent.mkdir(parents=True, exist_ok=True)
                _state_file().write_text(json.dumps({"model": model, "style": style}), encoding="utf-8")
            return b, model
        except Exception as e:
            msg = str(e)
            errors.append(f"{model}/{style}: {msg[:90]}")
            if any(k in msg for k in ("API_KEY_INVALID", "API key not valid")):
                break
            if "SAFETY" in msg.upper() or "declined" in msg:
                raise RuntimeError("Google declined to draw that — try describing it differently.")
    raise RuntimeError("Gemini images unavailable on this key (" + "; ".join(errors[-3:]) + ")")


def _pollinations(prompt: str, shape: str) -> bytes:
    import requests
    w, h = SHAPES[shape]
    params = {"model": "flux", "width": w, "height": h, "nologo": "true", "enhance": "false",
              "safe": "true", "seed": random.randint(1, 10_000_000)}
    q = "&".join(f"{k}={v}" for k, v in params.items())
    r = requests.get(f"https://image.pollinations.ai/prompt/{quote(prompt[:1500])}?{q}", timeout=120)
    r.raise_for_status()
    if "image" not in r.headers.get("content-type", "image"):
        raise RuntimeError("the free service returned an error page")
    return r.content


def _openai(prompt: str, shape: str) -> bytes:
    import requests
    key = _config().get("openai_api_key", "")
    if not key:
        raise RuntimeError("No 'openai_api_key' set.")
    size = {"16:9": "1536x1024", "4:3": "1536x1024", "9:16": "1024x1536", "3:4": "1024x1536"}.get(shape, "1024x1024")
    r = requests.post("https://api.openai.com/v1/images/generations",
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": "gpt-image-1", "prompt": prompt, "n": 1, "size": size, "quality": "high"}, timeout=180)
    r.raise_for_status()
    return base64.b64decode(r.json()["data"][0]["b64_json"])


def _save(data: bytes, request: str) -> Path:
    from io import BytesIO
    slug = "".join(ch if ch.isalnum() else " " for ch in request).split()
    name = "_".join(slug[:6]) or "image"
    path = _output_dir() / f"{name}_{time.strftime('%Y%m%d_%H%M%S')}.png"
    try:
        from PIL import Image
        Image.open(BytesIO(data)).save(path, "PNG")       # lossless, whatever format came back
    except Exception:
        path = path.with_suffix(".jpg"); path.write_bytes(data)
    return path


def make(request: str, edit: bool = False, status=None) -> tuple[Path, str]:
    """Returns (saved path, how it was made). Raises with a friendly message.
    status(stage_text) is called at each step (for progress updates)."""
    status = status or (lambda s: None)
    provider = str(_config().get("image_provider") or "auto").lower()
    shape = pick_shape(request)
    edit_from = _last["path"] if edit else None
    if edit and (edit_from is None or not Path(edit_from).exists()):
        raise RuntimeError("there's no previous image to edit yet")
    if not edit:
        status("writing a detailed prompt")
    prompt = request if edit else improve_prompt(request)
    status(f"drawing it now ({'wide' if shape == '16:9' else 'tall' if shape in ('9:16', '3:4') else 'square'} format)")
    if provider == "openai":
        return _save(_openai(prompt, shape), request), "OpenAI gpt-image-1"
    if provider in ("auto", "gemini"):
        try:
            data, model = _gemini(prompt, shape, Path(edit_from) if edit_from else None)
            return _save(data, request), model
        except RuntimeError as e:
            if "declined" in str(e) or provider == "gemini" or edit:
                raise
            print(f"[ImageGenerator] {e} — using the free fallback")
            status("Google's image model isn't available on this key, so I'm using the free image service")
    return _save(_pollinations(prompt, shape), request), "free fallback (Pollinations) — lower quality"


def _update_every() -> int:
    """Seconds between spoken "still working" updates ("image_status_seconds", 0 = off)."""
    try:
        return int(float(_config().get("image_status_seconds", 12)))
    except Exception:
        return 12


def _work(request: str, edit: bool, player, session_memory):
    t0 = time.monotonic()
    state = {"stage": "starting", "done": False}

    def status(stage: str) -> None:            # each step → HUD log (quietly)
        state["stage"] = stage
        _log(f"Image: {stage}…", player)

    every = _update_every()

    def ticker():                              # every ~12 s → a short spoken update
        n = 0
        while not state["done"] and every > 0:
            time.sleep(1)
            el = int(time.monotonic() - t0)
            if not state["done"] and el >= every * (n + 1):
                n += 1
                msg = (f"Still working on your image — {state['stage']}, {el} seconds so far." if n < 4
                       else f"Almost there, sir — {el} seconds so far.")
                _log(msg, player); _say(player, msg)
    threading.Thread(target=ticker, daemon=True, name="image-status").start()
    try:
        path, how = make(request, edit, status)
    except Exception as e:
        state["done"] = True
        err = f"Sir, I couldn't {'edit' if edit else 'generate'} that image: {e}"
        _log(err, player); _say(player, err)
        return
    state["done"] = True
    _last["path"] = path
    _open_file(path)
    done = f"Here's your image, sir — done in {int(time.monotonic() - t0)} seconds, it's open now (saved in Pictures, JARVIS)."
    if "fallback" in how:
        done += " Note: Google's image model isn't available on this key, so this is the lower-quality free version."
    _log(f"{done} [{how}]", player)
    _say(player, done)
    if session_memory:
        try:
            session_memory.set_last_search(query=f"generate image: {request}", response=done)
        except Exception:
            pass


def generate_image(parameters: dict, player=None, session_memory=None) -> str:
    p = parameters or {}
    prompt = str(p.get("prompt", "")).strip()
    edit = str(p.get("mode") or "").lower() == "edit"
    if not prompt:
        msg = "Sir, I need a description of the image you'd like."
        _log(msg, player)
        return msg
    threading.Thread(target=_work, args=(prompt, edit, player, session_memory), daemon=True).start()
    msg = "On it, sir — " + ("editing the last image." if edit else "creating that image in high quality. It takes about 15 to 40 seconds — I'll keep you posted.")
    _log(msg, player)
    return msg


TOOL = {
    "name": "generate_image",
    "description": (
        "Creates a high-quality image from a description (or edits the last image with mode='edit'), in the "
        "background, and opens it. Pass the user's full description including style, mood, and words like "
        "'wallpaper', 'phone wallpaper' or 'poster' (they set the shape)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "Full description of the image, or the change to make when editing."},
            "mode": {"type": "STRING", "description": "'new' (default) or 'edit' (change the last image)."}},
        "required": ["prompt"]
    },
    "handler": generate_image,
}
