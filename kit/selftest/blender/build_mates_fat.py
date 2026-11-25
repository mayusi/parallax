"""build_mates_fat.py — twin of build_mates.py with the word `fat` (see its docstring for what the build must
say). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("fat")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_mates.py"), run_name="__main__")
