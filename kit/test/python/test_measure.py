"""kit refs measure on a STAGED, ANIMATED library model — what the first real download (a Colt 1911 assembly
animation, 2026-10-07) was: a backdrop plane, a punch tool lying apart, parts flying in. The object must be measured
alone, at its most-assembled frame, at the real length asked for, with every part's own size."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import cad_check  # noqa: E402

MEASURE = os.path.join(HERE, "..", "..", "refs", "measure.py")
BLENDER = cad_check.blender()

STAGE = r'''
import bpy, sys
out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
def box(name, loc, size):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)  # keep the place: Flyer is keyed
    return o
box("Body", (0, 0, 0), (2.0, 0.3, 0.6))           # the object: three touching parts, 2.0 long (the author's units)
box("Top", (0, 0, 0.45), (1.8, 0.3, 0.3))
flyer = box("Flyer", (0.2, 0, -0.45), (0.4, 0.3, 0.3))
flyer.location = (0.2, 0, -6.0)                   # it flies IN: far below at frame 1, in place at frame 20
flyer.keyframe_insert("location", frame=1)
flyer.location = (0.2, 0, -0.45)
flyer.keyframe_insert("location", frame=20)
box("Floor", (0, 0, -8.0), (12.0, 12.0, 0.0))     # staging: a flat backdrop, bigger than everything
box("Punch", (4.0, 3.0, 0), (0.1, 0.1, 0.4))      # a tool lying apart
bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, 20
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_animations=True)
'''


def _result(out):
    for line in out.splitlines():
        if line.startswith('{"schema"'):
            return json.loads(line)
    raise AssertionError("no result line:\n" + out[-2000:])


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class TestStagedAnimatedModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        script = os.path.join(cls.tmp, "stage.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(STAGE)
        cls.glb = os.path.join(cls.tmp, "staged.glb")
        subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--", cls.glb],
                       check=True, capture_output=True, timeout=300)

    def measure(self, *extra):
        env = dict(os.environ, KIT_BUILD=self.tmp)
        p = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", MEASURE, "--",
                            self.glb, "--name", "staged", "--out", self.tmp, "--stations", "6", *extra],
                           capture_output=True, text=True, timeout=300, env=env)
        r = _result(p.stdout)
        self.assertEqual(r["status"], "pass", r)
        with open(os.path.join(self.tmp, "staged.measure.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_the_object_alone_assembled_at_the_real_length(self):
        m = self.measure("--length-mm", "200")
        why = {d["name"]: d["why"] for d in m["dropped"]}
        self.assertIn("backdrop", why.get("Floor", ""))
        self.assertIn("apart", why.get("Punch", ""))
        self.assertEqual(sorted(p["name"] for p in m["parts"]), ["Body", "Flyer", "Top"])
        self.assertGreaterEqual(m["frame"], 18)  # assembled: the flyer in place, not at frame 1
        width, height, length = m["size_mm"]
        self.assertAlmostEqual(length, 200.0, delta=0.5)
        self.assertAlmostEqual(width, 30.0, delta=0.5)
        self.assertAlmostEqual(height, 120.0, delta=2.0)  # Top's crown to the Flyer's foot, scaled by 0.1
        body = next(p for p in m["parts"] if p["name"] == "Body")
        self.assertAlmostEqual(body["size_mm"][2], 200.0, delta=0.5)

    def test_front_min_turns_the_model_never_mirrors_it(self):
        flyer = lambda m: next(p for p in m["parts"] if p["name"] == "Flyer")  # noqa: E731
        as_is = flyer(self.measure("--length-mm", "200"))
        turned = flyer(self.measure("--length-mm", "200", "--front", "min"))
        self.assertAlmostEqual(as_is["centre_mm"][2], 120.0, delta=0.5)   # 0.2 ahead of the middle, x 0.1 -> mm
        self.assertAlmostEqual(turned["centre_mm"][2], 80.0, delta=0.5)   # the other end is the front now
        self.assertEqual(as_is["size_mm"], turned["size_mm"])

    def test_only_measures_the_named_part(self):
        m = self.measure("--only", "body")
        self.assertEqual([p["name"] for p in m["parts"]], ["Body"])
        self.assertAlmostEqual(m["size_mm"][2], 2000.0, delta=1.0)  # no --length-mm: the file's own metres

    def test_a_cut_box_leaves_a_protrusion_out_of_the_sizes_and_says_so(self):
        m = self.measure("--length-mm", "200", "--cut", "95..145,0..29")  # (the Flyer's foot, under the front half)
        self.assertAlmostEqual(m["size_mm"][1], 90.0, delta=1.0)        # the Body's floor is the bottom now
        self.assertAlmostEqual(m["size_uncut_mm"][1], 120.0, delta=2.0)
        self.assertAlmostEqual(m["size_mm"][2], 200.0, delta=0.5)       # the length is the whole model's
        self.assertEqual(m["cut"]["vertices_left_out"], 12)  # (the foot's 4 corners, split per face by glTF)
        self.assertEqual((m["cut"]["length_mm"], m["cut"]["height_mm"]), ([95.0, 145.0], [0.0, 29.0]))
        env = dict(os.environ, KIT_BUILD=self.tmp)
        for bad in ("95..145", "0..1,200..201"):  # (not a box; a box with nothing in it)
            p = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", MEASURE, "--",
                                self.glb, "--name", "staged_bad", "--out", self.tmp, "--length-mm", "200",
                                "--cut", bad], capture_output=True, text=True, timeout=300, env=env)
            self.assertEqual(_result(p.stdout)["status"], "fail", bad)

    def test_views_are_square_shaded_at_a_known_scale_and_turned_like_photographs(self):
        import numpy as np
        from PIL import Image

        m = self.measure("--length-mm", "200", "--views", "all", "--view-px-mm", "6")
        self.assertEqual(sorted(m["shots"]), ["front", "rear", "side-left", "side-right", "top"])
        self.assertEqual(m["shot_px_per_mm"], 6.0)
        box = {}
        for view in m["shots"]:
            im = np.asarray(Image.open(os.path.join(self.tmp, "refs", f"staged_{view}_view.png")).convert("RGB"))
            self.assertTrue((im[0, 0] >= 250).all(), view)  # (on white, opaque)
            ys, xs = np.where((im < 250).any(axis=2))
            box[view] = (xs.min(), ys.min(), xs.max(), ys.max(), im.shape[1])
        mm = lambda v, k: (box[v][k + 2] - box[v][k] + 1) / 6.0  # noqa: E731
        for view in ("side-right", "side-left", "top"):  # the length across, at 6 px per mm
            self.assertAlmostEqual(mm(view, 0), 200.0, delta=2.0)
        self.assertAlmostEqual(mm("top", 1), 30.0, delta=1.5)
        for view in ("front", "rear"):
            self.assertAlmostEqual(mm(view, 0), 30.0, delta=1.5)
            self.assertAlmostEqual(mm(view, 1), 120.0, delta=3.0)

        def flyer_x(view):  # the Flyer hangs under the front half: its foot is the lowest object pixels
            im = np.asarray(Image.open(os.path.join(self.tmp, "refs", f"staged_{view}_view.png")).convert("RGB"))
            ys, xs = np.where((im < 250).any(axis=2))
            return xs[ys >= ys.max() - 3].mean() / im.shape[1]

        self.assertGreater(flyer_x("side-right"), 0.5)  # the front to the right
        self.assertLess(flyer_x("side-left"), 0.5)      # seen from the other side: the front to the left


if __name__ == "__main__":
    unittest.main()
