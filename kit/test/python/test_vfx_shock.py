"""Unit tests of shockwave distortion, baked (kit/vfx/comp.py "shock"; the VFX methods audit, stage 30): a ring that
runs out from a point and bends the picture it passes over.
Run: python -m pytest kit/test/python/test_vfx_shock.py -q"""
import copy
import json
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import comp as C  # noqa: E402
import methods as M  # noqa: E402


def spec(**shock):
    s = C.new_spec("shock")
    s["cell"] = 128
    s["comp"]["shock"].update(shock)
    return s


class TheLens(unittest.TestCase):
    S = {"from": 0.1, "to": 0.4, "width": 0.06, "amount": 0.018, "centre": [0.5, 0.5]}

    def grid(self, n=128):
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
        return xx, yy

    def test_it_bends_nothing_further_than_three_widths_from_its_line(self):
        xx, yy = self.grid()
        for t in (0.0, 0.5, 1.0):
            x, y, q = C.shock_at(self.S, xx, yy, t, 128)
            moved = np.hypot(x - xx, y - yy)
            self.assertEqual(float(moved[np.abs(q) >= C.SHOCK_REACH].max()), 0.0)
            self.assertGreater(float(moved[np.abs(q) < 1.5].max()), 1.0)                   # and it does bend at its line: over a pixel

    def test_it_is_a_lens_out_beyond_its_line_and_in_inside_it_and_most_a_width_away(self):
        xx, yy = self.grid()
        x, y, q = C.shock_at(self.S, xx, yy, 0.5, 128)
        r0 = np.hypot(xx - 64, yy - 64)
        r1 = np.hypot(x - 64, y - 64)                                                      # where each place is READ from
        outside, inside = (q > 0.5) & (q < 2), (q < -0.5) & (q > -2)
        self.assertTrue((r1[outside] < r0[outside]).all())                                 # read from nearer the centre: the picture is pushed OUT
        self.assertTrue((r1[inside] > r0[inside]).all())                                   # read from further out: pulled IN
        most = np.abs(r1 - r0)
        self.assertAlmostEqual(float(most.max()), self.S["amount"] * 128, delta=0.05)      # its "amount" of the cell, at the most
        self.assertAlmostEqual(abs(float(q.reshape(-1)[int(np.argmax(most))])), 1.0, delta=0.08)   # a width from the line
        self.assertLess(float(np.abs(np.arctan2(y - 64, x - 64) - np.arctan2(yy - 64, xx - 64))[r0 > 2].max()), 1e-9)   # along the radius only

    def test_the_ring_is_where_its_radius_says_and_nothing_is_bent_at_the_very_centre(self):
        xx, yy = self.grid()
        for t, want in ((0.0, 0.1), (1.0, 0.4)):
            _, _, q = C.shock_at(self.S, xx, yy, t, 128)
            on_line = np.hypot(xx - 64, yy - 64)[np.abs(q) < 0.05] / 128
            self.assertAlmostEqual(float(on_line.mean()), want, delta=0.004)
        near = dict(self.S, **{"from": 0.0})
        x, y, _ = C.shock_at(near, xx, yy, 0.0, 128)
        self.assertLess(float(np.hypot(x - xx, y - yy)[62:67, 62:67].max()), 0.3)          # every way is "out" there: it would pinwheel

    def test_the_picture_is_never_folded_or_creased(self):
        """along a radius, where the picture is read from must run on smoothly: a corner in it is a crease ring that
        stands still while the shock runs out (the first centre damping left one at a width, the reach window one near 2.3)"""
        n = 512
        r = np.arange(4.0, 250.0, 0.25)
        x, y = 256.0 + r, np.full_like(r, 256.0)
        worst_jump, least = 0.0, 9.0
        for width, amount in ((0.07, 0.021), (0.07, 0.01), (0.15, 0.045), (0.03, 0.009)):
            for start in (width, 0.2):
                s = {"from": start, "to": 0.45, "width": width, "amount": amount, "centre": [0.5, 0.5]}
                for t in (0.0, 0.3, 0.7, 1.0):
                    rx, _, _ = C.shock_at(s, x, y, t, n)
                    slope = np.diff(rx - 256.0) / 0.25                                     # how fast the read place moves as the place does
                    least = min(least, float(slope.min()))
                    worst_jump = max(worst_jump, float(np.abs(np.diff(slope)).max()))
        self.assertGreater(least, 0.45)                                                    # never folded, never stretched to much over twice
        self.assertLess(worst_jump, 0.03)                                                  # no corner: the slope itself runs on (a crease jumped by 0.5)


class TheSheet(unittest.TestCase):
    def test_the_starter_bakes_and_its_ring_bends_runs_out_and_touches_nothing_else(self):
        o = C.checked(spec())
        frames, plain = C.frames_of(o), C.frames_of(o, shock=False)
        rows = {c["name"]: c for c in C.check(frames, o, plain)}
        self.assertTrue(all(c["ok"] for c in rows.values()), {k: v["value"] for k, v in rows.items() if not v["ok"]})
        for name in ("bends", "bends only at its ring", "runs out"):
            self.assertIn(name, rows)
        self.assertEqual(rows["bends only at its ring"]["value"], 0.0)
        # with no shock the sheet is a still picture: every frame the same
        self.assertLess(max(float(np.abs(a - b).max()) for a, b in zip(plain, plain[1:])), 1e-12)

    def test_a_shock_that_bends_nothing_you_can_see_is_refused(self):
        with self.assertRaisesRegex(ValueError, "under a pixel"):
            C.checked(spec(amount=0.0005))
        flat = spec()
        del flat["comp"]["noise"]                                                          # a flat fill: nothing in it for the ring to move
        flat["comp"]["shape"]["radius"] = 0.2
        flat["comp"]["shock"].update({"from": 0.3, "to": 0.45})                            # ... and the ring runs where there is no picture
        o = C.checked(flat)
        rows = {c["name"]: c for c in C.check(C.frames_of(o), o, C.frames_of(o, shock=False))}
        self.assertFalse(rows["bends"]["ok"])

    def test_what_cannot_be_a_shock_is_said_in_words(self):
        for other, block in (("erode", {"at": 0.3}), ("halftone", {"dot": 6, "angle": 45})):
            mixed = spec()
            mixed["comp"][other] = block
            with self.assertRaisesRegex(ValueError, f'a "shock" does not go with "{other}"'):
                C.checked(mixed)
        for change, word in (({"amount": 0.05}, "over three tenths of its \"width\""), ({"to": 0.05}, 'a shock runs OUT'), ({"width": 0.9}, "shock.width"),
                             ({"amount": 0}, "shock.amount is 0"), ({"from": 0.02}, "would start on its own centre"),
                             ({"centre": [0.5]}, "shock.centre is [x, y]"), ({"glow": 1}, '"shock" does not read glow'),
                             ({"from": 0.05, "to": 0.9, "width": 0.03, "amount": 0.008}, "it would jump from place to place")):
            with self.assertRaises(ValueError) as e:
                C.checked(spec(**change))
            self.assertIn(word, str(e.exception), change)
        looped = spec()
        looped["comp"]["loop"] = True
        with self.assertRaisesRegex(ValueError, "a one-shot"):
            C.checked(looped)
        tiled = spec()
        tiled["comp"]["tile"] = True
        del tiled["comp"]["shape"]
        with self.assertRaisesRegex(ValueError, "not on a \"tile\""):
            C.checked(tiled)
        graph = C.new_spec("graph")
        graph["comp"]["loop"] = False
        graph["comp"]["shock"] = dict(spec()["comp"]["shock"])
        with self.assertRaisesRegex(ValueError, '"graph" stands in place of'):
            C.checked(graph)

    def test_a_sheet_with_no_shock_is_checked_as_it_always_was(self):
        ring = C.checked(dict(C.new_spec("ring"), cell=128))
        names = [c["name"] for c in C.check(C.frames_of(ring), ring)]
        self.assertNotIn("bends", names)


class TheRegister(unittest.TestCase):
    def test_shockwave_distortion_is_closed_with_what_the_engine_bends_and_where(self):
        _, by = M.load()
        m = by["shockwave_distortion"]
        self.assertEqual(m["state"], "engine")                                             # the engine bends the live scene through Glass, at high graphics only
        self.assertIn("level 16 of 21", m["reason"])                                       # the level it was looked at, said
        self.assertIn("It bends its OWN sheet, not the scene behind it", m["how"])         # the baked ring: what it is not, still said
        for mid in ("refraction", "heat_distortion"):
            self.assertEqual(by[mid]["state"], "engine", mid)
            self.assertIn("level 16 of 21", by[mid]["reason"])

        def proves(s):
            return any(M.texture_proves(alt["texture"], s) for alt in m["proof"] if "texture" in alt)

        self.assertTrue(proves(spec()))
        off = spec(amount=0)
        self.assertFalse(proves(off))
        # a spec the comp would never bake proves nothing: a loop, an amount it refuses
        looped = copy.deepcopy(spec())
        looped["comp"]["loop"] = True
        self.assertFalse(proves(looped))
        self.assertFalse(proves(spec(amount=5)))
        none = copy.deepcopy(spec())
        del none["comp"]["shock"]
        self.assertFalse(proves(none))
        self.assertFalse(proves({"engine": "fx", "recipe": "ring"}))

    def test_no_method_of_the_owners_is_missing_and_the_made_row_is_not_one_of_his(self):
        methods, by = M.load()
        self.assertEqual(len(methods), 104)
        self.assertEqual([m["id"] for m in methods if m["state"] == "missing"], [])
        self.assertNotIn("_made_missing", [m["id"] for m in methods])                      # never listed, never counted
        self.assertEqual(by["_made_missing"]["state"], "missing")                          # but a plan may name it: the refusal stays tested
        doc = json.load(open(M.REGISTER, encoding="utf-8"))
        self.assertTrue(all(r["id"].startswith("_") for r in doc["made_for_tests"]))


if __name__ == "__main__":
    unittest.main()
