"""build_kits_fold.py — twin of build_kits.py with the word `fold` (see its docstring for what the build must
say). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("fold")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_kits.py"), run_name="__main__")
