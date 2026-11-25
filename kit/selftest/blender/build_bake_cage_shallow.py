"""build_bake_cage_shallow.py — NEGATIVE twin of build_bake_cage.py: the left lug's cage is set to 0.02 mm, under
what its rounded high stands off its faceted game mesh. The build must FAIL the check `bake_cage` and say the depth
it needs. Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("shallow")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_bake_cage.py"), run_name="__main__")
