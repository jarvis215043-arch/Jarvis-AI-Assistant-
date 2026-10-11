"""actions/desk_tools.py — Calculator & unit/currency converter, saved window
layouts, a typing-speed trainer page, and a screenshot organiser."""
import ast
import math
import operator as op
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser
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
LAYOUTS = H.mem_path("window_layouts.json")
_OPS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv, ast.Pow: op.pow,
        ast.Mod: op.mod, ast.FloorDiv: op.floordiv, ast.USub: op.neg, ast.UAdd: op.pos}
_FUNCS = {k: getattr(math, k) for k in ("sqrt", "sin", "cos", "tan", "log", "log10", "exp", "floor", "ceil", "factorial")}
_FUNCS.update(abs=abs, round=round, pi=math.pi, e=math.e)
UNITS = {  # to a base unit
    "length": {"mm": 0.001, "cm": 0.01, "m": 1, "km": 1000, "inch": 0.0254, "in": 0.0254, "ft": 0.3048, "foot": 0.3048, "feet": 0.3048, "yard": 0.9144, "mile": 1609.344, "miles": 1609.344},
    "mass": {"mg": 1e-6, "g": 0.001, "kg": 1, "tonne": 1000, "lb": 0.45359237, "pound": 0.45359237, "oz": 0.0283495},
    "volume": {"ml": 0.001, "l": 1, "litre": 1, "liter": 1, "gallon": 3.78541, "cup": 0.24},
    "speed": {"kmh": 1 / 3.6, "km/h": 1 / 3.6, "mph": 0.44704, "m/s": 1},
    "data": {"kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12},
}


def _safe_eval(expr: str) -> float:
    expr = expr.replace("^", "**").replace("×", "*").replace("÷", "/").replace("x", "*")
    def ev(n):
        if isinstance(n, ast.Expression): return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)): return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS: return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS: return _OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Name) and n.id in _FUNCS and not callable(_FUNCS[n.id]): return _FUNCS[n.id]
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError("not allowed")
    return ev(ast.parse(expr, mode="eval"))


def _convert(value: float, a: str, b: str):
    a, b = a.lower().rstrip("s") if a.lower() not in ("feet", "miles", "kmh") else a.lower(), b.lower()
    for table in UNITS.values():
        ka = next((k for k in table if k == a or k.rstrip("s") == a), None)
        kb = next((k for k in table if k == b or k.rstrip("s") == b.rstrip("s")), None)
        if ka and kb:
            return value * table[ka] / table[kb]
    temps = {("c", "f"): lambda v: v * 9 / 5 + 32, ("f", "c"): lambda v: (v - 32) * 5 / 9,
             ("c", "k"): lambda v: v + 273.15, ("k", "c"): lambda v: v - 273.15}
    key = (a[0], b[0]) if a and b else None
    if a in ("c", "f", "k", "celsius", "fahrenheit", "kelvin") and key in temps:
        return temps[key](value)
    return None


def _windows():
    import pygetwindow as gw
    import psutil
    import ctypes
    out = []
    for w in gw.getAllWindows():
        if not w.title or w.width < 200 or w.height < 150 or w.isMinimized:
            continue
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(w._hWnd, ctypes.byref(pid))
        try:
            exe = psutil.Process(pid.value).exe()
        except Exception:
            continue
        if any(x in exe.lower() for x in ("python", "jarvis", "explorer.exe", "textinputhost")):
            continue
        out.append({"title": w.title, "exe": exe, "rect": [w.left, w.top, w.width, w.height]})
    return out


TYPING_HTML = """<!doctype html><html><head><meta charset=utf-8><title>JARVIS Typing Trainer</title><style>
body{background:#000;color:#ff9a4d;font-family:Consolas,monospace;display:flex;flex-direction:column;align-items:center;padding:40px}
#t{max-width:900px;font-size:22px;line-height:1.6;color:#7a3a0c}#t .ok{color:#ffb070}#t .bad{color:#ff3b3b;text-decoration:underline}
textarea{width:900px;height:120px;background:#120700;color:#ffd2a8;border:1px solid #ff7a1a;font-size:20px;padding:10px;margin-top:20px}
#s{margin-top:16px;font-size:20px}button{background:#ff7a1a;border:0;padding:8px 18px;font-weight:bold;margin-top:12px;cursor:pointer}</style></head>
<body><h2>JARVIS TYPING TRAINER</h2><div id=t></div><textarea id=i placeholder="Start typing to begin..."></textarea>
<div id=s></div><button onclick="nxt()">NEW TEXT</button><div id=h style="margin-top:20px;color:#a85a1a"></div><script>
const T=["The quick brown fox jumps over the lazy dog while the orange sun sets slowly.","Science is a way of thinking much more than it is a body of knowledge.","Practice every day and your fingers will learn the keyboard faster than you think.","Jarvis, run a diagnostic on the suit and prepare the workshop for testing.","Small steps every day add up to big results over a whole school year."];
let txt,st=null;const t=document.getElementById('t'),i=document.getElementById('i'),s=document.getElementById('s');
function nxt(){txt=T[Math.floor(Math.random()*T.length)];i.value='';st=null;draw();s.textContent='';i.focus()}
function draw(){let v=i.value,h='';for(let k=0;k<txt.length;k++){let c=txt[k];h+=k<v.length?(v[k]==c?'<span class=ok>'+c+'</span>':'<span class=bad>'+c+'</span>'):c}t.innerHTML=h}
i.oninput=()=>{if(!st)st=Date.now();draw();let v=i.value;if(v.length>=txt.length){let m=(Date.now()-st)/60000,w=Math.round(txt.split(' ').length/m);
let e=0;for(let k=0;k<txt.length;k++)if(v[k]!=txt[k])e++;let acc=Math.round(100*(txt.length-e)/txt.length);s.textContent=w+' WPM  ·  '+acc+'% accuracy';
let hist=JSON.parse(localStorage.getItem('jt')||'[]');hist.push({d:new Date().toLocaleDateString(),w,acc});localStorage.setItem('jt',JSON.stringify(hist.slice(-20)));show()}};
function show(){let hist=JSON.parse(localStorage.getItem('jt')||'[]');document.getElementById('h').innerHTML='Recent: '+hist.slice(-8).map(x=>x.w+' wpm').join(' · ')+(hist.length?' &nbsp; Best: '+Math.max(...hist.map(x=>x.w))+' wpm':'')}
nxt();show();</script></body></html>"""


def desk_tools(parameters: dict, player=None) -> str:
    p = parameters or {}
    act = str(p.get("action") or "").lower()
    if act == "calculate":
        expr = str(p.get("expression") or "").strip()
        try:
            v = _safe_eval(expr)
            v = int(v) if isinstance(v, float) and v.is_integer() else round(v, 6)
            return f"{expr} = {v}"
        except Exception:
            return f"I couldn't calculate '{expr}'. Use numbers and + - × ÷ ^, sqrt(), etc."
    if act == "convert":
        try:
            val = float(p.get("value"))
        except (TypeError, ValueError):
            return "What value should I convert?"
        a, b = str(p.get("from_unit") or ""), str(p.get("to_unit") or "")
        res = _convert(val, a, b)
        if res is not None:
            return f"{val:g} {a} = {round(res, 4):g} {b}"
        if len(a) == 3 and len(b) == 3:
            try:
                return H.ai_search(f"Convert {val} {a.upper()} to {b.upper()} at today's exchange rate. Reply with just the result and the rate.")
            except Exception as e:
                return f"I couldn't get the exchange rate: {e}"
        return f"I don't know how to convert {a} to {b}."
    if act == "layout_save":
        name = str(p.get("name") or "default").lower()
        try:
            wins = _windows()
        except Exception as e:
            return f"I couldn't read your windows: {e}"
        data = H.load_json(LAYOUTS, {}); data[name] = wins; H.save_json(LAYOUTS, data)
        return f"Saved the '{name}' layout with {len(wins)} windows: " + ", ".join(Path(w['exe']).stem for w in wins)
    if act == "layout_restore":
        name = str(p.get("name") or "default").lower()
        lay = H.load_json(LAYOUTS, {}).get(name)
        if not lay:
            return f"No layout called '{name}'. Arrange your windows and say 'save this as {name} layout'."
        import pygetwindow as gw
        running = {}
        try:
            for w in _windows():
                running.setdefault(w["exe"].lower(), []).append(w["title"])
        except Exception:
            pass
        for w in lay:
            if w["exe"].lower() not in running:
                try:
                    subprocess.Popen([w["exe"]])
                except Exception:
                    pass
        time.sleep(3.5)
        moved = 0
        for w in lay:
            for g in gw.getAllWindows():
                if g.title and (g.title == w["title"] or Path(w["exe"]).stem.lower() in g.title.lower()):
                    try:
                        if g.isMinimized: g.restore()
                        g.moveTo(w["rect"][0], w["rect"][1]); g.resizeTo(w["rect"][2], w["rect"][3]); moved += 1
                    except Exception:
                        pass
                    break
        return f"Restored the '{name}' layout ({moved} of {len(lay)} windows placed)."
    if act == "layout_list":
        names = list(H.load_json(LAYOUTS, {}))
        return f"Saved layouts: {', '.join(names)}." if names else "No layouts saved yet."
    if act == "typing_trainer":
        f = H.documents_dir() / "Typing trainer.html"
        f.write_text(TYPING_HTML, encoding="utf-8")
        webbrowser.open(f.as_uri())
        return "Opened the typing trainer in your browser — it keeps your scores."
    if act == "screenshots_tidy":
        home = Path.home()
        srcs = [home / "Pictures" / "Screenshots", home / "Desktop", home / "OneDrive" / "Pictures" / "Screenshots"]
        dest_root = home / "Pictures" / "Screenshots"
        moved = 0
        for src in srcs:
            if not src.exists():
                continue
            for f in src.iterdir():
                if f.is_file() and f.suffix.lower() in (".png", ".jpg") and re.match(r"(?i)screen ?shot", f.name):
                    month = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m")
                    d = dest_root / month; d.mkdir(parents=True, exist_ok=True)
                    tgt = d / f.name
                    if tgt.exists():
                        continue
                    shutil.move(str(f), str(tgt)); moved += 1
        return f"Sorted {moved} screenshot(s) into Pictures, Screenshots, by month." if moved else "No loose screenshots to sort."
    return "Desk tools: calculate, convert, layout_save, layout_restore, layout_list, typing_trainer, screenshots_tidy."


TOOL = {
    "name": "desk_tools",
    "description": ("'calculate' (expression, e.g. '23*17+sqrt(81)'); 'convert' (value, from_unit, to_unit — "
                    "lengths, weights, volumes, speeds, data sizes, °C/°F/K, and currencies like INR→USD); window "
                    "layouts: 'layout_save' / 'layout_restore' / 'layout_list' (name, e.g. 'study'); 'typing_trainer' "
                    "opens a typing-speed test; 'screenshots_tidy' sorts screenshots into monthly folders."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "One of the actions above."},
        "expression": {"type": "STRING", "description": "Maths expression."},
        "value": {"type": "NUMBER", "description": "Value to convert."},
        "from_unit": {"type": "STRING", "description": "e.g. 'km', 'F', 'USD'."},
        "to_unit": {"type": "STRING", "description": "e.g. 'miles', 'C', 'INR'."},
        "name": {"type": "STRING", "description": "Layout name."}},
        "required": ["action"]},
    "handler": desk_tools,
}
