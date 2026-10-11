"""actions/live_info.py — Live information via search: stock and crypto prices,
sports scores (any sport), trending topics, air quality, sunrise/sunset,
gold/petrol prices and public holidays. Short answers to keep it quick and cheap."""
from datetime import date

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
ASK = {
    "stock":     "Current share price of {q} (stock) right now, with today's % change. One short line.",
    "crypto":    "Current price of {q} cryptocurrency in USD and INR, with 24h % change. One short line.",
    "sports":    "Latest score or result for {q} (live if a match is on now). One or two short lines.",
    "trending":  "Top 5 trending news topics in India right now{about}. One short line each.",
    "air":       "Current air quality index (AQI) in {city} and what it means for going outside. One short line.",
    "sun":       "Today's sunrise and sunset times in {city}. One short line.",
    "prices":    "Today's gold price (24K per 10 g) and petrol price per litre in {city}. One short line each.",
    "holidays":  "Public holidays in India in {month}{about} (date — name). Short list.",
}


def live_info(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    if act not in ASK:
        return "Live info: stock, crypto, sports, trending, air, sun, prices, holidays."
    q = str(p.get("query") or "").strip()
    if act in ("stock", "crypto", "sports") and not q:
        return "Which one?"
    city = str(p.get("city") or H.home_city() or "Delhi")
    try:
        out = H.ai_search(ASK[act].format(q=q, city=city, about=f" about {q}" if q else "",
                                          month=q if act == "holidays" and q else date.today().strftime("%B %Y")))
    except Exception as e:
        return f"I couldn't get that right now: {e}"
    if act in ("trending", "holidays"):
        H.show(player, act.upper(), out)
    return out[:900]


TOOL = {
    "name": "live_info",
    "description": ("Live info via search. action='stock' (query company), 'crypto' (query coin), 'sports' (query team/match/"
                    "league), 'trending' (optional query), 'air' (city), 'sun' (sunrise/sunset, city), 'prices' (gold & petrol, "
                    "city), 'holidays' (optional query month)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "query": {"type": "STRING", "description": "Company, coin, team, topic or month."},
        "city": {"type": "STRING", "description": "City (defaults to the user's city)."}}, "required": ["action"]},
    "handler": live_info,
}
