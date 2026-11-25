"""test_world_sinks.py - RIVERS THAT DRAIN INSIDE THE LAND (kit/world/terrain.py --sink; LIMITATIONS_FIXES_V3.md
stage E.1: "add sinks - internal drainage base levels (lakes / sea / valleys inside the playable basin) so
stream-power erosion carves interior vales instead of just the border"). The solver's only base level was the map's
edge: every river ran to the rim, so the rim took the cut (terrain-route-evidence: 60-88 % of the relief carved in the
outer 128 studs). A sink is base level inside the land; water that reaches it leaves there.
Held here: on a land that falls to its rim, a sink in the middle gathers the water of the land round it and the land
round it is carved toward it (and not without it); the flag is read, refused when wrong, recorded in the heightmap's
recipe and replayed by kit world check's route proof (a land whose recorded sink was dropped does not come back).
Not claimed: that a land drained this way looks right - that is a built world, looked at."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TERRAIN = os.path.join(HERE, "..", "..", "world", "terrain.py")
_spec = importlib.util.spec_from_file_location("kit_world_terrain_sinks", TERRAIN)
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)
_cspec = importlib.util.spec_from_file_location("kit_world_check_sinks", os.path.join(HERE, "..", "..", "world", "worldcheck.py"))
C = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(C)

N, CELL = 65, 4
MID = (N - 1) / 2
XS = (np.arange(N) - MID) * CELL
X, Z = np.meshgrid(XS, XS, indexing="ij")
DOME = 80.0 - 0.25 * np.sqrt(X ** 2 + Z ** 2)  # (high in the middle, falling to the rim: every river ran outward)


class Solver(unittest.TestCase):
    def test_a_sink_gathers_the_water_round_it_and_the_land_is_carved_toward_it(self):
        base = T.sink_mask([(40.0, 0.0, 10.0)], N, CELL)
        self.assertTrue(base[int(MID + 10), int(MID)])
        self.assertFalse(base[int(MID), int(MID)])
        plain, area0 = T.stream_power(DOME.copy(), CELL, 30, k=0.02)
        low = T.sink_apply(DOME.copy(), base)
        self.assertTrue(np.all(low[base] == DOME.min()) and np.array_equal(low[~base], DOME[~base]))
        sunk, area1 = T.stream_power(low, CELL, 30, k=0.02, base=base)
        # the water of the land round the sink ends there (a sink's cells pass nothing on: what they hold is the land
        # drained into them) - many times the sink's own cells
        self.assertGreater(float(area1[base].sum()), 4 * float(base.sum()))
        # and the slope from the summit down to the sink is cut down toward it, deeper than without the sink
        uphill = (X > 4) & (X < 28) & (np.abs(Z) < 12)
        self.assertGreater(float((plain - sunk)[uphill].mean()), 1.0)
        # what lies far from it (the far side of the summit) is the same land either way, near enough
        far = X < -60
        self.assertLess(float(np.abs(plain - sunk)[far].mean()), 0.5)
        # no sink: exactly the old solver (the same numbers)
        again, _ = T.stream_power(DOME.copy(), CELL, 30, k=0.02, base=None)
        self.assertTrue(np.array_equal(again, plain))

    def test_the_two_scale_solver_drains_to_a_small_sink_too(self):
        base = T.sink_mask([(40.0, 0.0, 6.0)], N, CELL)  # (smaller than one coarse cell)
        plain, _ = T.stream_multiscale(DOME.copy(), CELL, 20, 0.02)
        sunk, _ = T.stream_multiscale(T.sink_apply(DOME.copy(), base), CELL, 20, 0.02, base=base)
        # (smaller than a coarse cell: the fine pass alone drains to it - cut deeper next to it, and the slope above
        # nowhere left higher than with no sink; a coarse cell laid at base level for it had cut LESS)
        near = (X > 24) & (X < 34) & (np.abs(Z) < 12) & ~base
        self.assertGreater(float((plain - sunk)[near].mean()), 1.0)
        uphill = (X > 4) & (X < 34) & (np.abs(Z) < 12) & ~base
        self.assertGreater(float((plain - sunk)[uphill].min()), -0.5)

    def test_the_flag_is_read_or_refused(self):
        self.assertEqual(T.sink_config("40,-20,12"), ((40.0, -20.0, 12.0), None))
        for bad in ("40,20", "a,b,c", "1,2,0", "1,2,-3", "1,2,nan"):
            one, why = T.sink_config(bad)
            self.assertIsNone(one, bad)
            self.assertIn("--sink", why)
        self.assertIsNone(T.sink_mask([], N, CELL))
        self.assertIsNone(T.sink_mask([(5000.0, 0.0, 4.0)], N, CELL))  # (off the map: no sink)


class CommandLine(unittest.TestCase):
    ARGS = ["--size", "256", "--step", "4", "--seed", "7", "--relief", "40", "--erosion", "800", "--thermal", "6",
            "--stream", "20"]

    def run_terrain(self, out, *flags):
        return subprocess.run([sys.executable, TERRAIN, out, *self.ARGS, *flags], capture_output=True, text=True, timeout=300)

    def test_recorded_and_replayed_by_the_route_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain, sunk = os.path.join(tmp, "plain.hm.json"), os.path.join(tmp, "sunk.hm.json")
            self.assertEqual(self.run_terrain(plain).returncode, 0)
            res = self.run_terrain(sunk, "--sink", "30,-20,16")
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            a, b = (json.load(open(p, encoding="utf-8")) for p in (plain, sunk))
            self.assertEqual(b["options"]["sink"], ["30,-20,16"])
            self.assertNotIn("sink", a["options"])
            self.assertNotEqual(a["heights"], b["heights"])
            proof = C._remake(b, b["options"], None, [tmp], sunk, route="rivers")
            self.assertTrue(proof["ok"], proof)
            self.assertLess(proof["max_dh"], 0.02)
            # the recipe that lost its sink does not come back
            lost = dict(b)
            lost["options"] = {k: v for k, v in b["options"].items() if k != "sink"}
            self.assertFalse(C._remake(lost, lost["options"], None, [tmp], sunk, route="rivers")["ok"])
            for junk in ("30,-20,16", [5], None if False else {"x": 1}):
                bad = dict(b)
                bad["options"] = dict(b["options"], sink=junk)
                proof = C._remake(bad, bad["options"], None, [tmp], sunk, route="rivers")
                self.assertFalse(proof["ok"])
                self.assertIn("recorded sinks are not a list of texts", proof["why"])
            # a wrong flag is refused, said
            res = self.run_terrain(os.path.join(tmp, "x.hm.json"), "--sink", "30,-20")
            self.assertEqual(res.returncode, 1)
            self.assertIn("--sink", res.stdout)


if __name__ == "__main__":
    unittest.main()
