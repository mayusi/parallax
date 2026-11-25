"""The photogrammetry route's outline check, against EXACT answers (kit/blender/photoscan_outline.py; his D-R02).

An asymmetric box and hand-made COLMAP cameras (world -> camera R, t; x right, y DOWN, z ahead) whose true outlines
are drawn by projecting the box's corners: landscape and portrait photos, centred and off-centre principal points,
pixels wider and taller than square. The check must score each about 1, and must NOT score a wrong outline high: a
mask flipped top to bottom, a principal point 30 px off (the review, 2026-11-16: a flipped mask still passed on the
round urn, and a portrait camera's shift was divided by its height)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import cad_check  # noqa: E402

BLENDER = cad_check.blender()
LO, HI = np.array([0.1, -0.6, -0.1]), np.array([0.5, 0.2, 1.1])
CORNERS = np.array([[x, y, z] for x in (LO[0], HI[0]) for y in (LO[1], HI[1]) for z in (LO[2], HI[2])])
CASES = {"landscape": (480, 360, 500.0, 500.0, 240.0, 180.0),
         "landscape_off_centre": (480, 360, 500.0, 500.0, 290.0, 140.0),
         "portrait": (360, 480, 500.0, 500.0, 180.0, 240.0),
         "portrait_off_centre": (360, 480, 500.0, 500.0, 210.0, 300.0),
         "taller_pixels": (480, 360, 500.0, 540.0, 240.0, 180.0),
         "wider_pixels": (480, 360, 540.0, 500.0, 240.0, 180.0)}
BOX = '''
import sys, bpy
out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.3, -0.2, 0.5))
o = bpy.context.object
o.scale = (0.4, 0.8, 1.2)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_yup=True)
'''


def hull(p):
    p = sorted(map(tuple, p))

    def half(pts):
        h = []
        for q in pts:
            while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (q[1] - h[-2][1])
                                   - (h[-1][1] - h[-2][1]) * (q[0] - h[-2][0])) <= 0:
                h.pop()
            h.append(q)
        return h
    return half(p)[:-1] + half(p[::-1])[:-1]


def look(centre, target, roll):
    z = target - centre
    z /= np.linalg.norm(z)
    x = np.cross(z, [0, 0, 1.0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    c, s = np.cos(roll), np.sin(roll)
    return np.array([c * x + s * y, -s * x + c * y, z])


def views(folder, name, case, flip=False, shift_cx=0.0):
    from PIL import Image, ImageDraw  # noqa: PLC0415

    W, H, fx, fy, cx, cy = case
    tgt, out = np.array([0.3, -0.2, 0.5]), []
    for i, (az, el, roll) in enumerate([(0.3, 0.4, 0.0), (1.4, 0.1, 0.2), (2.6, 0.7, -0.3), (4.0, 0.25, 0.0)]):
        centre = tgt + 3.0 * np.array([np.cos(az) * np.cos(el), np.sin(az) * np.cos(el), np.sin(el)])
        r = look(centre, tgt + np.array([0.15, -0.1, 0.05]), roll)
        t = -r @ centre
        p = (r @ CORNERS.T).T + t
        uv = np.stack([fx * p[:, 0] / p[:, 2] + cx, fy * p[:, 1] / p[:, 2] + cy], 1)
        im = Image.new("L", (W, H), 0)
        ImageDraw.Draw(im).polygon([tuple(q) for q in hull(uv)], fill=255)
        m = np.asarray(im, np.float32) / 255.0
        path = os.path.join(folder, f"{name}_{i}.npy")
        np.save(path, m[::-1] if flip else m)
        out.append({"image": f"{name}_{i}", "R": r.tolist(), "t": t.tolist(), "width": W, "height": H,
                    "fx": fx, "fy": fy, "cx": cx + shift_cx, "cy": cy, "mask": path})
    spec = os.path.join(folder, f"{name}.json")
    json.dump({"to_scan": np.eye(4).tolist(), "views": out}, open(spec, "w", encoding="utf-8"))
    return spec


def score(glb, spec):
    out = spec + ".out.json"
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "blender", "photoscan_outline.py"), "--", glb, spec, out],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    assert r.returncode == 0, (r.stderr or r.stdout)[-500:]
    return json.load(open(out, encoding="utf-8"))


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Outline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.tmp.name
        cls.glb = os.path.join(d, "box.glb")
        src = os.path.join(d, "box.py")
        open(src, "w", encoding="utf-8").write(BOX)
        subprocess.run([BLENDER, "-b", "--factory-startup", "-P", src, "--", cls.glb], capture_output=True,
                       timeout=300)
        cls.scores = {n: score(cls.glb, views(d, n, c)) for n, c in CASES.items()}
        cls.flipped = score(cls.glb, views(d, "flipped", CASES["landscape"], flip=True))
        cls.shifted = score(cls.glb, views(d, "shifted", CASES["portrait_off_centre"], shift_cx=30.0))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_camera_kind_sees_the_exact_outline(self):
        for name, s in self.scores.items():
            self.assertGreater(s["worst"][0][1], 0.97, (name, s))

    def test_a_wrong_outline_scores_low(self):
        self.assertLess(self.flipped["median"], 0.8, self.flipped)
        self.assertLess(self.shifted["median"], 0.9, self.shifted)


if __name__ == "__main__":
    unittest.main()
