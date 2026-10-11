"""
core/suit_up.py — The start-up ("suit up") sound.

How start-up works now:
  1. Right after unlocking, the sound starts and the JARVIS window opens
     straight away — plugins, the mic connection etc. load while it plays.
  2. JARVIS stays quiet until the sound has finished: the briefing waits for it,
     and the mic isn't sent to JARVIS yet (so nothing talks over the sound).
  3. Press Esc in the JARVIS window to skip the sound; JARVIS carries on at once.

SOUND: put your file at config/suit_up.mp3 (or .wav / .m4a / .wma).
No file = no waiting, JARVIS starts normally.

The sound plays in a separate PowerShell process (Windows' built-in media
player), never inside JARVIS, so a sound problem can't crash the app.
"""
import subprocess
import sys
import threading
import time
from pathlib import Path

MAX_SECONDS = 60.0   # safety limit: JARVIS never waits longer than this
SOUND_NAMES = ("suit_up.mp3", "suit_up.wav", "suit_up.m4a", "suit_up.wma")

_lock = threading.Lock()
_proc: subprocess.Popen | None = None
_started_at = 0.0
_play_t0: float | None = None     # moment the sound ACTUALLY started (after the player loaded it)
_length: float | None = None      # length of the sound in seconds
_done = threading.Event()
_done.set()   # nothing playing until start_intro_sound() is called


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _sound_path() -> Path | None:
    for name in SOUND_NAMES:
        path = _base_dir() / "config" / name
        if path.exists():
            return path
    return None


def _launch(path: Path) -> subprocess.Popen:
    if sys.platform == "win32":
        safe = str(path).replace("'", "''")   # a folder like "Ranjan's PC" can't break it
        ps_script = (
            "Add-Type -AssemblyName presentationCore; "
            "$p = New-Object System.Windows.Media.MediaPlayer; "
            f"$p.Open([uri]'{safe}'); "
            # wait (max 5 s) for the file to load so its length is known
            "$t = 0; while (-not $p.NaturalDuration.HasTimeSpan -and $t -lt 50) "
            "{ Start-Sleep -Milliseconds 100; $t++ }; "
            "if (-not $p.NaturalDuration.HasTimeSpan) { exit 1 }; "   # couldn't open it
            "$p.Play(); "
            "[Console]::Out.WriteLine('PLAYING ' + $p.NaturalDuration.TimeSpan.TotalSeconds.ToString([Globalization.CultureInfo]::InvariantCulture)); "
            "[Console]::Out.Flush(); "
            f"$len = [Math]::Min($p.NaturalDuration.TimeSpan.TotalSeconds + 0.3, {MAX_SECONDS}); "
            "Start-Sleep -Milliseconds ([int]($len * 1000)); $p.Close()"
        )
        return subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
    if sys.platform == "darwin":
        return subprocess.Popen(["afplay", str(path)])
    return subprocess.Popen(["mpg123", "-q", str(path)])


def _watch(proc: subprocess.Popen) -> None:
    """Notes the real start moment + length the player reports, then marks the
    intro as finished when the sound process ends (or times out)."""
    global _play_t0, _length
    try:
        if proc.stdout is not None:
            line = proc.stdout.readline()          # "PLAYING 20.27" once the sound really starts
            if line.startswith("PLAYING"):
                _length = float(line.split()[1])
                _play_t0 = time.monotonic()
    except Exception:
        pass
    if _play_t0 is None:                           # player didn't report (other OS): assume now
        _play_t0 = time.monotonic()
    try:
        proc.wait(timeout=MAX_SECONDS)
    except Exception:
        stop_intro_sound()
    _done.set()


def has_intro_sound() -> bool:
    return _sound_path() is not None


def prepare_intro() -> None:
    """Marks the intro as 'about to play' BEFORE the sound starts, so the mic and the
    briefing already wait while the intro screen opens (the screen starts the sound)."""
    global _play_t0, _length
    _play_t0 = _length = None
    _done.clear()


def intro_timing():
    """(moment the sound really started, its length in seconds) — None until known."""
    return _play_t0, _length


def start_intro_sound() -> bool:
    """Starts the sound WITHOUT blocking. Returns True if a sound is playing."""
    global _proc, _started_at, _play_t0, _length
    path = _sound_path()
    if path is None:
        print("[SuitUp] No sound file in config/ — starting without intro sound.")
        _done.set()
        return False
    _play_t0 = _length = None
    try:
        proc = _launch(path)
    except Exception as e:
        print(f"[SuitUp] Could not play sound: {e}")
        _done.set()
        return False
    with _lock:
        _proc = proc
        _started_at = time.monotonic()
        _done.clear()
    threading.Thread(target=_watch, args=(proc,), daemon=True).start()
    print(f"[SuitUp] Playing {path.name}")
    return True


def intro_playing() -> bool:
    """True while the start-up sound is still playing."""
    return not _done.is_set()


def stop_intro_sound() -> bool:
    """Skips the sound (Esc). Returns True if it was playing."""
    with _lock:
        proc = _proc
    was_playing = intro_playing()
    if proc and proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass
    _done.set()
    return was_playing


def wait_for_intro(timeout: float = MAX_SECONDS) -> None:
    """Blocks until the sound has finished or was skipped."""
    _done.wait(timeout)


def play_suit_up_sequence() -> None:
    """Kept so older code calling it still works — now it just starts the sound."""
    start_intro_sound()