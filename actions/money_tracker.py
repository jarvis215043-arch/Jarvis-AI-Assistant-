"""actions/money_tracker.py — Pocket-money tracker: log spending and money in,
see the balance and weekly totals (memory/money.json, stays on this PC)."""
from datetime import date, timedelta

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
FILE = H.mem_path("money.json")


def money_tracker(parameters: dict, player=None) -> str:
    p = parameters or {}
    action = str(p.get("action") or "summary").lower()
    data = H.load_json(FILE, [])
    try:
        amount = round(abs(float(p.get("amount") or 0)), 2)
    except (TypeError, ValueError):
        amount = 0
    note = str(p.get("note") or "").strip()
    if action in ("spend", "spent", "income", "got", "add", "save"):
        if not amount:
            return "How much?"
        sign = -1 if action in ("spend", "spent") else 1
        data.append({"date": H.today(), "amount": sign * amount, "note": note})
        H.save_json(FILE, data)
        bal = sum(e["amount"] for e in data)
        return f"{'Spent' if sign < 0 else 'Added'} ₹{amount:g}{' on ' + note if note and sign < 0 else ''}. Balance: ₹{bal:g}."
    if action == "undo":
        if not data:
            return "Nothing to undo."
        e = data.pop(); H.save_json(FILE, data)
        return f"Removed the last entry (₹{abs(e['amount']):g} {e.get('note', '')})."
    bal = sum(e["amount"] for e in data)
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    week = [e for e in data if e["date"] >= week_ago]
    spent = -sum(e["amount"] for e in week if e["amount"] < 0)
    got = sum(e["amount"] for e in week if e["amount"] > 0)
    lines = [f"Balance: ₹{bal:g}", f"Last 7 days: spent ₹{spent:g}, got ₹{got:g}", ""]
    lines += [f"{e['date']}  {'−' if e['amount'] < 0 else '+'}₹{abs(e['amount']):g}  {e.get('note', '')}" for e in data[-12:]]
    H.show(player, "POCKET MONEY", "\n".join(lines))
    return f"Your balance is ₹{bal:g}. This week you spent ₹{spent:g} and got ₹{got:g}."


TOOL = {
    "name": "money_tracker",
    "description": ("Pocket-money tracker in rupees. action='spend' with amount and note; 'income' "
                    "with amount (pocket money, gifts); 'summary' (default) shows balance and the week; "
                    "'undo' removes the last entry."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'spend', 'income', 'summary' or 'undo'."},
        "amount": {"type": "NUMBER", "description": "Amount in rupees."},
        "note": {"type": "STRING", "description": "What it was for, e.g. 'snacks'."}},
        "required": []},
    "handler": money_tracker,
}
