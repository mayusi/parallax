"""build_pose_match_off.py — NEGATIVE fixture for trace_match(pose=): the same model and picture as
build_pose_match_ok.py, measured WITHOUT the pose — the picture's open lid is not where the model's shut one is. Must be
named: reference_side. Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy

os.environ["KIT_POSE_MATCH_NONE"] = "1"
os.environ["KIT_POSE_MATCH_NAME"] = "_selftest_pose_match_off"
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_pose_match_ok.py"), run_name="__main__")
