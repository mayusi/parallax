"""build_batch_fine.py — twin of build_batch.py with the word `fine` (see its docstring for what the build must
say). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("fine")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_batch.py"), run_name="__main__")
