"""build_strip_incomplete.py — NEGATIVE twin of build_strip_ok.py (KIT_STRIP=incomplete): must be named: disassembly. Used by
`lune run kit selftest`. Never "fix" this file."""
import os
import runpy

os.environ["KIT_STRIP"] = "incomplete"
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_strip_ok.py"), run_name="__main__")
