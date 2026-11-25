"""build_strip_soft_steel.py — NEGATIVE twin of build_strip_soft.py (KIT_SOFT=steel): the same sleeve in steel cannot
stretch over the lip: must be named: disassembly. Used by `lune run kit selftest`. Never "fix" this file."""
import os
import runpy

os.environ["KIT_SOFT"] = "steel"
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_strip_soft.py"), run_name="__main__")
