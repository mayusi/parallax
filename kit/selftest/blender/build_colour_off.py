"""build_colour_off.py — NEGATIVE fixture: the front half is GREEN where the reference is blue. Must be named:
colour_match. Never "fix" this file.
The model's colour map is compared region by region with the reference picture's colour with its lighting taken out
(kit vision albedo's .npz): the reference here is made at run time in build/selftest/ (a 400 x 120 px picture of a
4 x 1 stud block, rear half bronze, front half blue; its trace; two regions). Used by `lune run kit selftest`.
"""

import json
import os
import sys

import numpy as np

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

REAR, FRONT = (0.55, 0.36, 0.2), (0.2, 0.3, 0.6)  # the reference's colours (linear, as a.material takes them)


def srgb(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


out = os.path.join(rbx.BUILD, "selftest")
os.makedirs(out, exist_ok=True)
pic = "kit/selftest/refs/_colour_picture.png"  # (never loaded: the trace, the regions and the colours name it)
alb = np.ones((120, 400, 3), np.float32)  # the picture: x 20..380 is the block (its back on the left), y 20..110
alb[20:110, 20:200] = srgb(REAR)
alb[20:110, 200:380] = srgb(FRONT)
np.savez_compressed(os.path.join(out, "_colour.albedo.npz"), albedo=alb.astype(np.float16),
                    mask=np.ones((120, 400), bool), meta=json.dumps({"source": pic, "albedo_space": "srgb"}))
trace = {"name": "_colour_side", "source": pic, "front": "right", "height_ratio": 0.25, "holes": [],
         "outline": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.25], [0.0, 0.25]],
         "frame": {"x0": 20.0, "y1": 110.0, "length_px": 360.0}}
with open(os.path.join(out, "_colour_side.trace.json"), "w", encoding="utf-8") as fh:
    json.dump(trace, fh)
with open(os.path.join(out, "_colour.regions.json"), "w", encoding="utf-8") as fh:
    json.dump({"image": pic, "regions": [{"name": "rear", "box": [20, 20, 200, 110]},
                                         {"name": "front", "box": [200, 20, 380, 110]}]}, fh)

a = rbx.Asset("_selftest_colour_off", tex=64, size=(0.5, 1.0, 4.0))
a.material("rear", color=REAR)
a.material("front", color=(0.2, 0.6, 0.25))
a.box("Rear", (0.5, 1.0, 2.0), (0, 0.5, 1.0), "rear", bevel=0)
a.box("Front", (0.5, 1.0, 2.0), (0, 0.5, -1.0), "front", bevel=0)
a.trace_match(os.path.join(out, "_colour_side.trace.json"), albedo=os.path.join(out, "_colour.albedo.npz"),
              regions=os.path.join(out, "_colour.regions.json"))
a.build()
