"""actions/media_plus.py — Photo collage, meme maker, GIF maker, photo filters,
NASA's space photo of the day (optionally as wallpaper), and photo info (date,
camera, size). Everything except the space photo runs locally."""
import ctypes
import os
import sys
from datetime import datetime
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
IMG = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _src(p, player) -> Path | None:
    raw = str(p.get("path") or "").strip().strip('"') or str(getattr(player, "current_file", "") or "")
    if not raw:
        return None
    f = Path(raw).expanduser()
    if not f.is_absolute():
        for base in (Path.home() / "Pictures", Path.home() / "Desktop", Path.home() / "Downloads"):
            if (base / raw).exists():
                return base / raw
    return f if f.exists() else None


def _open(f: Path):
    if sys.platform == "win32":
        os.startfile(str(f))      # type: ignore[attr-defined]


def _font(size):
    from PIL import ImageFont
    for name in ("impact.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def media_plus(parameters: dict, player=None) -> str:
    from PIL import Image, ImageDraw, ImageFilter, ImageOps
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    out_dir = H.documents_dir("Media")
    stamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
    try:
        if act == "space_photo":
            import requests
            j = requests.get("https://api.nasa.gov/planetary/apod", params={"api_key": H.cfg().get("nasa_api_key", "DEMO_KEY")}, timeout=20).json()
            if j.get("media_type") != "image":
                return f"Today's NASA picture is a video: {j.get('title')} — {j.get('url')}"
            img = requests.get(j.get("hdurl") or j["url"], timeout=60).content
            f = out_dir / f"NASA {j.get('date')}.jpg"; f.write_bytes(img)
            if str(p.get("wallpaper")).lower() in ("true", "1", "yes") and sys.platform == "win32":
                ctypes.windll.user32.SystemParametersInfoW(20, 0, str(f), 3)
                return f"Today's space photo, '{j.get('title')}', is now your wallpaper. {j.get('explanation', '')[:250]}"
            _open(f)
            return f"NASA's space photo of the day: '{j.get('title')}'. {j.get('explanation', '')[:300]}"
        src = _src(p, player)
        if src is None:
            return "Which photo or folder? Drop it on the HUD or give the path."
        if act == "info":
            im = Image.open(src)
            exif = im.getexif()
            taken = exif.get(36867) or exif.get(306) or datetime.fromtimestamp(src.stat().st_mtime).strftime("%Y:%m:%d %H:%M")
            cam = " ".join(str(x) for x in (exif.get(271), exif.get(272)) if x)
            return f"{src.name}: {im.width}×{im.height}, {src.stat().st_size / 1e6:.1f} MB, taken {taken}{', camera ' + cam if cam else ''}."
        if act == "filter":
            kind = str(p.get("kind") or "grayscale").lower()
            im = Image.open(src).convert("RGB")
            if "gray" in kind or "black" in kind:
                im = ImageOps.grayscale(im)
            elif "sepia" in kind:
                g = ImageOps.grayscale(im); im = ImageOps.colorize(g, "#2e1a05", "#f5deb3")
            elif "blur" in kind:
                im = im.filter(ImageFilter.GaussianBlur(6))
            elif "sharp" in kind:
                im = im.filter(ImageFilter.SHARPEN)
            elif "invert" in kind:
                im = ImageOps.invert(im)
            elif "orange" in kind or "jarvis" in kind:
                g = ImageOps.grayscale(im); im = ImageOps.colorize(g, "#000000", "#ff7a1a", "#ffe2c4")
            elif "cartoon" in kind or "poster" in kind:
                im = ImageOps.posterize(im, 3)
            f = out_dir / f"{src.stem} {kind}.jpg"; im.save(f, quality=92); _open(f)
            return f"Applied '{kind}' — saved as a new photo in Documents, JARVIS, Media."
        if act == "meme":
            top, bottom = str(p.get("top") or "").upper(), str(p.get("bottom") or "").upper()
            im = Image.open(src).convert("RGB")
            d = ImageDraw.Draw(im); size = max(24, im.width // 12); font = _font(size)
            for text, y in ((top, size // 3), (bottom, im.height - size - size // 2)):
                if not text:
                    continue
                w = d.textlength(text, font=font)
                d.text(((im.width - w) / 2, y), text, font=font, fill="white", stroke_width=max(2, size // 15), stroke_fill="black")
            f = out_dir / f"meme {stamp}.jpg"; im.save(f, quality=92); _open(f)
            return "Meme made and opened (saved in Documents, JARVIS, Media)."
        files = [src] if src.is_file() else sorted(x for x in src.iterdir() if x.suffix.lower() in IMG)
        if act == "collage":
            files = files[:12]
            if len(files) < 2:
                return "I need at least 2 photos (give me a folder)."
            cols = 3 if len(files) > 4 else 2
            rows = (len(files) + cols - 1) // cols
            cell = 400
            sheet = Image.new("RGB", (cols * cell + (cols + 1) * 10, rows * cell + (rows + 1) * 10), (10, 10, 10))
            for i, f in enumerate(files):
                im = ImageOps.fit(Image.open(f).convert("RGB"), (cell, cell))
                sheet.paste(im, (10 + (i % cols) * (cell + 10), 10 + (i // cols) * (cell + 10)))
            f = out_dir / f"collage {stamp}.jpg"; sheet.save(f, quality=90); _open(f)
            return f"Collage of {len(files)} photos made and opened."
        if act == "gif":
            files = files[:40]
            if len(files) < 2:
                return "I need at least 2 images (give me a folder)."
            frames = [ImageOps.contain(Image.open(f).convert("RGB"), (640, 640)) for f in files]
            f = out_dir / f"animation {stamp}.gif"
            frames[0].save(f, save_all=True, append_images=frames[1:], duration=int(float(p.get("ms") or 400)), loop=0)
            _open(f)
            return f"GIF with {len(frames)} frames made and opened."
    except Exception as e:
        return f"That didn't work: {e}"
    return "Media: collage, meme (top, bottom), gif (ms), filter (kind), info, space_photo (wallpaper)."


TOOL = {
    "name": "media_plus",
    "description": ("Photos & media (saved in Documents/JARVIS/Media). path = photo or folder (or the file dropped on the HUD). "
                    "action='collage' (folder), 'meme' (top, bottom text), 'gif' (folder, ms per frame), 'filter' (kind grayscale/"
                    "sepia/blur/sharpen/invert/orange/cartoon), 'info' (date, camera, size), 'space_photo' (NASA picture of the day; "
                    "wallpaper=true to set it)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "path": {"type": "STRING", "description": "Photo or folder path."},
        "top": {"type": "STRING", "description": "Meme top text."},
        "bottom": {"type": "STRING", "description": "Meme bottom text."},
        "kind": {"type": "STRING", "description": "Filter name."},
        "ms": {"type": "NUMBER", "description": "GIF frame time in ms."},
        "wallpaper": {"type": "BOOLEAN", "description": "Set the space photo as wallpaper."}}, "required": ["action"]},
    "handler": media_plus,
}
