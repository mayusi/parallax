"""build___NAME__.py — __NAME__. Run: lune run kit asset __NAME__   (add --fast to skip the preview)

DESIGN FIRST (write it here before modelling — the gates check it):
  what it is / where it is used:
  size in studs (x, y, z):           -> Asset(size=...)   (R6 character = 5 tall; door 4x7; sword ~1.7x4.8)
  silhouette (what reads from far):
  big shapes / medium / small details:
  palette (main, trim/accent, detail):  value contrast matters more than hue
Proven examples to copy techniques from: lune run kit examples asset   (or start from one: kit new asset x --from sword)

ROBLOX SPACE: studs, Y up, -Z is the FRONT, +X is the right. rot=(rx, ry, rz) degrees == CFrame.Angles.
Workflow — ONE planned pass, stage by stage: `lune run kit plan __NAME__` says which stage you are at and its exact
commands (every tool: the parallax-3d skill's first page). brief + parts plan (how each part gets made) -> gather every
reference (pictures of every side, reference models, sizes, colours) -> a generated 3D draft (kit gen views / kit gen)
-> shape each part by its route (a.cad + kit cad check in seconds, a.import_mesh, a.param + kit fit; kit watch __NAME__
--geo: every check, no bake) -> surface from data (rbx.finish / rbx.real, scan=, pattern=, engraved markings) -> mechanism
-> full run: kit asset __NAME__ -> LOOK at build/renders/__NAME__.png beside the references (hero + R6 for scale |
back | silhouette / front | side | top) -> fresh judges (hero) -> kit showcase __NAME__.
API (kit/blender/rbx.py):
  a.material(name, color=(r,g,b), metal=0 or 1, rough=0..1, wear=0..1, alpha=0..1)   # linear colour
  a.material(name, **rbx.finish("painted_metal", color=...)) · **rbx.real("Iron")   # values a real surface has
  a.extrude(name, [(u, v), (u, v, r)...], depth, mat, plane="side|front|top")   # THE main tool: outline -> solid
  a.box(name, size, pos, mat, rot=, bevel=)            a.wedge(name, size, pos, mat, rot=)
  a.cylinder(name, radius, length, pos, mat, axis="X|Y|Z", radius_top=, segments=)
  a.sphere(name, radius, pos, mat, scale=(sx,sy,sz))   a.loft(name, [(along, r) ...], mat, axis=)
  a.tube(name, [points], radius, mat)                  a.mesh(name, verts, faces, mat)
  a.cad(name, code, mat)   # an exact CAD solid (build123d)   a.import_mesh(name, "assets/models/x.gen.glb", height=)
  L = a.param("length", 2.4, lo=1.8, hi=3.0)   # a proportion `kit fit __NAME__ --write` matches to the references
  pk = a.pack()   # the asset's PACK (`kit pack __NAME__`): pk.size("slide.length"), pk.profile("slide"),
                  # pk.colour("slide") (linear), pk.levels("<ref model>"), pk.draft() — read, never typed from memory
  a.cut("Target", a.box("Slot", ...))   # boolean: carve a cutter out of a part; cut walls take the cutter's material
  with a.mirror("X"): ...               # model one side, the other side appears (exact symmetry)
  with a.frame(pos=, rot=): ...         # sub-assembly (lid, turret, door) placed relative to a pivot
  group="glass"                         # any primitive: separate mesh/FBX (transparent or moving parts)
Details (kit/blender/rbx_parts.py, as P): bolts, rivets, grip, panel_line, vent, frame, light, wheel, handle.
MEASURE, don't eyeball: a.expect("Lid", touches="Body", above="Body") — a false statement fails with the exact distance.
Close-up of one part: kit asset __NAME__ --inspect <Part>. Match concept art: rbx.Asset(..., reference={"front": "refs/x.png"}).
"""

import os
import sys

# find the project root (the folder that contains kit/) from wherever this file lives
_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402
import rbx_parts as P  # noqa: E402

a = rbx.Asset("__NAME__", tex=1024, size=(2.2, 2.2, 2.2))
a.material("main", **rbx.finish("painted_metal", color=(0.55, 0.55, 0.58)), wear=0.2)
a.material("trim", color=(0.1, 0.1, 0.11), rough=0.8)

# Replace this placeholder with the real shape. Keep the base on y=0 so it sits on the ground in Studio.
a.box("Body", (2, 2, 2), (0, 1, 0), "main", bevel=0.08)
a.box("Trim", (2.1, 0.2, 2.1), (0, 0.1, 0), "trim")
P.bolts(a, "Bolt", [(x, 1.6, -1.0) for x in (-0.7, 0, 0.7)], "trim", facing="-Z")
a.expect("Trim", touches="Body")
a.build()
