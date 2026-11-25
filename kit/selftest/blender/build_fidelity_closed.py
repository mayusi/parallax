"""build_fidelity_closed.py — NEGATIVE fixture for the `collision` gate: build_fidelity.py's model, but its arch
DECLARES a convex hull (`a.collision("arch", "hull")`). A hull would shut the doorway a character walks through:
the build must fail `collision` by name. Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("closed")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_fidelity.py"), run_name="__main__")
