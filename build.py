"""
build.py — Builds Jarvis.exe with PyInstaller and copies the runtime folders
next to it. Run from the project folder:  python build.py   (rebuild.bat does this)

WHY THIS EXISTS
PyInstaller only bundles modules it can SEE being imported, starting from main.py.
Actions and plugins are loaded from disk at runtime, so PyInstaller never looks
inside them — any library only they use (email.mime.text for Gmail, anything a
new action like demo mode needs) is missing from the exe and the file gets
rejected with "No module named ...".

This script reads every .py file in the project, collects everything they import,
and passes each one to PyInstaller as a hidden import. Add a new action or plugin,
run this again, and its libraries are bundled automatically — no more editing a
list of --hidden-import lines by hand.
"""
import ast
import hashlib
import importlib.util
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Folders whose .py files get scanned for imports.
SCAN_DIRS = ["core", "actions", "plugins", "memory", "dashboard", "config"]
SCAN_FILES = ["main.py", "ui.py"]

# Folders copied next to Jarvis.exe after the build (loaded from disk at runtime).
COPY_DIRS = ["actions", "config", "memory", "plugins", "dashboard", "platform-tools"]

# Extra PyInstaller options that scanning can't work out on its own.
EXTRA_ARGS = [
    "--collect-all=mediapipe",
    "--collect-data=cv2",
    "--collect-submodules=email",
    "--collect-submodules=uvicorn",      # dashboard server loads these by name
    "--hidden-import=PIL._tkinter_finder",
    "--hidden-import=core.gmail_tool",
]
# PyOpenGL loads its Windows driver layer by name at runtime (GPU orb).
if importlib.util.find_spec("OpenGL") is not None:
    EXTRA_ARGS += ["--collect-submodules=OpenGL"]


def _local_names() -> set[str]:
    """Top-level names that belong to this project, not to installed packages."""
    names = {p.stem for p in ROOT.glob("*.py")}
    names |= {p.name for p in ROOT.iterdir() if p.is_dir()}
    return names


def _files_to_scan() -> list[Path]:
    files = [ROOT / f for f in SCAN_FILES if (ROOT / f).exists()]
    for d in SCAN_DIRS:
        folder = ROOT / d
        if folder.is_dir():
            files += sorted(folder.rglob("*.py"))
    return [f for f in files if "__pycache__" not in f.parts]


def _imports_in(path: Path) -> set[str]:
    """Every absolute module name imported anywhere in the file (including inside
    functions and try/except blocks)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as e:
        print(f"  ! Skipping {path.relative_to(ROOT)} — syntax error: {e}")
        return set()

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
            # "from PIL import Image" — Image may itself be a submodule.
            for alias in node.names:
                if alias.name != "*":
                    found.add(f"{node.module}.{alias.name}")
    return found


def _is_installed(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        # Raised when the parent isn't a package ("email.mime.text.MIMEText"),
        # or the parent fails to import. Either way: not a module we can bundle.
        return False


def collect_hidden_imports() -> list[str]:
    local = _local_names()
    wanted: set[str] = set()
    for f in _files_to_scan():
        wanted |= _imports_in(f)

    result = []
    for name in sorted(wanted):
        top = name.split(".")[0]
        if top in local or top == "__future__":
            continue
        if _is_installed(top) and _is_installed(name):
            result.append(name)
    return result


def run_pyinstaller(hidden: list[str]) -> None:
    import PyInstaller.__main__

    args = [
        "main.py",
        "--name=Jarvis",
        "--onedir",
        "--noconfirm",
        f"--paths={ROOT}",
    ]
    icon = ROOT / "config" / "jarvis.ico"
    if icon.exists():
        args.append(f"--icon={icon}")
    args += EXTRA_ARGS
    args += [f"--hidden-import={m}" for m in hidden]
    PyInstaller.__main__.run(args)


# In these folders the exe WRITES its own data (Jarvis's memory, login tokens,
# settings). Existing .json files there are never overwritten, or every rebuild
# would wipe what Jarvis has learned and log you out of Google.
KEEP_EXISTING_JSON = {"config", "memory"}


def _copy_folder(src: Path, dst: Path, keep_json: bool) -> None:
    for f in src.rglob("*"):
        if "__pycache__" in f.parts or not f.is_file():
            continue
        target = dst / f.relative_to(src)
        if keep_json and f.suffix == ".json" and target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)


def copy_runtime_files() -> None:
    dist = ROOT / "dist" / "Jarvis"
    for d in COPY_DIRS:
        src = ROOT / d
        if src.is_dir():
            _copy_folder(src, dist / d, keep_json=d in KEEP_EXISTING_JSON)

    # Every core file goes next to the exe too, so modules loaded by file path
    # (gmail_tool, text_generation, ...) always find the latest version.
    (dist / "core").mkdir(parents=True, exist_ok=True)
    for f in (ROOT / "core").iterdir():
        if f.is_file() and f.suffix in (".py", ".txt", ".json"):
            shutil.copy2(f, dist / "core" / f.name)

    for f in ("face.png", "watchdog.bat"):
        if (ROOT / f).exists():
            shutil.copy2(ROOT / f, dist / f)


def quick_update() -> int:
    """Copies edited actions/plugins/core files into dist without rebuilding."""
    if not (ROOT / "dist" / "Jarvis" / "Jarvis.exe").exists():
        print("No dist\\Jarvis\\Jarvis.exe yet — run rebuild.bat first.")
        return 1
    copy_runtime_files()
    print("Copied. Restart Jarvis.exe to load the changes.")
    return 0


# ── Skip the slow part when it isn't needed ──────────────────────────────────
# Files that get sealed INSIDE Jarvis.exe. If none of these changed (and no new
# library is imported anywhere), PyInstaller would produce the exact same exe,
# so we skip it and only copy the actions/plugins/prompt files — seconds, not minutes.
FROZEN_FILES = ["main.py", "ui.py"]
FROZEN_DIRS = ["core", "memory", "dashboard", "config"]
FINGERPRINT = ROOT / "build" / "jarvis_last_build.json"


def _fingerprint(hidden: list[str]) -> str:
    h = hashlib.sha256()
    files = [ROOT / f for f in FROZEN_FILES if (ROOT / f).exists()]
    for d in FROZEN_DIRS:
        if (ROOT / d).is_dir():
            files += sorted((ROOT / d).rglob("*.py"))
    for f in files:
        if "__pycache__" in f.parts:
            continue
        h.update(str(f.relative_to(ROOT)).encode())
        h.update(f.read_bytes())
    h.update("\n".join(hidden).encode())
    h.update("\n".join(EXTRA_ARGS).encode())
    return h.hexdigest()


def _needs_full_build(fp: str) -> bool:
    if "--full" in sys.argv:
        return True
    if not (ROOT / "dist" / "Jarvis" / "Jarvis.exe").exists():
        return True
    try:
        return json.loads(FINGERPRINT.read_text(encoding="utf-8")).get("fingerprint") != fp
    except Exception:
        return True


def _save_fingerprint(fp: str) -> None:
    FINGERPRINT.parent.mkdir(parents=True, exist_ok=True)
    FINGERPRINT.write_text(json.dumps({"fingerprint": fp}), encoding="utf-8")


def verify_dist() -> bool:
    """Checks the finished dist folder has everything JARVIS needs, so an
    incomplete build (e.g. the window closed early) is caught HERE, not mid-demo."""
    dist = ROOT / "dist" / "Jarvis"
    need = ["Jarvis.exe", "_internal", "actions", "plugins", "core", "config", "memory",
            "core/prompt.txt", "config/suit_up.mp3", "actions/more_tools.py"]
    missing = [n for n in need if not (dist / n).exists()]
    n_actions = len(list((dist / "actions").glob("*.py"))) if (dist / "actions").exists() else 0
    if n_actions < 90:
        missing.append(f"actions (only {n_actions} files, expected ~100)")
    if missing:
        print("\n" + "!" * 60 + "\n  BUILD INCOMPLETE — missing: " + ", ".join(missing))
        print("  Run rebuild.bat again and wait for 'Done! Ready to test'.\n" + "!" * 60)
        return False
    print(f"  Verified: Jarvis.exe + {n_actions} tools + core, config, memory, plugins ✓")
    return True


def main() -> int:
    if "--quick" in sys.argv:
        return quick_update()

    started = time.monotonic()
    print("Scanning project imports...")
    hidden = collect_hidden_imports()
    print(f"  {len(hidden)} modules will be bundled.")

    fp = _fingerprint(hidden)
    if not _needs_full_build(fp):
        print("\nOnly actions / plugins / prompt changed — no need to rebuild the exe.")
        copy_runtime_files()
        if not verify_dist():
            return 1
        print(f"Done in {time.monotonic() - started:.0f}s! Restart Jarvis.exe to load the changes.")
        print("(To force a full rebuild anyway: python build.py --full)")
        return 0
    print("  main.py, ui.py, core or a library changed — full rebuild needed.\n")

    try:
        run_pyinstaller(hidden)
    except SystemExit as e:
        if e.code not in (0, None):
            print("\nBUILD FAILED — external files were NOT copied.")
            return 1

    print("\nBuild succeeded. Copying runtime folders into dist\\Jarvis ...")
    copy_runtime_files()
    if not verify_dist():
        return 1
    _save_fingerprint(fp)
    print(f"Done in {(time.monotonic() - started) / 60:.1f} min! Ready to test: dist\\Jarvis\\Jarvis.exe")
    return 0


if __name__ == "__main__":
    sys.exit(main())