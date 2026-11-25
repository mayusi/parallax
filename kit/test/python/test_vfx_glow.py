"""A GLOW MASK packed beside a sheet (kit/vfx/fxfinish.py `post.emissive`; kit/vfx/surfaces.py; the V3 doc, VFX stages
C.2 and D.1: "an albedo atlas + its paired EmissiveMaskContent map"). A mesh shows a sheet through a SurfaceAppearance
whose EmissiveMask was the sheet itself, so the dim smoke glowed as much as the white-hot core. Now the packer writes
<key>_glow.png (white where the sheet gives light past a floor), registers it as its own texture and names it on the
sheet's entry; the surface templates use its id once it is uploaded, and say so while it is not.
Run: python -m pytest kit/test/python/test_vfx_glow.py -q"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import fxfinish as F  # noqa: E402
import surfaces as S  # noqa: E402

N = 64
YY, XX = np.mgrid[0:N, 0:N]
R = np.hypot(XX - 31.5, YY - 31.5)


def frame(i=0):
    """a hot core (white, r < 10) inside dim smoke (grey 0.3) that grows a little each frame (r < 20 + 2 i):
    premultiplied, as frames on disk are"""
    a = (R < 20 + 2 * i).astype(np.float32)
    tone = np.where(R < 10, 1.0, 0.3).astype(np.float32)
    return np.dstack([tone * a] * 3 + [a])


class Pack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for d in ("specs", "frames/hot", "out"):
            os.makedirs(os.path.join(self.tmp, d))
        for i in range(4):
            np.save(os.path.join(self.tmp, "frames", "hot", f"{i:03d}.npy"), frame(i))
        self.reg = os.path.join(self.tmp, "_textures.json")
        with open(self.reg, "w") as f:
            json.dump({}, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pack(self, post):
        with open(os.path.join(self.tmp, "specs", "hot.json"), "w") as f:
            json.dump({"engine": "fx", "grid": 2, "frames": 4, "post": {"tonemap": False, "border": 0, **post}}, f)
        argv = sys.argv
        sys.argv = ["fxfinish.py", "--specs", os.path.join(self.tmp, "specs"), "--frames", os.path.join(self.tmp, "frames"),
                    "--out", os.path.join(self.tmp, "out"), "--registry", self.reg, "--no-review"]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                code = F.main()
        finally:
            sys.argv = argv
        return code, json.loads(buf.getvalue().strip().splitlines()[-1])

    def test_the_mask_is_white_on_the_core_and_dark_on_the_smoke(self):
        code, out = self.pack({"emissive": True})
        self.assertEqual(code, 0, out["summary"])
        sheet = np.asarray(Image.open(os.path.join(self.tmp, "out", "hot.png")).convert("RGBA"))
        mask = np.asarray(Image.open(os.path.join(self.tmp, "out", "hot_glow.png")).convert("L")).astype(float) / 255
        self.assertEqual(mask.shape, sheet.shape[:2])                 # the same cells, the same size
        for cy, cx in ((32, 32), (32, 96), (96, 32), (96, 96)):        # every cell of the 2x2 sheet
            self.assertGreater(mask[cy, cx], 0.95)                     # the core glows
            self.assertLess(mask[cy, cx + 18], 0.05)                   # the smoke does not
            self.assertLess(mask[cy - 30, cx - 30], 0.05)              # nothing outside
        reg = json.load(open(self.reg))
        self.assertEqual(reg["hot"]["emissive"], "hot_glow")
        self.assertEqual(reg["hot_glow"]["glow_of"], "hot")
        self.assertEqual(reg["hot_glow"]["grid"], 2)
        self.assertEqual(reg["hot_glow"]["id"], "")                    # its own upload: the owner's step

    def test_a_floor_nothing_reaches_is_refused_and_a_bad_block_is_said(self):
        code, out = self.pack({"emissive": {"floor": 0.999, "soft": 0.0}})  # the core is 1.0: a high floor still finds it
        self.assertEqual(code, 0, out["summary"])
        for bad in ({"floor": 1.5}, {"floor": "high"}, "yes", {"soft": 0.9}):
            code, out = self.pack({"emissive": bad})
            self.assertEqual(code, 1)
            self.assertIn("post.emissive", out["summary"])

    def test_a_sheet_that_never_gives_light_enough_glows_nowhere_and_is_refused(self):
        for i in range(4):  # all smoke, no core
            a = (R < 20 + 2 * i).astype(np.float32)
            np.save(os.path.join(self.tmp, "frames", "hot", f"{i:03d}.npy"), np.dstack([0.3 * a] * 3 + [a]))
        code, out = self.pack({"emissive": True})
        self.assertEqual(code, 1)
        self.assertIn("nothing would glow", out["summary"])

    def test_dropping_emissive_drops_the_link(self):
        self.pack({"emissive": True})
        code, _ = self.pack({})
        self.assertEqual(code, 0)
        self.assertNotIn("emissive", json.load(open(self.reg))["hot"])


class Light(unittest.TestCase):
    def test_a_saturated_red_tail_is_not_white_hot(self):
        # seen on a real sheet (hk_tongue_gpu, 2026-11-18): read by its brightest channel the red tail glowed as
        # much as the yellow core; by its luminance only the core does
        px = np.zeros((4, 4, 4), dtype=np.uint8)
        px[..., 3] = 255
        px[0] = [255, 250, 80, 255]    # yellow-white core
        px[1] = [255, 60, 20, 255]     # red tail
        px[2] = [255, 140, 40, 255]    # orange
        mask, _ = F.glow_mask(Image.fromarray(px, "RGBA"), F.glow_block({"emissive": True}))
        m = np.asarray(mask.convert("L")).astype(float) / 255
        self.assertGreater(m[0].min(), 0.95)
        self.assertLess(m[1].max(), 0.05)
        self.assertTrue(m[1].max() < m[2].min() < m[0].min())  # orange glows between them


class Surfaces(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs(os.path.join("assets", "effects"))
        with open(os.path.join("assets", "effects", "piece.json"), "w") as f:
            json.dump({"version": 3, "layers": [{"kind": "mesh", "surface": True, "texture": "hot"},
                                                {"kind": "mesh", "surface": True, "texture": "plain"}]}, f)

    def tearDown(self):
        os.chdir(self.old)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_it(self, reg):
        with open(os.path.join("assets", "effects", "_textures.json"), "w") as f:
            json.dump(reg, f)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            S.main([])
        out = json.loads(buf.getvalue().strip().splitlines()[-1])
        model = json.load(open(os.path.join("assets", "effects", "_surfaces.model.json")))
        return out, {c["name"]: c["properties"] for c in model["children"]}

    def test_the_template_glows_through_the_mask_once_it_is_uploaded(self):
        out, t = self.run_it({"hot": {"id": "rbxassetid://1", "emissive": "hot_glow"},
                              "hot_glow": {"id": "rbxassetid://2"}, "plain": {"id": "rbxassetid://3"}})
        self.assertEqual(out["status"], "pass")
        self.assertEqual(t["hot"]["ColorMap"], "rbxassetid://1")
        self.assertEqual(t["hot"]["EmissiveMaskContent"], "rbxassetid://2")
        self.assertEqual(t["plain"]["EmissiveMaskContent"], "rbxassetid://3")  # no mask: the sheet itself, as before

    def test_a_mask_not_uploaded_falls_back_to_the_sheet_and_says_so(self):
        out, t = self.run_it({"hot": {"id": "rbxassetid://1", "emissive": "hot_glow"},
                              "hot_glow": {"id": ""}, "plain": {"id": "rbxassetid://3"}})
        self.assertEqual(out["status"], "warn")
        self.assertEqual(out["unglowed"], ["hot"])
        self.assertIn("glow mask NOT uploaded", out["summary"])
        self.assertEqual(t["hot"]["EmissiveMaskContent"], "rbxassetid://1")


if __name__ == "__main__":
    unittest.main()
