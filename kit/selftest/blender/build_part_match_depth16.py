"""build_part_match_depth16.py — POSITIVE fixture: build_part_match_ok.py (the handle exactly where the trace has it)
with the scene's output left at 16-bit PNG, as a projection's render once left it (its settings' restore recorded the
depth after the EXR format had already changed it). The part-ID render decodes EXACT 8-bit colours: under a 16-bit
output every part decoded as another and every part_match in a full build was garbage. Must NOT be named:
part_match_side. Used by `lune run kit selftest`. Never "fix" this file."""
import os
import runpy

os.environ["KIT_PART_MATCH_NAME"] = "_selftest_part_match_depth16"
os.environ["KIT_PART_MATCH_DEPTH"] = "16"
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_part_match_ok.py"), run_name="__main__")
