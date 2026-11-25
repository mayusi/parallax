"""build_slide_spring_steel.py — NEGATIVE twin of build_slide_spring.py (KIT_SLIDE_SPRING=steel): the slide racks into a
solid block (RecoilStop, not a spring): must be named: mechanism. Used by `lune run kit selftest`. Never "fix" this
file."""
import os
import runpy

os.environ["KIT_SLIDE_SPRING"] = "steel"
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_slide_spring.py"), run_name="__main__")
