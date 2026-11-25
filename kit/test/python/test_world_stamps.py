"""test_world_stamps.py - TERRAIN STAMPS (kit/world/terrain.py stamp / stamp_config; the owner's method list:
"Terrain stamping", "Terrain sculpting", "Heightmap terrain editing"): a land form from a small library, placed by
name, recorded in the land's recipe and re-made by the route proof.
Each form is held to its own shape on a level plain; then the command line: a stamp is in the recipe, the same
recipe gives the same land, and kit world check's route proof re-makes a stamped land from it.
Not claimed here: that a stamped land looks right. That is a built world, looked at."""
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
_spec = importlib.util.spec_from_file_location("kit_world_terrain_stamps", TERRAIN)
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)
_cspec = importlib.util.spec_from_file_location("kit_world_check_stamps", os.path.join(HERE, "..", "..", "world", "worldcheck.py"))
C = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(C)

N, CELL = 129, 4
MID = (N - 1) / 2
XS = (np.arange(N) - MID) * CELL  # (a stamp's x, z are studs from the map's middle)
X, Z = np.meshgrid(XS, XS, indexing="ij")
PLAIN = np.full((N, N), 50.0)


def laid(text, h=PLAIN):
    s, problem = T.stamp_config(text)
    assert problem is None, problem
    return T.stamp(h, CELL, s) - h  # (what the stamp changed)


def at(d, x, z):
    return float(d[int(round(x / CELL + MID)), int(round(z / CELL + MID))])


class Config(unittest.TestCase):
    def test_a_stamp_is_read_and_what_is_wrong_is_said(self):
        s, problem = T.stamp_config("crater, 120, -40, 60, 25")
        self.assertIsNone(problem)
        self.assertEqual((s["kind"], s["x"], s["z"], s["radius"], s["height"], s["turn"], s["worked"]),
                         ("crater", 120.0, -40.0, 60.0, 25.0, 0.0, False))
        s, _ = T.stamp_config("ridge,0,0,100,30,45,worked")
        self.assertEqual((s["turn"], s["worked"]), (45.0, True))
        self.assertTrue(T.stamp_config("mesa,0,0,100,30,worked")[0]["worked"])
        for bad, text in (("volcano,0,0,60,20", "the stamps are crater, mesa, cone, ridge, valley, mound, pit"),
                          ("crater,0,0,60", "is kind,x,z,radius,height"), ("crater,a,0,60,20", "are numbers"),
                          ("crater,0,0,4,20", "radius is 8 to 4096"), ("crater,0,0,60,0", "height (or depth) is over 0"),
                          ("crater,0,0,60,-5", "height (or depth) is over 0"), ("crater,0,0,60,20,0,now", "is kind,x,z"),
                          ("crater,0,0,nan,20", "are numbers"), ("crater,inf,0,60,20", "are numbers"),
                          ("crater,0,0,5000,20", "radius is 8 to 4096"), ("crater,0,0,60,2500", "up to 2000"),
                          ("crater,0,0,60,20,fresh", "are numbers")):
            s, problem = T.stamp_config(bad)
            self.assertIsNone(s, bad)
            self.assertIn(text, problem, bad)

    def test_a_stamp_is_written_back_as_it_was_read(self):
        for text in ("crater,120,-40,60,25", "ridge,0,0.5,100,30,45,worked", "mesa,-7.25,3,64,12,worked"):
            s, _ = T.stamp_config(text)
            again, problem = T.stamp_config(T.stamp_text(s))
            self.assertIsNone(problem)
            self.assertEqual(again, s)


class Forms(unittest.TestCase):
    def test_no_stamp_changes_anything_outside_its_radius(self):
        d0 = np.sqrt((X - 20) ** 2 + (Z + 40) ** 2)
        for kind in T.STAMPS:
            d = laid(f"{kind},20,-40,80,30,30")
            self.assertEqual(float(np.abs(d[d0 > 80]).max()), 0.0, kind)
            self.assertGreater(float(np.abs(d[d0 < 40]).max()), 5.0, kind)
            self.assertTrue(np.isfinite(d).all(), kind)

    def test_mound_and_pit(self):
        up, down = laid("mound,0,0,80,30"), laid("pit,0,0,80,30")
        self.assertAlmostEqual(at(up, 0, 0), 30.0, places=6)
        self.assertAlmostEqual(at(up, 40, 0), 15.0, places=6)  # (half way out: half)
        self.assertAlmostEqual(float(up.max()), 30.0, places=6)
        self.assertGreaterEqual(float(up.min()), 0.0)
        self.assertTrue(np.allclose(down, -up))
        self.assertGreater(at(up, 20, 0), at(up, 40, 0))
        self.assertGreater(at(up, 40, 0), at(up, 60, 0))

    def test_crater_a_bowl_with_a_raised_rim(self):
        d = laid("crater,0,0,80,30")
        self.assertAlmostEqual(at(d, 0, 0), -30.0, places=6)  # (its floor: the depth)
        self.assertAlmostEqual(at(d, 64, 0), 7.5, places=6)  # (the rim at 0.8 of the radius: a quarter of the depth)
        self.assertAlmostEqual(float(d.max()), 7.5, places=6)
        self.assertLess(at(d, 28, 0), -10)  # (still in the bowl half way to the rim's foot)
        self.assertAlmostEqual(at(d, 80, 0), 0.0, places=6)  # (back to the land at the edge)
        # round: the same along z and on the diagonal
        self.assertAlmostEqual(at(d, 0, 64), 7.5, places=6)

    def test_mesa_one_flat_top_with_steep_sides(self):
        rolling = 50 + 6 * np.sin(X / 37) + 4 * np.cos(Z / 23)
        d = laid("mesa,0,0,100,40", rolling)
        top = np.sqrt(X * X + Z * Z) <= 70 - 1e-9
        after = rolling + d
        self.assertLess(float(after[top].max() - after[top].min()), 1e-6)  # (ONE level, whatever the land under it)
        self.assertAlmostEqual(float(after[top].mean()), float(np.median(rolling[top])) + 40, places=6)
        self.assertAlmostEqual(at(d, 100, 0), 0.0, places=5)  # (meets the land at its edge)
        # its side: from the top to the land within 30 studs
        self.assertGreater(float(after[int(MID), int(MID)]) - float(after[int(MID + 96 / CELL), int(MID)]), 30)

    def test_a_mesa_never_lowers_the_land_and_a_small_one_reads_its_own_place(self):
        # on a hillside the ground that stands higher than the mesa's top stays (it cut a notch into the uphill side)
        hill = 100 + 1.0 * X
        d = laid("mesa,0,0,80,20", hill)
        self.assertGreaterEqual(float(d.min()), 0.0)
        self.assertGreater(at(d, -50, 0), 40)  # (the downhill side is lifted to the top)
        self.assertEqual(at(d, 60, 0), 0.0)  # (uphill the land is already over the top: left as it is)
        # a mesa smaller than the land's cells takes its level from the cell nearest ITS middle (it read the map's
        # middle: a 90-stud hole)
        coarse = np.arange(65) * 8.0 - 256
        CX, _ = np.meshgrid(coarse, coarse, indexing="ij")
        land = 200 + 0.5 * CX
        s, _ = T.stamp_config("mesa,204,204,8,10")
        after = T.stamp(land, 8, s)
        self.assertGreaterEqual(float((after - land).min()), 0.0)
        self.assertLessEqual(float((after - land).max()), 10.0 + 4.0)  # (10 over its own ground, a cell's slope more)
        self.assertGreater(float((after - land).max()), 6.0)  # (and it IS a mesa there: the ground is lifted)

    def test_cone_straight_flanks_a_rim_at_full_height_and_a_crater_in_its_top(self):
        d = laid("cone,0,0,100,50")
        self.assertAlmostEqual(at(d, 20, 0), 50.0, places=6)  # (the rim, a fifth of the radius out)
        self.assertAlmostEqual(float(d.max()), 50.0, places=6)
        self.assertAlmostEqual(at(d, 0, 0), 37.5, places=6)  # (the crater: a quarter of the height deep)
        self.assertAlmostEqual(at(d, 60, 0), 25.0, places=6)  # (half way down a straight flank)
        self.assertAlmostEqual(at(d, 28, 0), 45.0, places=6)  # (a tenth of the way down: a tenth of the height)
        self.assertAlmostEqual(at(d, 40, 0) - at(d, 60, 0), at(d, 60, 0) - at(d, 80, 0), places=6)  # (straight)
        self.assertAlmostEqual(at(d, 100, 0), 0.0, places=6)

    def test_ridge_and_valley_run_along_their_turn(self):
        along_z = laid("ridge,0,0,120,30")  # (turn 0: along z)
        self.assertAlmostEqual(at(along_z, 0, 0), 30.0, places=6)
        self.assertAlmostEqual(at(along_z, 0, 60), 30.0, places=6)  # (its crest holds 0.6 of the way along)
        self.assertAlmostEqual(at(along_z, 60, 0), 0.0, places=6)  # (across: a third of the radius wide - 40 studs)
        self.assertAlmostEqual(at(along_z, 20, 0), 15.0, places=6)  # (half way across its flank)
        self.assertLess(at(along_z, 0, 108), 15.0)  # (its end falls away)
        along_x = laid("ridge,0,0,120,30,90")
        self.assertAlmostEqual(at(along_x, 60, 0), 30.0, places=6)
        self.assertAlmostEqual(at(along_x, 0, 60), 0.0, places=6)
        self.assertTrue(np.allclose(along_x, along_z.T))  # (a quarter turn: the same form, x and z changed places)
        self.assertTrue(np.allclose(laid("valley,0,0,120,30,90"), -along_x))
        # a diagonal ridge: its crest on the diagonal, nothing on the other one
        diag = laid("ridge,0,0,120,30,45")
        self.assertGreater(at(diag, 40, 40), 29.0)
        self.assertAlmostEqual(at(diag, 40, -40), 0.0, places=6)

    def test_stamps_add_up_and_a_place_off_the_middle_is_where_it_says(self):
        d = laid("mound,100,-60,40,20")
        self.assertAlmostEqual(at(d, 100, -60), 20.0, places=6)
        self.assertAlmostEqual(at(d, 0, 0), 0.0, places=6)
        s1, _ = T.stamp_config("mound,0,0,80,30")
        s2, _ = T.stamp_config("pit,40,0,40,10")
        both = T.stamp(T.stamp(PLAIN, CELL, s1), CELL, s2) - PLAIN
        self.assertTrue(np.allclose(both, laid("mound,0,0,80,30") + laid("pit,40,0,40,10")))


class CommandLine(unittest.TestCase):
    ARGS = ["--size", "256", "--step", "4", "--seed", "7", "--relief", "40", "--erosion", "800", "--thermal", "6",
            "--stream", "20"]

    def run_terrain(self, out, *flags):
        return subprocess.run([sys.executable, TERRAIN, out, *self.ARGS, *flags], capture_output=True, text=True, timeout=300)

    def load(self, path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def grid(self, hm):
        n = hm["nx"]
        return np.array(hm["heights"]).reshape(n, n), (n - 1) / 2

    def test_a_stamp_is_a_local_edit_and_a_worked_one_makes_another_land_and_says_so_in_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain, local, worked = (os.path.join(tmp, f"{k}.hm.json") for k in ("plain", "local", "worked"))
            self.assertEqual(self.run_terrain(plain).returncode, 0)
            self.assertEqual(self.run_terrain(local, "--stamp", "crater,60,50,40,18").returncode, 0)
            a, b = self.load(plain), self.load(local)
            ha, c = self.grid(a)
            hb, _ = self.grid(b)
            n = a["nx"]
            xs = (np.arange(n) - c) * 4
            GX, GZ = np.meshgrid(xs, xs, indexing="ij")
            away = np.sqrt((GX - 60) ** 2 + (GZ - 50) ** 2) > 40
            # outside its radius NOT ONE height of the land moved (a fresh reader: a 6-stud bump laid before the
            # erosion moved 99 % of the map, by up to 93 studs)
            self.assertEqual(float(np.abs(hb - ha)[away].max()), 0.0)
            i, j = int(60 / 4 + c), int(50 / 4 + c)
            self.assertAlmostEqual(float(hb[i, j] - ha[i, j]), -18.0, delta=0.3)  # (its floor: 18 under the land, once; the cell is 2 studs off its middle)
            self.assertAlmostEqual(float(hb[int(92 / 4 + c), j] - ha[int(92 / 4 + c), j]), 4.5, delta=0.3)  # (its rim)
            self.assertEqual(a["relief"], b["relief"])
            self.assertEqual(b["options"]["stamp"], ["crater,60.0,50.0,40.0,18.0,0.0"])
            # "worked": the erosion works on it - and the whole land is another land (said by the word)
            self.assertEqual(self.run_terrain(worked, "--stamp", "mesa,-60,-60,50,25,worked").returncode, 0)
            w = self.load(worked)
            hw, _ = self.grid(w)
            self.assertTrue(w["options"]["stamp"][0].endswith(",worked"))
            far = np.sqrt((GX + 60) ** 2 + (GZ + 60) ** 2) > 100
            self.assertGreater(float((np.abs(hw - ha)[far] > 0.5).mean()), 0.2)
            rise = float(hw[int(-60 / 4 + c), int(-60 / 4 + c)] - ha[int(-60 / 4 + c), int(-60 / 4 + c)])
            self.assertGreater(rise, 8)  # (it stands)
            top = hw[np.sqrt((GX + 60) ** 2 + (GZ + 60) ** 2) < 30]
            self.assertGreater(float(top.max() - top.min()), 0.5)  # (worn by the erosion: no longer one flat level)

    def test_the_route_proof_re_makes_a_stamped_land_from_its_recipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            stamped = os.path.join(tmp, "stamped.hm.json")
            flags = ("--stamp", "mesa,-60,-60,50,25,worked", "--stamp", "crater,60,50,40,18")
            res = self.run_terrain(stamped, *flags)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            b = self.load(stamped)
            self.assertEqual(len(b["options"]["stamp"]), 2)
            # the same recipe: the same land
            again = os.path.join(tmp, "again.hm.json")
            self.assertEqual(self.run_terrain(again, *flags).returncode, 0)
            self.assertEqual(self.load(again)["heights"], b["heights"])
            proof = C._remake(b, b["options"], None, [tmp], stamped, route="rivers")
            self.assertTrue(proof["ok"], proof)
            self.assertLess(proof["max_dh"], 0.02)
            # a land whose recipe LOST a stamp (typed out by hand) does not come back - either kind
            for drop in (0, 1):
                lost = dict(b)
                lost["options"] = dict(b["options"], stamp=[st for k, st in enumerate(b["options"]["stamp"]) if k != drop])
                proof = C._remake(lost, lost["options"], None, [tmp], stamped, route="rivers")
                self.assertFalse(proof["ok"], drop)
            # recorded stamps that are no list of texts are said as that (not as "flats", not a crash)
            for junk in (["mound,0,0,40,10", None], "mound,0,0,40,10", {"kind": "mound"}, 5):
                bad = dict(b)
                bad["options"] = dict(b["options"], stamp=junk)
                proof = C._remake(bad, bad["options"], None, [tmp], stamped, route="rivers")
                self.assertFalse(proof["ok"])
                self.assertIn("recorded stamps are not a list of texts", proof["why"])

    def test_a_tall_form_laid_on_the_finished_land_does_not_thin_the_rivers_share(self):
        # (the river step's cut is measured against the land's relief: a 600-stud cone laid afterwards made the proof
        # call a genuine river land "a token stream")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "cone.hm.json")
            res = self.run_terrain(out, "--stamp", "cone,0,0,100,600")
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            b = self.load(out)
            self.assertGreater(b["relief"], 500)
            proof = C._remake(b, b["options"], None, [tmp], out, route="rivers")
            self.assertTrue(proof["ok"], proof)
            self.assertNotIn("fault", {k: v for k, v in proof.items() if v})
            # ... and what the summary calls the erosion's work is the erosion's, not the cone's
            self.assertIn("erosion moved", res.stdout)
            moved = float(res.stdout.split("erosion moved ")[1].split(" ")[0])
            plain = os.path.join(tmp, "plain.hm.json")
            base = self.run_terrain(plain)
            self.assertAlmostEqual(moved, float(base.stdout.split("erosion moved ")[1].split(" ")[0]), delta=0.05)

    def test_what_cannot_be_laid_stops_the_command_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "bad.hm.json")
            for flags, text in ((("--stamp", "volcano,0,0,60,20"), "the stamps are"), (("--stamp",), "--stamp needs"),
                                (("--stamp", "crater,0,0,2,20"), "radius is 8 to 4096"),
                                (("--stamp", "mound,400,0,40,10"), "lies off the land"),
                                (("--stamp", "mound,1e20,0,40,10"), "lies off the land"),
                                (("--stamp", "pit,80,80,40,300"), "under the land's floor"),
                                (("--stamp", "pit,80,80,40,300,worked"), "under the land's floor")):
                res = self.run_terrain(out, *flags)
                self.assertNotEqual(res.returncode, 0, flags)
                self.assertIn(text, res.stdout, flags)
                self.assertFalse(os.path.exists(out), flags)
            # a mound that only overlaps the edge is on the land
            self.assertEqual(self.run_terrain(out, "--stamp", "mound,150,0,40,10").returncode, 0)


if __name__ == "__main__":
    unittest.main()
