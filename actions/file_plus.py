"""actions/file_plus.py — File tools that run entirely on this PC (no AI, no cost):
batch rename, batch resize/convert images, compress images, merge PDFs, split /
extract PDF pages, zip a folder, unzip, and find duplicate files. Originals are
never overwritten — results go into a new folder/file."""
import hashlib
import os
import re
import zipfile
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
IMG = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}
DONE_NAME = {"resize": "resized", "convert": "converted", "compress": "compressed"}


def _pdf():
    """PdfReader/PdfWriter from PyPDF2, or from its newer replacement pypdf."""
    try:
        from PyPDF2 import PdfReader, PdfWriter
    except ImportError:
        from pypdf import PdfReader, PdfWriter
    return PdfReader, PdfWriter


def _folder(p, player) -> Path | None:
    raw = str(p.get("path") or "").strip().strip('"')
    if raw:
        f = Path(raw).expanduser()
        if not f.is_absolute():
            for base in (Path.home() / "Desktop", Path.home() / "Documents", Path.home() / "Downloads", Path.home() / "Pictures", Path.home()):
                if (base / raw).exists():
                    return base / raw
        return f if f.exists() else None
    cur = str(getattr(player, "current_file", "") or "")
    return Path(cur) if cur and Path(cur).exists() else None


def _files(folder: Path, exts=None):
    if folder.is_file():
        return [folder]
    return sorted(f for f in folder.iterdir() if f.is_file() and (exts is None or f.suffix.lower() in exts))


def file_plus(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    target = _folder(p, player)
    if target is None and act not in ():
        return "Which folder or file? Give me the path (e.g. 'Desktop\\Trip photos') or drop a file on the HUD."
    try:
        if act == "rename":
            pattern = str(p.get("pattern") or "file").strip()
            files = _files(target)
            plan = [(f, f.with_name(f"{pattern} {i:03d}{f.suffix.lower()}")) for i, f in enumerate(files, 1)]
            if any(n.exists() for _, n in plan):
                return "Some new names already exist — pick a different pattern."
            for f, n in plan:
                f.rename(n)
            return f"Renamed {len(plan)} files to '{pattern} 001…'."
        if act in ("resize", "convert", "compress"):
            from PIL import Image
            files = _files(target, IMG)
            if not files:
                return "No images there."
            out = (target if target.is_dir() else target.parent) / f"JARVIS {DONE_NAME[act]}"
            out.mkdir(exist_ok=True)
            fmt = str(p.get("format") or "").lower().lstrip(".")
            width = int(float(p.get("width") or 1280))
            q = int(float(p.get("quality") or (60 if act == "compress" else 90)))
            before = after = 0
            for f in files:
                im = Image.open(f)
                if act == "resize" and im.width > width:
                    im = im.resize((width, int(im.height * width / im.width)))
                ext = ("." + fmt) if (act == "convert" and fmt) else (".jpg" if act == "compress" else f.suffix.lower())
                dst = out / (f.stem + ext)
                if ext in (".jpg", ".jpeg"):
                    im = im.convert("RGB")
                im.save(dst, quality=q, optimize=True) if ext in (".jpg", ".jpeg", ".webp") else im.save(dst)
                before += f.stat().st_size; after += dst.stat().st_size
            return f"Done: {len(files)} image(s) in '{out.name}' ({before / 1e6:.1f} MB → {after / 1e6:.1f} MB)."
        if act == "pdf_merge":
            PdfReader, PdfWriter = _pdf()
            pdfs = [f for f in _files(target, {".pdf"}) if f.name != "merged.pdf"]
            if len(pdfs) < 2:
                return "Put at least two PDFs in the folder."
            w = PdfWriter()
            for f in pdfs:
                for pg in PdfReader(str(f)).pages:
                    w.add_page(pg)
            dst = (target if target.is_dir() else target.parent) / "merged.pdf"
            with open(dst, "wb") as fh:
                w.write(fh)
            return f"Merged {len(pdfs)} PDFs into merged.pdf."
        if act == "pdf_split":
            PdfReader, PdfWriter = _pdf()
            f = target if target.is_file() else next(iter(_files(target, {".pdf"})), None)
            if not f or f.suffix.lower() != ".pdf":
                return "Which PDF?"
            r = PdfReader(str(f)); n = len(r.pages)
            rng = str(p.get("pages") or "").strip()
            pages = []
            for part in rng.split(","):
                m = re.match(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*$", part)
                if m:
                    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
                    pages += [i for i in range(a, b + 1) if 1 <= i <= n]
            if not pages:
                out = f.parent / f"{f.stem} pages"; out.mkdir(exist_ok=True)
                for i, pg in enumerate(r.pages, 1):
                    w = PdfWriter(); w.add_page(pg); w.write(str(out / f"page {i:03d}.pdf"))
                return f"Split {n} pages into '{out.name}'."
            w = PdfWriter()
            for i in pages:
                w.add_page(r.pages[i - 1])
            dst = f.parent / f"{f.stem} (pages {rng}).pdf"; w.write(str(dst))
            return f"Saved pages {rng} as '{dst.name}'."
        if act == "zip":
            src = target
            dst = src.parent / f"{src.stem}.zip"
            with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
                if src.is_file():
                    z.write(src, src.name)
                else:
                    for dp, _, fns in os.walk(src):
                        for fn in fns:
                            fp = Path(dp) / fn; z.write(fp, fp.relative_to(src.parent))
            return f"Zipped to {dst.name} ({dst.stat().st_size / 1e6:.1f} MB)."
        if act == "unzip":
            if target.suffix.lower() != ".zip":
                return "That isn't a .zip file."
            out = target.with_suffix("")
            with zipfile.ZipFile(target) as z:
                for m_ in z.namelist():                         # never write outside the folder
                    if ".." in Path(m_).parts or Path(m_).is_absolute():
                        return "That zip has unsafe paths; I won't extract it."
                z.extractall(out)
            return f"Unzipped into '{out.name}'."
        if act == "duplicates":
            seen, dups = {}, []
            for dp, _, fns in os.walk(target):
                for fn in fns:
                    fp = Path(dp) / fn
                    try:
                        if fp.stat().st_size < 1024:
                            continue
                        h = hashlib.md5(fp.read_bytes()).hexdigest()
                    except Exception:
                        continue
                    if h in seen:
                        dups.append((fp, seen[h]))
                    else:
                        seen[h] = fp
            if not dups:
                return "No duplicate files found."
            waste = sum(a.stat().st_size for a, _ in dups)
            H.show(player, "DUPLICATES", "\n".join(f"{a.name}\n   = {b.name}  ({a.parent.name})" for a, b in dups[:30]))
            return f"Found {len(dups)} duplicate file(s) wasting {waste / 1e6:.1f} MB — listed on screen (nothing was deleted)."
    except Exception as e:
        return f"That didn't work: {e}"
    return "Files: rename (pattern), resize (width), convert (format), compress (quality), pdf_merge, pdf_split (pages), zip, unzip, duplicates."


TOOL = {
    "name": "file_plus",
    "description": ("File tools (local, never overwrite originals). path = a folder or file (or the file dropped on the HUD). "
                    "action='rename' (pattern), 'resize' (width), 'convert' (format jpg/png/webp), 'compress' (quality), "
                    "'pdf_merge' (folder of PDFs), 'pdf_split' (pages like '1-3,5'; empty = every page), 'zip', 'unzip', 'duplicates'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "path": {"type": "STRING", "description": "Folder or file path."},
        "pattern": {"type": "STRING", "description": "New base name for rename."},
        "width": {"type": "NUMBER", "description": "Max width in pixels."},
        "format": {"type": "STRING", "description": "Image format."},
        "quality": {"type": "NUMBER", "description": "JPEG quality 1-95."},
        "pages": {"type": "STRING", "description": "Pages to extract."}}, "required": ["action"]},
    "handler": file_plus,
}
