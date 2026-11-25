"""check_methods_lock.py — fixture: THE METHODS LOCK at build time (rbx.Asset._methods_used / _typed_alike /
_methods_check / a.repeat(at=), rbx_plan.methods_check). Nothing is built: models are made and asked, one line
`METHODS_LOCK {json}`, read by kit/test/python/test_methods_lock.py.
  a model that uses every new method: the build's own record names all six, and how many pieces each made
  a model of plain boxes: none
  five bolts typed one by one: found as ONE shape typed five times; the same five made with a.repeat(at=): not
  alike by a hair, in another material, named with "~", absorbed by a.fuse, typed inside a token a.repeat:
  found all the same
  a brief written beside a (temporary) script whose plan names a.repeat for a fence the model types post by
  post: with the lock ON the build's own check fails and says so; the model that repeats them passes; with the
  lock off the check is not asked
  a.repeat(at=) whose first place is not where the part was modelled is refused; places from a generator work
Never "fix" this file."""

import json
import os
import sys
import tempfile

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import rbx  # noqa: E402
import rbx_plan  # noqa: E402

PLACES = [(0, 0.1, 0), (0.7, 0.1, 0.2), (1.1, 0.1, -0.6), (-0.9, 0.1, 0.4), (-0.3, 0.1, -0.8)]
BRIEF = ("# x\n- parts plan:\n"
         "  1. Plate | code: a.box | top | iron\n"
         "  2. Bolts x5 | code: a.cylinder in a.repeat at its places | top | iron\n"
         "  3. Fence | code: a.box post in a.repeat, a row | side | iron\n")


TMP = tempfile.mkdtemp(prefix="kit_methods_lock_")


def held(m, blockout=False):
    """the build's own check with the lock ON: a brief beside the model's (temporary) script. Asked while the
    model is still the scene's (the next rbx.Asset clears it)."""
    with open(os.path.join(TMP, f"{m.name}.brief.md"), "w", encoding="utf-8") as fh:
        fh.write(BRIEF)
    m.script_path = os.path.join(TMP, f"build_{m.name}.py")
    was, args = os.environ.get("KIT_METHODS_LOCK"), m.args
    os.environ["KIT_METHODS_LOCK"] = "1"
    if blockout:
        m.args = list(args) + ["--blockout"]
    try:
        return m._methods_check(m.name)
    finally:
        m.args = args
        os.environ.pop("KIT_METHODS_LOCK", None) if was is None else os.environ.__setitem__("KIT_METHODS_LOCK", was)


def scene(name):
    a = rbx.Asset(name, size=(6, 3, 6), ground=False)
    a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
    a.material("brass", color=(0.7, 0.55, 0.25), metal=1.0, rough=0.4)
    return a


# ---- every new method, used once
a = scene("_selftest_methods_all")
a.box("Slab", (4.0, 0.2, 4.0), (0, -0.1, 0), "iron", bevel=0)
with a.repeat(3, step=(0.5, 0, 0)):
    a.box("Tooth", (0.2, 0.3, 0.2), (-1, 0.15, 1.5), "iron", bevel=0)
with a.scatter("Slab", count=6, where=lambda c, n: n[1] > 0.9, margin=0.3):
    a.box("Stud", (0.05, 0.05, 0.05), (0, 0.025, 0), "iron", bevel=0)
a.box("Horn", (0.2, 1.0, 0.2), (1.5, 0.5, -1.5), "iron", bevel=0)
a.taper("Horn", along="Y", end=0.3)
a.sweep("Rail", [(-1.5, 0.1, -1.5), (0, 0.1, -1.5)], 0.05, "iron")
a.box("Case", (0.8, 0.4, 0.6), (-1.2, 0.2, 0), "iron", bevel=0)
a.inset("Case", "+Y", 0.1)
a.box("Pod", (0.6, 0.4, 0.6), (1.2, 0.2, 0.5), "iron", bevel=0)
a.smooth("Pod", levels=1)
used = a._methods_used()

# ---- plain boxes; five bolts typed one by one
b = scene("_selftest_methods_typed")
b.box("Plate", (3.0, 0.2, 3.0), (0, -0.1, 0), "iron", bevel=0)
for i, place in enumerate(PLACES, 1):
    b.cylinder(f"Bolt{i}", 0.05, 0.2, place, "iron", axis="Y", segments=8)
for i, x in enumerate((-1.2, -0.4, 0.4, 1.2), 1):
    b.box(f"Post{i}", (0.1, 0.8, 0.1), (x, 0.4, 1.3), "iron", bevel=0)      # a fence, post by post
used_plain, typed = b._methods_used(), b._typed_alike()
check_bad, check_blockout = held(b), held(b, blockout=True)

# ---- the same, made by its methods
g = scene("_selftest_methods_good")
g.box("Plate", (3.0, 0.2, 3.0), (0, -0.1, 0), "iron", bevel=0)
with g.repeat(at=PLACES):
    g.cylinder("Bolt", 0.05, 0.2, PLACES[0], "iron", axis="Y", segments=8)
with g.repeat(4, step=(0.8, 0, 0)):
    g.box("Post", (0.1, 0.8, 0.1), (-1.2, 0.4, 1.3), "iron", bevel=0)
typed_good, used_good = g._typed_alike(), g._methods_used()
bolts_good = sum(1 for o, _g in g.parts if o.name.split("~")[0] == "Bolt")
check_good = held(g)
os.environ["KIT_METHODS_LOCK"] = "0"
check_unlocked = g._methods_check(g.name)
os.environ.pop("KIT_METHODS_LOCK", None)

# ---- alike all the same: by a hair, in another material, named with "~", absorbed by a.fuse, in a token repeat
h = scene("_selftest_methods_hair")
h.box("Plate", (3.0, 0.2, 3.0), (0, -0.1, 0), "iron", bevel=0)
for i, x in enumerate((-1.2, -0.4, 0.4, 1.2)):
    h.box(f"Post{i}", (0.1, 0.8 + 0.0006 * i, 0.1), (x, 0.4, 1.3), "brass" if i % 2 else "iron", bevel=0)
    h.box(f"Peg~{i}", (0.1, 0.2, 0.1), (x, 0.1, -1.3), "iron", bevel=0)
for i, place in enumerate(PLACES):
    h.cylinder(f"Bolt{i}", 0.05, 0.2, (place[0], 0.05, place[2]), "iron", axis="Y", segments=8)
h.fuse("Plate", *[f"Bolt{i}" for i in range(len(PLACES))])
with h.repeat(2, step=(0, 0, 0.5)):
    for i in range(4):
        h.box(f"Tooth{i}", (0.1, 0.3, 0.1), (-1 + 0.3 * i, 0.15, -0.5), "iron", bevel=0)
typed_hair, used_hair = h._typed_alike(), h._methods_used()
different = scene("_selftest_methods_different")                            # four boxes that are NOT one shape
for i, s in enumerate(((0.2, 0.2, 0.2), (0.4, 0.2, 0.2), (0.2, 0.6, 0.2), (0.3, 0.3, 0.3))):
    different.box(f"Block{i}", s, (i, 0.3, 0), "iron", bevel=0)
typed_different = different._typed_alike()

# ---- a.repeat(at=): the first place is the part's own; places may come from a generator
r = scene("_selftest_methods_places")
try:
    with r.repeat(at=[(1, 0.1, 1), (2, 0.1, 1)]):
        r.box("Nub", (0.1, 0.1, 0.1), (0, 0.1, 0), "iron", bevel=0)
    first_place = "accepted"
except ValueError as e:
    first_place = str(e)
with r.repeat(3, at=(p for p in PLACES[:3])):
    r.cylinder("Pin", 0.05, 0.2, PLACES[0], "iron", axis="Y", segments=8)
pins = sum(1 for o, _g in r.parts if o.name.split("~")[0] == "Pin")

print("METHODS_LOCK " + json.dumps({
    "used": used, "used_plain": used_plain, "used_good": used_good, "used_hair": used_hair,
    "typed": typed, "typed_good": typed_good, "typed_hair": typed_hair, "typed_different": typed_different,
    "bolts_good": bolts_good, "check_bad": check_bad, "check_good": check_good, "check_blockout": check_blockout,
    "check_unlocked": check_unlocked, "first_place": first_place, "pins": pins,
}))
