"""build_trim_wall_off.py — NEGATIVE twin of build_trim_wall.py: the wall module is 7.5 studs long on a 4-stud grid
(it would leave a half-stud gap beside its neighbour) and its 3.5-stud panel is laid into the half-stud "rivets" band
(the finish pulled 7 times too tall). Must be flagged: module_grid (an error, naming the axis and the size) and
trim_fit (a warning, naming the part and the band). Used by `lune run kit selftest`. Never "fix" this file."""

import os
import runpy
import sys

sys.argv.append("off")
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_trim_wall.py"), run_name="__main__")
