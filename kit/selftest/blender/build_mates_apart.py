"""build_mates_apart.py — twin of build_mates.py with the word `apart` (see its docstring for what the build must
say). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("apart")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_mates.py"), run_name="__main__")
