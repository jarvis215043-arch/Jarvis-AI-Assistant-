"""
core/bug_report.py — One zip with everything needed to fix a problem (2.6).

  "JARVIS, make a bug report"  /  "something went wrong"   (actions/bug_report.py)
  bug_report.bat               (works even when JARVIS won't start)

The zip goes on your Desktop as "JARVIS bug report <date time>.zip" and holds:
  WHAT HAPPENED.txt   what you said went wrong, version, PC, Python, libraries
  log.txt             the last ~4000 lines JARVIS printed (this run)
  log-previous.txt    the end of the previous run (shows a crash at start-up)
  tools.txt           the last 300 tools JARVIS ran: which, how long, result
  settings.txt        your settings — every key / token / password shown only as [set]
  diagnostics.txt     a quick self-test (no internet or hardware tests)
  gestures.txt        gesture mode, calibration, which tools are switched off
NOT included: keys, Google sign-in, memory files, photos, documents.
The log CAN include what you asked JARVIS — open the zip and look before you send it.
"""
import json
import platform
import sys
import time
import zipfile
from pathlib import Path

SECRET_WORDS = ("key", "token", "secret", "password", "passwd", "pin", "credential", "cookie")
PACKAGES = ("google-genai", "PyQt6", "numpy", "mediapipe", "opencv-python", "PyAudio", "sounddevice", "psutil",
            "pyautogui", "requests", "Pillow", "openwakeword", "PyOpenGL", "google-api-python-client")


def _base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _cfg() -> dict:
    try:
        from core.secure_config import read_config
        return read_config()
    except Exception:
        try:
            return json.loads((_base() / "config" / "api_keys.json").read_text(encoding="utf-8"))
        except Exception:
            return {}


def safe_settings(cfg: dict) -> dict:
    out = {}
    for k, v in sorted(cfg.items()):
        if any(w in k.lower() for w in SECRET_WORDS) and not isinstance(v, bool):
            out[k] = "[set]" if v not in (None, "", [], {}) else "[empty]"
        else:
            out[k] = v
    return out


def _versions() -> list[str]:
    rows = []
    try:
        from importlib.metadata import version, PackageNotFoundError
    except Exception:
        return rows
    alts = {"opencv-python": ("opencv-python", "opencv-contrib-python", "opencv-python-headless",
                              "opencv-contrib-python-headless")}
    for p in PACKAGES:
        found = None
        for name in alts.get(p, (p,)):
            try:
                found = f"{version(name)}" + (f" ({name})" if name != p else "")
                break
            except Exception:
                pass
        rows.append(f"  {p:26} {found or 'not installed'}")
    return rows


def _desktop() -> Path:
    home = Path.home()
    for d in (home / "Desktop", home / "OneDrive" / "Desktop"):
        if d.is_dir():
            return d
    d = home / "Documents" / "JARVIS"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _diag(decls=None, run_tool=None) -> str:
    try:
        from core import diagnostics as D
        rep = D.run(_cfg(), decls or (lambda: []), run_tool or (lambda n, a: "skipped in bug report"),
                    network=False, hardware=False)
        text = rep.text()
        if decls is None:                                   # bug_report.bat: JARVIS isn't running, so no tools to count
            import re
            text = re.sub(r"^ ! 0 tools loaded.*$", " · tools not checked (JARVIS wasn't running — the log shows them loading)",
                          text, flags=re.M)
        return text
    except Exception as e:
        return f"(quick self-test couldn't run: {e})"


def _gestures() -> str:
    lines = []
    try:
        from core import gesture_modes
        lines.append(f"Gesture mode now: {gesture_modes.current()}")
    except Exception as e:
        lines.append(f"Gesture mode: unknown ({e})")
    cal = _base() / "config" / "gesture_calibration.json"
    lines.append("Calibration: " + (cal.read_text(encoding="utf-8") if cal.exists() else "not done"))
    try:
        from core import holo_gestures as G
        lines.append(f"Active thresholds: min_score={G.MIN_SCORE} hold={G.HOLD} pinch_in={G.PINCH_IN} pinch_out={G.PINCH_OUT}")
    except Exception:
        pass
    try:
        from core import tool_prefs
        lines.append("Switched-off tools: " + (", ".join(sorted(tool_prefs.disabled(
            [p.stem for p in (_base() / "actions").glob("*.py")] + ["holograms"]))) or "none"))
    except Exception:
        pass
    return "\n".join(lines)


def build(what: str = "", decls=None, run_tool=None, out_dir: Path | None = None) -> Path:
    from core import run_log
    now = time.strftime("%Y-%m-%d %H.%M")
    out = (out_dir or _desktop()) / f"JARVIS bug report {now}.zip"
    try:
        version = (_base() / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        version = "?"
    head = [f"JARVIS BUG REPORT — {time.strftime('%d %b %Y %H:%M')}",
            "", "WHAT WENT WRONG (in your words):", "  " + (what.strip() or "(not described)"), "",
            f"JARVIS version: {version}   ({'Jarvis.exe' if getattr(sys, 'frozen', False) else 'python main.py'})",
            f"Windows: {platform.platform()}", f"Python: {sys.version.split()[0]}", "", "Libraries:", *_versions(), "",
            "Check before sending: log.txt can include what you asked JARVIS. Keys are never in here."]
    tools = run_log.tool_history(300)
    tool_txt = "\n".join(
        f"{time.strftime('%d %b %H:%M:%S', time.localtime(r.get('t', 0)))}  {r.get('tool', '?'):22} "
        f"{'ok ' if r.get('ok') else 'ERR'} {r.get('secs', 0):6.1f}s  {r.get('args', '')}  →  {r.get('result', '')}"
        for r in tools) or "(no tool calls recorded yet)"
    files = {
        "WHAT HAPPENED.txt": "\n".join(head),
        "log.txt": "\n".join(run_log.tail_lines(4000)) or "(no log yet — it starts with JARVIS 2.6)",
        "log-previous.txt": "\n".join(run_log.tail_lines(1500, previous_run=True)) or "(no previous run)",
        "tools.txt": tool_txt,
        "settings.txt": json.dumps(safe_settings(_cfg()), indent=2, ensure_ascii=False),
        "diagnostics.txt": _diag(decls, run_tool),
        "gestures.txt": _gestures(),
    }
    routing = run_log.log_dir() / "routing_last.txt"
    if routing.exists():
        files["routing-test.txt"] = routing.read_text(encoding="utf-8", errors="replace")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, run_log.redact(text))
    return out


def reveal(path: Path) -> None:
    """Show the zip in Explorer (Windows) — best effort."""
    try:
        import subprocess
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(path)])
    except Exception:
        pass


if __name__ == "__main__":                                 # bug_report.bat
    sys.path.insert(0, str(_base()))
    try:
        what = input("What went wrong? (one line, Enter to skip): ").strip()
    except EOFError:
        what = ""
    p = build(what)
    print(f"\nSaved: {p}\nOpen it and look through log.txt, then send me the zip.")
    reveal(p)
