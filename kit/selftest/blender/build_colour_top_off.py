"""build_colour_top_off.py — NEGATIVE fixture: seen from ABOVE, the model's right side is GREEN where the top
picture shows it blue. Must be named: colour_match (its region "top right side"). A synthetic top picture (its front on
the right, so the model's LEFT at the top), its albedo, trace and two regions are made at run time in build/selftest/.
Its twin build_colour_top_ok.py must NOT be named — the pair pins the top view's turn (a silhouette cannot: it reads
the same flipped). Never "fix" this file. Used by `lune run kit selftest`.
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

RIGHT, LEFT = (0.2, 0.3, 0.6), (0.55, 0.36, 0.2)   # the model's right (+X) side blue, its left bronze (linear)


def srgb(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


out = os.path.join(rbx.BUILD, "selftest")
os.makedirs(out, exist_ok=True)
pic = "kit/selftest/refs/_colour_top_picture.png"   # (never loaded: the trace, the regions and the colours name it)
alb = np.ones((120, 400, 3), np.float32)   # seen from ABOVE, its front on the right: the model's LEFT at the top
alb[20:65, 20:380] = srgb(LEFT)
alb[65:110, 20:380] = srgb(RIGHT)
np.savez_compressed(os.path.join(out, "_colour_top.albedo.npz"), albedo=alb.astype(np.float16),
                    mask=np.ones((120, 400), bool), meta=json.dumps({"source": pic, "albedo_space": "srgb"}))
trace = {"name": "_colour_top", "source": pic, "front": "right", "height_ratio": 0.25, "holes": [],
         "outline": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.25], [0.0, 0.25]],
         "frame": {"x0": 20.0, "y1": 110.0, "length_px": 360.0}}
with open(os.path.join(out, "_colour_top.trace.json"), "w", encoding="utf-8") as fh:
    json.dump(trace, fh)
with open(os.path.join(out, "_colour_top.regions.json"), "w", encoding="utf-8") as fh:
    json.dump({"image": pic, "regions": [{"name": "left side", "box": [20, 20, 380, 65]},
                                         {"name": "right side", "box": [20, 65, 380, 110]}]}, fh)

a = rbx.Asset("_selftest_colour_top_off", tex=64, size=(1.0, 0.5, 4.0))
a.material("right", color=(0.2, 0.6, 0.25))
a.material("left", color=LEFT)
a.box("Right", (0.5, 0.5, 4.0), (0.25, 0.25, 0), "right", bevel=0)   # (+X: the model's right)
a.box("Left", (0.5, 0.5, 4.0), (-0.25, 0.25, 0), "left", bevel=0)
a.trace_match(os.path.join(out, "_colour_top.trace.json"), view="top",
              albedo=os.path.join(out, "_colour_top.albedo.npz"), regions=os.path.join(out, "_colour_top.regions.json"))
a.build()
