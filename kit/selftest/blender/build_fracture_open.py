"""build_fracture_open.py — twin of build_fracture.py with the word `open` (see its docstring for what the build
must say). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("open")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_fracture.py"), run_name="__main__")
