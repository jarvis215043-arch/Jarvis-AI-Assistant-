"""actions/math_tools.py — 9 maths helpers. Almost all run locally (no AI, no
cost): primes & factors, GCD/LCM, percentages/discounts/tips, number bases,
dice/coins/random picks, statistics, fractions, and a graph plotter. Only
'solve' (step-by-step equations) asks the fast AI model."""
import math
import os
import random
import statistics as st
import sys
from fractions import Fraction

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


def _nums(text) -> list:
    import re
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", str(text or ""))]


def _factors(n: int):
    out, d = [], 2
    while d * d <= n:
        while n % d == 0:
            out.append(d); n //= d
        d += 1
    if n > 1:
        out.append(n)
    return out


def math_tools(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    v = _nums(p.get("numbers") or p.get("expression") or "")
    try:
        if act == "solve":
            eq = str(p.get("expression") or "").strip()
            if not eq:
                return "Which equation?"
            out = H.ai_fast(f"Solve step by step for a school student, numbered steps, final answer last: {eq}")
            H.show(player, "SOLVE", out)
            return out[:1200]
        if act == "prime":
            n = int(v[0])
            if n < 2:
                return f"{n} is not prime."
            f = _factors(n)
            return f"{n} is prime." if len(f) == 1 else f"{n} is not prime: {' × '.join(map(str, f))}."
        if act == "gcd_lcm":
            ints = [int(x) for x in v]
            if len(ints) < 2:
                return "Give me at least two numbers."
            g = ints[0]; l = ints[0]
            for x in ints[1:]:
                g = math.gcd(g, x); l = l * x // math.gcd(l, x)
            return f"GCD (HCF) = {g}, LCM = {l}."
        if act == "percent":
            kind = str(p.get("kind") or "of").lower()
            a, b = (v + [0, 0])[:2]
            if kind == "of":
                return f"{a:g}% of {b:g} = {a * b / 100:g}."
            if kind == "discount":
                return f"{b:g}% off {a:g} = {a * (1 - b / 100):g} (you save {a * b / 100:g})."
            if kind == "tip":
                ppl = int(v[2]) if len(v) > 2 else 1
                tot = a * (1 + b / 100)
                return f"Bill {a:g} + {b:g}% tip = {tot:.2f}" + (f", that's {tot / ppl:.2f} each for {ppl}." if ppl > 1 else ".")
            if kind == "change":
                return f"From {a:g} to {b:g} is a {((b - a) / a * 100) if a else 0:+.1f}% change."
            return f"{a:g} is {a / b * 100 if b else 0:.1f}% of {b:g}."
        if act == "base":
            n = int(str(p.get("expression") or "0").strip(), int(p.get("from_base") or 10))
            return f"{n} = binary {bin(n)[2:]} = octal {oct(n)[2:]} = hex {hex(n)[2:].upper()}."
        if act == "random":
            kind = str(p.get("kind") or "dice").lower()
            if kind == "coin":
                return f"🪙 {random.choice(['Heads', 'Tails'])}!"
            if kind == "dice":
                k = int(v[0]) if v else 1
                rolls = [random.randint(1, 6) for _ in range(max(1, min(k, 10)))]
                return f"🎲 {', '.join(map(str, rolls))}" + (f" (total {sum(rolls)})" if len(rolls) > 1 else "")
            if kind == "card":
                return f"🃏 {random.choice(['A','2','3','4','5','6','7','8','9','10','J','Q','K'])} of {random.choice(['♠ spades','♥ hearts','♦ diamonds','♣ clubs'])}"
            if kind == "pick":
                items = [x.strip() for x in str(p.get("numbers") or "").split(",") if x.strip()]
                return f"I pick: {random.choice(items)}!" if items else "Give me the options, separated by commas."
            lo, hi = (int(v[0]), int(v[1])) if len(v) >= 2 else (1, 100)
            return f"Random number between {lo} and {hi}: {random.randint(min(lo, hi), max(lo, hi))}."
        if act == "stats":
            if len(v) < 2:
                return "Give me at least two numbers."
            modes = st.multimode(v)
            out = (f"Count {len(v)}, mean {st.mean(v):.3g}, median {st.median(v):g}, mode {', '.join(f'{m:g}' for m in modes[:3])}, "
                   f"range {max(v) - min(v):g}, std dev {st.pstdev(v):.3g}.")
            return out
        if act == "fraction":
            expr = str(p.get("expression") or "").replace(" ", "")
            import re
            parts = re.split(r"([+\-*/])", expr)
            val = Fraction(parts[0])
            for i in range(1, len(parts) - 1, 2):
                op, x = parts[i], Fraction(parts[i + 1])
                val = val + x if op == "+" else val - x if op == "-" else val * x if op == "*" else val / x
            whole = f" = {val.numerator // val.denominator} {val.numerator % val.denominator}/{val.denominator}" if abs(val) > 1 and val.denominator != 1 else ""
            return f"{expr} = {val}{whole} ≈ {float(val):.4g}."
        if act == "plot":
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import numpy as np
            fx = str(p.get("expression") or "").replace("^", "**").replace("y=", "").strip()
            x = np.linspace(float(p.get("x_min") or -10), float(p.get("x_max") or 10), 800)
            safe = {k: getattr(np, k) for k in ("sin", "cos", "tan", "sqrt", "log", "exp", "abs", "pi")}
            import re as _re
            words = set(_re.findall(r"[A-Za-z_]+", fx))
            if not _re.fullmatch(r"[0-9x+\-*/().\s]*|.*", fx) or not words <= set(safe) | {"x"} or "__" in fx:
                return "I can only plot maths: numbers, x, + - * / ^ ( ) and sin, cos, tan, sqrt, log, exp, abs, pi."
            if _re.search(r"[^0-9A-Za-z_+\-*/().\s]", fx):
                return "I can only plot maths: numbers, x, + - * / ^ ( ) and sin, cos, tan, sqrt, log, exp, abs, pi."
            y = eval(fx, {"__builtins__": {}}, {**safe, "x": x})
            fig, ax = plt.subplots(figsize=(7, 4.5), facecolor="black")
            ax.set_facecolor("black"); ax.plot(x, y, color="#ff7a1a", lw=2)
            ax.axhline(0, color="#7a3a0c", lw=0.8); ax.axvline(0, color="#7a3a0c", lw=0.8)
            ax.grid(color="#2a1405"); ax.tick_params(colors="#ffb070"); ax.set_title(f"y = {fx}", color="#ffb070")
            out = H.documents_dir("Graphs") / ("graph " + "".join(ch for ch in fx if ch.isalnum())[:30] + ".png")
            fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)
            if sys.platform == "win32":
                os.startfile(str(out))      # type: ignore[attr-defined]
            return f"Plotted y = {fx}; it's open (saved in Documents, JARVIS, Graphs)."
    except (ValueError, IndexError, ZeroDivisionError) as e:
        return f"I couldn't work that out ({e}). Check the numbers."
    except Exception as e:
        return f"That didn't work: {e}"
    return "Maths: solve, prime, gcd_lcm, percent, base, random, stats, fraction, plot."


TOOL = {
    "name": "math_tools",
    "description": ("Maths helpers (mostly instant, no AI). action='solve' (expression: an equation, step by step); 'prime' "
                    "(numbers: one number → prime check / factors); 'gcd_lcm' (numbers); 'percent' (kind of/discount/tip/change/"
                    "what, numbers 'a b [people]'); 'base' (expression, from_base); 'random' (kind dice/coin/card/number/pick, "
                    "numbers = count/range/options); 'stats' (numbers); 'fraction' (expression like '3/4+5/6'); 'plot' "
                    "(expression like 'x^2-3*x', x_min, x_max)."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "numbers": {"type": "STRING", "description": "Numbers (or comma-separated options for pick)."},
        "expression": {"type": "STRING", "description": "Equation, fraction sum, number, or function of x."},
        "kind": {"type": "STRING", "description": "Sub-type for percent / random."},
        "from_base": {"type": "NUMBER", "description": "Base of the input number (2, 8, 10, 16)."},
        "x_min": {"type": "NUMBER", "description": "Plot range start."},
        "x_max": {"type": "NUMBER", "description": "Plot range end."}}, "required": ["action"]},
    "handler": math_tools,
}
