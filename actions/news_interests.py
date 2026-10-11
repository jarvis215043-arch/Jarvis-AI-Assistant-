"""actions/news_interests.py — A news digest only on topics you pick
(cricket, space, gaming...). Topics saved in memory/news_interests.json."""
import concurrent.futures as cf

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
FILE = H.mem_path("news_interests.json")


def news_interests(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "digest").lower()
    topic = str(p.get("topic") or "").strip().lower()
    topics = H.load_json(FILE, [])
    if action == "add":
        if not topic:
            return "Which topic?"
        if topic not in topics:
            topics.append(topic); H.save_json(FILE, topics)
        return f"Added {topic}. Your news topics: {', '.join(topics)}."
    if action == "remove":
        topics = [t for t in topics if t != topic]; H.save_json(FILE, topics)
        return f"Removed {topic}." + (f" Topics left: {', '.join(topics)}." if topics else "")
    if action == "list":
        return f"Your news topics: {', '.join(topics)}." if topics else "No news topics yet. Try 'add cricket to my news'."
    if not topics:
        return "You haven't picked any news topics yet. Try 'add cricket and space to my news'."
    def one(t):
        try:
            return t, H.ai_search(f"Latest news about {t} from the last 2 days: 2 short headlines with one-line summaries, plain text.")
        except Exception as e:
            return t, f"(couldn't fetch: {e})"
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(one, topics[:8]))
    text = "\n\n".join(f"■ {t.upper()}\n{r}" for t, r in results)
    H.show(player, "YOUR NEWS", text)
    return "[NEWS DIGEST] It's on screen. Give the user the single most interesting item from each topic in one sentence each:\n" + text[:3000]


TOOL = {
    "name": "news_interests",
    "description": ("Personal news digest on the user's chosen topics. action='digest' (default); "
                    "'add' / 'remove' with topic; 'list'."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'digest', 'add', 'remove' or 'list'."},
        "topic": {"type": "STRING", "description": "A topic, e.g. 'cricket'."}}, "required": []},
    "handler": news_interests,
}
