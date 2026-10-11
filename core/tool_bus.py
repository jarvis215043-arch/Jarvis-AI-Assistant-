"""
core/tool_bus.py — lets tools use each other, and lets background features
talk, show things on the HUD and react to events.

main.py registers:
  - a runner (run any JARVIS tool by name, same safety checks as Gemini's calls)
  - the speak() function and the UI (so background features can speak / show)
and emits events such as "speaking" (True/False) for things like the reactor lamp.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

_runner: Callable[[str, dict], str] | None = None
_decls: Callable[[], list[dict]] | None = None
_speak: Callable[[str], None] | None = None
_ui = None
_lock = threading.Lock()
_ready_hooks: list[Callable[[], None]] = []
_is_ready = False
_subs: dict[str, list[Callable]] = {}


# ── registration (main.py) ───────────────────────────────────────────────────
def register(runner: Callable[[str, dict], str], declarations: Callable[[], list[dict]]) -> None:
    global _runner, _decls
    with _lock:
        _runner, _decls = runner, declarations


def register_ui(speak: Callable[[str], None], ui) -> None:
    """Called by main.py once speaking and the HUD are available; starts any
    background features that asked to run (see on_ready)."""
    global _speak, _ui, _is_ready
    with _lock:
        _speak, _ui = speak, ui
        hooks, _is_ready = list(_ready_hooks), True
    for fn in hooks:
        threading.Thread(target=_safe, args=(fn,), daemon=True, name="toolbus-ready").start()


def on_ready(fn: Callable[[], None]) -> None:
    """Background features call this when they're imported; fn runs once in its
    own thread after JARVIS has started (or immediately if it already has)."""
    with _lock:
        if not _is_ready:
            _ready_hooks.append(fn)
            return
    threading.Thread(target=_safe, args=(fn,), daemon=True, name="toolbus-ready").start()


def _safe(fn) -> None:
    try:
        fn()
    except Exception as e:
        print(f"[ToolBus] background feature failed: {e}")


# ── tools ────────────────────────────────────────────────────────────────────
def available() -> bool:
    return _runner is not None


def declarations() -> list[dict]:
    if _decls is None:
        return []
    try:
        return list(_decls())
    except Exception:
        return []


def run_tool(name: str, args: dict | None = None, timeout: float = 90.0) -> str:
    """Runs a tool by name and returns its result text. Never raises."""
    if _runner is None:
        return "Tools aren't available yet — JARVIS is still starting."
    box: dict = {}

    def _work():
        try:
            box["r"] = _runner(name, dict(args or {}))
        except Exception as e:
            box["r"] = f"Tool '{name}' failed: {e}"

    t = threading.Thread(target=_work, daemon=True, name=f"toolbus-{name}")
    t.start()
    t.join(timeout)
    if t.is_alive():
        return f"Tool '{name}' took longer than {int(timeout)} seconds and was skipped."
    return str(box.get("r") or "Done.")


# ── talking to the user from background features ─────────────────────────────
def say(text: str) -> None:
    """Makes JARVIS say something (it gets text as an instruction to speak).
    Optional heads-ups (rain, meetings, disk…) go through core/heads_up.py: a daily
    limit and quiet hours. Held-back ones still show in the HUD log."""
    try:
        from core import heads_up
        if not heads_up.allow(text):
            log("SYS: (heads-up held back — daily limit / quiet hours) " + str(text)[:120])
            return
    except Exception:
        pass
    if _speak:
        try:
            _speak(text)
        except Exception:
            pass


def show(title: str, text: str) -> None:
    if _ui is not None and hasattr(_ui, "show_content"):
        try:
            _ui.show_content(title, text)
        except Exception:
            pass


def log(text: str) -> None:
    if _ui is not None:
        try:
            _ui.write_log(text)
        except Exception:
            pass


def is_speaking_busy() -> bool:
    """True while the user is likely busy with something JARVIS shouldn't
    interrupt (muted). Background alerts check this before speaking."""
    try:
        return bool(_ui is not None and _ui.muted)
    except Exception:
        return False


# ── events ───────────────────────────────────────────────────────────────────
def subscribe(event: str, fn: Callable) -> None:
    _subs.setdefault(event, []).append(fn)


def emit(event: str, data=None) -> None:
    for fn in list(_subs.get(event, [])):
        try:
            fn(data)
        except Exception as e:
            print(f"[ToolBus] '{event}' listener failed: {e}")
