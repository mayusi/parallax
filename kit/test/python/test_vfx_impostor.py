"""kit vfx impostor (kit/vfx/impostor.py; the V3 doc, VFX stage E.1): one GPU sim seen from a ring of 8 to 16 angles -
the view_variant specs gpusim renders with the sim, and the `views` table whose keys the stage's pickView reads as
degrees. Run: python -m pytest kit/test/python/test_vfx_impostor.py -q"""
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
import impostor as I  # noqa: E402

SIM = {"engine": "fx", "recipe": "gpu_smoke", "frames": 64, "grid": 8, "cell": 128, "params": {"res": [96, 96, 128]},
       "post": {"alpha": "coverage", "exposure": 1.2}}


class Ring(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        json.dump(SIM, open(os.path.join(self.dir, "puff.json"), "w"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_it(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = I.main([*argv, "--specs", self.dir])
        return code, json.loads(buf.getvalue().strip().splitlines()[-1])

    def test_eight_views_evenly_round_the_sim_itself_the_first(self):
        code, out = self.run_it("puff", "--angles", "8")
        self.assertEqual(code, 0, out["summary"])
        self.assertEqual(list(out["views"]), ["0", "45", "90", "135", "180", "225", "270", "315"])
        self.assertEqual(out["views"]["0"], "puff")
        self.assertEqual(len(out["written"]), 7)
        v = json.load(open(os.path.join(self.dir, "puff_v135.json")))
        self.assertEqual((v["recipe"], v["of"], v["yaw"]), ("view_variant", "puff", 135.0))
        for k in ("frames", "grid", "cell", "post"):
            self.assertEqual(v[k], SIM[k])                          # the same sheet as the sim: they swap frame for frame
        self.assertNotIn("params", v)

    def test_sixteen_views_keep_their_half_degrees(self):
        code, out = self.run_it("puff", "--angles", "16")
        self.assertEqual(code, 0)
        self.assertIn("22.5", out["views"])
        self.assertEqual(out["views"]["22.5"], "puff_v022_5")
        self.assertTrue(os.path.isfile(os.path.join(self.dir, "puff_v022_5.json")))
        # the stage reads a key as tonumber(key): every key is a number
        self.assertTrue(all(float(k) == float(k) for k in out["views"]))

    def test_a_tuned_view_is_kept_and_another_sims_file_never_written_over(self):
        self.run_it("puff", "--angles", "8")
        tuned = os.path.join(self.dir, "puff_v045.json")
        spec = json.load(open(tuned))
        spec["light"] = "left"
        json.dump(spec, open(tuned, "w"))
        code, out = self.run_it("puff", "--angles", "8")
        self.assertEqual(code, 0)
        self.assertIn("puff_v045", out["kept"])
        self.assertEqual(json.load(open(tuned))["light"], "left")
        json.dump({"recipe": "view_variant", "of": "other"}, open(os.path.join(self.dir, "puff_v090.json"), "w"))
        code, out = self.run_it("puff", "--angles", "8", "--force")
        self.assertEqual(code, 1)
        self.assertIn("not written over", out["summary"])

    def test_what_is_refused(self):
        for argv, words in ((["puff", "--angles", "4"], "8 to 16"), (["puff", "--angles", "17"], "8 to 16"),
                            (["nothing"], "no spec"), (["puff", "--light", "under"], "--light")):
            code, out = self.run_it(*argv)
            self.assertEqual(code, 1)
            self.assertIn(words, out["summary"])
        json.dump({"engine": "fx", "recipe": "comp"}, open(os.path.join(self.dir, "flat.json"), "w"))
        code, out = self.run_it("flat")
        self.assertEqual(code, 1)
        self.assertIn("not a GPU sim", out["summary"])


if __name__ == "__main__":
    unittest.main()
