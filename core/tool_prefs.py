"""
core/tool_prefs.py — Which tools are switched off (2.6).

Switched-off tools are not sent to the voice model at all (cheaper turns, fewer
wrong picks) and more_tools refuses them. Nothing is deleted — "turn X back on"
brings a tool back instantly.

  config "disabled_tools": [...]     tools you switched off (tool_usage prune / disable)
  config "enabled_tools":  [...]     tools you insisted on keeping (overrides the default below)

Default: an old tool called "hologram" (from an older JARVIS) is switched off
whenever the newer "holograms" tool exists — the two competed, and JARVIS
sometimes picked the old one.
"""
import json
import sys
from pathlib import Path

NEVER_DISABLE = {"more_tools", "tool_usage", "bug_report", "diagnostics", "jarvis_update", "mic_control",
                 "shutdown_jarvis", "save_memory", "recall_memory", "undo", "system_status", "demo_mode_control"}
DEFAULT_OFF_IF = {"hologram": "holograms"}           # old tool → switched off when the new one exists


def _cfg() -> dict:
    try:
        from core.secure_config import read_config
        return read_config()
    except Exception:
        base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
        try:
            return json.loads((base / "config" / "api_keys.json").read_text(encoding="utf-8"))
        except Exception:
            return {}


def disabled(all_names=None) -> set:
    c = _cfg()
    off = {str(x).strip() for x in (c.get("disabled_tools") or []) if str(x).strip()}
    keep = {str(x).strip() for x in (c.get("enabled_tools") or [])}
    names = set(all_names or [])
    for old, new in DEFAULT_OFF_IF.items():
        if old in names and new in names and old not in keep:
            off.add(old)
    return off - NEVER_DISABLE - keep


def filter_decls(decls: list, all_names=None) -> list:
    names = set(all_names or []) | {d.get("name") for d in decls}
    off = disabled(names)
    return [d for d in decls if d.get("name") not in off]
