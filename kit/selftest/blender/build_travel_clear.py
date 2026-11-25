"""build_travel_clear.py — POSITIVE twin of build_travel_pin.py: the same runner and travel, the pin standing BESIDE
the path. Posed at every stop of the travel, the runner meets nothing: the mechanism gate must not flag it. Used by
`lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("clear")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_travel_pin.py"), run_name="__main__")
