"""
core/run_log.py — JARVIS's own black box (2.6).

  install()        at start-up: everything JARVIS prints also goes to
                   memory/logs/jarvis.log (kept to ~2 MB, the previous run in
                   jarvis.log.1) — so a bug report can show what happened even
                   after a crash, and even in Jarvis.exe where there's no console.
  record_tool()    every tool JARVIS runs → memory/logs/tools.jsonl
                   (time, tool, the real tool behind more_tools, how long, ok/error,
                   the first 160 characters of the result). Used by the bug report
                   and by tool_usage ("which tools do I never use?").
  tail_lines() / tool_history() / usage_counts()   readers for those.

Everything stays on this PC. Keys are never written: text that looks like an API
key or token is replaced with [hidden] before it is saved.
"""
import json
import re
import sys
import threading
import time
from pathlib import Path

_lock = threading.Lock()
MAX_LOG = 2_000_000
MAX_TOOLS = 1_500_000
_SECRET = re.compile(r"(AIza[0-9A-Za-z_\-]{20,}|sk-[0-9A-Za-z_\-]{20,}|ghp_[0-9A-Za-z]{20,}|github_pat_[0-9A-Za-z_]{20,}"
                     r"|\b\d{8,10}:[0-9A-Za-z_\-]{30,}\b|ya29\.[0-9A-Za-z_\-\.]{20,}|1//[0-9A-Za-z_\-]{30,})")


def _base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def log_dir() -> Path:
    d = _base() / "memory" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def redact(text: str) -> str:
    return _SECRET.sub("[hidden]", str(text))


class _Tee:
    """Writes to the original stream (if any) AND the log file, line-stamped."""

    def __init__(self, orig, fh, tag):
        self._orig, self._fh, self._tag = orig, fh, tag
        self._at_line_start = True

    def write(self, s):
        if self._orig is not None:
            try:
                self._orig.write(s)
            except Exception:
                pass
        if not s:
            return 0
        try:
            with _lock:
                out = []
                for part in str(s).splitlines(True):
                    if self._at_line_start:
                        out.append(time.strftime("%H:%M:%S ") + self._tag)
                    out.append(part)
                    self._at_line_start = part.endswith("\n")
                self._fh.write(redact("".join(out)))
                self._fh.flush()
        except Exception:
            pass
        return len(s)

    def flush(self):
        for f in (self._orig, self._fh):
            try:
                f and f.flush()
            except Exception:
                pass

    def isatty(self):
        try:
            return bool(self._orig and self._orig.isatty())
        except Exception:
            return False

    def reconfigure(self, **kw):
        try:
            self._orig and self._orig.reconfigure(**kw)
        except Exception:
            pass

    @property
    def encoding(self):
        return getattr(self._orig, "encoding", "utf-8") or "utf-8"

    def fileno(self):
        if self._orig is None:
            raise OSError("no console")
        return self._orig.fileno()

    def __getattr__(self, name):                          # anything else (buffer, errors…) → the real console
        orig = self.__dict__.get("_orig")
        if orig is None:
            raise AttributeError(name)
        return getattr(orig, name)


_installed = False


def install() -> None:
    """Mirror stdout/stderr into memory/logs/jarvis.log (safe to call twice)."""
    global _installed
    if _installed:
        return
    try:
        p = log_dir() / "jarvis.log"
        if p.exists():                                     # keep the previous run as .1
            try:
                old = p.with_suffix(".log.1")
                if old.exists():
                    old.unlink()
                p.rename(old)
            except Exception:
                pass
        fh = open(p, "a", encoding="utf-8", errors="replace", buffering=1)
        fh.write(f"===== JARVIS started {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        sys.stdout = _Tee(sys.stdout, fh, "")
        sys.stderr = _Tee(sys.stderr, fh, "! ")
        _installed = True
        threading.Thread(target=_trim_loop, args=(p,), daemon=True, name="log-trim").start()
    except Exception:
        pass


def _trim_loop(p: Path) -> None:
    while True:
        time.sleep(300)
        try:
            if p.stat().st_size > MAX_LOG:
                with _lock:
                    data = p.read_bytes()[-MAX_LOG // 2:]
                    cut = data.find(b"\n")
                    p.write_bytes(b"... (older lines trimmed)\n" + data[cut + 1:])
        except Exception:
            pass


def record_tool(name: str, args: dict | None, result, secs: float) -> None:
    """One line per tool JARVIS runs (never raises)."""
    try:
        args = dict(args or {})
        real = str(args.get("tool") or "").strip() if name == "more_tools" else name
        text = str(result if not isinstance(result, dict) else result.get("result", result))
        ok = not re.search(r"(?i)\b(error|failed|couldn't|could not|timed out|unknown tool|no tool called)\b", text[:300])
        row = {"t": round(time.time(), 1), "day": time.strftime("%Y-%m-%d"), "tool": real or name, "via": name,
               "secs": round(float(secs), 2), "ok": ok,
               "args": redact(json.dumps(args, ensure_ascii=False))[:240], "result": redact(text)[:160]}
        p = log_dir() / "tools.jsonl"
        with _lock:
            with open(p, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if p.stat().st_size > MAX_TOOLS:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-6000:]
                p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def tail_lines(n: int = 3000, previous_run: bool = False) -> list[str]:
    p = log_dir() / ("jarvis.log.1" if previous_run else "jarvis.log")
    try:
        return p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except Exception:
        return []


def tool_history(limit: int = 0) -> list[dict]:
    p = log_dir() / "tools.jsonl"
    out = []
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    except Exception:
        pass
    return out[-limit:] if limit else out


def usage_counts() -> tuple[dict, float]:
    """({tool: times used}, days of history)."""
    rows = tool_history()
    c = {}
    for r in rows:
        c[r.get("tool")] = c.get(r.get("tool"), 0) + 1
    span = (time.time() - rows[0]["t"]) / 86400 if rows else 0.0
    return c, span
