"""build_fade_master.py — twin of build_fade.py with the word `master` (see its docstring for what the build must
say). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("master")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_fade.py"), run_name="__main__")
