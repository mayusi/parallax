"""build_colour_front_ok.py — POSITIVE twin of build_colour_front_off.py: the model's right side blue and its left
bronze, as the synthetic FRONT picture shows them (the model's right on the picture's LEFT). Must NOT be named
colour_match — a front view compared mirrored would name both regions. Never "fix" this file. Used by `lune run kit
selftest`.
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
pic = "kit/selftest/refs/_colour_front_picture.png"   # (never loaded: the trace, the regions and the colours name it)
alb = np.ones((120, 400, 3), np.float32)   # seen from the FRONT: the model's right (+X) on the picture's LEFT
alb[20:110, 20:200] = srgb(RIGHT)
alb[20:110, 200:380] = srgb(LEFT)
np.savez_compressed(os.path.join(out, "_colour_front.albedo.npz"), albedo=alb.astype(np.float16),
                    mask=np.ones((120, 400), bool), meta=json.dumps({"source": pic, "albedo_space": "srgb"}))
trace = {"name": "_colour_front", "source": pic, "front": "right", "height_ratio": 0.25, "holes": [],
         "outline": [[0.0, 0.0], [1.0, 0.0], [1.0, 0.25], [0.0, 0.25]],
         "frame": {"x0": 20.0, "y1": 110.0, "length_px": 360.0}}
with open(os.path.join(out, "_colour_front.trace.json"), "w", encoding="utf-8") as fh:
    json.dump(trace, fh)
with open(os.path.join(out, "_colour_front.regions.json"), "w", encoding="utf-8") as fh:
    json.dump({"image": pic, "regions": [{"name": "right side", "box": [20, 20, 200, 110]},
                                         {"name": "left side", "box": [200, 20, 380, 110]}]}, fh)

a = rbx.Asset("_selftest_colour_front_ok", tex=64, size=(4.0, 1.0, 0.5))
a.material("right", color=RIGHT)
a.material("left", color=LEFT)
a.box("Right", (2.0, 1.0, 0.5), (1.0, 0.5, 0), "right", bevel=0)   # (+X: the model's right)
a.box("Left", (2.0, 1.0, 0.5), (-1.0, 0.5, 0), "left", bevel=0)
a.trace_match(os.path.join(out, "_colour_front.trace.json"), view="front",
              albedo=os.path.join(out, "_colour_front.albedo.npz"), regions=os.path.join(out, "_colour_front.regions.json"))
a.build()
