"""Unit tests of forced perspective's rule and tool (kit/vfx/forced.py).
Run: python -m pytest kit/test/python/test_vfx_forced.py -q"""
import contextlib
import io
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import forced as F  # noqa: E402
import methods as M  # noqa: E402


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = F.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


class TheRule(unittest.TestCase):
    def test_keep_1_holds_the_size_on_the_screen(self):
        f = {"ref": 40, "keep": 1, "min": 0.01, "max": 100}
        for d in (4, 10, 40, 80, 400, 3000):
            self.assertAlmostEqual(F.scale(d, f) * 40 / d, 1)            # size on screen goes as size / distance

    def test_it_is_1_at_ref_whatever_the_keep(self):
        for keep in (-1, -0.3, 0.2, 0.5, 1):
            self.assertAlmostEqual(F.scale(40, {"ref": 40, "keep": keep}), 1)

    def test_a_part_keep_shrinks_with_distance_but_less_than_the_lens(self):
        f = {"ref": 40, "keep": 0.5, "min": 0.01, "max": 100}
        on_screen = F.scale(160, f) * 40 / 160
        self.assertAlmostEqual(on_screen, 0.5)                           # the lens alone: 0.25; held: 1
        self.assertAlmostEqual(F.scale(160, f), 2)

    def test_a_negative_keep_shrinks_faster_than_the_lens(self):
        self.assertAlmostEqual(F.scale(160, {"ref": 40, "keep": -1, "min": 0.01, "max": 100}), 0.25)

    def test_the_multiplier_never_leaves_min_and_max(self):
        f = {"ref": 40, "keep": 1, "min": 0.25, "max": 4}
        self.assertEqual(F.scale(0, f), 0.25)                            # the camera inside the layer
        self.assertEqual(F.scale(1, f), 0.25)
        self.assertEqual(F.scale(1e7, f), 4)
        self.assertEqual(F.scale(40, {"ref": 40, "keep": 1, "min": 1, "max": 1}), 1)

    def test_the_defaults_are_keep_1_between_a_quarter_and_four(self):
        self.assertEqual([F.scale(d, {"ref": 40}) for d in (5, 20, 80, 800)], [0.25, 0.5, 2, 4])

    def test_a_ref_that_is_nothing_changes_nothing(self):
        self.assertEqual(F.scale(80, {"ref": 0}), 1.0)


class TheBlock(unittest.TestCase):
    def test_what_is_wrong_is_said_in_words(self):
        for f, word in ((40, "is a block"), ({"ref": 40, "hold": 1}, "does not read hold"), ({}, "forced.ref is"), ({"ref": True}, "forced.ref is"),
                        ({"ref": 0.5}, "forced.ref is"), ({"ref": 40, "keep": 2}, "forced.keep is -1 to 1"), ({"ref": 40, "keep": 0}, "does nothing"), ({"ref": 40, "keep": 0.0001}, "does nothing"),
                        ({"ref": 40, "min": 1, "max": 1}, "hold the multiplier at 1"),
                        ({"ref": 40, "min": 2}, "forced.min is"), ({"ref": 40, "max": 0.5}, "forced.min is"), ({"ref": float("nan")}, "forced.ref is")):
            with self.assertRaisesRegex(ValueError, word, msg=str(f)):
                F.checked(f)
        F.checked({"ref": 40})
        F.checked({"ref": 40, "keep": -1, "min": 0.01, "max": 100})


class TheCommand(unittest.TestCase):
    def test_it_prints_the_multiplier_and_the_on_screen_size_at_each_distance(self):
        code, said = run(["--ref", "40", "--keep", "0.5", "--min", "0.01", "--max", "100", "--at", "10,40,160"])
        self.assertEqual(code, 0)
        self.assertEqual([(r["multiplier"], r["on_screen"]) for r in said["rows"]], [(0.5, 2.0), (1.0, 1.0), (2.0, 0.5)])
        self.assertIn('"forced": {"ref": 40, "keep": 0.5', said["next_action"])

    def test_wrong_asks_are_said_in_words(self):
        for argv, word in ((["--keep", "3"], "forced.keep"), (["--glide", "1"], "not an option"), (["--at", "0,40"], "--at is distances"),
                           (["--ref"], "no value"), (["--ref", "far"], "forced")):
            code, said = run(argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, said["summary"], argv)


class TheRegister(unittest.TestCase):
    def test_forced_perspective_is_a_layer_whose_size_answers_the_camera(self):
        _, by = M.load()
        m = by["forced_perspective"]
        self.assertEqual(m["state"], "has")

        class Empty:
            def get(self, key):
                return None

        def proved(layer):
            return M.proved(m, [dict({"kind": "mesh", "life": 1}, **layer)], Empty(), ".", "s") is not None

        self.assertTrue(proved({"forced": {"ref": 40}}))
        self.assertTrue(proved({"forced": {"ref": 40, "keep": 0.5}}))
        self.assertFalse(proved({"forced": {"ref": 40, "keep": 0}}))      # switched off
        self.assertFalse(proved({"forced": {"keep": 1}}))                 # no ref: the layer would not change
        self.assertFalse(proved({}))
        self.assertIsNotNone(M.proved(m, [{"kind": "impact", "life": 1, "camera": {"cut": True}}], Empty(), ".", "s"))


if __name__ == "__main__":
    unittest.main()
