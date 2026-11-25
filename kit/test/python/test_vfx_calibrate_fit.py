"""kit/vfx/calibrate.py fit (LIMITATIONS_FIXES_V4 Phase 1 item 3: the player's CAL from measurements, not typed): one
measurement per judging sky -> each multiplier = the CAL the player recorded with / the ratio it measured (player /
booth) in its phase, per sky; across skies the least-squares fit in log space. Refused while any asked sky has no
measurement, or a phase's ratio is unusable."""

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
CAL = os.path.join(ROOT, "kit", "vfx", "calibrate.py")


def run(cwd, *args):
    r = subprocess.run([sys.executable, CAL, *args], cwd=cwd, capture_output=True, text=True, timeout=60)
    return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])


class CalibrateFit(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kit_cal_fit_")
        os.makedirs(os.path.join(self.dir, "build", "vfx", "booth"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def measure(self, sky, charge, hit, base, cal=None):
        data = {"name": "fx", "sky": sky, "phases": {"charge": {"ratio": charge}, "hit": {"ratio": hit},
                                                       "base": {"ratio": base}, "tail": None}}
        if cal:
            data["cal"] = cal
        with open(os.path.join(self.dir, "build", "vfx", "booth", f"fx_calibration_{sky}.json"), "w") as fh:
            json.dump(data, fh)

    def test_a_missing_sky_is_refused_and_nothing_written(self):
        self.measure("night", 1.0, 1.0, 1.0)
        code, v = run(self.dir, "fit", "fx")
        self.assertEqual(code, 1)
        self.assertIn("no measurement for day, overcast, sunset", v["summary"])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "assets", "effects", "_calibrated.json")))

    def test_each_sky_meets_the_booth_and_all_is_the_log_space_fit(self):
        # night: the player twice as bright in the charge (sprite halves), day: half as bright (sprite doubles)
        self.measure("night", 2.0, 1.0, 1.0)
        self.measure("day", 0.5, 1.0, 1.0)
        self.measure("overcast", 1.0, 1.4, 1.0, cal={"sprite": 0.4, "beam": 0.7, "light": 18})
        self.measure("sunset", 1.0, 1.0, 0.9, cal={"light": 20})
        code, v = run(self.dir, "fit", "fx")
        self.assertEqual(code, 0, v)
        with open(os.path.join(self.dir, "assets", "effects", "_calibrated.json")) as fh:
            out = json.load(fh)
        self.assertAlmostEqual(out["skies"]["night"]["sprite"], 0.2, places=4)
        self.assertAlmostEqual(out["skies"]["day"]["sprite"], 0.8, places=4)
        self.assertAlmostEqual(out["skies"]["overcast"]["beam"], 0.5, places=4)
        self.assertAlmostEqual(out["skies"]["sunset"]["light"], 20 / 0.9, places=3)   # (recorded with its own CAL)
        self.assertAlmostEqual(out["all"]["sprite"], math.exp((math.log(0.2) + math.log(0.8) + 2 * math.log(0.4)) / 4),
                               places=4)   # (a 2x and a 0.5x error cancel: 0.4 again)

    def test_an_unusable_ratio_is_refused(self):
        for sky in ("night", "day", "overcast"):
            self.measure(sky, 1.0, 1.0, 1.0)
        self.measure("sunset", 1.0, 0.0, 1.0)   # (a black recording)
        code, v = run(self.dir, "fit", "fx")
        self.assertEqual(code, 1)
        self.assertIn("sunset: no usable hit ratio", v["summary"])


if __name__ == "__main__":
    unittest.main()
