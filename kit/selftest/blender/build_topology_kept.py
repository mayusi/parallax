"""build_topology_kept.py — twin of build_topology.py with the word `kept` (see its docstring for what the build must
say). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("kept")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_topology.py"), run_name="__main__")
