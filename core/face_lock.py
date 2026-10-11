"""
core/face_lock.py — Face-recognition unlock for JARVIS, with PIN as a
guaranteed fallback (a camera issue, bad lighting, or a bad hair day can
never lock you out of your own PC).

REQUIRES opencv-contrib-python instead of plain opencv-python:
    pip uninstall opencv-python opencv-contrib-python -y
    pip install opencv-contrib-python

First run ever: sets up a PIN (mandatory), then optionally offers to enroll
your face on top of it.
Every run after: if a face is enrolled, tries to recognize you live via
webcam for a few seconds, with "Use PIN instead" always available.

HONEST LIMITATION: this uses OpenCV's LBPH face recognizer, a basic
brightness-pattern matcher — not depth-sensing like a phone's Face ID. It's
a convenience layer, not strong security. A photo held up to the camera
could plausibly pass.
"""
import hashlib
import json
import re
import sys
import time
import tkinter as tk
from pathlib import Path

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False

try:
    from PIL import Image, ImageTk
    _PIL = True
except ImportError:
    _PIL = False

_HAS_FACE_MODULE = _CV2 and _PIL and hasattr(cv2, "face")


def _face_unavailable_reason() -> str:
    """Returns '' if face unlock's dependencies are all present, else a
    specific, honest reason why not — shown on screen instead of silently
    skipping to PIN-only."""
    if not _CV2:
        return "OpenCV isn't installed."
    if not _PIL:
        return "Pillow isn't installed."
    if not hasattr(cv2, "face"):
        return "You have plain 'opencv-python' installed, not 'opencv-contrib-python'."
    return ""


MAX_PIN_ATTEMPTS      = 5
FACE_TIMEOUT          = 12.0
CONFIDENCE_THRESHOLD  = 70.0
MATCH_HOLD_FRAMES     = 5
ENROLL_SAMPLES        = 25
FACE_SIZE             = (200, 200)


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _config_path() -> Path:
    return _base_dir() / "config" / "api_keys.json"


def _face_model_path() -> Path:
    return _base_dir() / "config" / "face_model.yml"


def _load_config() -> dict:
    try:
        return json.loads(_config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config(cfg: dict) -> None:
    _config_path().write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _hash(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def _is_valid_pin(pin: str) -> bool:
    has_letter = bool(re.search(r'[A-Za-z]', pin))
    has_digit  = bool(re.search(r'[0-9]', pin))
    has_symbol = bool(re.search(r'[^A-Za-z0-9]', pin))
    return len(pin) >= 6 and has_letter and has_digit and has_symbol


def _cascade():
    path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    return cv2.CascadeClassifier(path)


def _largest_face(gray_frame, cascade):
    faces = cascade.detectMultiScale(gray_frame, scaleFactor=1.3, minNeighbors=5, minSize=(100, 100))
    if len(faces) == 0:
        return None
    return max(faces, key=lambda f: f[2] * f[3])


def _open_camera():
    """DirectShow (CAP_DSHOW) opens dramatically faster than the default
    Windows backend (MSMF), and a smaller capture resolution makes face
    detection much faster per frame too."""
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)   # fallback if DSHOW isn't available
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return cap


def require_face_or_pin() -> bool:
    """
    Shows the combined lock screen. Returns True to let JARVIS continue
    starting, False if the user closed the window or ran out of attempts.
    """
    cfg = _load_config()
    stored_hash = cfg.get("pin_hash", "")
    has_pin = bool(stored_hash)
    face_enrolled = _face_model_path().exists()
    face_reason = _face_unavailable_reason()
    has_face = face_enrolled and not face_reason

    result = {"ok": False}

    root = tk.Tk()
    root.title("JARVIS — Access")
    root.configure(bg="#0a0e14")
    root.geometry("420x480")
    root.resizable(False, False)
    root.eval('tk::PlaceWindow . center')

    title_label = tk.Label(root, text="", fg="#4fd1e8", bg="#0a0e14", font=("Segoe UI", 13, "bold"))
    title_label.pack(pady=(18, 6))

    sub_label = tk.Label(root, text="", fg="#6b7785", bg="#0a0e14", font=("Segoe UI", 9), wraplength=380)
    sub_label.pack()

    video_label = tk.Label(root, bg="#131924")

    video_frame_state = {"cap": None, "running": False, "hold": 0, "start": 0.0}

    entry_frame = tk.Frame(root, bg="#0a0e14")
    entry = tk.Entry(entry_frame, show="•", justify="center", font=("Segoe UI", 16),
                      bg="#131924", fg="#e6f1f5", insertbackground="#e6f1f5",
                      relief="flat", width=20)
    confirm_entry = tk.Entry(entry_frame, show="•", justify="center", font=("Segoe UI", 14),
                              bg="#131924", fg="#e6f1f5", insertbackground="#e6f1f5",
                              relief="flat", width=20)
    error_label = tk.Label(root, text="", fg="#ff6b6b", bg="#0a0e14", font=("Segoe UI", 9), wraplength=380)
    error_label.pack(pady=(6, 0))

    status_label = tk.Label(root, text="", fg="#5a6472", bg="#0a0e14", font=("Segoe UI", 8), wraplength=380)
    status_label.pack(side="bottom", pady=10)

    button_frame = tk.Frame(root, bg="#0a0e14")

    attempts = {"left": MAX_PIN_ATTEMPTS}

    def _stop_camera():
        video_frame_state["running"] = False
        cap = video_frame_state.get("cap")
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
        video_frame_state["cap"] = None

    def _close_ok():
        _stop_camera()
        result["ok"] = True
        root.destroy()

    def _close_cancel():
        _stop_camera()
        root.destroy()

    def _show_pin_ui(is_setup: bool, on_success, status_text: str = ""):
        video_label.pack_forget()
        for w in button_frame.winfo_children():
            w.destroy()
        button_frame.pack_forget()

        entry_frame.pack(pady=10)
        entry.pack_forget()
        confirm_entry.pack_forget()
        entry.pack(pady=(0, 6))
        entry.delete(0, "end")
        error_label.config(text="")
        status_label.config(text=status_text)
        title_label.config(text="Create your JARVIS PIN" if is_setup else "Enter PIN to unlock JARVIS")
        sub_label.config(text="Must include a letter, a number, and a symbol (6+ chars)" if is_setup else "")

        if is_setup:
            confirm_entry.pack(pady=(0, 4))
            confirm_entry.delete(0, "end")
        entry.focus_set()

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
                cfg2 = _load_config()
                cfg2["pin_hash"] = _hash(pin)
                _save_config(cfg2)
                on_success()
                return

            if _hash(pin) == stored_hash:
                on_success()
            else:
                attempts["left"] -= 1
                if attempts["left"] <= 0:
                    error_label.config(text="Too many attempts. Closing.")
                    root.after(1200, _close_cancel)
                else:
                    error_label.config(text=f"Incorrect PIN — {attempts['left']} attempt(s) left.")
                    entry.delete(0, "end")

        entry.bind("<Return>", _submit)
        confirm_entry.bind("<Return>", _submit)

        button_frame.pack(pady=8)
        tk.Button(button_frame, text="Set PIN" if is_setup else "Unlock", command=_submit,
                  bg="#1c8ca8", fg="white", activebackground="#166b82", relief="flat",
                  font=("Segoe UI", 10, "bold"), width=12).pack()

    def _run_enrollment():
        entry_frame.pack_forget()
        for w in button_frame.winfo_children():
            w.destroy()
        button_frame.pack_forget()
        video_label.pack(pady=10)
        title_label.config(text="Look at the camera")
        sub_label.config(text="Hold still — capturing your face now...")
        error_label.config(text="")

        cascade = _cascade()
        cap = _open_camera()
        video_frame_state["cap"] = cap
        video_frame_state["running"] = True
        samples = []

        def _step():
            if not video_frame_state["running"]:
                return
            ret, frame = cap.read()
            if not ret:
                root.after(30, _step)
                return

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            box = _largest_face(gray, cascade)
            display = frame.copy()
            if box is not None:
                x, y, w, h = box
                cv2.rectangle(display, (x, y), (x + w, y + h), (79, 209, 232), 2)
                if len(samples) < ENROLL_SAMPLES:
                    face_roi = cv2.resize(gray[y:y + h, x:x + w], FACE_SIZE)
                    samples.append(face_roi)

            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb).resize((360, 270))
            photo = ImageTk.PhotoImage(img)
            video_label.imgtk = photo
            video_label.configure(image=photo)

            sub_label.config(text=f"Captured {len(samples)}/{ENROLL_SAMPLES} — hold still...")

            if len(samples) >= ENROLL_SAMPLES:
                _stop_camera()
                import numpy as np
                recognizer = cv2.face.LBPHFaceRecognizer_create()
                recognizer.train(samples, np.array([1] * len(samples)))
                recognizer.save(str(_face_model_path()))
                title_label.config(text="Face enrolled!")
                sub_label.config(text="You're all set — JARVIS will recognize you next time.")
                root.after(1500, _close_ok)
                return

            root.after(30, _step)

        _step()

    def _offer_face_enrollment():
        video_label.pack_forget()
        entry_frame.pack_forget()
        title_label.config(text="Enable Face Unlock?")
        sub_label.config(text="Optional — you can always use your PIN instead, even with this on.")
        error_label.config(text="")
        status_label.config(text="")

        for w in button_frame.winfo_children():
            w.destroy()
        button_frame.pack(pady=12)
        tk.Button(button_frame, text="Set up Face Unlock", command=_run_enrollment,
                  bg="#1c8ca8", fg="white", activebackground="#166b82", relief="flat",
                  font=("Segoe UI", 10, "bold"), width=18).pack(pady=4)
        tk.Button(button_frame, text="Skip for now", command=_close_ok,
                  bg="#242c38", fg="#c8d3dc", activebackground="#2f3947", relief="flat",
                  font=("Segoe UI", 9), width=18).pack(pady=4)

    def _show_face_unavailable_and_continue(after):
        """Shown instead of silently skipping — makes the reason visible."""
        video_label.pack_forget()
        entry_frame.pack_forget()
        title_label.config(text="Face Unlock unavailable")
        sub_label.config(text=(
            f"{face_reason}\n\nRun this to fix it:\n"
            "pip uninstall opencv-python opencv-contrib-python -y\n"
            "pip install opencv-contrib-python"
        ))
        error_label.config(text="")
        status_label.config(text="")

        for w in button_frame.winfo_children():
            w.destroy()
        button_frame.pack(pady=12)
        tk.Button(button_frame, text="Continue with PIN only", command=after,
                  bg="#1c8ca8", fg="white", activebackground="#166b82", relief="flat",
                  font=("Segoe UI", 10, "bold"), width=20).pack()

    def _fallback_to_pin():
        video_label.pack_forget()
        for w in button_frame.winfo_children():
            w.destroy()
        button_frame.pack_forget()
        _show_pin_ui(is_setup=False, on_success=_close_ok)

    def _run_face_check():
        video_label.pack(pady=10)
        title_label.config(text="Looking for your face...")
        sub_label.config(text="")
        error_label.config(text="")
        status_label.config(text="")

        for w in button_frame.winfo_children():
            w.destroy()
        button_frame.pack(pady=6)
        tk.Button(button_frame, text="Use PIN instead",
                  command=lambda: (_stop_camera(), _fallback_to_pin()),
                  bg="#242c38", fg="#c8d3dc", activebackground="#2f3947", relief="flat",
                  font=("Segoe UI", 9), width=16).pack()

        cascade = _cascade()
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.read(str(_face_model_path()))

        cap = _open_camera()
        video_frame_state["cap"] = cap
        video_frame_state["running"] = True
        video_frame_state["hold"] = 0
        video_frame_state["start"] = time.monotonic()

        def _step():
            if not video_frame_state["running"]:
                return
            if time.monotonic() - video_frame_state["start"] > FACE_TIMEOUT:
                _stop_camera()
                _fallback_to_pin()
                return

            ret, frame = cap.read()
            if not ret:
                root.after(30, _step)
                return

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            box = _largest_face(gray, cascade)
            display = frame.copy()

            if box is not None:
                x, y, w, h = box
                face_roi = cv2.resize(gray[y:y + h, x:x + w], FACE_SIZE)
                label_id, confidence = recognizer.predict(face_roi)
                matched = confidence < CONFIDENCE_THRESHOLD
                color = (79, 209, 232) if matched else (255, 107, 107)
                cv2.rectangle(display, (x, y), (x + w, y + h), color, 2)

                if matched:
                    video_frame_state["hold"] += 1
                else:
                    video_frame_state["hold"] = 0

                if video_frame_state["hold"] >= MATCH_HOLD_FRAMES:
                    title_label.config(text="Welcome back!")
                    sub_label.config(text="")
                    _stop_camera()
                    root.after(400, _close_ok)
                    return

            rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb).resize((360, 270))
            photo = ImageTk.PhotoImage(img)
            video_label.imgtk = photo
            video_label.configure(image=photo)

            root.after(30, _step)

        _step()

    # ── Decide the starting stage ──────────────────────────────────────────
    if not has_pin:
        def _after_pin_setup():
            if _HAS_FACE_MODULE:
                _offer_face_enrollment()
            else:
                _show_face_unavailable_and_continue(_close_ok)
        _show_pin_ui(is_setup=True, on_success=_after_pin_setup)
    elif has_face:
        _run_face_check()
    else:
        status_text = f"Face unlock: {face_reason}" if face_reason else "Face unlock: not set up yet."
        _show_pin_ui(is_setup=False, on_success=_close_ok, status_text=status_text)

    root.protocol("WM_DELETE_WINDOW", _close_cancel)
    root.mainloop()

    return result["ok"]