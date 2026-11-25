"""build_cycle_loop_jump.py — NEGATIVE twin of build_cycle_loop.py: the wheel's cycle is said to LOOP and ends half
a turn from where it began - in the game the wheel would jump back every time it came round. Must be flagged:
cycle_loop, naming the joint ("Wheel"). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("jump")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_cycle_loop.py"), run_name="__main__")
