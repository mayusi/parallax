"""build_fade_solid.py — twin of build_fade.py with the word `solid` (see its docstring for what the build must
say). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("solid")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_fade.py"), run_name="__main__")
