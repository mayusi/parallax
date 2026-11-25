"""build_topology.py — fixtures for THE TOPOLOGY OF A BUILT MODEL (rbx_topology, a.drop_hidden, a.shade; the 3D
methods audit, stage T). One script, four models by the word after `--`:
  (none)   GOOD: a slab, a block of the same footprint standing on it with two cores wholly inside it, and a
           16-sided drum on the block, shaded flat (a.shade) - with a.drop_hidden(): the faces between the slab
           and the block, under the drum and all of the two cores go; the block's top (half under the drum) stays; the build says "hidden faces dropped: main ...", `hidden_faces`
           and `shading` hold.
  kept     the same model with no a.drop_hidden(): `hidden_faces` must WARN (build_topology_kept.py).
  round    the drum asked flat and then made round again behind the builder's back: `shading` must FAIL
           (build_topology_round.py).
  poor     a slab whose top is an 8 x 8 grid of flat quads, a 24-sided cone and a shim two thousandths thick:
           `polygon_waste`, `poles` and `needles` must WARN (build_topology_poor.py).
After the build one line `TOPO {json}`: the facts of the group. Used by `lune run kit selftest`. Never "fix" this
file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOW = next((w for w in ("kept", "round", "poor") if w in ARGS), "good")

if HOW == "poor":
    a = rbx.Asset("_selftest_topology_poor", tex=256, size=(4.0, 3.0, 4.0), ground=True)
    a.material("stone", color=(0.6, 0.6, 0.58), rough=0.8)
    n = 8
    top = [(-2 + 4 * x / n, 1.0, -2 + 4 * z / n) for z in range(n + 1) for x in range(n + 1)]
    verts = top + [(-2, 0, -2), (2, 0, -2), (2, 0, 2), (-2, 0, 2)]
    b = len(top)
    at = lambda x, z: z * (n + 1) + x  # noqa: E731
    faces = [[at(x, z), at(x, z + 1), at(x + 1, z + 1), at(x + 1, z)] for z in range(n) for x in range(n)]
    faces += [[b, b + 1, b + 2, b + 3],
              [b + 1, b] + [at(x, 0) for x in range(n + 1)],                    # the front side
              [b + 2, b + 1] + [at(n, z) for z in range(n + 1)],                # the right side
              [b + 3, b + 2] + [at(x, n) for x in range(n, -1, -1)],            # the back
              [b, b + 3] + [at(0, z) for z in range(n, -1, -1)]]                # the left
    a.mesh("Slab", verts, faces, "stone")
    a.cylinder("Cone", 0.8, 1.6, (0, 1.8, 0), "stone", axis="Y", segments=24, radius_top=0, bevel=0)
    a.box("Shim", (3.0, 0.002, 0.4), (0, 1.001, 1.5), "stone", bevel=0)
else:
    a = rbx.Asset("_selftest_topology_" + HOW, tex=256, size=(4.0, 3.0, 4.0), ground=True)
    a.material("stone", color=(0.6, 0.6, 0.58), rough=0.8)
    a.box("Slab", (4.0, 1.0, 4.0), (0, 0.5, 0), "stone", bevel=0)
    a.box("Block", (4.0, 1.0, 4.0), (0, 1.5, 0), "stone", bevel=0)
    a.cylinder("Drum", 1.0, 1.0, (0, 2.5, 0), "stone", axis="Y", segments=16, bevel=0)
    a.box("CoreA", (1.0, 0.5, 1.0), (-1.0, 1.5, 0), "stone", bevel=0)     # two cores wholly inside the block
    a.box("CoreB", (1.0, 0.5, 1.0), (1.0, 1.5, 0), "stone", bevel=0)
    a.shade("Drum", "flat")
    if HOW != "kept":
        a.drop_hidden()
    if HOW == "round":
        # (the shading asked is undone after the builder applied it: the check must read the MESH, not the ask)
        _apply = rbx.Asset._shade_apply
        rbx.Asset._shade_apply = lambda self, obj: None
a.build()

manifest = json.load(open(os.path.join(rbx.BUILD, "models", f"{a.name}.manifest.json"), encoding="utf-8"))
print("TOPO " + json.dumps({"tris": manifest["groups"]["main"].get("tris")}))
