"""build_hair_thin.py — twin of build_hair.py with the word `thin` (see its docstring for what the build must say).
Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("thin")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_hair.py"), run_name="__main__")
