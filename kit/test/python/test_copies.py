"""What a part's copies take from it (card nrey, the repeat stage's review; kit/selftest/blender/build_copies.py,
parts made inside `with a.mirror("X"):`): a.fuse fuses each copy of an absorbed part into the target's copy that
stands the same way (all of them went into the one target, its own copy left bare); a.displace presses the detail
onto a copy where its PART has the point (mirrored), not where the copy stands (it read nothing there); a.texel's
density reaches the copies (a copy's name "Wheel~m1" missed the factor given to "Wheel")."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_uvparts as U  # noqa: E402

BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def build(how):
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                          os.path.join(ROOT, "kit", "selftest", "blender", "build_copies.py"), "--", how],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    dec = json.JSONDecoder()
    i = out.stdout.rfind("COPIES ")
    got = dec.raw_decode(out.stdout[i + 7:])[0] if i >= 0 else None
    k = out.stdout.find('{"schema"')
    status = dec.raw_decode(out.stdout[k:])[0] if k >= 0 else None
    return out.returncode, got, status, out.stdout[-1500:] + out.stderr[-1500:]


class Weights(unittest.TestCase):
    def test_a_copy_takes_its_parts_factor(self):
        w = {"Wheel": 2.0}
        self.assertEqual(U.weight_of(w, "Wheel"), 2.0)
        self.assertEqual(U.weight_of(w, "Wheel~m1"), 2.0)
        self.assertEqual(U.weight_of(w, "Wheel~r3"), 2.0)
        self.assertEqual(U.weight_of(w, "Block"), 1.0)
        self.assertEqual(U.weight_of({"Wheel": 2.0, "Wheel~m1": 0.5}, "Wheel~m1"), 0.5)   # (its own, when given)


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class TheCopies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {h: build(h) for h in ("fuse", "displace", "texel")}

    def test_each_body_takes_the_boss_beside_it(self):
        code, g, st, log = self.runs["fuse"]
        self.assertEqual(code, 0, log)
        b = g["bodies"]
        self.assertEqual(b["Body"], b["Body~m1"], b)          # (the same shape on both sides)
        self.assertGreater(b["Body"]["faces"], 6, b)           # (a box with a boss fused on: more than a box)
        self.assertEqual(g["boss_left"], [])
        self.assertEqual(st["status"], "pass", st["summary"])

    def test_the_copy_carries_the_detail_mirrored(self):
        code, g, st, log = self.runs["displace"]
        self.assertEqual(code, 0, log)
        self.assertGreater(g["Plate"]["moved"], 10, g)
        self.assertEqual(g["Plate~m1"]["moved"], g["Plate"]["moved"], g)
        self.assertLess(g["mirrored_max_mm"], 0.01, g)
        self.assertEqual(st["status"], "pass", st["summary"])

    def test_the_copy_is_as_dense_as_its_part(self):
        code, _g, st, log = self.runs["texel"]
        self.assertEqual(code, 0, log)
        parts = st["facts"]["uv_parts"]["main"]["parts"]
        self.assertEqual(parts["Wheel~m1"]["weight"], 2.0, parts)
        self.assertAlmostEqual(parts["Wheel~m1"]["tx_per_mm"], parts["Wheel"]["tx_per_mm"], delta=0.02)
        self.assertGreater(parts["Wheel~m1"]["tx_per_mm"], 1.6 * parts["Block"]["tx_per_mm"], parts)


if __name__ == "__main__":
    unittest.main()
