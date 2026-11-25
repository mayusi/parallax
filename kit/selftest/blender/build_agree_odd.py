"""build_agree_odd.py — twin of build_agree.py with the word `odd` (see its docstring for what the build must
say). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("odd")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_agree.py"), run_name="__main__")
