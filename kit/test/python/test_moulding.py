"""H4 mouldings (his limitations review V3, 9.4: "a.trim(<profile>, along=..., miter=True) ... bisector plane
mitering ... uniform real-world U ... fixing fczy [0,N] seam wrap + curved corners"): a profile run along a part's
outline with its corners mitred (a.moulding), carrying its STRIP - the studs along its own length, the share round
its section - so a trim sheet's band runs on round a curve and through every mitre (a.trim), never face by face."""

import json
import math
import os
import subprocess
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_sweep as W  # noqa: E402

BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
SQUARE = [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)]
SECTION = [(0, 0), (0.1, 0), (0.1, 0.05), (0, 0.05)]


class Strip(unittest.TestCase):
    def test_a_loop_runs_its_whole_length_and_closes_without_a_jump(self):
        verts, faces, st, length, perim = W.solid(SQUARE, SECTION, smooth=False, closed=True, up=(0, 0, 1),
                                                  strip=True)
        self.assertEqual(len(st), len(faces))
        self.assertTrue(all(x is not None for x in st))            # (a loop has no end caps)
        self.assertAlmostEqual(length, 6.0, places=6)               # (the path's own length: 2 + 1 + 2 + 1)
        top = max(s for f in st for s, _t in f.values())
        self.assertAlmostEqual(top, 6.0, places=6)                  # (the closing faces read the whole length)
        for f in st:   # every face runs forward along the path, never back across the loop
            ss = [s for s, _t in f.values()]
            self.assertLess(max(ss) - min(ss), 2.0 + 1e-6)
            ts = [t for _s, t in f.values()]
            self.assertTrue(0.0 <= min(ts) and max(ts) <= 1.0)
            self.assertLess(max(ts) - min(ts), 0.5)                  # (round the section, never back across it)
        self.assertAlmostEqual(perim, 0.3, places=6)                # (the section's way round)

    def test_the_same_point_reads_the_same_s_on_every_face_but_the_closing_one(self):
        _v, faces, st, length, _p = W.solid(SQUARE, SECTION, smooth=False, closed=True, up=(0, 0, 1), strip=True)
        seen = {}
        for f in st:
            for vi, (s, _t) in f.items():
                seen.setdefault(vi, set()).add(round(s, 6))
        jumps = [vi for vi, ss in seen.items() if len(ss) > 1]
        self.assertEqual(len(jumps), len(SECTION))                   # (the first station's points: 0 and the length)
        self.assertTrue(all(ss == {0.0, round(length, 6)} for vi, ss in seen.items() if vi in jumps))

    def test_an_open_path_caps_its_ends_and_the_old_call_is_unchanged(self):
        v1, f1 = W.solid([(0, 0, 0), (1, 0, 0), (1, 1, 0)], 0.1, smooth=False)
        v2, f2, st, _l, _p = W.solid([(0, 0, 0), (1, 0, 0), (1, 1, 0)], 0.1, smooth=False, strip=True)
        self.assertTrue(np.array_equal(v1, v2) and f1 == f2)
        self.assertEqual(sum(1 for x in st if x is None), 2)

    def test_a_curve_s_is_its_arc_length(self):
        arc = [(math.cos(t), math.sin(t), 0) for t in [math.pi * k / 32 for k in range(33)]]
        _v, _f, st, length, _p = W.solid(arc, 0.05, smooth=False, strip=True)
        self.assertAlmostEqual(length, math.pi, delta=0.01)


def build(script):
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                          os.path.join(ROOT, "kit", "selftest", "blender", script)],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200)
    return out.returncode, out.stdout, out.stderr


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class TheBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sheet = os.path.join(ROOT, os.environ.get("KIT_BUILD", "build"), "models", "_selftest_trim_sheet.manifest.json")
        if not os.path.isfile(sheet):
            build("build_trim_sheet.py")
        cls.code, out, err = build("build_moulding.py")
        i = out.rfind("MOULD ")
        cls.got = json.JSONDecoder().raw_decode(out[i + 6:])[0] if i >= 0 else None
        cls.log = out[-2000:] + err[-2000:]

    def test_built(self):
        self.assertEqual(self.code, 0, self.log)
        self.assertIsNotNone(self.got, self.log)

    def test_every_corner_mitred_on_its_bisector(self):
        self.assertEqual(self.got["mitred"], [self.got["section_points"]] * 4, self.got)

    def test_the_band_runs_on_round_the_frame_and_the_curve(self):
        g = self.got
        self.assertEqual(g["frame_jumps"], g["section_points"], g)   # (only the loop's one closing point)
        self.assertEqual(g["rail_jumps"], 0, g)
        self.assertAlmostEqual(g["frame_u"], 10.0 / 8.0, places=3)   # (3 x 2 panel: 10 studs on an 8-stud sheet)
        self.assertAlmostEqual(g["rail_u"], 0.6 * math.pi / 8.0, delta=0.002)
        self.assertTrue(g["v_in_band"])


if __name__ == "__main__":
    unittest.main()
