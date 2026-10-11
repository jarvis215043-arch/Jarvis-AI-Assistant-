r"""
clap_launcher.py — Clap twice to start JARVIS.

OPTIONAL. Opening JARVIS normally already shows a "clap twice" screen. This
launcher is for starting JARVIS without opening anything first: it runs quietly
in the background, and a double clap starts JARVIS straight at the PIN screen. While JARVIS is running
it stops listening (so it doesn't use the mic), and starts again after JARVIS
closes. Nothing is recorded or sent anywhere — it only measures loudness.

  python clap_launcher.py             run it (a small console shows what it hears)
  python clap_launcher.py --test      test mode: shows levels and every clap it detects
  python clap_launcher.py --install   start it automatically, hidden, when Windows starts
  python clap_launcher.py --uninstall stop starting it with Windows
"""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from core.clap import ClapDetector   # noqa: E402

RATE = 16000
STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP_FILE = STARTUP_DIR / "JARVIS Clap Launcher.vbs"


def _cfg() -> dict:
    try:                                    # works while the keys are locked too
        from core.secure_config import read_config
        return read_config()
    except Exception:
        try:
            return json.loads((BASE / "config" / "api_keys.json").read_text(encoding="utf-8"))
        except Exception:
            return {}


def jarvis_running() -> bool:
    try:
        import psutil
    except ImportError:
        return False
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (p.info.get("name") or "").lower()
            cmd = " ".join(p.info.get("cmdline") or []).lower()
            if name == "jarvis.exe" or ("main.py" in cmd and str(BASE).lower() in cmd):
                return True
            if "main.py" in cmd and os.path.samefile(p.cwd(), BASE):
                return True
        except Exception:
            continue
    return False


def start_jarvis() -> None:
    exe = BASE / "dist" / "Jarvis" / "Jarvis.exe"
    if exe.exists():
        subprocess.Popen([str(exe), "--clapped"], cwd=str(exe.parent))
        return
    pyw = Path(sys.executable).with_name("pythonw.exe")
    py = str(pyw if pyw.exists() else sys.executable)
    subprocess.Popen([py, str(BASE / "main.py"), "--clapped"], cwd=str(BASE))


def install() -> None:
    pyw = Path(sys.executable).with_name("pythonw.exe")
    py = pyw if pyw.exists() else Path(sys.executable)
    STARTUP_DIR.mkdir(parents=True, exist_ok=True)
    STARTUP_FILE.write_text(
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'sh.CurrentDirectory = "{BASE}"\r\n'
        f'sh.Run Chr(34) & "{py}" & Chr(34) & " " & Chr(34) & "{BASE / "clap_launcher.py"}" & Chr(34), 0, False\r\n',
        encoding="utf-8")
    print(f"Installed: the clap launcher will start hidden every time Windows starts.\n  ({STARTUP_FILE})")
    print("Starting it now too...")
    subprocess.Popen([str(py), str(BASE / "clap_launcher.py")], cwd=str(BASE))


def uninstall() -> None:
    if STARTUP_FILE.exists():
        STARTUP_FILE.unlink()
        print("Removed — it won't start with Windows any more.")
    else:
        print("It wasn't set to start with Windows.")


def single_instance():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 47653))
        return s
    except OSError:
        return None


def listen(test: bool = False) -> None:
    import sounddevice as sd
    c = _cfg()
    det = ClapDetector(RATE, threshold=float(c.get("clap_threshold", 0.30)))
    print("Listening for a double clap... (Ctrl+C to stop)")
    while True:
        if not test and jarvis_running():
            time.sleep(3)
            continue
        fired = {"v": False}

        def cb(indata, frames, t, status):
            if det.feed(indata[:, 0] if indata.ndim > 1 else indata):
                fired["v"] = True
            if test:
                lvl = float(abs(indata).max()) / 32768
                bar = "#" * int(lvl * 60)
                print(f"\r level {lvl:4.2f} {bar:<60}", end="", flush=True)

        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=RATE // 20, callback=cb):
            while not fired["v"]:
                time.sleep(0.05)
                if not test and jarvis_running():
                    break
        if fired["v"]:
            print("\n👏👏 Double clap!")
            if not test and not jarvis_running():
                start_jarvis()
                for _ in range(40):                 # give JARVIS time to appear
                    if jarvis_running():
                        break
                    time.sleep(0.5)


def main() -> None:
    args = sys.argv[1:]
    if "--install" in args:
        install(); return
    if "--uninstall" in args:
        uninstall(); return
    lock = single_instance()
    if lock is None and "--test" not in args:
        print("The clap launcher is already running.")
        return
    try:
        listen(test="--test" in args)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
