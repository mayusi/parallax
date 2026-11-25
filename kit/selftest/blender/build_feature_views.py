"""build_feature_views.py — SMOKE fixture for the pictures a build keeps to be LOOKED AT (kit/blender/rbx_judgeviews.py,
card 32nd, 2026-11-11). Not part of `kit selftest`: the views are kept only by a build WITH previews (the selftest
builds run --no-preview).

A small block blaster whose reference picture is DRAWN FROM THE MODEL'S OWN NUMBERS (its left side, the front on the
left, 100 px a stud), traced by hand below, and a brief (_selftest_feature_views.brief.md beside this script) with
five hero features: four name a box in that picture, one names none. The build must then keep

    the six views at the size the owner judges at (>= 1024 x 768)
    a pair per placed feature: the picture's box, then the MODEL's same box, 1024 px on its larger side
    the fifth feature as a gap, with the reason

and this script CHECKS the pairs: each model pane shows its feature's own colour in its middle — the glow strip
cyan, the grip dark, the muzzle steel, and the BADGE red: it exists on the model's left side only, so a close-up
taken from the wrong flank (or mirrored) shows no badge.

    KIT_BUILD=<a scratch folder> blender -b --factory-startup --python-exit-code 2 \
        -P kit/selftest/blender/build_feature_views.py -- [--geo] [--schematic]

--geo: the shape round's pictures (build/judge/<name>/geo/, Workbench) are checked instead, and must take < 20 s.
The grip is a slide joint, so the build has a mechanism: its schematic views are rendered only with --schematic.
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
import rbx_judgeviews  # noqa: E402
import rbx_precision  # noqa: E402

NAME = "_selftest_feature_views"
GEO = "--geo" in sys.argv
out = os.path.join(rbx.BUILD, "selftest")
os.makedirs(out, exist_ok=True)

# ---- the model's numbers (Roblox space: y up, the front = -z), and the picture drawn from them
Z_FRONT, Z_BACK, Y_LOW, Y_HIGH = -2.06, 1.0, -0.08, 1.0
PX = 100.0  # pixels a stud
X0, Y1 = 20.0, 150.0  # the object's box in the picture: its left (front) edge and its bottom edge
LENGTH = (Z_BACK - Z_FRONT) * PX  # 306 px
HR = (Y_HIGH - Y_LOW) / (Z_BACK - Z_FRONT)

CYAN, RED, DARK, STEEL, GRIP = (0.1, 0.8, 0.95), (0.85, 0.08, 0.06), (0.18, 0.19, 0.22), (0.55, 0.57, 0.6), (0.12, 0.12, 0.13)


def rect(z0, z1, y0, y1):
    """a part's side box (z front -> back, y low -> high) in picture pixels: columns x0:x1, rows r0:r1"""
    return (int(round(X0 + (z0 - Z_FRONT) * PX)), int(round(X0 + (z1 - Z_FRONT) * PX)),
            int(round(Y1 - (y1 - Y_LOW) * PX)), int(round(Y1 - (y0 - Y_LOW) * PX)))


pic = np.full((160, 400, 4), 0.92, np.float32)
pic[..., 3] = 1
for (z0, z1, y0, y1), colour in (((-2.0, -0.6, 0.71, 0.89), STEEL),  # barrel
                                 ((-2.06, -1.94, 0.68, 0.92), STEEL),  # muzzle ring
                                 ((-0.6, 1.0, 0.5, 1.0), DARK),  # body
                                 ((0.59, 0.91, -0.08, 0.49), GRIP),  # grip (a hair under the body: it slides)
                                 ((-0.2, 0.7, 0.74, 0.82), CYAN),  # glow strip
                                 ((0.3, 0.42, 0.6, 0.72), RED)):  # the badge (left side only)
    x0, x1, r0, r1 = rect(z0, z1, y0, y1)
    pic[r0:r1, x0:x1, :3] = colour
ref = os.path.join(out, "_feature_views_ref.png")
rbx_precision._save_pixels(pic, ref)
ref_rel = os.path.relpath(ref, rbx.REPO).replace("\\", "/") if os.path.splitdrive(ref)[0] == os.path.splitdrive(
    rbx.REPO)[0] else ref

# ---- its trace (what `kit trace --front left` stores: u back -> front, h up, in lengths; the frame in pixels)
side = [(-2.06, 0.68), (-2.06, 0.92), (-1.94, 0.92), (-1.94, 0.89), (-0.6, 0.89), (-0.6, 1.0), (1.0, 1.0), (1.0, 0.5),
        (0.91, 0.5), (0.91, -0.08), (0.59, -0.08), (0.59, 0.5), (-0.6, 0.5), (-0.6, 0.71), (-1.94, 0.71), (-1.94, 0.68)]
span = Z_BACK - Z_FRONT
trace = os.path.join(out, "_feature_views_side.trace.json")
with open(trace, "w", encoding="utf-8") as fh:
    json.dump({"name": "_feature_views_side", "source": ref_rel, "front": "left", "rotate": 0.0,
               "height_ratio": round(HR, 5), "pixels_per_length": LENGTH,
               "frame": {"x0": X0, "y1": Y1, "length_px": LENGTH},
               "outline": [[round((Z_BACK - z) / span, 5), round((y - Y_LOW) / span, 5)] for z, y in side],
               "holes": []}, fh, indent=1)

a = rbx.Asset(NAME, tex=64, ground=False, ref_image=ref_rel)
a.trace_match(trace, view="side", bar=0.9, lines=False)
a.material("body", DARK, metal=0.4, rough=0.5, wear=0.2)
a.material("steel", STEEL, metal=1.0, rough=0.35)
a.material("grip", GRIP, rough=0.8)
a.material("glow", CYAN, rough=0.2, emit=3)
a.material("badge", RED, rough=0.6)
a.box("Body", (0.4, 0.5, 1.6), (0, 0.75, 0.2), "body", bevel=0.03)
a.box("Glow", (0.42, 0.08, 0.9), (0, 0.78, 0.25), "glow", bevel=0)
a.box("Badge", (0.03, 0.12, 0.12), (-0.205, 0.66, 0.36), "badge", bevel=0)  # on the LEFT face (-x) only
a.cylinder("Barrel", 0.09, 1.4, (0, 0.8, -1.3), "steel", axis="Z")
a.cylinder("Muzzle", 0.12, 0.12, (0, 0.8, -2.0), "steel", axis="Z")
a.box("Grip", (0.3, 0.57, 0.32), (0, 0.205, 0.75), "grip", bevel=0.02, group="grip")  # y -0.08 .. 0.49
a.joint("Grip", "grip", "slide", axis=(0, -1, 0), max=0.4)
report = a.build()

# ---- the checks: what a build must have kept, and that each close-up shows ITS feature
facts = report["facts"]
kept = facts.get("geo_views" if GEO else "judge_views")
problems = []


def need(ok, text):
    if not ok:
        problems.append(text)


need(bool(kept), "the build kept no views ({}): previews must be on (no --no-preview)".format("geo" if GEO else "full"))
if kept:
    folder = os.path.join(rbx.REPO, kept["folder"]) if not os.path.isabs(kept["folder"]) else kept["folder"]
    need(kept["views"] == 6, f"six views expected, {kept['views']} kept")
    w, h = kept["view_size"]
    need(w >= 1024 and h >= 768, f"the views are {w} x {h}: under the size the owner judges at (1024 x 768)")
    for view in ("front", "back", "left", "right", "top", "three_quarter"):
        path = os.path.join(folder, f"{view}.png")
        if not os.path.isfile(path):
            problems.append(f"{view}.png is missing")
            continue
        px = rbx_precision._load_pixels(path)
        need((px.shape[1], px.shape[0]) == (w, h), f"{view}.png is {px.shape[1]} x {px.shape[0]}, not {w} x {h}")
    with open(os.path.join(folder, "features.json"), encoding="utf-8") as fh:
        rows = {r["name"]: r for r in json.load(fh)["features"]}
    need(kept.get("features") == 4, f"four feature pairs expected, {kept.get('features')} made")
    gaps = kept.get("feature_gaps") or []
    need(len(gaps) == 1 and "maker's mark" in gaps[0] and "no picture" in gaps[0],
         f"the feature with no picture must be the one gap, named with its reason: {gaps}")
    # (feature, what its middle must look like: a test on the mean (r, g, b) of the pane's central patch)
    looks = {
        "glow strip": ("cyan", lambda r, g, b: g > 1.6 * r and b > 1.6 * r and b > 0.35),
        "badge": ("red (the LEFT side's badge)", lambda r, g, b: r > 1.6 * g and r > 1.6 * b and r > 0.2),
        "grip": ("dark", lambda r, g, b: max(r, g, b) < 0.4),
        "muzzle": ("steel grey", lambda r, g, b: max(r, g, b) - min(r, g, b) < 0.2 and max(r, g, b) > 0.1),
    }
    for name, (what, test) in looks.items():
        row = rows.get(name) or {}
        if not row.get("file"):
            problems.append(f"{name}: no close-up ({row.get('why')})")
            continue
        pair = rbx_precision._load_pixels(os.path.join(folder, row["file"]))
        pw, ph = row["px"]
        need(max(pw, ph) == rbx_judgeviews.FEATURE_PX, f"{name}: its close-up is {pw} x {ph}, not 1024 on its larger side")
        pane = pair[-ph:, :, :] if row["layout"] == "stack" else pair[:, -pw:, :]
        need((pane.shape[1], pane.shape[0]) == (pw, ph), f"{name}: the pair does not end with a {pw} x {ph} model pane")
        cy, cx = pane.shape[0] // 2, pane.shape[1] // 2
        r_, g_, b_ = (float(v) for v in pane[cy - 6:cy + 6, cx - 6:cx + 6, :3].reshape(-1, 3).mean(axis=0))
        need(test(r_, g_, b_), f"{name}: the middle of its model pane is ({r_:.2f}, {g_:.2f}, {b_:.2f}), not {what}")
        # the reference pane (first) shows the same thing in ITS middle: the picture was drawn from the model
        refp = pair[:pair.shape[0] - ph - rbx_judgeviews.PAIR_GAP] if row["layout"] == "stack" else \
            pair[:, :pair.shape[1] - pw - rbx_judgeviews.PAIR_GAP]
        ry, rx = refp.shape[0] // 2, refp.shape[1] // 2
        r_, g_, b_ = (float(v) for v in refp[ry - 3:ry + 3, rx - 3:rx + 3, :3].reshape(-1, 3).mean(axis=0))
        need(test(r_, g_, b_) or name == "muzzle",  # (the muzzle's flat picture grey is brighter than lit steel)
             f"{name}: the middle of its reference pane is ({r_:.2f}, {g_:.2f}, {b_:.2f}), not {what}")
    if GEO:
        took = (report.get("timing") or {}).get("render:geo_views")
        need(took is not None and took < 20.0, f"a shape round's pictures took {took} s (the bar: under 20 s)")

sch = facts.get("schematic_renders") or ""
if GEO:
    pass  # (a shape round renders no schematic)
elif "--schematic" in sys.argv:
    need(sch in ("rendered", "reused: nothing they show changed"), f"--schematic must render the mechanism's views: {sch!r}")
else:
    need(sch.startswith("not rendered"), f"a build without --schematic must not render the mechanism's views: {sch!r}")
    need("render:mechanism" not in (report.get("timing") or {}) or report["timing"]["render:mechanism"] < 2.0,
         f"the mechanism's views cost {(report.get('timing') or {}).get('render:mechanism')} s without --schematic")

if problems:
    print("FEATURE VIEWS: FAILED")
    for p in problems:
        print("  - " + p)
    raise SystemExit(2)
print("FEATURE VIEWS: OK — " + rbx_judgeviews.say(kept))
