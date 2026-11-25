"""A part broken beforehand, through REAL builds (kit/selftest/blender/build_fracture.py and its twin; the 3D methods
audit, stage O): the whole stays, its pieces are closed, fit (their volumes add up to it), are baked as if alone
(not in the whole's shadow) and are named in the manifest; a part that is not closed stops the build."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import cad_check  # noqa: E402

BLENDER = cad_check.blender()
OUT = os.path.join("build", "_test_fracture_build")


def run(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                          cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                          errors="replace")


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = run("build_fracture.py")
        got = next((x for x in cls.good.stdout.splitlines() if x.startswith("FRACTURE ")), None)
        assert got, (cls.good.stderr or cls.good.stdout)[-800:]
        cls.at = json.loads(got[9:])
        line = next(x for x in reversed(cls.good.stdout.splitlines()) if x.startswith("{") and '"status"' in x)
        cls.v = json.loads(line)   # (strict: the kit reads this line the same way)
        cls.open = run("build_fracture_open.py")

    def test_the_whole_stays_and_its_pieces_fit(self):
        self.assertEqual(self.v["status"], "pass", self.v["summary"][:300])
        f = self.at["fracture"]["Crate"]
        self.assertEqual(f["whole"], "crate")
        self.assertEqual(f["groups"], ["crate_p1", "crate_p2", "crate_p3", "crate_p4", "crate_p5"])
        self.assertAlmostEqual(f["held"], 1.0, delta=0.02)               # their volumes add up to the crate's
        self.assertEqual(self.at["groups"],
                         ["crate", "crate_p1", "crate_p2", "crate_p3", "crate_p4", "crate_p5", "main"])
        # a paint said for the crate is on its pieces too (the review: they swapped in unpainted)
        painted = self.v["facts"]["paint"]
        self.assertEqual(sorted(painted), ["crate", "crate_p1", "crate_p2", "crate_p3", "crate_p4", "crate_p5"])
        self.assertEqual([c["name"] for c in self.v["design"] if c["name"] == "fracture"], [])
        self.assertIn("broken beforehand: Crate in 5 pieces", self.v["summary"])

    def test_every_piece_is_closed_and_none_is_said_hidden(self):
        for g in self.at["fracture"]["Crate"]["groups"]:
            failed = [c["name"] for c in self.v["groups"][g]["checks"] if not c["ok"]]
            self.assertNotIn("manifold", failed, g)
            self.assertNotIn("hidden_faces", failed, g)                  # (hidden until it breaks: by design)

    def test_a_piece_is_baked_as_if_alone_not_in_the_wholes_shadow(self):
        import numpy as np  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415

        def luma(group):
            rel = self.v["groups"][group].get("textures", {}).get("color") if "textures" in self.v["groups"][group] \
                else None
            man = json.load(open(os.path.join(ROOT, OUT, "models", "_selftest_fracture.manifest.json"),
                                 encoding="utf-8"))
            rel = man["groups"][group]["textures"]["color"]
            px = np.asarray(Image.open(os.path.join(ROOT, rel) if not os.path.isabs(rel) else rel).convert("RGB"),
                            float)
            lit = px.mean(axis=2)
            return float(np.median(lit[lit > 8]))                        # (the map's covered texels)

        whole = luma("crate")
        for g in ("crate_p1", "crate_p3", "crate_p5"):
            self.assertGreater(luma(g), 0.7 * whole, g)                  # (in the whole's shadow it is near black)

    def test_a_part_that_is_not_closed_stops_the_build(self):
        self.assertNotEqual(self.open.returncode, 0)
        self.assertIn('fracture: "Crate" is not one closed solid', self.open.stderr + self.open.stdout)


if __name__ == "__main__":
    unittest.main()
