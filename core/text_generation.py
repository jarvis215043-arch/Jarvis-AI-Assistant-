"""
core/text_generation.py — Shared text-generation helper with automatic local
LLM fallback for PPT/Word/Excel content generation.

Tries Gemini first (fast, best quality). Two failure categories are handled
differently:
  - Short-lived transient errors (503/504/UNAVAILABLE/timeout) — retried a
    few times with backoff, since these often resolve within seconds.
  - Quota/rate-limit errors (429/RESOURCE_EXHAUSTED) — NOT retried, since
    these are often a hard DAILY cap that won't reset for hours.

If Gemini can't deliver, this falls back to a local model via Ollama
(core/llm_client.py), with a generous timeout for the model's first-load
cold start.

generate_json() additionally handles the fact that smaller local models are
noticeably worse than Gemini at strictly outputting valid JSON — it extracts
the JSON object out of any surrounding text the model added, and repairs a
couple of common small-model mistakes (trailing commas) before parsing, so a
minor formatting slip doesn't blow up the whole generation.
"""
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

_RETRY_MARKERS = ("503", "504", "UNAVAILABLE", "DEADLINE_EXCEEDED", "overload", "timeout")
_QUOTA_MARKERS = ("429", "RESOURCE_EXHAUSTED")


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _config() -> dict:
    try:
        return json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _is_retryable(err: Exception) -> bool:
    return any(marker in str(err) for marker in _RETRY_MARKERS)


def _is_quota_exhausted(err: Exception) -> bool:
    return any(marker in str(err) for marker in _QUOTA_MARKERS)


def _load_llm_client():
    key = "jarvis_ext_llm_client"
    if key in sys.modules:
        return sys.modules[key]
    path = _base_dir() / "core" / "llm_client.py"
    if not path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location(key, str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[key] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        print(f"[TextGeneration] Could not load llm_client.py: {e}")
        return None


def _try_gemini(prompt: str, attempts: int = 3, timeout_ms: int = 60000, json_mode: bool = False) -> str:
    from google import genai as _genai
    from google.genai import types as _types

    client = _genai.Client(
        api_key=_config().get("gemini_api_key", ""),
        http_options=_types.HttpOptions(timeout=timeout_ms),
    )

    # In JSON mode, let the API itself enforce valid JSON syntax rather than
    # relying on prompt instructions — this is what actually prevents the
    # "unescaped quote breaks the string" failures that _repair_json can't fix.
    config = _types.GenerateContentConfig(response_mime_type="application/json") if json_mode else None

    last_err = None
    for attempt in range(attempts):
        try:
            resp = client.models.generate_content(model="gemini-flash-latest", contents=prompt, config=config)
            return (resp.text or "").strip()
        except Exception as e:
            last_err = e
            if _is_quota_exhausted(e):
                print(f"[TextGeneration] Gemini quota exhausted (not time-based) — skipping retries.")
                break
            if _is_retryable(e) and attempt < attempts - 1:
                wait = 2 ** (attempt + 1)
                print(f"[TextGeneration] Gemini attempt {attempt + 1}/{attempts} failed, retrying in {wait}s — {e}")
                time.sleep(wait)
                continue
            break
    raise last_err


def _try_local_llm(prompt: str) -> tuple[str, str]:
    """Returns (result, status). result is '' on failure; status explains why."""
    mod = _load_llm_client()
    if mod is None:
        return "", "core/llm_client.py could not be loaded"
    try:
        if not mod.ensure_ollama_running(timeout=8):
            return "", "Ollama isn't installed or isn't running (see ollama.com)"
        print("[TextGeneration] Calling local model — first use can take a couple minutes while it loads into memory...")
        result = mod.call_llm_text(prompt=prompt, timeout=360)
        if not result:
            return "", "Ollama responded but returned empty text"
        return result, "ok"
    except Exception as e:
        return "", f"Ollama call failed: {e}"


def generate_text(prompt: str, json_mode: bool = False) -> str:
    """
    Tries Gemini first; on quota exhaustion or repeated transient failure,
    tries a local model via Ollama before giving up with a clear combined
    error. json_mode asks Gemini to enforce valid JSON syntax on its output
    (used by generate_json) — the local-LLM fallback has no equivalent
    switch, so it still relies on prompt instructions alone.
    """
    try:
        return _try_gemini(prompt, json_mode=json_mode)
    except Exception as gemini_err:
        if not (_is_retryable(gemini_err) or _is_quota_exhausted(gemini_err)):
            raise

        print(f"[TextGeneration] Gemini unavailable ({gemini_err}) — trying local LLM fallback...")
        local_result, status = _try_local_llm(prompt)
        if local_result:
            print("[TextGeneration] Local LLM fallback succeeded.")
            return local_result

        raise RuntimeError(
            f"Gemini failed ({gemini_err}) AND the local fallback failed too: {status}"
        )


def _extract_json_object(text: str) -> str:
    """Pulls the first complete {...} object out of text, ignoring any
    leading/trailing prose, markdown fences, or commentary the model added.
    Uses brace-depth counting that respects string literals, so it survives
    braces that appear inside quoted values."""
    start = text.find("{")
    if start == -1:
        return text.strip()

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return text[start:]   # unbalanced — return what we have, let json.loads report the real error


def _repair_json(raw: str) -> str:
    """Fixes the most common small-model JSON mistake: a trailing comma right
    before a closing ] or }. Deliberately conservative — no aggressive
    rewriting that could silently change meaning."""
    return re.sub(r",\s*([\]}])", r"\1", raw)


def generate_json(prompt: str) -> dict:
    """
    Like generate_text, but for callers that need structured JSON back.
    Extracts the JSON object from the response and repairs common small-model
    formatting slips (trailing commas) before parsing. If it still can't be
    parsed, raises with a snippet of the actual raw response included, so a
    failure is debuggable instead of a bare parser error with no context.
    """
    raw = generate_text(prompt, json_mode=True)
    candidate = _extract_json_object(raw)

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    try:
        return json.loads(_repair_json(candidate))
    except json.JSONDecodeError as e:
        snippet = raw[:300] + ("..." if len(raw) > 300 else "")
        raise ValueError(f"The model's response wasn't valid JSON ({e}). It started with: {snippet!r}")