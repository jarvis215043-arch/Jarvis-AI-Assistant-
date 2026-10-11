"""actions/jarvis_update.py — "Check for updates" / "update yourself".
Uses updater.py. Installing asks you to CONFIRM, then JARVIS closes, updates,
and starts again by itself (source installs) or runs the new installer (exe)."""
import os
import subprocess
import sys
import threading
from pathlib import Path

def _load_helpers():
    import importlib.util, sys
    from pathlib import Path
    key = "actions._helpers"
    if key in sys.modules:
        return sys.modules[key]
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(key, str(base / "actions" / "_helpers.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


H = _load_helpers()


def _updater():
    import importlib.util
    key = "jarvis_updater"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, str(H.base_dir() / "updater.py"))
    mod = importlib.util.module_from_spec(spec); sys.modules[key] = mod; spec.loader.exec_module(mod)
    return mod


def _quit_app():
    from PyQt6.QtCore import QMetaObject, Qt
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        QMetaObject.invokeMethod(app, "quit", Qt.ConnectionType.QueuedConnection)


def _restart_with(U, extra: list) -> None:
    """Close JARVIS, let updater.py do its work, then start JARVIS again."""
    flags = 0x00000008 | 0x00000200 if sys.platform == "win32" else 0      # detached, new group
    subprocess.Popen([sys.executable, str(H.base_dir() / "updater.py"), "--wait", str(os.getpid()), *extra, "--restart"],
                     cwd=str(H.base_dir()), creationflags=flags, close_fds=True)
    threading.Timer(2.0, _quit_app).start()


def _zip_actions(act: str, parameters: dict, player) -> str:
    from core import confirm as gate
    U = _updater()
    if getattr(sys, "frozen", False):
        return ("You're running Jarvis.exe — install the update in your Jarvis source folder with install_update.bat, "
                "then run rebuild.bat.")
    if act == "rollback":
        root = H.base_dir() / "backups"
        if not root.exists() or not list(root.glob("before-*/_info.json")):
            return "There's no installed update to undo."
        def _go():
            _restart_with(U, ["--rollback"])
            return "Undoing the last update — JARVIS will close and come back in a moment."
        return gate.request("jarvis_rollback", "Undo the last JARVIS update?",
                            "JARVIS will close, put the previous files back and restart.", _go)
    path = str((parameters or {}).get("path") or "").strip()
    z = Path(path) if path else U.find_update_zip()
    if not z or not z.exists():
        return ("I couldn't find a JARVIS update zip in Downloads or on the Desktop. Save the JARVIS_…_update.zip "
                "there (don't unzip it), then ask again — or drag it onto install_update.bat.")
    try:
        plan = U.install_zip(z, dry=True)
    except Exception as e:
        return f"That zip can't be installed: {e}"
    if not plan["replaced"] and not plan["added"]:
        return f"{z.name} is already installed — nothing to change."
    detail = (f"{z.name}: {len(plan['replaced'])} files updated, {len(plan['added'])} new "
              f"({plan['from']} → {plan['to']}). Replaced files are backed up first; 'undo the last update' reverses it.")
    if plan["edited_by_you"]:
        detail += " You edited: " + ", ".join(plan["edited_by_you"][:4]) + " — your copies go in the backup."
    def _go():
        _restart_with(U, ["--install-zip", str(z)])
        return "Installing — JARVIS will close and come back in a moment."
    return gate.request("jarvis_install_zip", f"Install {plan['to']}?", detail, _go)


def jarvis_update(parameters: dict, player=None) -> str:
    act = str((parameters or {}).get("action") or "check").lower()
    if act in ("install_zip", "install", "zip", "rollback", "undo"):
        return _zip_actions("rollback" if act in ("rollback", "undo") else "install", parameters, player)
    try:
        U = _updater()
        info = U.check()
    except Exception as e:
        return f"I couldn't check for updates: {e}"
    if act != "apply" or not info.get("available"):
        return info["message"] + (" Say 'install the update' to install it." if info.get("available") else "")
    from core import confirm as gate

    def _go():
        if getattr(sys, "frozen", False):
            exe = U.download_installer(info)
            subprocess.Popen([str(exe)], close_fds=True)
        else:
            flags = 0x00000008 | 0x00000200 if sys.platform == "win32" else 0   # detached, new group
            subprocess.Popen([sys.executable, str(H.base_dir() / "updater.py"), "--wait", str(os.getpid()), "--restart"],
                             cwd=str(H.base_dir()), creationflags=flags, close_fds=True)
        threading.Timer(2.0, _quit_app).start()
        return "Updating — JARVIS will close and come back in a minute."
    return gate.request("jarvis_update", f"Install JARVIS update {info.get('latest', '')}?",
                        "JARVIS will close, update and restart. Your keys, settings and memory are kept.", _go)


TOOL = {
    "name": "jarvis_update",
    "description": ("JARVIS updates. action='install_zip' installs a downloaded JARVIS update zip (finds the newest in "
                    "Downloads/Desktop, or path) — use for 'install the update'; 'rollback' undoes the last installed "
                    "update; 'check' (default) / 'apply' use GitHub if set up. All ask to CONFIRM."),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "'install_zip', 'rollback', 'check' or 'apply'."},
        "path": {"type": "STRING", "description": "Optional: full path of the update zip."}}, "required": []},
    "handler": jarvis_update,
}
