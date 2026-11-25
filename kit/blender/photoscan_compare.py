"""photoscan_compare.py - how far a scan lies from the TRUE shape (the photogrammetry route's proof; his D-R02).

blender -b --factory-startup -P photoscan_compare.py -- <scan.glb> <truth.obj> [--no-scale]

The truth is placed the way photoscan_finish.py places a scan (base on the ground, middle on the origin, its
longest way across the ground along Y); the scan is then turned about the up axis (both ways round, the
longest-way rule leaves a half turn open) and moved by a few rounds of nearest-point fitting (ICP, no scaling:
the scan's own scale is what is judged). Both ways are measured, each surface against the other: the points of
one sampled over its area, their distance to the other's surface. Prints COMPARE {json}: p50 / p90 / max as a
share of the truth's height (scale-free), the sizes of both."""

import json
import math
import random
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ARGS = sys.argv[sys.argv.index("--") + 1:]
SCAN, TRUTH = ARGS[0], ARGS[1]
SAMPLES = 20000

bpy.ops.wm.read_factory_settings(use_empty=True)


def load(path):
    before = set(bpy.data.objects)
    if path.lower().endswith((".glb", ".gltf")):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        bpy.ops.wm.obj_import(filepath=path, forward_axis="Y", up_axis="Z")
    objs = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    vs, fs = [], []
    for o in objs:
        m = o.matrix_world
        base = len(vs)
        vs += [tuple(m @ v.co) for v in o.data.vertices]
        o.data.calc_loop_triangles()
        fs += [tuple(base + i for i in t.vertices) for t in o.data.loop_triangles]
    return np.array(vs, float), np.array(fs, int)


def place(v):
    """base on the ground, middle on the origin, the longest way across the ground along Y"""
    xy = v[:, :2] - v[:, :2].mean(axis=0)
    w, vecs = np.linalg.eigh(xy.T @ xy)
    major = vecs[:, int(np.argmax(w))]
    a = math.atan2(major[0], major[1])
    c, s = math.cos(a), math.sin(a)
    r = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    v = v @ r.T
    lo, hi = v.min(axis=0), v.max(axis=0)
    return v - np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])


def sample(v, f, n, seed):
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(f), size=n, p=area / area.sum())
    u, w = rng.random(n), rng.random(n)
    flip = u + w > 1
    u[flip], w[flip] = 1 - u[flip], 1 - w[flip]
    return a[pick] + (b[pick] - a[pick]) * u[:, None] + (c[pick] - a[pick]) * w[:, None]


def tree(v, f):
    return BVHTree.FromPolygons([tuple(p) for p in v], [tuple(t) for t in f])


def dist(points, t):
    return np.array([t.find_nearest(Vector(p))[3] for p in points])


tv, tf = load(TRUTH)
sv, sf = load(SCAN)
tv, sv = place(tv), place(sv)
t_tree = tree(tv, tf)
s_pts = sample(sv, sf, SAMPLES, 1)
best = None
for turn in (0.0, math.pi):   # (the longest-way rule leaves a half turn open)
    c, s = math.cos(turn), math.sin(turn)
    rot = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    pts = s_pts @ rot.T
    total_r, total_t = rot.copy(), np.zeros(3)
    for _ in range(25):   # ICP: nearest points on the truth, then the best rigid move (Kabsch), no scaling
        near = np.array([tuple(t_tree.find_nearest(Vector(p))[0]) for p in pts[::4]])
        src = pts[::4]
        ms, mn = src.mean(axis=0), near.mean(axis=0)
        h = (src - ms).T @ (near - mn)
        u_, _s, vt = np.linalg.svd(h)
        d = np.sign(np.linalg.det(vt.T @ u_.T))
        r = vt.T @ np.diag([1, 1, d]) @ u_.T
        t = mn - r @ ms
        pts = pts @ r.T + t
        total_r, total_t = r @ total_r, r @ total_t + t
    err = float(np.median(dist(pts[::8], t_tree)))
    if best is None or err < best[0]:
        best = (err, pts, total_r, total_t)
_e, s_pts, R, T = best
moved = sv @ R.T + T
s_tree = tree(moved, sf)
height = float(tv[:, 2].max() - tv[:, 2].min())
a = dist(s_pts, t_tree)                        # the scan's surface off the truth's
b = dist(sample(tv, tf, SAMPLES, 2), s_tree)   # the truth's surface off the scan's (a part the scan missed)
both = np.concatenate([a, b])
t_pts = sample(tv, tf, SAMPLES, 2)
far = t_pts[b > 0.03 * height]                 # (the truth's surface the scan missed by over 3% of the height)
out = {"missed_share": round(float(len(far)) / len(t_pts), 4),
       "missed_where": [round(float(x), 3) for x in far.mean(axis=0)] if len(far) else None,
       "missed_low": round(float((far[:, 2] < 0.1 * height).mean()), 3) if len(far) else None,
       "p50": round(float(np.percentile(both, 50)) / height, 5), "p90": round(float(np.percentile(both, 90)) / height, 5),
       "max": round(float(both.max()) / height, 5), "missed_p90": round(float(np.percentile(b, 90)) / height, 5),
       "truth_size": [round(float(x), 4) for x in tv.max(axis=0) - tv.min(axis=0)],
       "scan_size": [round(float(x), 4) for x in moved.max(axis=0) - moved.min(axis=0)]}
print("COMPARE " + json.dumps(out))
