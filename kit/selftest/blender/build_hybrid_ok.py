"""build_hybrid_ok.py — the ok case of build_hybrid.py (the hybrid route: a generated part on a game mesh). Used by
`lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("ok")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_hybrid.py"), run_name="__main__")
