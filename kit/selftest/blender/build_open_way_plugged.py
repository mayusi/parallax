"""build_open_way_plugged.py — NEGATIVE twin of build_open_way.py: the same bored block with a plug left standing in
the bore the script named open. Must be flagged: open_ways, naming the opening ("Bore") and what stands in it
("Plug"). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("plugged")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_open_way.py"), run_name="__main__")
