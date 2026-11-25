"""Unit tests of the authored vector field's rule and tool (kit/vfx/field.py).
Run: python -m pytest kit/test/python/test_vfx_field.py -q"""
import contextlib
import io
import json
import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import field as F  # noqa: E402


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = F.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def speed(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


class TheRule(unittest.TestCase):
    def test_a_wind_is_the_same_everywhere_and_as_fast_as_said(self):
        els = [{"kind": "wind", "dir": [3, 0, 4], "speed": 10}]
        for p in ([0, 0, 0], [50, -3, 7]):
            v = F.at(els, *p)
            self.assertAlmostEqual(v[0], 6)
            self.assertAlmostEqual(v[2], 8)
            self.assertEqual(v[1], 0)

    def test_a_vortex_turns_round_its_axis_fastest_at_its_radius(self):
        els = [{"kind": "vortex", "at": [0, 0, 0], "axis": [0, 1, 0], "radius": 4, "speed": 12}]
        v = F.at(els, 4, 0, 0)
        self.assertAlmostEqual(speed(v), 12)                            # at the radius: the speed said
        self.assertAlmostEqual(v[0], 0)                                 # across the line to the axis, not along it
        self.assertEqual(v[1], 0)
        self.assertEqual(F.at(els, 0, 5, 0), [0.0, 0.0, 0.0])           # on the axis: still
        self.assertLess(speed(F.at(els, 1, 0, 0)), 12)
        self.assertLess(speed(F.at(els, 12, 0, 0)), 12)
        self.assertLess(speed(F.at(els, 60, 0, 0)), 0.01)               # far away it is gone
        self.assertAlmostEqual(speed(F.at(els, 4, 9, 0)), 12)           # the same all the way along the axis

    def test_a_vortexs_turn_is_one_way_round_and_the_other_with_a_negative_speed(self):
        els = [{"kind": "vortex", "at": [0, 0, 0], "radius": 4, "speed": 12}]
        back = [{"kind": "vortex", "at": [0, 0, 0], "radius": 4, "speed": -12}]
        places = [[4, 0, 0], [0, 0, 4], [-4, 0, 0], [0, 0, -4]]
        spins = [p[2] * F.at(els, *p)[0] - p[0] * F.at(els, *p)[2] for p in places]   # the turn about +y
        self.assertTrue(all(s > 0 for s in spins) or all(s < 0 for s in spins), spins)
        self.assertTrue(all(a * (p[2] * F.at(back, *p)[0] - p[0] * F.at(back, *p)[2]) < 0 for a, p in zip(spins, places)))

    def test_pull_draws_in_and_lift_goes_along_the_axis(self):
        els = [{"kind": "vortex", "at": [0, 0, 0], "axis": [0, 2, 0], "radius": 4, "speed": 0, "pull": 5, "lift": 7}]
        v = F.at(els, 4, 0, 0)
        self.assertAlmostEqual(v[0], -5)                                # toward the axis
        self.assertAlmostEqual(F.at(els, 0, 0, 0)[1], 7)                # the lift is strongest on the axis
        self.assertLess(v[1], 7)

    def test_a_points_pull_dies_at_the_point_so_a_speck_comes_to_rest_there(self):
        els = [{"kind": "point", "at": [0, 0, 0], "radius": 6, "speed": -8}]
        self.assertLess(speed(F.at(els, 0.05, 0, 0)), 0.1)              # next to nothing right at the point
        self.assertGreater(speed(F.at(els, 2, 0, 0)), 4)                # and strong a third of the radius out
        p = [3.0, 0.5, -1.0]
        for _ in range(600):                                            # ten seconds of a speck riding it
            v = F.at(els, *p)
            p = [p[i] + v[i] / 60 for i in range(3)]
        last = []
        for _ in range(60):
            v = F.at(els, *p)
            p = [p[i] + v[i] / 60 for i in range(3)]
            last.append(speed(v))
        self.assertLess(math.sqrt(sum(c * c for c in p)), 0.6)           # it is at the point
        self.assertLess(sum(last) / 60, 0.5)                             # and no longer shooting through it

    def test_a_radius_of_nothing_or_an_axis_that_is_not_three_numbers_gives_no_nan(self):
        for els in ([{"kind": "vortex", "at": [0, 0, 0], "radius": 0, "speed": 5}], [{"kind": "point", "at": [0, 0, 0], "radius": 0, "speed": 5}],
                    [{"kind": "path", "points": [[0, 0, 0], [1, 0, 0]], "radius": 0, "speed": 5}]):
            self.assertEqual(F.at(els, 1, 1, 1), [0.0, 0.0, 0.0], els[0]["kind"])
        a = F.at([{"kind": "vortex", "at": [0, 0, 0], "axis": [], "radius": 4, "speed": 12}], 4, 0, 0)
        b = F.at([{"kind": "vortex", "at": [0, 0, 0], "radius": 4, "speed": 12}], 4, 0, 0)
        self.assertEqual(a, b)                                          # the default axis: up

    def test_a_point_pushes_away_and_pulls_in_with_a_negative_speed(self):
        out = F.at([{"kind": "point", "at": [1, 1, 1], "radius": 3, "speed": 8}], 3, 1, 1)
        back = F.at([{"kind": "point", "at": [1, 1, 1], "radius": 3, "speed": -8}], 3, 1, 1)
        self.assertGreater(out[0], 0)
        self.assertAlmostEqual(out[0], -back[0])
        self.assertEqual((out[1], out[2]), (0, 0))
        self.assertEqual(F.at([{"kind": "point", "at": [1, 1, 1], "radius": 3, "speed": 8}], 1, 1, 1), [0.0, 0.0, 0.0])

    def test_a_path_flows_along_itself_and_draws_specks_onto_its_line(self):
        els = [{"kind": "path", "points": [[0, 0, 0], [10, 0, 0], [10, 10, 0]], "radius": 2, "speed": 6, "pull": 4}]
        on = F.at(els, 5, 0, 0)
        self.assertAlmostEqual(on[0], 6)                                # on the line: along it, as fast as said
        self.assertAlmostEqual(on[1], 0)
        off = F.at(els, 5, 1, 0)
        self.assertGreater(off[0], 0)
        self.assertLess(off[1], 0)                                      # above the line: drawn back down to it
        up = F.at(els, 10, 5, 0)
        self.assertAlmostEqual(up[1], 6)                                # the second stretch flows its own way
        self.assertAlmostEqual(up[0], 0)
        self.assertLess(speed(F.at(els, 5, 40, 0)), 1e-6)               # far from every stretch: nothing

    def test_a_stretch_of_no_length_is_passed_over(self):
        a = F.at([{"kind": "path", "points": [[0, 0, 0], [0, 0, 0], [10, 0, 0]], "radius": 2, "speed": 6}], 5, 0.5, 0)
        b = F.at([{"kind": "path", "points": [[0, 0, 0], [10, 0, 0]], "radius": 2, "speed": 6}], 5, 0.5, 0)
        self.assertEqual(a, b)

    def test_elements_add_up(self):
        w = {"kind": "wind", "dir": [1, 0, 0], "speed": 4}
        vx = {"kind": "vortex", "at": [0, 0, 0], "radius": 4, "speed": 12}
        both, a, b = F.at([w, vx], 2, 1, 3), F.at([w], 2, 1, 3), F.at([vx], 2, 1, 3)
        for i in range(3):
            self.assertAlmostEqual(both[i], a[i] + b[i])


class TheFile(unittest.TestCase):
    def test_the_starters_are_fields(self):
        for kind, f in F.STARTERS.items():
            F.checked(json.loads(json.dumps(f)))
            self.assertFalse([c for c in F.check(f) if not c["ok"]], kind)

    def test_what_is_wrong_is_said_in_words(self):
        w = {"kind": "wind", "dir": [1, 0, 0], "speed": 4}
        for field, word in (({}, "one element or more"), ({"elements": []}, "one element or more"), ({"elements": [w] * 17}, "16 elements at most"),
                            ({"elements": [w], "bounds": 0}, "bounds is"), ({"elements": [w], "bound": 20}, "does not read bound at its top"),
                            ({"elements": [w], "schema": 2}, "schema is 1"), ({"elements": [{"kind": "tornado"}]}, "kind is wind, vortex, point or path"),
                            ({"elements": [dict(w, gust=2)]}, "does not read gust"), ({"elements": [dict(w, speed="fast")]}, "speed is studs a second"),
                            ({"elements": [dict(w, speed=True)]}, "speed is studs a second"), ({"elements": [dict(w, dir=[0, 0, 0])]}, "not all 0"),
                            ({"elements": [{"kind": "vortex", "at": [0, 0, 0], "speed": 4}]}, "radius is"),
                            ({"elements": [{"kind": "vortex", "at": [0, 0], "radius": 2, "speed": 4}]}, "at is [x, y, z]"),
                            ({"elements": [{"kind": "vortex", "at": [0, 0, 0], "radius": 2, "speed": 4, "axis": [0, 0, 0]}]}, "axis is"),
                            ({"elements": [{"kind": "path", "points": [[0, 0, 0]], "radius": 2, "speed": 4}]}, "2 to 32 places"),
                            ({"elements": [{"kind": "path", "points": [[1, 1, 1], [1, 1, 1]], "radius": 2, "speed": 4}]}, "all one place"),
                            ({"elements": [{"kind": "path", "points": [[0, 0, 0], [1, 0, 0]], "radius": 2, "speed": 4, "pull": -1}]}, "pull is 0 to")):
            with self.assertRaisesRegex(ValueError, word.replace("[", r"\[").replace("]", r"\]"), msg=str(field)[:60]):
                F.checked(field)

    def test_air_that_stands_still_in_its_bounds_is_caught(self):
        far = {"bounds": 4, "elements": [{"kind": "vortex", "at": [300, 0, 0], "radius": 2, "speed": 12}]}
        self.assertEqual({c["name"] for c in F.check(far) if not c["ok"]}, {"moves", "carries"})

    def test_a_small_or_thin_field_in_a_big_space_is_still_a_field(self):
        for els in ([{"kind": "point", "at": [0, 0, 0], "radius": 2, "speed": 30}], [{"kind": "vortex", "at": [5, 0, 5], "radius": 2, "speed": 12}],
                    [{"kind": "path", "points": [[-6, 0, 0], [6, 0, 0]], "radius": 0.5, "speed": 10, "pull": 4}]):
            f = {"bounds": 30 if els[0]["kind"] != "path" else 8, "elements": els}
            self.assertFalse([c["name"] for c in F.check(f) if not c["ok"]], els[0]["kind"])

    def test_a_field_that_only_shivers_carries_nothing(self):
        # two winds that cancel, and a pull so local that a speck beside it moves a hair: the path is long nowhere
        w = {"kind": "wind", "dir": [1, 0, 0], "speed": 5}
        back = {"kind": "wind", "dir": [-1, 0, 0], "speed": 5}
        self.assertIn("carries", [c["name"] for c in F.check({"bounds": 8, "elements": [w, back]}) if not c["ok"]])

    def test_speeds_that_add_up_past_the_limit_are_caught(self):
        w = {"kind": "wind", "dir": [1, 0, 0], "speed": 300}
        self.assertIn("bounded", [c["name"] for c in F.check({"bounds": 4, "elements": [w, w]}) if not c["ok"]])

    def test_the_specks_are_the_same_every_run(self):
        self.assertEqual(F.seeds(8), F.seeds(8))
        self.assertTrue(all(abs(c) <= 8 for p in F.seeds(8) for c in p))


class TheCommand(unittest.TestCase):
    def test_a_starter_is_made_checked_and_drawn_and_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = ["--out-dir", os.path.join(tmp, "fields"), "--look-dir", os.path.join(tmp, "look")]
            code, said = run(["whirl", "--new", "vortex"] + args)
            self.assertEqual((code, said["status"]), (0, "pass"))
            self.assertTrue(os.path.isfile(os.path.join(tmp, "fields", "whirl.json")))
            self.assertTrue(os.path.isfile(os.path.join(tmp, "look", "whirl.png")))
            self.assertIn('"field": {"name": "whirl"}', said["summary"])
            code, said = run(["whirl", "--new", "wind"] + args)
            self.assertEqual(code, 1)
            self.assertIn("already there", said["summary"])
            self.assertEqual(json.load(open(os.path.join(tmp, "fields", "whirl.json"), encoding="utf-8"))["elements"][0]["kind"], "vortex")
            self.assertEqual(run(["whirl"] + args)[0], 0)             # checked again, as after an edit

    def test_an_edited_field_that_is_wrong_is_refused_and_draws_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "fields"))
            with open(os.path.join(tmp, "fields", "bad.json"), "w", encoding="utf-8") as fh:
                json.dump({"elements": [{"kind": "vortex", "at": [0, 0, 0], "radius": 2, "speed": 4, "swirl": 3}]}, fh)
            code, said = run(["bad", "--out-dir", os.path.join(tmp, "fields"), "--look-dir", os.path.join(tmp, "look")])
            self.assertEqual(code, 1)
            self.assertIn("does not read swirl", said["summary"])
            self.assertFalse(os.path.exists(os.path.join(tmp, "look", "bad.png")))

    def test_wrong_asks_are_said_in_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = ["--out-dir", tmp, "--look-dir", tmp]
            for argv, word in ((["Whirl"], "lowercase"), (["caf\u00e9"], "lowercase"), ([], "name ONE"), (["a", "b"], "name ONE"), (["whirl", "--new", "tornado"], "--new is one of"),
                               (["whirl", "--glide", "1"], "not an option"), (["nope"], "no field"), (["whirl", "--new"], "no value")):
                code, said = run(argv + ([] if "--glide" in argv or argv[-1:] == ["--new"] else args))
                self.assertEqual(code, 1, argv)
                self.assertIn(word, said["summary"], argv)


if __name__ == "__main__":
    unittest.main()
