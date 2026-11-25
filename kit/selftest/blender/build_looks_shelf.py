"""build_looks_shelf.py — POSITIVE fixture: a shelf of blocks, each a LOOK (rbx.look) with a life — a nitride slide
and a polymer frame (the owner-rated Glock's), walnut, end grain (rings round y), leather, concrete, brass worn,
powder coat — plus colour variation (vary) and dust settling on the dark slide block (grime_tone="dust"). Every bake channel
these add runs; must NOT be named pbr_values, material_values or dark_finishes. Used by `lune run kit selftest`.
Never "fix" this file."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("_selftest_looks_shelf", tex=512, size=(4.4, 0.6, 0.55))
a.real_scale(280.0)
a.material("slide", **rbx.look("nitride_slide"), life="used", grime_tone="dust")
a.material("frame", **rbx.look("polymer_frame"), life="used")
a.material("walnut", **rbx.look("walnut_wood"), life="light")
a.material("rings", **rbx.look("end_grain"), grain=(0, 1, 0))
a.material("leather", **rbx.look("leather_brown"), life="used")
a.material("concrete", **rbx.look("concrete"), life="heavy")
a.material("brass", **rbx.look("brass_worn"), life="used")
a.material("paint", **rbx.look("powder_coat", color=(0.30, 0.05, 0.04)), life="used")
a.box("Shelf", (4.4, 0.1, 0.55), (0, 0.05, 0), "walnut", bevel=0.02)   # (every block stands on it)
for i, m in enumerate(("slide", "frame", "walnut", "rings", "leather", "concrete", "brass", "paint")):
    a.box(f"B{i}", (0.45, 0.5, 0.45), (-1.85 + i * 0.53, 0.35, 0), m, bevel=0.03)
a.build()
