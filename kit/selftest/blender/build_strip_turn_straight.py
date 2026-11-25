"""build_strip_turn_straight.py — NEGATIVE twin of build_strip_turn.py (KIT_STRIP_TURN=straight): the flap lifted
straight up runs into the keeper over its end: must be named: disassembly. Used by `lune run kit selftest`. Never "fix"
this file."""
import os
import runpy

os.environ["KIT_STRIP_TURN"] = "straight"
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_strip_turn.py"), run_name="__main__")
