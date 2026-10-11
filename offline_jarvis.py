r"""
offline_jarvis.py — Basic JARVIS with NO internet.

Speech recognition: Vosk (offline).  Brain: Ollama (local AI).  Voice: Windows'
built-in voice (pyttsx3).  Handles: the time and date, opening apps, volume, and
general chat. Start it with offline_jarvis.bat when the internet is down.

One-time setup (needs internet once):
  1. python -m pip install vosk pyttsx3 sounddevice requests
  2. Download the small English model from https://alphacephei.com/vosk/models
     (vosk-model-small-en-us-0.15, ~40 MB), unzip it into  models\  so you have
     models\vosk-model-small-en-us-0.15\
  3. Install Ollama from https://ollama.com, then run:  ollama pull llama3.2
"""
import json
import os
import queue
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
MODEL_DIR = next((p for p in (BASE / "models").glob("vosk-model*") if p.is_dir()), None) if (BASE / "models").exists() else None
OLLAMA = "http://localhost:11434"
LLM = "llama3.2"
APPS = {"notepad": "notepad", "calculator": "calc", "paint": "mspaint", "explorer": "explorer",
        "file explorer": "explorer", "command prompt": "cmd", "settings": "ms-settings:"}


def speak(engine, text: str) -> None:
    print(f"JARVIS: {text}")
    engine.say(text)
    engine.runAndWait()


def ask_llm(history: list, text: str) -> str:
    import requests
    history.append({"role": "user", "content": text})
    try:
        r = requests.post(f"{OLLAMA}/api/chat", json={"model": LLM, "messages": history[-12:], "stream": False}, timeout=120)
        reply = r.json()["message"]["content"].strip()
    except Exception:
        return "My offline brain isn't running. Start Ollama and make sure llama3.2 is downloaded."
    history.append({"role": "assistant", "content": reply})
    return reply


def volume(up: bool) -> None:
    try:
        import pyautogui
        for _ in range(5):
            pyautogui.press("volumeup" if up else "volumedown")
    except Exception:
        pass


def handle(engine, history: list, text: str) -> bool:
    t = text.lower().strip()
    if not t:
        return True
    if any(w in t for w in ("goodbye jarvis", "exit offline", "close offline", "shut down offline")):
        speak(engine, "Going offline. Goodbye.")
        return False
    if "time" in t and ("what" in t or "tell" in t):
        speak(engine, datetime.now().strftime("It's %I:%M %p.").replace(" 0", " "))
    elif "date" in t or "what day" in t:
        speak(engine, datetime.now().strftime("Today is %A, %d %B %Y."))
    elif t.startswith("open "):
        name = t[5:].strip()
        target = APPS.get(name, name)
        try:
            os.startfile(target)  # type: ignore[attr-defined]
            speak(engine, f"Opening {name}.")
        except Exception:
            speak(engine, f"I couldn't open {name}.")
    elif "volume up" in t or "louder" in t:
        volume(True); speak(engine, "Volume up.")
    elif "volume down" in t or "quieter" in t:
        volume(False); speak(engine, "Volume down.")
    else:
        speak(engine, ask_llm(history, text))
    return True


def main() -> None:
    try:
        import pyttsx3
        import sounddevice as sd
        from vosk import KaldiRecognizer, Model
    except ImportError as e:
        print(f"Missing package: {e}. Run: python -m pip install vosk pyttsx3 sounddevice requests")
        input("Press Enter to close."); return
    if MODEL_DIR is None:
        print("No Vosk model found. Download vosk-model-small-en-us-0.15 from https://alphacephei.com/vosk/models "
              "and unzip it into the 'models' folder next to this file.")
        input("Press Enter to close."); return
    engine = pyttsx3.init()
    engine.setProperty("rate", 175)
    rec = KaldiRecognizer(Model(str(MODEL_DIR)), 16000)
    q: queue.Queue = queue.Queue()
    history = [{"role": "system", "content": "You are JARVIS, a helpful, slightly witty assistant running "
                "offline. Keep answers to 1-3 short sentences; they will be spoken aloud."}]

    def cb(indata, frames, t, status):
        q.put(bytes(indata))

    speak(engine, "Offline mode ready. I can tell the time, open apps, change the volume, and chat.")
    with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype="int16", channels=1, callback=cb):
        running = True
        while running:
            data = q.get()
            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get("text", "")
                if text:
                    print(f"You: {text}")
                    while not q.empty():
                        q.get_nowait()
                    running = handle(engine, history, text)
                    while not q.empty():          # drop what the mic heard while JARVIS talked
                        q.get_nowait()


if __name__ == "__main__":
    main()
