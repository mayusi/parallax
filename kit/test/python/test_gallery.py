"""kit/tools/gallery.py - gallery tuning (research proposal 10): the owner's taste over a generator's settings from
picks (the picked candidate beat every other one shown) and rejections (an "All bad"), and the next sheet chosen with it:
likely-good beside informative, spaced apart.
Run: python kit/test/python/run.py -k test_gallery"""

import itertools
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "tools")))
import gallery as G  # noqa: E402

SPACE = G.Space(("time", "weight"), ("arms",))


def pt(t, w, arms="habit:1:out"):
    return {"time": t, "weight": w, "arms": arms}


class ModelTest(unittest.TestCase):
    def test_a_pick_lifts_its_neighbourhood_above_the_others_shown(self):
        shown = [pt(0.8, 0.5), pt(-0.8, -0.5, "habit:0:out"), pt(0.1, 0.9, "technique"), pt(-0.2, -0.9)]
        m = G.Model(SPACE, shown, prefs=[(0, 1), (0, 2), (0, 3)])
        self.assertGreater(m.f[0], max(m.f[1:]))
        mean, _ = m.predict([pt(0.7, 0.5), pt(-0.9, -0.6, "habit:0:out"), pt(0.95, -0.95, "habit:3:x")])
        self.assertGreater(mean[0], 0.3)  # beside the pick
        self.assertLess(mean[1], 0.0)  # beside a candidate it beat
        self.assertGreater(mean[0], mean[2])  # far from anything shown: no opinion
        self.assertAlmostEqual(float(mean[2]), 0.0, delta=0.1)

    def test_all_bad_sinks_its_region_below_unexplored_space(self):
        shown = [pt(0.8, 0.5), pt(0.6, 0.7), pt(0.9, 0.3), pt(0.7, 0.6)]
        m = G.Model(SPACE, shown, bad=[0, 1, 2, 3])
        mean, _ = m.predict(shown + [pt(-0.9, -0.9, "habit:2:up")])
        self.assertTrue(all(v < -0.3 for v in mean[:4]))
        self.assertGreater(mean[4], max(mean[:4]))
        self.assertAlmostEqual(float(mean[4]), 0.0, delta=0.1)

    def test_uncertainty_grows_away_from_anything_shown(self):
        shown = [pt(0.0, 0.0), pt(0.2, 0.1)]
        m = G.Model(SPACE, shown, prefs=[(0, 1)])
        _, std = m.predict([pt(0.0, 0.0), pt(0.5, 0.5), pt(-1.0, 1.0, "technique")])
        self.assertLess(std[0], std[1])
        self.assertLess(std[1], std[2])
        none = G.Model(SPACE, shown)  # no evidence: the prior - no opinion, fully unsure
        mean, std = none.predict([pt(0.0, 0.0)])
        self.assertEqual((float(mean[0]), float(std[0])), (0.0, 1.0))

    def test_each_differing_part_of_a_choice_lowers_the_kernel(self):
        k = G.kernel(SPACE, [pt(0, 0, "habit:1:out")], [pt(0, 0, "habit:1:out"), pt(0, 0, "habit:1:down_back"),
                                                         pt(0, 0, "habit:2:up"), pt(0, 0, "technique")])[0]
        self.assertEqual(float(k[0]), 1.0)
        self.assertGreater(k[1], k[2])  # same habit, another whip > another habit and whip
        self.assertGreater(k[2], k[3])  # another kind of arms altogether: every part differs
        pts = [pt(x, y, a) for x, y, a in [(0, 0, "technique"), (0.3, 0.1, "habit:1:out"), (0.3, 0.1, "habit:1:out"),
                                             (-0.5, 0.2, "prior:0"), (0.9, -0.9, None)]]
        self.assertGreater(float(np.linalg.eigvalsh(G.kernel(SPACE, pts, pts)).min()), -1e-9)  # a valid GP kernel


def line(n):
    """items on a line, the first four nearly the same (cousins)"""
    xs = [0.0, 0.01, 0.02, 0.03] + [0.25 * k for k in range(1, n - 3)]
    return [{"x": x, "s": pt(x, 0.0)} for x in xs]


def dist(a, b):
    return abs(a["x"] - b["x"])


class SelectTest(unittest.TestCase):
    def test_the_sheet_is_spaced_apart_where_the_first_built_were_cousins(self):
        items = line(10)
        chosen, info = G.select(items, 4, lambda it: it["s"], dist)
        self.assertEqual(len(set(chosen)), 4)
        self.assertGreater(G.spread([items[i] for i in chosen], dist)[0], G.spread(items[:4], dist)[0] * 10)
        self.assertTrue(all(v["role"] == "spread" for v in info.values()))  # nothing learned: spread only
        self.assertEqual(chosen[0], 0)  # with no evidence it starts from the first built
        self.assertEqual(G.select(items, 4, lambda it: it["s"], dist), (chosen, info))  # the same sheet every time

    def test_with_evidence_the_sheet_mixes_likely_and_learn(self):
        shown = [pt(0.8, 0.8), pt(-0.8, -0.8), pt(0.8, -0.8), pt(-0.8, 0.8)]
        m = G.Model(SPACE, shown, prefs=[(0, 1), (0, 2), (0, 3)])
        rs = np.random.default_rng(3)
        items = [{"x": i, "s": pt(float(a), float(b))} for i, (a, b) in enumerate(rs.uniform(-1, 1, (24, 2)))]
        chosen, info = G.select(items, 8, lambda it: it["s"], lambda a, b: float(np.hypot(a["s"]["time"] - b["s"]["time"], a["s"]["weight"] - b["s"]["weight"])), model=m)
        roles = [info[i]["role"] for i in chosen]
        self.assertEqual((roles.count("likely"), roles.count("learn")), (4, 4))
        self.assertEqual(roles[0], "likely")  # the best guess first
        lik = [info[i]["mean"] for i in chosen if info[i]["role"] == "likely"]
        lrn = [info[i]["std"] for i in chosen if info[i]["role"] == "learn"]
        others = [i for i in range(24) if i not in chosen]
        mean, std = m.predict([items[i]["s"] for i in others])
        self.assertGreater(np.mean(lik), np.mean(mean))  # the likely ones are the better guesses
        self.assertGreater(np.mean(lrn), np.mean(std))  # the learn ones are where it knows least

    def test_a_group_keeps_its_share_while_others_have_items_then_fills_the_sheet(self):
        items = [{"x": i * 0.1, "g": 0} for i in range(10)] + [{"x": 5 + i * 0.1, "g": 1} for i in range(2)] + [{"x": 9.0, "g": 2}]
        chosen, _ = G.select(items, 6, lambda it: {}, dist, group=lambda it: it["g"], cap=2)
        per = [sum(1 for i in chosen if items[i]["g"] == g) for g in range(3)]
        self.assertEqual(len(chosen), 6)
        self.assertEqual(per[1:], [2, 1])  # the small groups are all in
        self.assertEqual(per[0], 3)  # the big group past its cap only to fill the sheet

    def test_the_sheet_is_the_widest_the_pool_allows(self):
        # the greedy turns from the first built: 0, then 10, then 4 (a tie with 6: the earlier), then 6 - closest pair
        # 2; the widest sheet of 4 from 0 is 0, 3, 6, 10 - closest pair 3 (2026-11-09: DTDrillSpin round 4's turns
        # left 8.5 deg where its pool held 12.6)
        items = [{"x": x, "s": pt(0.0, 0.0)} for x in (0.0, 3.0, 4.0, 6.0, 10.0)]
        chosen, info = G.select(items, 4, lambda it: it["s"], dist)
        self.assertEqual(chosen[0], 0)
        self.assertEqual(chosen, [0, 4, 3, 1])  # sheet order: the first, then each the farthest from those before it
        self.assertEqual(G.spread([items[i] for i in chosen], dist)[0], 3.0)
        self.assertEqual(min(v["spacing"] for v in info.values()), 3.0)  # the cards' spacing is the final sheet's
        self.assertTrue(all(v["role"] == "spread" for v in info.values()))

    def test_the_widest_sheet_keeps_each_lines_share_and_the_first(self):
        rs = np.random.default_rng(11)

        def d2(a, b):
            return float(np.hypot(*(a["p"] - b["p"])))

        for _ in range(20):
            items = [{"p": p, "g": k % 3} for k, p in enumerate(rs.uniform(-1, 1, (18, 2)))]
            chosen, _ = G.select(items, 6, lambda it: {}, d2, group=lambda it: it["g"], cap=2)
            self.assertEqual(chosen[0], 0)
            self.assertEqual(sorted(items[i]["g"] for i in chosen), [0, 0, 1, 1, 2, 2])

            def closest(sub):
                return min(d2(items[a], items[b]) for k, a in enumerate(sub) for b in sub[k + 1:])

            by = {g: [i for i in range(18) if items[i]["g"] == g] for g in range(3)}
            best = max(closest([0, a] + list(b) + list(c)) for a in by[0][1:]
                       for b in itertools.combinations(by[1], 2) for c in itertools.combinations(by[2], 2))
            self.assertAlmostEqual(closest(chosen), best, places=12)  # every sheet with those shares and that first

    def test_past_its_budget_the_widest_found_so_far_never_below_the_turns(self):
        items = [{"x": x, "s": pt(0.0, 0.0)} for x in (0.0, 3.0, 4.0, 6.0, 10.0)]
        old = G.WIDEST_BUDGET
        try:
            G.WIDEST_BUDGET = 0
            chosen, _ = G.select(items, 4, lambda it: it["s"], dist)
        finally:
            G.WIDEST_BUDGET = old
        self.assertEqual(sorted(chosen), [0, 2, 3, 4])  # the greedy turns' sheet (0, 4, 6, 10), as it was
        self.assertEqual(G.spread([items[i] for i in chosen], dist)[0], 2.0)


class ProposeTest(unittest.TestCase):
    def test_proposals_go_near_the_pick_and_into_the_unknown(self):
        shown = [pt(0.8, 0.8), pt(-0.8, -0.8), pt(0.0, -0.8)]
        m = G.Model(SPACE, shown, prefs=[(0, 1), (0, 2)])
        rs = np.random.default_rng(5)
        sample = [pt(float(a), float(b)) for a, b in rs.uniform(-1, 1, (200, 2))]
        got = G.propose(m, sample, 2, 2)
        self.assertEqual(len(got), 4)
        mean, std = m.predict(got)
        self.assertTrue(all(np.hypot(p["time"] - 0.8, p["weight"] - 0.8) < 0.6 for p in got[:2]))  # likely: by the pick
        self.assertGreater(min(std[2:]), max(std[:2]))  # learn: where it knows least
        self.assertEqual(G.propose(G.Model(SPACE, shown), sample, 2, 2), [])  # nothing learned: nothing proposed


if __name__ == "__main__":
    unittest.main()
