"""
core/pin_lock.py — A PIN gate shown before JARVIS starts.

First run (no PIN set yet): asks the user to create one — must contain a
letter, a number, and a symbol — and stores its SHA-256 hash in
config/api_keys.json (never the PIN itself, in plain text).
Every later run: asks for the PIN and only lets JARVIS start if it matches.
"""
import hashlib
import json
import re
import sys
import tkinter as tk
from pathlib import Path

MAX_ATTEMPTS = 5


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _config_path() -> Path:
    return _base_dir() / "config" / "api_keys.json"


def _load_config() -> dict:
    try:
        return json.loads(_config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_pin_hash(pin: str) -> None:
    cfg = _load_config()
    cfg["pin_hash"] = hashlib.sha256(pin.encode("utf-8")).hexdigest()
    _config_path().write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _hash(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def _is_valid_pin(pin: str) -> bool:
    has_letter = bool(re.search(r'[A-Za-z]', pin))
    has_digit  = bool(re.search(r'[0-9]', pin))
    has_symbol = bool(re.search(r'[^A-Za-z0-9]', pin))
    return len(pin) >= 6 and has_letter and has_digit and has_symbol


def require_pin() -> bool:
    """
    Blocks until the correct PIN is entered (or a new one is created on first
    run). Returns True to let JARVIS continue starting, False if the user
    closed the window or ran out of attempts.
    """
    cfg = _load_config()
    stored_hash = cfg.get("pin_hash", "")
    is_setup = not stored_hash
    attempts = {"left": MAX_ATTEMPTS}
    result = {"ok": False}

    root = tk.Tk()
    root.title("JARVIS — Access")
    root.configure(bg="#0a0e14")
    root.geometry("380x260")
    root.resizable(False, False)
    root.eval('tk::PlaceWindow . center')

    title_text = "Create your JARVIS PIN" if is_setup else "Enter PIN to unlock JARVIS"
    tk.Label(root, text=title_text, fg="#4fd1e8", bg="#0a0e14",
             font=("Segoe UI", 13, "bold")).pack(pady=(20, 4))

    if is_setup:
        tk.Label(root, text="Must include a letter, a number, and a symbol (6+ chars)",
                 fg="#6b7785", bg="#0a0e14", font=("Segoe UI", 9)).pack()

    entry = tk.Entry(root, show="•", justify="center", font=("Segoe UI", 16),
                      bg="#131924", fg="#e6f1f5", insertbackground="#e6f1f5",
                      relief="flat", width=20)
    entry.pack(pady=14)
    entry.focus_set()

    confirm_entry = None
    if is_setup:
        confirm_entry = tk.Entry(root, show="•", justify="center", font=("Segoe UI", 14),
                                  bg="#131924", fg="#e6f1f5", insertbackground="#e6f1f5",
                                  relief="flat", width=20)
        confirm_entry.pack(pady=(0, 4))
        tk.Label(root, text="confirm PIN above", fg="#6b7785", bg="#0a0e14",
                 font=("Segoe UI", 8)).pack()

    error_label = tk.Label(root, text="", fg="#ff6b6b", bg="#0a0e14", font=("Segoe UI", 9))
    error_label.pack(pady=(6, 0))

    def _submit(event=None):
        pin = entry.get()

        if is_setup:
            confirm = confirm_entry.get()
            if not _is_valid_pin(pin):
                error_label.config(text="Needs a letter, a number, and a symbol (6+ chars).")
                return
            if pin != confirm:
                error_label.config(text="PINs don't match — try again.")
                entry.delete(0, "end")
                confirm_entry.delete(0, "end")
                entry.focus_set()
                return
            _save_pin_hash(pin)
            result["ok"] = True
            root.destroy()
            return

        if _hash(pin) == stored_hash:
            result["ok"] = True
            root.destroy()
        else:
            attempts["left"] -= 1
            if attempts["left"] <= 0:
                error_label.config(text="Too many attempts. Closing.")
                root.after(1200, root.destroy)
            else:
                error_label.config(text=f"Incorrect PIN — {attempts['left']} attempt(s) left.")
                entry.delete(0, "end")

    entry.bind("<Return>", _submit)
    if confirm_entry is not None:
        confirm_entry.bind("<Return>", _submit)

    tk.Button(root, text="Set PIN" if is_setup else "Unlock", command=_submit,
              bg="#1c8ca8", fg="white", activebackground="#166b82", relief="flat",
              font=("Segoe UI", 10, "bold"), width=12).pack(pady=8)

    root.protocol("WM_DELETE_WINDOW", root.destroy)  # closing the window = cancel
    root.mainloop()

    return result["ok"]