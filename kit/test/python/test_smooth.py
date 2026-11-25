"""SMOOTHING BY SUBDIVISION (kit/blender/rbx_subd.py, rbx.Asset.smooth): any mesh part smoothed, its chosen edges
held - proven on plain boxes (a pebble inside its own box, a box whose every edge is held, a held foot that
stays the full square), on a mirrored pair and a varied row, on a part of two materials, after box modelling,
and on what it refuses with nothing changed. Fixtures: kit/selftest/blender/check_smooth_cases.py (nothing
built) and build_smooth.py."""

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
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_smooth"))
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(REPO, "kit", "selftest", "blender", script), "--", "--no-preview", *args],
                          cwd=REPO, capture_output=True, text=True, timeout=900, env=e, encoding="utf-8",
                          errors="replace")


def cases(*args):
    r = blender("check_smooth_cases.py", *args)
    line = next((x for x in r.stdout.splitlines() if x.startswith("SMOOTH_CASES ")), None)
    assert r.returncode == 0 and line, (r.stderr or r.stdout)[-800:]
    return json.loads(line.split(" ", 1)[1])


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Cases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = cases()
        cls.p = cls.d["parts"]

    def test_every_part_stays_a_closed_solid_the_right_way_out(self):
        for name, row in {**self.p, "Soft": self.d["soft"]}.items():
            self.assertEqual(row["faults"], [0, 0], name)
            self.assertEqual((row["doubled"], row["crossing"]), (0, 0), name)
            self.assertGreater(row["volume"], 0, name)

    def test_all_soft_a_box_becomes_a_pebble_inside_itself(self):
        soft = self.d["soft"]
        self.assertEqual(soft["faces"], 6 * 4 ** 3)
        self.assertTrue(0.30 < soft["volume"] < 0.37, soft["volume"])            # a third of the box it was
        for lo, hi, a_, b_ in zip(soft["lo"], soft["hi"], (-0.5, 0.0, -0.5), (0.5, 1.0, 0.5)):
            self.assertTrue(a_ < lo and hi < b_)                                 # wholly inside it
            self.assertAlmostEqual(hi - lo, 0.849, delta=0.01)                   # 85% as wide, every way alike

    def test_every_sharp_edge_held_it_is_the_same_box_with_more_faces(self):
        hard = self.p["Hard"]
        self.assertEqual((hard["volume"], hard["faces"]), (1.0, 6 * 4 ** 3))
        self.assertEqual((hard["lo"][0], hard["hi"][0], hard["hi"][1]), (-0.5, 0.5, 1.0))

    def test_a_held_foot_stays_the_full_square_and_the_rest_goes_round(self):
        foot = self.d["foot"]
        self.assertEqual(foot["at_foot"], [1.0, 1.0])                            # (without its corners held: 0.92)
        self.assertLess(max(foot["at_top"]), 0.3)                                # its top: a small round cap
        self.assertEqual(self.p["Foot"]["lo"][1], 0.0)                           # standing where it stood
        self.assertTrue(self.d["soft"]["volume"] < self.p["Foot"]["volume"] < 1.0)

    def test_hold_sets_how_hard_a_held_edge_stays(self):
        self.assertTrue(self.p["Foot"]["volume"] < self.p["Half"]["volume"] < self.p["Hard"]["volume"])
        # hold 0, 0.25, 0.5, 0.75, 1 on a unit box, at 1, 2 and 3 levels: each softer than the next AT EVERY
        # level count (the first build passed the number straight on: 0.5 and over did nothing at all)
        for lv, row in self.d["holds"].items():
            self.assertEqual(row, sorted(row), lv)
            self.assertEqual(row[-1], 1.0, lv)                                   # 1: the box itself
            self.assertTrue(all(b - a_ > 0.03 for a_, b in zip(row, row[1:])), (lv, row))   # every step shows
            self.assertTrue(0.5 < row[2] < 0.9, (lv, row))                       # 0.5: clearly rounded, still a box

    def test_a_mirrored_part_is_held_on_its_own_outer_end(self):
        pair = self.d["pair"]
        self.assertEqual(pair["outer"], [1.0, 1.0])                              # the part: square at x = 6
        self.assertEqual(pair["twin_outer"], [1.0, 1.0])                         # its mirror: square at x = -6
        self.assertLess(max(pair["inner"] + pair["twin_inner"]), 0.5)            # both: round at their inner ends
        self.assertEqual(self.p["Pair"]["volume"], self.p["Pair~m1"]["volume"])

    def test_every_copy_of_a_row_is_smoothed_in_its_own_size(self):
        for name, s_ in zip(("Row", "Row~m1", "Row~m2"), self.d["row_scales"]):
            self.assertAlmostEqual(self.p[name]["volume"], self.p["Row"]["volume"] * s_ ** 3, places=3, msg=name)
        self.assertGreater(max(self.d["row_scales"]) - min(self.d["row_scales"]), 0.05)

    def test_a_copy_is_the_parts_own_points_at_its_place(self):
        # (a lopsided rule on the row, a one-ended rule on the pair: a copy smoothed in the wrong frame would differ)
        self.assertLess(self.d["copies"]["mirror"], 1e-5)
        self.assertLess(self.d["copies"]["row"], 1e-5)

    # ---- the faults the review of the first build found
    def test_a_part_with_a_hole_cut_through_it_smooths_without_a_face_through_another(self):
        for key, (was, row) in self.d["holes"].items():
            self.assertEqual((row["faults"], row["doubled"], row["crossing"]), ([0, 0], 0, 0), key)
            if key.startswith("sharp"):                                          # its flat faces kept: only the
                self.assertAlmostEqual(row["volume"], was, delta=0.004, msg=key)  # hole's 16 sides round off
            else:
                self.assertTrue(0.5 * was < row["volume"] < 0.7 * was, key)

    def test_a_notched_part_with_its_edges_held_is_the_same_solid(self):
        was, row = self.d["notch"]                                               # (the first build refused it)
        self.assertEqual(row["volume"], was)
        self.assertEqual((row["doubled"], row["crossing"]), (0, 0))

    def test_a_rule_on_direction_sees_every_edge_one_way_round(self):
        held = next(f["held"] for f in self.d["facts"] if f["part"] == "Zs")
        self.assertEqual(held, 4)                                                # all four along z (the first: one)

    def test_a_numpy_true_is_held_like_pythons(self):
        self.assertEqual(self.d["bools"][0], self.d["bools"][1])

    def test_nothing_is_left_behind(self):
        self.assertEqual(self.d["left_behind"], {"temp": [], "creases": []})
        self.assertEqual(self.d["bevel_after"], 0.0)                             # no round's width passed on

    def test_every_face_keeps_its_material(self):
        top, rest, brass = self.d["two"]
        self.assertEqual((top, rest), ([brass], [0]))
        self.assertEqual(self.p["Two"]["slots"], [0, 1])

    def test_a_form_cut_from_a_box_can_be_smoothed(self):
        pod = self.p["Pod"]
        self.assertEqual(pod["faces"], 18 * 4 ** 2)                              # the cut box had 18 faces
        self.assertGreater(pod["hi"][1], 1.2)                                    # its pushed-up middle still stands up
        self.assertTrue(1.2 < pod["volume"] < 2.18)                              # smaller than its cage (2.18)

    def test_a_flat_rim_round_a_pocket_does_not_fold_over_it(self):
        lid = self.p["Lid"]                                                      # every sharp edge held
        self.assertAlmostEqual(lid["volume"], 1.6 * 0.8 * 1.1 - 1.32 * 0.82 * 0.08, places=4)   # the same solid
        self.assertEqual((lid["doubled"], lid["faces"]), (0, 14 * 16))
        error, kept = self.d["fold"]                                             # its mitres left soft by a rule:
        self.assertIn("fold through itself", error)                              # refused, said why
        self.assertTrue(kept)

    def test_what_is_not_allowed_is_said_and_changes_nothing(self):
        e = self.d["errors"]
        for key, word in (("levels0", "levels=0"), ("levels9", "levels=9"), ("crisp", "crisp='hard'"),
                          ("answer", "answered 2.0"), ("hold", "hold=3"), ("copy", 'is a copy of "Pair"'),
                          ("unknown", 'no part "Nobody"'), ("faces", "at most 120000"),
                          ("levels_true", "levels=True"), ("levels_float", "levels=2.0"),
                          ("levels_text", "levels='1'"), ("answer_text", "True, False or a number"),
                          ("angle", "angle=nan"), ("round_after", "no edge sharper"),
                          ("ngons", "at most 120000")):                          # 400-sided caps counted as they split
            self.assertIn(word, e[key], key)
        self.assertTrue(self.d["kept"])                                          # the box they were tried on: to the vertex

    def test_the_facts_say_the_step_and_how_many_edges_it_held(self):
        said = {f["part"]: (f["said"], f.get("held")) for f in self.d["facts"] if f["kind"] == "smooth"}
        self.assertEqual(said["Soft"], ("smooth x3", 0))
        self.assertEqual(said["Hard"], ("smooth x3", 12))
        self.assertEqual(said["Foot"], ("smooth x3", 4))

    def test_a_cad_part_is_refused(self):
        d = cases("--cad")
        self.assertIn("is a CAD part", d["cad"])
        self.assertTrue(d["kept"])


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Built(unittest.TestCase):
    def test_the_fixture_builds_and_says_how_it_was_modelled(self):
        r = blender("build_smooth.py", "--geo")
        line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith('{"schema"')), None)
        self.assertTrue(r.returncode == 0 and line, (r.stderr or r.stdout)[-800:])
        rep = json.loads(line)
        self.assertEqual(rep["status"], "pass", rep["summary"])
        self.assertIn("modelled: Case (inset +Y, smooth x2), Pod (loop x2, push, smooth x2)", rep["summary"])


if __name__ == "__main__":
    unittest.main()
