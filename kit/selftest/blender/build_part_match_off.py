"""build_part_match_off.py — NEGATIVE fixture for the per-part check: the same body and trace as build_part_match_ok.py,
the handle built 0.7 studs too far forward and 0.4 studs short — the whole outline still overlaps the trace well, the
part does not. Must be named: part_match_side. Used by `lune run kit selftest`. Never "fix" this file."""

import json
import os
import runpy

os.environ["KIT_PART_MATCH_HANDLE"] = json.dumps({"pos": [0, -0.9, 0.5], "size": [0.4, 0.8, 0.6]})
os.environ["KIT_PART_MATCH_NAME"] = "_selftest_part_match_off"
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_part_match_ok.py"), run_name="__main__")
