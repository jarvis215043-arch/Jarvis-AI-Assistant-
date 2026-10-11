r"""
diagnostics.py — Run the JARVIS self-test WITHOUT starting JARVIS
(useful when JARVIS won't start). Double-click diagnostics.bat, or:
    python diagnostics.py          full test
    python diagnostics.py --quick  skip internet / mic / webcam
The report is printed and saved to Documents\JARVIS\diagnostics.txt.
"""
import sys
import types
import logging as _logging
_logging.getLogger("google_genai.models").setLevel(_logging.ERROR)   # hides a harmless "AFC" notice
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))


def main() -> int:
    from core import diagnostics as D
    from core.secure_config import read_config
    from core.action_loader import discover_actions
    print("Loading tools…")
    reg = discover_actions(BASE / "actions", logger=lambda m: None)
    ctx = {"player": None, "speak": None}
    quick = "--quick" in sys.argv
    print("Running checks (about 30 seconds)…\n")
    rep = D.run(read_config(), reg.get_tool_declarations, lambda n, a: reg.run(n, a, ctx),
                network=not quick, hardware=not quick)
    text = rep.text()
    print(text)
    out = Path.home() / "Documents" / "JARVIS"
    out.mkdir(parents=True, exist_ok=True)
    (out / "diagnostics.txt").write_text(text, encoding="utf-8")
    print(f"\nSaved to {out / 'diagnostics.txt'}")
    return 1 if rep.counts()["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
