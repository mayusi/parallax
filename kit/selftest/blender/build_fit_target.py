"""build_fit_target.py — kit fit's proof case: a rifle-like side profile whose two a.param() numbers (where the body
ends, how tall the barrel is) start WRONG; its reference trace was drawn from the TRUE values (split 0.62, barrel 0.27
of the body's height: kit/selftest/blender/fit_target_side.trace.json). `kit fit` must find them from the silhouette
match alone. Never "fix" this file or its trace."""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

L, H, T = 4.0, 1.0, 0.4  # length, body height, thickness (studs)
here = os.path.dirname(os.path.abspath(__file__))
a = rbx.Asset("_selftest_fit_target", size=(T, H, L), symmetric=True, ground=False, bevel=0,
              reference={"side": os.path.join(here, "fit_target_side.trace.json")})
split = a.param("split", 0.50, lo=0.35, hi=0.85)  # where the body ends, as a share of the length (true 0.62)
barrel = a.param("barrel", 0.35, lo=0.12, hi=0.6)  # the barrel's height as a share of the body's (true 0.27)
a.material("steel", (0.3, 0.31, 0.33), metal=0.6, rough=0.45)
body_len = L * split
# side outline (u = toward the front, v = up), the back at u = -L/2
a.extrude("Body", [(-L / 2, 0.0), (-L / 2 + body_len, 0.0), (-L / 2 + body_len, H), (-L / 2, H)], T, "steel",
          plane="side")
bh = H * barrel
a.extrude("Barrel", [(-L / 2 + body_len - 0.01, H * 0.6 - bh / 2), (L / 2, H * 0.6 - bh / 2),
                     (L / 2, H * 0.6 + bh / 2), (-L / 2 + body_len - 0.01, H * 0.6 + bh / 2)], T * 0.6, "steel",
          plane="side")
a.build()
