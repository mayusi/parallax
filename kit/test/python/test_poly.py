"""BOX MODELLING BY RULE (kit/blender/rbx_poly.py, rbx.Asset.inset / push / loop / round): a part cut into the
pieces its form needs, faces picked by where they look, inset and pushed - proven by volume on plain boxes, on a
mirrored pair and a varied row (the copies are modelled as the part is), and on what it refuses with nothing
changed. Fixtures: kit/selftest/blender/check_poly_cases.py (nothing built) and build_poly.py."""

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


def blender(script, *args):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_poly"))
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(REPO, "kit", "selftest", "blender", script), "--", "--no-preview", *args],
                          cwd=REPO, capture_output=True, text=True, timeout=900, env=e, encoding="utf-8",
                          errors="replace")


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Cases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = blender("check_poly_cases.py")
        line = next((x for x in r.stdout.splitlines() if x.startswith("POLY_CASES ")), None)
        assert r.returncode == 0 and line, (r.stderr or r.stdout)[-800:]
        cls.d = json.loads(line.split(" ", 1)[1])
        cls.p = cls.d["parts"]

    def test_every_part_stays_a_closed_solid_the_right_way_out_with_no_face_on_another(self):
        for name, row in self.p.items():
            self.assertEqual(row["faults"], [0, 0], name)
            self.assertEqual(row["doubled"], 0, name)                # (closed by its edges is not enough)
            self.assertGreater(row["volume"], 0, name)               # signed: inside out would be under 0

    def test_an_inset_is_a_flat_rim_and_takes_nothing_away(self):
        self.assertAlmostEqual(self.p["Flat"]["volume"], 2.0, places=4)
        self.assertEqual(self.p["Flat"]["faces"], 6 + 4)                 # four rim faces round the lid's panel

    def test_a_sunk_or_raised_panel_has_straight_walls(self):
        self.assertAlmostEqual(self.p["Sunk"]["volume"], 2.0 - 1.6 * 0.6 * 0.1, places=4)    # the panel, 0.1 deep
        self.assertEqual(self.p["Sunk"]["hi"][1], 1.0)                   # its rim where the top was
        self.assertAlmostEqual(self.p["Raised"]["volume"], 2.0 + 1.6 * 0.6 * 0.1, places=4)
        self.assertAlmostEqual(self.p["Raised"]["hi"][1], 1.1, places=4)

    def test_a_push_moves_whole_faces_and_makes_the_walls(self):
        self.assertAlmostEqual(self.p["Boss"]["volume"], 2.5, places=4)  # its +X side, 0.5 further out
        self.assertAlmostEqual(self.p["Boss"]["hi"][0], 1.5, places=4)
        self.assertAlmostEqual(self.p["Boss"]["lo"][0], -1.0, places=4)

    def test_cuts_make_a_face_where_the_pocket_goes(self):
        slot = self.p["Slot"]
        self.assertAlmostEqual(slot["volume"], 2.0 - 0.6 * 0.5 * 0.3, places=4)      # a pocket 0.6 x 0.5, 0.3 deep
        self.assertEqual((slot["lo"], slot["hi"]), ([-1.0, 0.0, -6.5], [1.0, 1.0, -5.5]))   # nothing else moved

    def test_a_mirrored_part_is_modelled_on_its_own_outer_side(self):
        part, twin = self.p["Pair"], self.p["Pair~m1"]
        for row in (part, twin):
            self.assertAlmostEqual(row["volume"], 1.0 + 0.6 * 0.6 * 0.25, places=4)
        self.assertAlmostEqual(part["hi"][0], 5.75, places=4)            # the boss on its +X side
        self.assertAlmostEqual(part["lo"][0], 4.5, places=4)
        self.assertAlmostEqual(twin["lo"][0], -5.75, places=4)           # the mirrored one: on its -X side
        self.assertAlmostEqual(twin["hi"][0], -4.5, places=4)

    def test_every_copy_of_a_row_is_modelled_in_its_own_size(self):
        scales = self.d["row_scales"]
        for name, s_ in zip(("Row", "Row~m1", "Row~m2"), scales):        # (each also turned: its box says nothing)
            self.assertAlmostEqual(self.p[name]["volume"], (1.0 - 0.6 * 0.6 * 0.1) * s_ ** 3, places=3, msg=name)
        self.assertGreater(max(scales) - min(scales), 0.05)              # and they really are different sizes

    def test_rounding_last_takes_only_the_edges(self):
        r = self.p["Round"]
        self.assertTrue(1.97 < r["volume"] < 2.0, r["volume"])
        self.assertGreater(r["faces"], 6)
        self.assertEqual((r["lo"], r["hi"]), ([-1.0, 0.0, 8.5], [1.0, 1.0, 9.5]))

    def test_a_rule_that_picks_faces_in_two_places_is_said(self):
        fact = [f for f in self.d["facts"] if f["part"] == "Twice"][-1]
        self.assertEqual((fact["said"], fact.get("places")), ("push (2 places)", 2))
        self.assertNotIn("places", next(f for f in self.d["facts"] if f["part"] == "Boss"))
        self.assertAlmostEqual(self.p["Twice"]["volume"], 2.0 + 2 * 0.4 * 1.0 * 0.1, places=4)   # two strips, out 0.1

    # ---- the faults the review of the first build found
    def test_a_pockets_floor_pushed_out_is_refused_not_given_doubled_walls(self):
        self.assertIn("foot of a wall", self.d["errors"]["floor_out"])
        self.assertTrue(self.d["kept"]["pocket"])                        # to the vertex

    def test_a_pocket_can_be_made_in_a_round_body(self):
        for name in ("drum", "ball"):                                    # (the first build refused both)
            before, after = self.d["round_bodies"][name]
            self.assertTrue(0 < before - after < 0.03, (name, before, after))

    def test_a_boss_on_a_painted_face_has_that_paint_all_round(self):
        walls, brass = self.d["painted_walls"]
        self.assertEqual(walls, [brass] * 4)                             # (the first build: three brass, one iron)

    def test_cuts_by_share_are_shares_of_the_stretch_asked(self):
        self.assertEqual(self.d["halves_x"], [-1.0, 0.5, 1.0])           # half way along its second half

    def test_a_cad_part_is_refused_whichever_route_it_is_on_but_may_be_cut(self):
        r = blender("check_poly_cases.py", "--cad")
        line = next((x for x in r.stdout.splitlines() if x.startswith("POLY_CASES ")), None)
        self.assertTrue(r.returncode == 0 and line, (r.stderr or r.stdout)[-800:])
        d = json.loads(line.split(" ", 1)[1])
        for what in ("push", "inset", "round"):                          # (the first build changed a plain a.cad part)
            self.assertIn("is a CAD part", d["cad"][what])
        self.assertTrue(d["kept"])
        self.assertEqual((d["after_loop"]["volume"], d["after_loop"]["faces"]), (1.0, 10))   # cut once: four faces more

    def test_what_is_not_allowed_is_said_and_changes_nothing(self):
        e = self.d["errors"]
        self.assertIn("picked no face", e["none"])
        self.assertIn("room for", e["wide"])
        self.assertIn("every way at once", e["every_way"])
        self.assertIn("wall of no thickness", e["to_the_edge"])
        self.assertIn("where=", e["rule"])
        self.assertIn('no part "Nobody"', e["unknown"])
        self.assertIn('is a copy of "Pair"', e["copy"])
        self.assertIn("shares of the part's length", e["loop"])
        self.assertIn("width=", e["round"])
        self.assertIn("run into each other", e["round_wide"])            # (the first build clamped it to slivers)
        self.assertIn("segments=", e["segments"])
        self.assertIn("cuts nothing", e["count0"])
        self.assertEqual(self.d["plain"][0], self.d["plain"][1])         # the box they were tried on: as it was
        self.assertTrue(self.d["kept"]["plain"])                         # ... to the vertex

    def test_the_facts_say_each_step_in_order(self):
        said = [(f["part"], f["said"]) for f in self.d["facts"]]
        self.assertEqual(said[:8], [("Flat", "inset +Y"), ("Sunk", "inset +Y"), ("Raised", "inset +Y"),
                                    ("Boss", "push +X"), ("Slot", "loop x2"), ("Slot", "loop x3"), ("Slot", "push"),
                                    ("Pair", "inset +X")])


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Built(unittest.TestCase):
    def test_the_fixture_builds_and_says_how_it_was_modelled(self):
        r = blender("build_poly.py", "--geo")
        line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith('{"schema"')), None)
        self.assertTrue(r.returncode == 0 and line, (r.stderr or r.stdout)[-800:])
        rep = json.loads(line)
        self.assertEqual(rep["status"], "pass", rep["summary"])
        self.assertIn("modelled: Crate (inset +Y, loop x2, push, inset, round 0.02), Foot (inset +X, round 0.012)",
                      rep["summary"])


if __name__ == "__main__":
    unittest.main()
