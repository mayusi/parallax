"""kit/vfx/gpusim.py named profiles - "Raise gpusim.py to 256^3-384^3 (vorticity >= 2)" (LIMITATIONS_FIXES_V4 3.4 step 4)
WITHOUT moving a judged bake. What is proven: a spec with no profile is simulated with its own params dict untouched
and the old defaults table IS the code's fallbacks (a small sim with every default written out is the same, bit for
bit, as one with none - so the defaults did not move); "profile": "hero" gives a 256 x 256 x 320 grid, vorticity 2,
speeds scaled to the grid, the spec's own keys winning; a hero under the bar (or an unknown profile) is refused before
anything runs; --new writes a hero spec and never overwrites one.
(The old-vs-new proof on a real judged sheet, 2026-11-20: assets/textures/gpu_smoke + its 3 lit variants baked by the
HEAD gpusim and by this one: the same sha256 over every frame, 1b81788b...6688a3.)
Run: python -m pytest kit/test/python/test_vfx_gpusim_profile.py -q"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import gpusim as G  # noqa: E402


class OldDefaults(unittest.TestCase):
    def test_no_profile_is_the_spec_own_dict(self):
        spec = {"params": {"res": [96, 96, 128], "vorticity": 0.9}}
        self.assertIs(G.params_of(spec), spec["params"])
        self.assertEqual(G.profile_problems(spec), [])

    def test_the_old_defaults_table_is_the_code_fallbacks(self):
        import torch
        small = {"res": [20, 20, 24]}
        bare = {"recipe": "gpu_smoke", "frames": 3, "seed": 5, "params": dict(small, steps=6)}
        said = {"recipe": "gpu_smoke", "frames": 3, "seed": 5, "params": dict(G.OLD_DEFAULTS, steps=6, **small)}
        a = G.simulate(bare, keep=True)
        b = G.simulate(said, keep=True)
        self.assertEqual(len(a), len(b))
        for fa, fb in zip(a, b):
            for x, y in zip(fa, fb):
                self.assertTrue(torch.equal(x, y))


class Hero(unittest.TestCase):
    def test_hero_defaults(self):
        p = G.params_of({"profile": "hero", "params": {}})
        self.assertEqual(p["res"], [256, 256, 320])
        self.assertGreaterEqual(p["vorticity"], 2.0)
        self.assertEqual(p["velocity"], G.OLD_DEFAULTS["velocity"] * 2)
        self.assertEqual(p["max_speed"], G.OLD_DEFAULTS["max_speed"] * 2)
        self.assertEqual(G.profile_problems({"profile": "hero", "params": {}}), [])

    def test_the_spec_own_keys_win(self):
        p = G.params_of({"profile": "hero", "params": {"velocity": 0.9, "res": [320, 320, 384]}})
        self.assertEqual(p["velocity"], 0.9)
        self.assertEqual(p["res"], [320, 320, 384])
        self.assertEqual(p["vorticity"], 2.0)

    def test_a_hero_under_the_bar_is_refused(self):
        bad = G.profile_problems({"profile": "hero", "params": {"res": [128, 128, 160], "vorticity": 0.7}})
        self.assertEqual(len(bad), 2)
        self.assertIn("256..384 cells a side", bad[0])
        self.assertIn("vorticity is 2.0 or more", bad[1])
        self.assertIn("not one of", G.profile_problems({"profile": "huge"})[0])

    def test_refused_before_it_runs(self):
        d = tempfile.mkdtemp(prefix="gpusim_profile_")
        try:
            with open(os.path.join(d, "small_hero.json"), "w", encoding="utf-8") as fh:
                json.dump({"engine": "fx", "recipe": "gpu_smoke", "profile": "hero", "frames": 4,
                           "params": {"res": [64, 64, 64]}}, fh)
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                code = G.main(["--specs", d, "--out", os.path.join(d, "out"), "--force"])
            line = json.loads(said.getvalue().strip().splitlines()[-1])
            self.assertEqual(code, 1)
            self.assertIn("256..384 cells a side", line["summary"])
            self.assertFalse(os.path.isdir(os.path.join(d, "out", "small_hero")))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_new_writes_a_hero_spec_once(self):
        d = tempfile.mkdtemp(prefix="gpusim_new_")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(G.main(["--specs", d, "--new", "cloud_a"]), 0)
                self.assertEqual(G.main(["--specs", d, "--new", "cloud_a"]), 1)   # never over an existing spec
                self.assertEqual(G.main(["--specs", d, "--new", "Bad-Name"]), 1)
            with open(os.path.join(d, "cloud_a.json"), encoding="utf-8") as fh:
                spec = json.load(fh)
            self.assertEqual(spec["profile"], "hero")
            self.assertEqual(G.profile_problems(spec), [])
            self.assertGreaterEqual(min(G.params_of(spec)["res"]), 256)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
