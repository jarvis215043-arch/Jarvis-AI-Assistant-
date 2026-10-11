"""actions/recall.py — Smart memory: "what did I say about my science project
last week?", "when is Rahul's birthday?", "what did I decide about the guitar?".

Searches EVERYTHING JARVIS has saved — past conversations, memos, journal,
sticky notes, goals, doubts, exams, to-dos, contacts, watchlist, long-term
memory… — with a fast keyword-relevance search (BM25) that runs on this PC for
free. Only the final step (turning the best matches into one answer) uses the
small, cheap model. action='search' skips even that and just lists the matches.
Nothing leaves the PC except the few matching snippets used for the answer."""
import json
import math
import re
from collections import Counter
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
SKIP_JSON = {"screen_time.json", "flashcards_srs.json", "drill_scores.json", "downloads_tidy.json",
             "system_alerts.json", "birthdays_notified.json", "rain_alert.json"}
STOP = set("a an the is are was were be to of and or in on at for with my me i you it this that what when where who "
           "how did do does about from by as we our your his her their they them there here can could would should "
           "have has had will just so if not no yes ok".split())
_cache = {"sig": None, "docs": [], "idx": None}


def _tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in STOP or len(w) < 2:
            continue
        for suf in ("ing", "ed", "es", "s"):                 # light stemming: project/projects, plan/planned
            if len(w) > 4 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


def _flatten(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten(v, f"{prefix}{k}: " if not prefix else f"{prefix}{k} ")
    elif isinstance(obj, list):
        for v in obj:
            yield from _flatten(v, prefix)
    elif obj not in (None, "", True, False):
        yield f"{prefix}{obj}"


def _collect(mem: Path) -> list[dict]:
    docs = []
    ch = mem / "chat_history"
    if ch.exists():
        for f in sorted(ch.glob("*.txt")):
            lines = [l.strip() for l in f.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
            for i in range(0, len(lines), 5):                # small windows → precise matches
                docs.append({"src": "conversation", "date": f.stem, "text": " ".join(lines[max(0, i - 1): i + 6])})
    jd = mem / "journal"
    if jd.exists():
        for f in sorted(jd.glob("*.txt")):
            for part in f.read_text(encoding="utf-8", errors="replace").split("\n\n"):
                if part.strip():
                    docs.append({"src": "journal", "date": f.stem, "text": part.strip()})
    for f in sorted(mem.glob("*.json")):
        if f.name in SKIP_JSON:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            text = " | ".join(_flatten(it))[:1500]
            if text.strip():
                date = (it.get("date") or it.get("time") or it.get("created") or "") if isinstance(it, dict) else ""
                docs.append({"src": f.stem.replace("_", " "), "date": str(date)[:16], "text": text})
    return docs


def _index():
    mem = H.mem_path("x").parent
    files = [p for p in mem.rglob("*") if p.is_file() and p.suffix in (".json", ".txt")]
    sig = tuple(sorted((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files))
    if sig != _cache["sig"]:
        docs = _collect(mem)
        toks = [Counter(_tokens(d["text"] + " " + d["src"])) for d in docs]
        df = Counter()
        for t in toks:
            df.update(t.keys())
        avg = sum(sum(t.values()) for t in toks) / max(1, len(toks))
        _cache.update(sig=sig, docs=docs, idx=(toks, df, avg))
    return _cache["docs"], _cache["idx"]


def search(query: str, k: int = 8) -> list[dict]:
    docs, (toks, df, avg) = _index()
    q = _tokens(query)
    if not q or not docs:
        return []
    n = len(docs)
    scores = []
    for i, t in enumerate(toks):
        dl = sum(t.values()) or 1
        s = 0.0
        for w in q:
            f = t.get(w, 0)
            if f:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * dl / avg))
        if s > 0:
            scores.append((s, i))
    scores.sort(reverse=True)
    return [dict(docs[i], score=round(s, 2)) for s, i in scores[:k]]


def recall(parameters: dict, player=None) -> str:
    p = parameters or {}
    q = str(p.get("query") or "").strip()
    if not q:
        return "What should I look for?"
    hits = search(q)
    if not hits:
        return f"I don't have anything saved about '{q}'."
    listing = "\n".join(f"[{h['src']}{', ' + h['date'] if h['date'] else ''}] {h['text'][:400]}" for h in hits)
    if str(p.get("action") or "ask").lower() == "search":
        H.show(player, f"MEMORY — {q}", listing)
        return f"Found {len(hits)} matching notes (on screen). Best: {hits[0]['text'][:200]}"
    try:
        ans = H.ai_fast("Answer the user's question using ONLY these saved notes from their own JARVIS. Mention when it "
                        "was (the date) if known. If the notes don't answer it, say you don't have a note about that.\n"
                        f"Question: {q}\n\nNotes:\n{listing}")
    except Exception:
        ans = "Here's what I found: " + hits[0]["text"][:300]
    H.show(player, f"MEMORY — {q}", ans + "\n\n— matches —\n" + listing)
    return ans


TOOL = {
    "name": "recall",
    "description": ("Search everything the user told or saved in JARVIS before (past conversations, memos, journal, notes, "
                    "goals, doubts, exams, to-dos, contacts, watchlist, long-term memory) and answer from it. Use for 'what "
                    "did I say/decide about…', 'when did I…', 'did I ever mention…'. action='ask' (default) or 'search' "
                    "(just list matches); query = what to look for."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'ask' or 'search'."},
        "query": {"type": "STRING", "description": "What to look for, in the user's words."}}, "required": ["query"]},
    "handler": recall,
}
