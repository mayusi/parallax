"""check_strew_cases.py — fixture: a.scatter's corner cases, each one a fault the review of the first build found
(card nkjm, 2026-11-13). Nothing is built: the parts are made and their places printed, one line
`STREW_CASES {json}`, read by kit/test/python/test_strew.py.
  FStud   a scatter opened inside a moved a.frame: the pieces are on the dome, not a frame's offset away
  RStud   a scatter inside a.repeat onto a part made in that repeat: twelve on EACH dome, none in the air
  MStud   a scatter inside a.mirror: twenty on each side, the facts say twenty
  Spike   scattered spikes, then a.taper along the spike's own Y and a.zone on its own top face: every spike
          tapered to its tip and painted on its outer end, wherever on the ball it stands
  Stone   vary= size and shift on a flat floor: every stone still stands ON it
  Tile    margin=: no tile nearer the deck's edge than asked
  Few     count= with a pitch that cannot hold it: fewer, and the facts say how many were asked
  refusals  a negative sink, a negative margin, a.conform on a scattered part
Never "fix" this file."""

import json
import os
import sys

import numpy as np

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402

BACK = rbx.BL_FROM_RBX.inverted()


def points(o):
    m = np.array(BACK @ o.matrix_world, np.float64)
    co = np.empty(len(o.data.vertices) * 3, np.float32)
    o.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3).astype(np.float64) @ m[:3, :3].T + m[:3, 3]


def pieces(name):
    return [o for o, _g in a.parts if o.name.split("~")[0] == name]


def mids(name):
    return [[round(float(c), 4) for c in points(o).mean(axis=0)] for o in pieces(name)]


a = rbx.Asset("_selftest_strew_cases", size=(20, 4, 20), ground=False)
a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
a.material("paint", color=(0.55, 0.2, 0.15), rough=0.6)

with a.frame(pos=(-6, 1, -6)):
    a.sphere("FDome", 0.5, (0, 0, 0), "iron", segments=32, rings=16)
    with a.scatter("FDome", count=10):
        a.box("FStud", (0.05, 0.05, 0.05), (0, 0.025, 0), "iron", bevel=0.0)

with a.repeat(3, step=(1.5, 0, 0)):
    a.sphere("RDome", 0.4, (0, 0, 6), "iron", segments=32, rings=16)
    with a.scatter("RDome", count=12):
        a.box("RStud", (0.05, 0.05, 0.05), (0, 0.025, 0), "iron", bevel=0.0)

with a.mirror("X"):
    a.sphere("MBall", 0.4, (3, 0, -6), "iron", segments=32, rings=16)
    with a.scatter("MBall", count=20):
        a.box("MStud", (0.05, 0.05, 0.05), (0, 0.025, 0), "iron", bevel=0.0)
m_fact = dict(a._scatter_facts[-1])

a.sphere("TDome", 0.5, (0, 0, -10), "iron", segments=32, rings=16)
with a.scatter("TDome", count=8):
    a.box("Spike", (0.06, 0.3, 0.06), (0, 0.15, 0), "iron", bevel=0.0)
a.taper("Spike", along="Y", end=0.2)
zoned = a.zone("Spike", "paint", lambda c, n: n[1] > 0.9)      # its own top face, as it was modelled
spikes = []
centre = np.array([0.0, 0.0, -10.0])
for o in pieces("Spike"):
    p = points(o)
    away = np.linalg.norm(p - centre, axis=1)
    foot, tip = p[away < away.min() + 0.02], p[away > away.max() - 0.01]
    slot = next((i for i, m in enumerate(o.data.materials) if m == a._mat("paint")), None)
    hit = [f for f in o.data.polygons if f.material_index == slot] if slot is not None else []
    out = [float(np.linalg.norm(np.array(BACK @ (o.matrix_world @ f.center)) - centre)) for f in hit]
    spikes.append({"foot": round(float(np.ptp(foot, axis=0).max()), 4), "tip": round(float(np.ptp(tip, axis=0).max()), 4),
                   "tall": round(float(away.max() - away.min()), 4), "zoned": len(hit),
                   "zone_at": round(max(out, default=0.0), 4), "far": round(float(away.max()), 4)})

a.box("Floor", (4.0, 0.2, 4.0), (6, -0.1, -10), "iron", bevel=0.0)        # its top at y = 0
with a.scatter("Floor", count=20, where=lambda c, n: n[1] > 0.9, spin=False,
               vary={"size": 0.4, "shift": 0.1}):
    a.box("Stone", (0.3, 0.5, 0.3), (0, 0.25, 0), "iron", bevel=0.0)
stones = [[round(float(points(o)[:, 1].min()), 4), round(float(points(o)[:, 1].max()), 4)] for o in pieces("Stone")]

a.box("Deck", (2.0, 0.2, 2.0), (-6, -0.1, 6), "iron", bevel=0.0)
with a.scatter("Deck", pitch=0.2, where=lambda c, n: n[1] > 0.9, margin=0.3):
    a.box("Tile", (0.05, 0.02, 0.05), (0, 0.01, 0), "iron", bevel=0.0)

a.box("Cube", (0.5, 0.5, 0.5), (6, 0.25, 0), "iron", bevel=0.0)
with a.scatter("Cube", count=50, pitch=0.3):
    a.box("Few", (0.03, 0.03, 0.03), (0, 0.015, 0), "iron", bevel=0.0)
few_fact = dict(a._scatter_facts[-1])

errors = {}
for what, kw in (("sink", dict(count=3, sink=-0.1)), ("margin", dict(count=3, margin=-1)),
                 ("room", dict(count=3, where=lambda c, n: n[1] > 0.9, margin=5.0))):
    try:
        with a.scatter("Deck", **kw):
            pass
        errors[what] = None
    except ValueError as e:
        errors[what] = str(e)
try:
    a.conform("Spike", "TDome", toward="-Y")
    errors["conform"] = None
except ValueError as e:
    errors["conform"] = str(e)

print("STREW_CASES " + json.dumps({
    "fstud": mids("FStud"), "rstud": mids("RStud"), "mstud": mids("MStud"), "m_fact": m_fact,
    "spikes": spikes, "zoned": zoned, "stones": stones, "tiles": mids("Tile"), "few": few_fact,
    "few_made": len(pieces("Few")), "errors": errors, "open_after": len(a._repeats),
}))
