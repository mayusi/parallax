"""build_spec_occ.py — fixture for SPECULAR OCCLUSION (the owner, 2026-11-17: "New pieces only"): a steel block with a
deep slot between two walls. By the word after `--`:
  on    spec_occlusion=1.0: the slot (its floor, the walls' inner faces) bakes rougher and less metallic
  off   spec_occlusion=0.0: no change anywhere (the bake as it was: one roughness, fully metallic)
After the build `SPECOCC {json}`: over the covered texels, the share rougher than 0.40 and less metallic than 0.95,
the roughest and least metallic texel (the facts: the build's own status line, facts.spec_occlusion).
Used by kit/test/python/test_spec_occ.py. Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import rbx  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOW = "off" if "off" in ARGS else "on"

a = rbx.Asset("_selftest_spec_occ_" + HOW, tex=128, size=(2.0, 1.0, 1.0), ground=True,
              spec_occlusion=1.0 if HOW == "on" else 0.0, edge_wear=0.0)
a.material("steel", color=(0.55, 0.56, 0.58), metal=1.0, rough=0.35)
a.box("Base", (2.0, 0.2, 1.0), (0, 0.1, 0), "steel", bevel=0)
a.box("WallL", (0.9, 0.8, 1.0), (-0.55, 0.6, 0), "steel", bevel=0)
a.box("WallR", (0.9, 0.8, 1.0), (0.55, 0.6, 0), "steel", bevel=0)
a.build()


def stats(obj_name):
    """the baked maps over the texels the model covers (colour alpha): the share rougher than the material's 0.35 and
    less metallic than its 1.0, the roughest and the least metallic texel"""
    maps = {}
    for ch in ("color", "rough", "metal"):
        img = bpy.data.images.load(os.path.join(rbx.TEXTURES, f"{obj_name}_{ch}.png"), check_existing=False)
        maps[ch] = np.array(img.pixels[:], np.float32).reshape(img.size[1], img.size[0], 4)
        bpy.data.images.remove(img)
    cov = maps["color"][..., 3] > 0.5
    r, m = maps["rough"][..., 0][cov], maps["metal"][..., 0][cov]
    return {"rougher": round(float((r > 0.40).mean()), 4), "less_metal": round(float((m < 0.95).mean()), 4),
            "rough_max": round(float(r.max()), 3), "metal_min": round(float(m.min()), 3), "texels": int(cov.sum())}


print("SPECOCC " + json.dumps(stats([o.name for o in bpy.data.objects if o.type == "MESH"][0])))
