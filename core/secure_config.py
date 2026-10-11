"""
core/secure_config.py — Keeps your keys locked whenever JARVIS isn't running.

Your Gemini key, Google secret, Telegram token and Google login tokens live in
config/. While JARVIS runs they're normal files (every tool reads them). When it
closes, each one is encrypted with Windows' own protection (DPAPI) into a
".locked" file and the readable copy is deleted. Only YOUR Windows account on
THIS PC can unlock it — a copied folder, a stolen USB or a backup zip is useless
to anyone else.

  unlock()       at start-up (main.py)          .locked → readable
  lock()         when JARVIS closes (atexit)     readable → .locked
  read_config()  read the settings WITHOUT unlocking anything on disk
  protect()/unprotect()  raw encrypt / decrypt (used by the backup tool)

If JARVIS crashes, the readable copy stays until the next normal close.
On a NEW PC the .locked files can't be opened (that's the point): JARVIS asks for
the Gemini key again and you log in to Google again.
Turn off with  "secure_keys": false  in config/api_keys.json (or Advanced Settings).
"""
import ctypes
import json
import sys
from pathlib import Path

MAGIC = b"JARVIS-DPAPI-1\n"


def _base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


CONFIG = _base() / "config"
PATTERNS = ["api_keys.json", "*token*.json", "client_secret*.json", "*credentials*.json"]


def available() -> bool:
    return sys.platform == "win32"


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    b = _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    b._keep = buf                                      # keep the buffer alive
    return b


def _call(fn_name: str, data: bytes) -> bytes:
    crypt = ctypes.windll.crypt32
    out = _BLOB()
    fn = getattr(crypt, fn_name)
    inp = _blob(data)
    ok = fn(ctypes.byref(inp), None, None, None, None, 0x1, ctypes.byref(out))   # 0x1 = no UI prompts
    if not ok:
        raise OSError(f"{fn_name} failed (error {ctypes.GetLastError()})")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def protect(data: bytes) -> bytes:
    return MAGIC + _call("CryptProtectData", data)


def unprotect(blob: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        raise ValueError("not a JARVIS locked file")
    return _call("CryptUnprotectData", blob[len(MAGIC):])


def _enabled() -> bool:
    if not available():
        return False
    try:
        f = CONFIG / "api_keys.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8")).get("secure_keys", True) is not False
        lf = CONFIG / "api_keys.json.locked"
        if lf.exists():
            return json.loads(unprotect(lf.read_bytes()).decode("utf-8")).get("secure_keys", True) is not False
    except Exception:
        pass
    return True


def secret_files() -> list[Path]:
    seen = []
    for pat in PATTERNS:
        for f in CONFIG.glob(pat):
            if f.is_file() and f not in seen and not f.name.endswith(".locked"):
                seen.append(f)
    return seen


def unlock() -> list[str]:
    """.locked → readable (start-up). Returns problems (empty = fine)."""
    problems = []
    if not available():
        return problems
    for lf in CONFIG.glob("*.locked"):
        plain = lf.with_suffix("")                     # api_keys.json.locked → api_keys.json
        if plain.exists():
            continue                                   # left by a crash: it's the newest copy
        try:
            plain.write_bytes(unprotect(lf.read_bytes()))
        except Exception as e:
            problems.append(f"{plain.name}: can't unlock on this PC/account ({e})")
    return problems


def lock() -> int:
    """readable → .locked (on close). Returns how many files were locked."""
    if not _enabled():
        return 0
    n = 0
    for f in secret_files():
        try:
            data = f.read_bytes()
            lf = f.with_name(f.name + ".locked")
            tmp = lf.with_name(lf.name + ".tmp")
            tmp.write_bytes(protect(data))
            if unprotect(tmp.read_bytes()) != data:     # never delete the original unless the lock round-trips
                tmp.unlink(); continue
            tmp.replace(lf)
            f.unlink()
            n += 1
        except Exception as e:
            print(f"[Secure] Couldn't lock {f.name}: {e}")
    return n


def read_config() -> dict:
    """api_keys.json contents, from the readable file or (in memory) the locked one."""
    f = CONFIG / "api_keys.json"
    try:
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
        lf = CONFIG / "api_keys.json.locked"
        if lf.exists() and available():
            return json.loads(unprotect(lf.read_bytes()).decode("utf-8"))
    except Exception:
        pass
    return {}
