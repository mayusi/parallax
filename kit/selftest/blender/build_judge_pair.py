"""build_judge_pair.py — SMOKE fixture for pairwise judging (`kit judge <asset> --pair`). Not part of `kit selftest`:
the six judge views are kept only by a full build WITH previews (the selftest builds run --no-preview).
A small block blaster with a region map (barrel, body, grip) on a reference picture made at run time in
build/selftest/, and a brief (_selftest_judge_pair.brief.md beside this script) saying players see it in first
person — so a build also renders the game camera. Build it twice, the second time with a shorter glow strip (an
a.param: another iteration, the same size, so the same camera), then pair the two builds:

    KIT_BUILD=build blender -b --factory-startup --python kit/selftest/blender/build_judge_pair.py
    KIT_PARAMS='{"glow": 0.5}' KIT_PARAMS_SCRIPT=<this script's full path>  (the same again)
    lune run kit judge _selftest_judge_pair --pair current previous
(a longer barrel — KIT_PARAMS='{"barrel": 2.0}' — outgrows the sticky frame: a new camera, and the packet says so)
"""

import json
import os
import sys

import bpy
import numpy as np

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

out = os.path.join(rbx.BUILD, "selftest")
os.makedirs(out, exist_ok=True)
# the reference: a side view 400 x 160 px, the front (the muzzle) on the LEFT
pic = np.full((160, 400, 4), 0.92, np.float32)
pic[..., 3] = 1
pic[55:75, 20:170, :3] = (0.55, 0.57, 0.6)  # barrel
pic[40:95, 170:330, :3] = (0.18, 0.19, 0.22)  # body
pic[60:72, 200:300, :3] = (0.1, 0.8, 0.95)  # a glow strip on the body
pic[95:150, 270:320, :3] = (0.12, 0.12, 0.13)  # grip
img = bpy.data.images.new("_judge_pair_ref", 400, 160)
img.pixels.foreach_set(np.flipud(pic).ravel())  # (Blender rows run bottom-up)
ref = os.path.join(out, "_judge_pair_ref.png")
img.filepath_raw, img.file_format = ref, "PNG"
img.save()
ref_rel = os.path.relpath(ref, rbx.REPO).replace("\\", "/")
regions = os.path.join(out, "_judge_pair.regions.json")
with open(regions, "w", encoding="utf-8") as fh:
    json.dump({"image": ref_rel, "regions": [
        {"name": "barrel", "box": [15, 45, 175, 85], "parts": ["Barrel", "Muzzle"],
         "questions": ["Is the barrel a plain light-grey tube as long as the body?"]},
        {"name": "body", "box": [165, 35, 335, 100], "parts": ["Body", "Glow"],
         "questions": ["Is the body a dark block with a cyan glow strip along its side?"]},
        {"name": "grip", "box": [260, 90, 330, 155], "parts": ["Grip"],
         "questions": ["Is the grip a dark block under the back of the body?"]},
    ]}, fh, indent=1)

a = rbx.Asset("_selftest_judge_pair", tex=64, ground=False, ref_image=ref_rel)
a.region_map(regions)
barrel = a.param("barrel", 1.4, lo=1.0, hi=2.4)
glow = a.param("glow", 0.9, lo=0.3, hi=1.2)
a.material("body", (0.18, 0.19, 0.22), metal=0.4, rough=0.5, wear=0.2)
a.material("steel", (0.55, 0.57, 0.6), metal=1.0, rough=0.35)
a.material("grip", (0.12, 0.12, 0.13), rough=0.8)
a.material("glow", (0.1, 0.8, 0.95), rough=0.2, emit=3)
a.box("Body", (0.4, 0.5, 1.6), (0, 0.75, 0.2), "body", bevel=0.03)
a.box("Glow", (0.42, 0.08, glow), (0, 0.78, 0.25), "glow", bevel=0)
a.cylinder("Barrel", 0.09, barrel, (0, 0.8, -0.6 - barrel / 2), "steel", axis="Z")
a.cylinder("Muzzle", 0.12, 0.12, (0, 0.8, -0.6 - barrel), "steel", axis="Z")
a.box("Grip", (0.3, 0.6, 0.32), (0, 0.22, 0.75), "grip", bevel=0.02)
a.build()
