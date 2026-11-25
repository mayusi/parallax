"""build_hybrid.py — fixture for THE HYBRID ROUTE (LIMITATIONS_FIXES_V4 3D-X, 13.2: kit/gen/hybrid_fabricate.py): a
short hilt - a CAD grip and a CAD guard CAST as one piece (a.cast, the cad route: one fused solid, the joint filleted),
an engraved ornament on the guard (a.ornament: relief in the normal map), and a GENERATED pommel (a generator-like
crust made on the spot by make_gen_part.py: 44,000 triangles of soup with its own painted map). By the word after `--`:
  ok    the pommel RETOPOLOGISED (kit/gen/retopo_part.py: Instant Meshes quads, its colour baked across) and its
        dense skin given as its high (a.import_mesh(low, high=...)): its relief baked into the low's normal map.
        Must NOT be named: generated_topology.
  soup  the pommel imported as the generator left it (thinned to the same triangle count by a plain decimate: the
        soup a decimated generator mesh is). Must be named: generated_topology.
Used by `lune run kit selftest` and kit/test/python/test_hybrid.py. Never "fix" this file."""

import os
import subprocess
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bpy  # noqa: E402
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOW = "soup" if "soup" in ARGS else "ok"
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(rbx.BUILD, "selftest", "hybrid")
os.makedirs(WORK, exist_ok=True)
GEN = os.path.join(WORK, "gen_part.glb")
LOW = os.path.join(WORK, "Pommel.glb")
HIGH = os.path.join(WORK, "Pommel_high.glb")
SOUP = os.path.join(WORK, "Pommel_soup.glb")
BLENDER = bpy.app.binary_path


def blender(script, *args):
    res = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--", *args],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit(f"hybrid fixture: {os.path.basename(script)} failed: {res.stdout[-600:]} {res.stderr[-600:]}")


if not os.path.isfile(GEN):
    blender(os.path.join(HERE, "make_gen_part.py"), GEN)
if HOW == "ok" and not (os.path.isfile(LOW) and os.path.isfile(HIGH)):
    blender(os.path.join(_root, "kit", "gen", "retopo_part.py"), GEN, LOW, "--quads", "2500", "--size", "1024")
if HOW == "soup" and not os.path.isfile(SOUP):
    blender(os.path.join(HERE, "thin_gen_part.py"), GEN, SOUP, "--tris", "5000")

MM = 280.0
a = rbx.Asset(f"_selftest_hybrid_{HOW}", tex=512, size=(0.6, 0.9, 0.3), ground=True, low=12000)
a.real_scale(MM)
a.material("brass", color=(0.62, 0.45, 0.2), metal=1.0, rough=0.35)
a.material("leather", color=(0.18, 0.1, 0.06), rough=0.7)
a.cad("Grip", "part = Cylinder(14, 160)\n", "leather", pos=(0, 0.3 + 80 / MM, 0), rot=(90, 0, 0), group="hilt")
a.cad("Guard", "part = fillet(Box(160, 16, 30).edges().filter_by(Axis.X), 4)\n", "brass", pos=(0, 0.3 + 158 / MM, 0),
      group="hilt")
a.cast("Hilt", ["Grip", "Guard"], "brass", fillet_mm=2.0, mode="auto")   # (the grip runs 10 mm into the guard)
a.ornament(os.path.join(HERE, "ornament_scroll.png"), at=(0, 0.3 + 158 / MM, -15.2 / MM), width=0.45, facing="-Z",
           depth_mm=0.8, profile="v")
if HOW == "ok":
    a.import_mesh("Pommel", LOW, high=HIGH, height=0.3, pos=(0, 0.03, 0), group="pommel")
else:
    a.import_mesh("Pommel", SOUP, height=0.3, pos=(0, 0.03, 0), group="pommel")
a.build()
