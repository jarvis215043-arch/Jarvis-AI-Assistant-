"""actions/file_finder.py — Find files by description ("the photo of my dog from
last month", "my science project PowerPoint"). Searches Desktop, Documents,
Pictures, Downloads, Videos and Music; for photos it actually looks at them."""
import os
import subprocess
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
_last: list = []
IMG = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp", ".gif"}


def _roots():
    h = Path.home()
    return [h / n for n in ("Desktop", "Documents", "Pictures", "Downloads", "Videos", "Music", "OneDrive")
            if (h / n).exists()]


def _scan(limit: int = 6000):
    files = []
    for root in _roots():
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if not d.startswith(".") and d not in ("node_modules", "__pycache__", "AppData")]
            for fn in fns:
                fp = Path(dp) / fn
                try:
                    stt = fp.stat()
                except Exception:
                    continue
                files.append((fp, stt.st_mtime, stt.st_size))
                if len(files) >= limit * 3:
                    break
    files.sort(key=lambda x: -x[1])
    return files[:limit]


def file_finder(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "find").lower()
    if action == "open":
        try:
            f = _last[int(float(p.get("number") or 1)) - 1]
        except Exception:
            return "Which result number?"
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(f)])
        return f"Showing {f.name} in File Explorer."
    desc = str(p.get("description") or "").strip()
    if not desc:
        return "Describe the file you're looking for."
    plan = H.ai_json(
        f"A user wants to find a file on their PC: \"{desc}\". Today is {datetime.now():%Y-%m-%d}. "
        'Return ONLY JSON: {"keywords": [words likely in the file name, lowercase], "extensions": [like ".jpg"], '
        '"date_from": "YYYY-MM-DD or empty", "date_to": "YYYY-MM-DD or empty", "is_photo_content": true if '
        'they describe what is IN a picture}') or {}
    exts = {e.lower() if e.startswith(".") else "." + e.lower() for e in plan.get("extensions") or []}
    kws = [k.lower() for k in plan.get("keywords") or [] if len(k) > 1]
    def ts(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").timestamp()
        except Exception:
            return None
    t0, t1 = ts(plan.get("date_from") or ""), ts(plan.get("date_to") or "")
    if t1:
        t1 += 86400
    cands = [(f, m, s) for f, m, s in _scan()
             if (not exts or f.suffix.lower() in exts) and (not t0 or m >= t0) and (not t1 or m <= t1)]
    scored = sorted(cands, key=lambda x: -sum(k in x[0].name.lower() for k in kws))
    named = [c for c in scored if kws and any(k in c[0].name.lower() for k in kws)]
    picks = named[:10]
    if plan.get("is_photo_content"):
        imgs, thumbs = [], []
        try:
            from PIL import Image
        except Exception:
            Image = None
        for c in cands:
            if Image is None or len(imgs) >= 16:
                break
            if c[0].suffix.lower() not in IMG:
                continue
            try:                                   # skip unreadable / corrupted pictures
                thumbs.append(H.to_jpeg(Image.open(c[0]), 384))
                imgs.append(c)
            except Exception:
                continue
        if imgs:
            try:
                ans = H.ai_vision(f"These are {len(thumbs)} photos numbered 1 to {len(thumbs)} in order. "
                                  f"Which match: \"{desc}\"? Reply ONLY with matching numbers separated by commas, or NONE.", thumbs)
                nums = [int(x) for x in ans.replace(" ", "").split(",") if x.isdigit()]
                picks = [imgs[n - 1] for n in nums if 1 <= n <= len(imgs)] + [c for c in picks if c not in imgs]
            except Exception:
                pass
    if not picks:
        picks = scored[:5] if kws == [] else []
    if not picks:
        return f"I couldn't find a file matching \"{desc}\". Try other words, or tell me roughly when you made it."
    _last[:] = [c[0] for c in picks[:8]]
    H.show(player, "FILES FOUND", "\n".join(f"{i}. {f.name}\n   {f.parent}   ({datetime.fromtimestamp(m):%d %b %Y})"
                                            for i, (f, m, s) in enumerate(picks[:8], 1)))
    return f"Found {len(_last)} likely match(es); they're on screen. Best: {_last[0].name}. Say 'open number 1' to show it."


TOOL = {
    "name": "file_finder",
    "description": ("Finds files by description, including what's in a photo ('the photo of my dog from "
                    "last month', 'my science PowerPoint'). action='find' (default) with description; "
                    "'open' with number to show a result in File Explorer."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'find' or 'open'."},
        "description": {"type": "STRING", "description": "What the file is / looks like / when it was made."},
        "number": {"type": "NUMBER", "description": "For open: result number."}}, "required": []},
    "handler": file_finder,
}
