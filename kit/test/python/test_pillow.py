"""a.pillow() (kit/blender/rbx_pillow.py) — sculpted plate parts by inflation: every part comes out closed; a domed
disc is as thick as its profile says (2 x (core + h + top)) and holds clearly less than the slab of that thickness
(its faces are convex, not flat); a one-sided panel (with a hole, in the ZY plane) is core + h thick; a strip
thinner than 2 x edge gets a round top lower than the full profile; a zone 3 mm thicker shows in the thickness; a
part riding a domed host sits ON it (lifted to the dome's top less the sink), never floating. The fixture: kit/selftest/blender/
build_pillow.py."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import cad_check  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = cad_check.blender()
MANIFEST = os.path.join(REPO, "build", "models", "_selftest_pillow.manifest.json")


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Pillow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.isfile(MANIFEST):
            os.remove(MANIFEST)
        script = os.path.join(REPO, "kit", "selftest", "blender", "build_pillow.py")
        cls.run_ = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script, "--", "--no-preview"], cwd=REPO,
                                  capture_output=True, text=True, timeout=900)
        assert cls.run_.returncode == 0 and os.path.isfile(MANIFEST), (cls.run_.stderr or cls.run_.stdout)[-800:]
        with open(MANIFEST, encoding="utf-8") as fh:
            m = json.load(fh)
        cls.p = {c["part"]: c for c in m.get("facts", {}).get("pillow") or []}

    def test_closed(self):
        for part in ("Disc", "Panel", "Strip", "Zoned", "Rider", "Trim", "Overhang", "Rider2"):
            self.assertEqual(self.p[part]["open_edges"], 0, self.p[part])

    def test_disc_profile_and_convex_faces(self):
        d = self.p["Disc"]
        self.assertAlmostEqual(d["thickness_mm"], 2 * (1.0 + 3.0 + 0.5), delta=0.3)
        slab = d["outline_area_mm2"] * d["thickness_mm"]
        self.assertLess(d["volume_mm3"], 0.9 * slab, d)        # (convex faces: well under the slab ...)
        self.assertGreater(d["volume_mm3"], 0.6 * slab, d)     # (... but the shape, not a lens)

    def test_one_sided_panel(self):
        d = self.p["Panel"]
        self.assertAlmostEqual(d["thickness_mm"], 0.6 + 2.0, delta=0.1)
        self.assertEqual(d["holes"], 1)

    def test_thin_strip_gets_a_round_top(self):
        d = self.p["Strip"]
        self.assertLess(d["thickness_mm"], 2 * 2.0 - 0.2, d)   # (half-width 1.5 < edge 2.5: never the full h)
        self.assertGreater(d["thickness_mm"], 2.0, d)

    def test_a_zone_thickens_its_region(self):
        d = self.p["Zoned"]
        self.assertAlmostEqual(d["thickness_mm"], 2 * (3.0 + 1.0), delta=0.15)   # (not the default 2 x (1 + 1))
        self.assertEqual(d["zones"], [[3.0, 1.0]])

    def test_a_rider_sits_on_the_dome(self):
        r = self.p["Rider"]["ride"]
        self.assertEqual(r["host"], "Disc")
        self.assertEqual(r["hit_share"], 1.0)
        lo, hi = r["lift_mm"]
        self.assertGreater(lo, 4.0)    # (the disc's middle: 1 + 3 + a 0.5 crown = 4.5, less the 0.3 sink)
        self.assertLess(hi, 4.4)

    def test_a_rider_past_the_hosts_edge_is_not_left_behind(self):
        r = self.p["Overhang"]["ride"]
        self.assertLess(r["hit_share"], 0.9)        # (part of it runs off the disc ...)
        self.assertGreater(r["span_mm"][0], 0.5)    # (... and still sits out on the disc's rim, not at x = 0)

    def test_a_rider_over_several_hosts(self):
        r = self.p["Rider2"]["ride"]
        self.assertEqual(r["host"], ["Strip", "Disc"])
        self.assertEqual(r["hit_share"], 1.0)
        self.assertLess(r["span_mm"][1], -3.5)   # (on the disc's -Z face: its dome, not the strip, and not floating)


if __name__ == "__main__":
    unittest.main()
