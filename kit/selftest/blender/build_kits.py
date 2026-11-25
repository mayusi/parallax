"""build_kits.py — fixtures for KITS AND EXOTIC SURFACES (a.patch, a.blob, a.kitbash, a.also_gltf; the 3D methods
audit, stage K). By the word after `--`:
  (none)   a base carrying a WING drawn by a 3 x 4 control net, a PUFF of three balls that flow into one skin and
           a DRUM lent by the kit's own topology fixture (its build must exist: build_topology.py first; it comes
           as that build left it - the face nobody saw there dropped - and this build closes it, and says so) -
           with every group also written as a .glb that reads back. After the build `KITS {json}`.
  fold     the wing's net with two columns crossed far over each other: the build must STOP (build_kits_fold.py).
  unloved  a part asked of a build the owner never approved: the build must STOP and say only an approved build
           lends its geometry (build_kits_unloved.py).
Used by `lune run kit selftest`. Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOW = next((w for w in ("fold", "unloved") if w in ARGS), "good")

a = rbx.Asset("_selftest_kits_" + HOW, tex=128, size=(6.0, 1.8, 4.0), ground=True,
              allow_floating=("Wing", "Puff", "Knob"))
a.material("paint", color=(0.2, 0.35, 0.6), rough=0.5)
a.material("steel", color=(0.55, 0.56, 0.58), metal=1.0, rough=0.4)
a.box("Base", (6.0, 0.4, 4.0), (0, 0.2, 0), "steel", bevel=0)
xs = (-2.0, 5.0, -2.0, 2.0) if HOW == "fold" else (-2.0, -0.7, 0.7, 2.0)
net = [[(x, 1.0 + (0.5 if 0 < i < 3 else 0.0), -1.0) for i, x in enumerate(xs)],
       [(x, 1.3 + (0.9 if 0 < i < 3 else 0.0), 0.0) for i, x in enumerate(xs)],
       [(x, 1.0 + (0.5 if 0 < i < 3 else 0.0), 1.0) for i, x in enumerate(xs)]]
a.patch("Wing", net, "paint", steps=(12, 8), thick_mm=30)
a.blob("Puff", [(0, 0, 0, 0.5), (0.45, 0.15, 0, 0.35), (-0.4, 0.1, 0.15, 0.3)], "paint", resolution=0.1,
       pos=(-2.2, 1.0, 1.3))
if HOW == "unloved":
    a.kitbash("Knob", "car_wheel_rim_nobody_scored", "Hub", "steel", pos=(2.3, 0.9, 1.3))
else:
    a.kitbash("Knob", "_selftest_topology_good", "Drum", "steel", pos=(2.3, 0.9, 1.3), scale=0.5)
a.also_gltf()
a.build()

manifest = json.load(open(os.path.join(rbx.BUILD, "models", f"{a.name}.manifest.json"), encoding="utf-8"))
glb = manifest["groups"]["main"].get("glb")
print("KITS " + json.dumps({"glb": glb, "glb_there": bool(glb) and os.path.isfile(
    glb if os.path.isabs(glb) else os.path.join(rbx.REPO, glb)), "tris": manifest["groups"]["main"].get("tris")}))
