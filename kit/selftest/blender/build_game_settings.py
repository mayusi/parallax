"""build_game_settings.py — fixtures for THE GAME'S SETTINGS A SCRIPT SAYS (a.physics, a.far; the 3D methods audit,
stage O). By the word after `--`:
  (none)   a wheel: its tyre (a group of its own) grips and bounces (friction 1.6, elasticity 0.6), the model asks
           for Roblox's far stand-in. The manifest must carry `physics` on the tyre alone and `far`; the build
           says "game: tyre elasticity 0.6 friction 1.6, far StreamingMesh". After the build `GAME {json}`.
  nogroup  a.physics for a group the asset has not: the build must STOP and name the groups it has
           (build_game_settings_nogroup.py).
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
NOGROUP = "nogroup" in ARGS

a = rbx.Asset("_selftest_game_nogroup" if NOGROUP else "_selftest_game", tex=128, size=(2.0, 2.0, 0.8), ground=True)
a.material("steel", color=(0.55, 0.56, 0.58), metal=1.0, rough=0.4)
a.material("rubber", color=(0.05, 0.05, 0.05), rough=0.9)
a.cylinder("Hub", 0.6, 0.6, (0, 1.0, 0), "steel", axis="Z", segments=16, bevel=0)
a.cylinder("Tyre", 1.0, 0.8, (0, 1.0, 0), "rubber", axis="Z", segments=24, bevel=0, group="tyre")
a.physics("tire" if NOGROUP else "tyre", friction=1.6, elasticity=0.6)
a.far()
a.build()

manifest = json.load(open(os.path.join(rbx.BUILD, "models", f"{a.name}.manifest.json"), encoding="utf-8"))
print("GAME " + json.dumps({"far": manifest.get("far"), "tyre": manifest["groups"]["tyre"].get("physics"),
                            "main": manifest["groups"]["main"].get("physics")}))
