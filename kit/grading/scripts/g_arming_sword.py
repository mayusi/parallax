"""build_arming_sword.py — a medieval ARMING SWORD fitted to a real one: its proportions are a.param() numbers that
`lune run kit fit arming_sword` moves until the front silhouette matches the reference (an Albion "Crecy" sword,
photo by Søren Niedziella, CC BY 2.0 — refs/SOURCES.md), traced with BiRefNet (the polished blade is as white as the
backdrop) into assets/models/arming_sword_front.trace.json. Measured materials (rbx.real: physicallybased.info, CC0)
and the other Albion photos as its style images.
Run: lune run kit asset arming_sword   ·   fit: lune run kit fit arming_sword [--write]
"""

import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

a = rbx.Asset("g_arming_sword", size=(0.9, 4.2, 0.16), ground=False, symmetric=True,
              reference={"front": "assets/models/arming_sword_front.trace.json"},
              style=["refs/arming_sword_style_1.jpg", "refs/arming_sword_style_2.jpg", "refs/arming_sword_style_3.jpg"])

# ---- the proportions the reference decides (studs; the defaults are a guess, kit fit finds the real ones) --------
blade_len = a.param("blade_len", 3.0, lo=2.2, hi=4.0)  # guard to tip
blade_w = a.param("blade_w", 0.34, lo=0.18, hi=0.48)  # at the guard
tip_w = a.param("tip_w", 0.60, lo=0.25, hi=0.95)  # the blade's width 85% of the way up, as a share of blade_w
guard_span = a.param("guard_span", 1.05, lo=0.6, hi=1.6)  # quillon tip to quillon tip
guard_h = a.param("guard_h", 0.12, lo=0.05, hi=0.22)
grip_len = a.param("grip_len", 0.62, lo=0.35, hi=0.95)
grip_w = a.param("grip_w", 0.13, lo=0.08, hi=0.22)
pommel_r = a.param("pommel_r", 0.15, lo=0.08, hi=0.26)

# ---- materials: measured where a real substance is named -----------------------------------------------------
a.material("steel", **rbx.real("Stainless Steel", rough=0.28), wear=0.15, grime=0.06, pattern="brushed")
a.material("iron", **rbx.real("Iron"), wear=0.2)
a.material("leather", (0.18, 0.08, 0.05), rough=0.85, wear=0.25, grime=0.15, pattern="grid")

# ---- build from the pommel up (front view: u = right, v = up; the blade's flat faces the viewer) ----------------
T = 0.07  # blade thickness at the centre
y0 = 2 * pommel_r * 0.85  # the grip starts where the pommel's top sinks into it
a.cylinder("Pommel", pommel_r, 0.16, (0, pommel_r, 0), "steel", axis="Z", segments=24, bevel=0.02)
a.extrude("Grip", [(-grip_w / 2, y0), (grip_w / 2, y0), (grip_w * 0.42, y0 + grip_len), (-grip_w * 0.42, y0 + grip_len)],
          0.12, "leather", plane="front")
yg = y0 + grip_len  # the guard's underside
a.extrude("Guard", [(-guard_span / 2, yg + guard_h * 0.15), (-guard_span * 0.42, yg), (guard_span * 0.42, yg),
                    (guard_span / 2, yg + guard_h * 0.15), (guard_span / 2, yg + guard_h * 0.85),
                    (guard_span * 0.42, yg + guard_h), (-guard_span * 0.42, yg + guard_h),
                    (-guard_span / 2, yg + guard_h * 0.85)], 0.14, "iron", plane="front")
yb = yg + guard_h  # the blade's base
a.extrude("Blade", [(-blade_w / 2, yb), (blade_w / 2, yb), (blade_w * tip_w / 2, yb + blade_len * 0.85),
                    (0.0, yb + blade_len), (-blade_w * tip_w / 2, yb + blade_len * 0.85)], T, "steel", plane="front")
a.expect("Guard", touches="Blade")
a.expect("Grip", touches="Guard")
a.expect("Pommel", touches="Grip")
a.build()
