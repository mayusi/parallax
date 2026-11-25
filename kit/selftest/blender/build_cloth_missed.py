"""build_cloth_missed.py — twin of build_cloth.py with the word `missed` (see its docstring for what the build must
say). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("missed")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_cloth.py"), run_name="__main__")
