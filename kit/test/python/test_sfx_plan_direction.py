"""`kit sfx plan`'s DIRECTION stage (LIMITATIONS_FIXES_V4 SFX-X B, "kit sfx plan omits the direction gate"): every
set is shown the stage - a set that names no direction doc is told to make one and have the owner pick it, FIRST
(before its references and design); a set that names one is read from its doc as before."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
PLAN = os.path.join(ROOT, "kit", "audio", "plan.py")


def plan(cwd, name):
    env = dict(os.environ, KIT_GAME="none")
    r = subprocess.run([sys.executable, PLAN, name], cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout.strip().splitlines()[-1])


class DirectionStage(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kit_sfx_plan_")
        os.makedirs(os.path.join(self.dir, "assets", "sounds", "sets"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, name, data):
        with open(os.path.join(self.dir, "assets", "sounds", "sets", f"{name}.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def test_a_set_with_no_direction_is_told_to_pick_one_first(self):
        self.write("rain_hits", {"members": {"rain_a": {}}})
        d = plan(self.dir, "rain_hits")
        self.assertEqual(d["stages"][0]["key"], "direction")
        self.assertEqual(d["stages"][0]["status"], "to do")
        self.assertEqual(d["next"], "direction")
        self.assertEqual(d["next_action"], "lune run kit sfx direction RainHits --new")
        self.assertIn("names no direction doc", d["stages"][0]["missing"][0])

    def test_a_named_direction_whose_doc_is_missing_is_still_to_do(self):
        self.write("rain_hits", {"members": {"rain_a": {}}, "direction": "Monsoon"})
        d = plan(self.dir, "rain_hits")
        self.assertEqual(d["stages"][0]["key"], "direction")
        self.assertEqual(d["stages"][0]["status"], "to do")
        self.assertEqual(d["next_action"], "lune run kit sfx direction Monsoon --new")


if __name__ == "__main__":
    unittest.main()
