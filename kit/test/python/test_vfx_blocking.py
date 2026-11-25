"""Unit tests of solid blocking for the animatic (kit/vfx/blocking.py; the owner's limitations file, F-R07): where a
solid stands, how much of each gameplay angle it fills, what hides it - by geometry, held to what a pinhole camera says.
Run: python -m pytest kit/test/python/test_vfx_blocking.py -q"""
import hashlib
import json
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import animatic as A  # noqa: E402
import blocking as B  # noqa: E402

FRONT = {"pos": [0, 5, 40], "look": [0, 5, 0], "fov": 60}        # level, 40 studs back, looking down -z
SIDE = {"pos": [40, 5, 0], "look": [0, 5, 0], "fov": 60}


def solid(form, size, at=(0, 0), lift=0):
    return B.checked({"form": form, "size": size, "at": list(at), "lift": lift})


def row(index, beat, s, t=0.0, life=1.0):
    return {"index": index, "beat": beat, "t": t, "life": life, "solid": s}


class TheSolid(unittest.TestCase):
    def test_its_box_stands_on_the_ground(self):
        mid, size = B.box_of(solid("pillar", 8, (3, -2)))
        self.assertEqual((mid, size), ([3.0, 4.0, -2.0], [2.0, 8.0, 2.0]))
        mid, size = B.box_of(solid("slab", 8))
        self.assertEqual((mid, size), ([0.0, 0.5, 0.0], [8.0, 1.0, 8.0]))
        mid, size = B.box_of(solid("ball", 6, lift=2))
        self.assertEqual((mid, size), ([0.0, 5.0, 0.0], [6.0, 6.0, 6.0]))

    def test_what_is_not_a_solid_is_said_in_words(self):
        for bad, word in ((None, '"solid" is'), ({"form": "cone", "size": 4}, '"form" is one of'), ({"form": "ball"}, '"size" is a number'),
                          ({"form": "ball", "size": 0.1}, '"size" is a number'), ({"form": "ball", "size": True}, '"size" is a number'),
                          ({"form": "ball", "size": 4, "at": [1]}, '"at" is [x, z]'), ({"form": "ball", "size": 4, "at": [1, float("nan")]}, '"at" is a number'),
                          ({"form": "ball", "size": 4, "lift": -1}, '"lift" is a number'), ({"form": "ball", "size": 4, "glow": 1}, 'has no "glow"')):
            with self.assertRaises(ValueError) as e:
                B.checked(bad)
            self.assertIn(word, str(e.exception), bad)


class TheCamera(unittest.TestCase):
    def test_a_ball_covers_what_a_pinhole_camera_says(self):
        """a sphere of radius r, d away, straight ahead: its outline is a disc of angular radius asin(r / d)"""
        got = B.seen(FRONT, solid("ball", 10))
        t = math.tan(math.radians(30))
        disc = math.pi * math.tan(math.asin(5 / 40)) ** 2
        self.assertAlmostEqual(got["share"], disc / (2 * t * 2 * t * 16 / 9), delta=0.003)
        self.assertEqual((got["in_frame"], got["hidden"], got["by"]), (1.0, 0.0, None))

    def test_a_card_facing_one_camera_is_a_line_from_the_side_and_a_solid_is_not(self):
        """why a flat card is not enough: the same pillar covers as much from the side as from the front"""
        p = solid("pillar", 12)
        front, side = B.seen(FRONT, p)["share"], B.seen(SIDE, p)["share"]
        self.assertGreater(front, 0.01)
        self.assertAlmostEqual(front, side, delta=0.002)
        flat = solid("slab", 12)                                       # a plate on the ground, seen level: thin from every side
        self.assertLess(B.seen(FRONT, flat)["share"], 0.4 * front * 12 / 3)

    def test_a_solid_off_to_the_side_is_partly_or_wholly_outside_the_picture(self):
        self.assertEqual(B.seen(FRONT, solid("ball", 6, (0, 0)))["in_frame"], 1.0)
        edge = B.seen(FRONT, solid("ball", 6, (41, 0)))              # the picture's edge is 41 studs out at this distance
        self.assertTrue(0.3 < edge["in_frame"] < 0.7, edge)
        gone = B.seen(FRONT, solid("ball", 6, (90, 0)))
        self.assertEqual((gone["in_frame"], gone["share"]), (0.0, 0.0))
        behind = B.seen(FRONT, solid("ball", 6, (0, 80)))             # behind the camera
        self.assertEqual((behind["in_frame"], behind["share"]), (0.0, 0.0))

    def test_a_nearer_solid_hides_a_farther_one_from_one_angle_and_not_from_another(self):
        far, near = solid("ball", 3, (0, -10)), solid("pillar", 16, (0, 10))
        front = B.seen(FRONT, far, [near])
        self.assertGreater(front["hidden"], 0.5)
        self.assertEqual(front["by"], 0)
        self.assertEqual(B.seen(SIDE, far, [near])["hidden"], 0.0)   # side by side from there
        self.assertEqual(B.seen(FRONT, near, [far])["hidden"], 0.0)  # the one in front is not hidden by the one behind

    def test_solids_that_meet(self):
        self.assertTrue(B.touching(solid("ball", 4), solid("slab", 8)))               # a ball on a plate's place
        self.assertTrue(B.touching(solid("pillar", 8, (3, 0)), solid("pillar", 8, (5, 0))))
        self.assertFalse(B.touching(solid("pillar", 8, (0, 0)), solid("pillar", 8, (5, 0))))
        self.assertFalse(B.touching(solid("ball", 4, lift=6), solid("slab", 8)))      # floating over it


class TheAngles(unittest.TestCase):
    def test_every_solid_beat_is_reported_from_every_angle(self):
        rows = [row(0, "strike", solid("pillar", 12)), row(1, "crater", solid("slab", 14), t=0.5), {"index": 2, "beat": "flash", "t": 0.6, "life": 0.2}]
        report, problems = B.angles(rows, {"front": FRONT, "side": SIDE})
        self.assertEqual(problems, [])
        self.assertEqual(sorted(report), ["front", "side"])
        self.assertEqual([r["beat"] for r in report["front"]], ["strike", "crater"])   # the flat beat is not a solid
        strike = report["front"][0]
        self.assertTrue(strike["grounded"])
        self.assertEqual(strike["touches"], ["crater"])
        self.assertGreater(strike["share"], 0.01)

    def test_a_beat_an_angle_cannot_show_is_a_problem_in_words(self):
        rows = [row(0, "far", solid("ball", 6, (90, 0))), row(1, "tiny", solid("ball", 0.5, (0, -200))),
                row(2, "back", solid("ball", 6, (0, -10))), row(3, "wall", solid("pillar", 16, (0, 10)))]
        _, problems = B.angles(rows, {"front": FRONT})
        text = " | ".join(problems)
        self.assertIn("beat far (a ball of 6 studs) from the front angle: none of it is in the picture", text)
        self.assertIn("beat tiny", text)
        self.assertIn("a speck", text)
        self.assertIn("beat back", text)
        self.assertIn("is hidden behind beat wall", text)
        self.assertEqual(len(problems), 3)

    def test_solids_that_are_not_alive_together_do_not_hide_each_other(self):
        rows = [row(0, "back", solid("ball", 6, (0, -10)), t=0.0, life=0.5), row(1, "wall", solid("pillar", 16, (0, 10)), t=1.0, life=0.5)]
        report, problems = B.angles(rows, {"front": FRONT})
        self.assertEqual(problems, [])
        self.assertEqual(report["front"][0]["hidden"], 0.0)
        self.assertEqual(report["front"][0]["touches"], [])

    def test_a_floating_solid_is_said_not_to_touch_the_ground(self):
        report, _ = B.angles([row(0, "orb", solid("ball", 6, lift=4))], {"front": FRONT})
        self.assertFalse(report["front"][0]["grounded"])


class WhatTheReviewFound(unittest.TestCase):
    def test_a_pillar_is_the_cylinder_it_is_drawn_as(self):
        """tested as its box it was 1.38 times too wide from a corner-on view, and the plan's share 38 % over what is drawn"""
        p = solid("pillar", 12)                                                         # 3 across, 12 tall
        t = math.tan(math.radians(30))
        got = B.seen(FRONT, p)["share"]
        want = (3 / 40) * (12 / 40) / (2 * t * 2 * t * 16 / 9)                          # a cylinder's outline is its width x its height, from any side
        self.assertAlmostEqual(got, want, delta=0.2 * want)                             # (rays 0.4 studs apart there, and the near side looms a little)
        corner = {"pos": [28.28, 5, 28.28], "look": [0, 5, 0], "fov": 60}               # 40 studs away, corner-on to its box
        self.assertAlmostEqual(B.seen(corner, p)["share"], got, delta=0.1 * got)

    def test_a_solid_that_fills_the_picture_is_seen_though_most_of_it_is_outside(self):
        rows = [row(0, "beam", solid("pillar", 60)), row(1, "crater", solid("slab", 40), t=2.0)]
        report, problems = B.angles(rows, {"hero": A.view_of("hero"), "combat": A.view_of("combat")})
        self.assertEqual(problems, [])
        self.assertLess(report["hero"][0]["in_frame"], 0.5)                             # it runs out of the top of the frame
        self.assertGreater(report["hero"][0]["share"], B.FILLS)

    def test_a_camera_inside_a_solid_is_said(self):
        _, problems = B.angles([row(0, "floor", solid("slab", 80))], {"hero": A.view_of("hero")})
        self.assertEqual(len(problems), 1)
        self.assertIn("the camera is INSIDE it", problems[0])
        self.assertTrue(B.holds(solid("ball", 10), [0, 5, 0]) and not B.holds(solid("ball", 10), [0, 11, 0]))
        self.assertTrue(B.holds(solid("pillar", 8), [0.9, 4, 0]) and not B.holds(solid("pillar", 8), [0.9, 4, 0.9]))   # round: its box's corner is outside it

    def test_a_camera_that_looks_straight_down_is_not_an_angle(self):
        _, problems = B.angles([row(0, "orb", solid("ball", 6))], {"above": {"pos": [0, 50, 0], "look": [0, 0, 0], "fov": 60}})
        self.assertEqual(len(problems), 1)
        self.assertIn("the above angle: a camera that looks straight up or down", problems[0])


class TheAnimatic(unittest.TestCase):
    """a chart's solid beat through the animatic's own plan (kit/vfx/animatic.py)"""

    BEATS = [{"beat": "strike", "t": 0.2, "len": 0.6, "key": True, "solid": {"form": "pillar", "size": 14}},
             {"beat": "crater", "t": 0.2, "len": 0.8, "solid": {"form": "slab", "size": 16}},   # (at the strike's own moment: a beat ends where the next starts)
             {"beat": "spark", "t": 0.9, "len": 0.3}]

    def rows(self, beats=None):
        beats = self.BEATS if beats is None else beats
        return A.plan_rows(beats, [None] * len(beats), 2.0)

    def test_a_chart_with_no_solid_beat_is_the_plan_it_always_was(self):
        flat = [{k: v for k, v in b.items() if k != "solid"} for b in self.BEATS]
        rows = self.rows(flat)
        view = A.view_of("hero")
        self.assertEqual(A.block_solids(rows, "hero", view), ({}, [], []))
        self.assertTrue(all("solid" not in r for r in rows))
        # the id by the rule as it was before solids (written out here): the same
        core = [[r["beat"], r["t"], r["life"], r["hold"], r["slow"], r["arrive"], r["go"], r["on"], r.get("step"), r["share"], r["shape"], r["key"]] for r in rows]
        text = json.dumps([A.GENERATOR, "s", "hero", [view["pos"], view["look"], view["fov"]], 2.0, core, None, None], sort_keys=True)
        self.assertEqual(A.plan_id("s", rows, "hero", 2.0, None, None, view), hashlib.sha1(text.encode("utf-8")).hexdigest()[:12])
        self.assertEqual(A.preset_of("s", rows, "hero", view, 2.0, None)["booth"], {"views": ["hero"]})
        _, problems, _ = A.block_solids(rows, "hero", view, ["combat"])
        self.assertIn("this chart has none", problems[0])                               # --angles on a chart of cards: said

    def test_a_solid_beat_is_worked_out_from_its_own_view_and_the_gameplay_angle(self):
        rows = self.rows()
        self.assertEqual(rows[0]["solid"], {"form": "pillar", "size": 14.0, "at": [0.0, 0.0], "lift": 0.0})
        report, problems, names = A.block_solids(rows, "hero", A.view_of("hero"))
        self.assertEqual((problems, names), ([], ["hero", "combat"]))                    # `combat` unless said
        self.assertEqual([r["beat"] for r in report["combat"]], ["strike", "crater"])
        strike = report["hero"][0]
        self.assertEqual(rows[0]["share"], round(max(0.004, min(strike["share"], 0.95)), 4))   # its share is what the view sees of it
        self.assertIn("a solid (pillar, 14 studs)", rows[0]["notes"][-1])
        self.assertTrue(strike["grounded"] and strike["touches"] == ["crater"])
        _, _, names = A.block_solids(self.rows(), "hero", A.view_of("hero"), ["side", "combat"])
        self.assertEqual(names, ["hero", "side", "combat"])

    def test_a_solid_or_an_angle_that_cannot_be_is_a_problem_in_words(self):
        bad = self.rows([{"beat": "strike", "t": 0.2, "len": 0.6, "solid": {"form": "cone", "size": 4}}])
        self.assertIn('beat strike: the solid\'s "form" is one of', bad[0]["problem"])
        rows = self.rows([{"beat": "far", "t": 0.2, "len": 0.6, "solid": {"form": "ball", "size": 4, "at": [400, 0]}}])
        _, problems, _ = A.block_solids(rows, "hero", A.view_of("hero"))
        self.assertTrue(any("beat far" in x and "in the picture" in x for x in problems), problems)
        _, problems, _ = A.block_solids(self.rows(), "hero", A.view_of("hero"), ["nowhere"])
        self.assertEqual(problems, ["no camera view 'nowhere' in kit/vfx/views.json"])

    def test_the_plan_is_another_when_a_solid_or_an_angle_changes(self):
        view = A.view_of("hero")

        def plan(beats, asked=None):
            rows = self.rows(beats)
            _, _, names = A.block_solids(rows, "hero", view, asked)
            return A.plan_id("s", rows, "hero", 2.0, None, None, view, names)

        base = plan(self.BEATS)
        self.assertEqual(base, plan(self.BEATS))
        moved = [dict(self.BEATS[0], solid={"form": "pillar", "size": 14, "at": [2, 0]})] + self.BEATS[1:]
        self.assertNotEqual(base, plan(moved))
        self.assertNotEqual(base, plan(self.BEATS, ["side"]))
        self.assertNotEqual(base, plan([{k: v for k, v in b.items() if k != "solid"} for b in self.BEATS]))

    def test_what_the_record_keeps_gives_the_same_plan_back(self):
        """--angles hero (the filmed view itself) was read back as "nothing asked": the plan read stale the moment it was made"""
        view = A.view_of("hero")
        for asked in (None, ["hero"], ["combat"], ["cine", "combat"], ["combat", "combat"], ["hero", "cine"]):
            rows = self.rows()
            _, _, names = A.block_solids(rows, "hero", view, asked)
            made = A.plan_id("s", rows, "hero", 2.0, None, None, view, names)
            kept = list(asked or [])                                                    # what the record keeps: "angles_asked"
            again = self.rows()
            _, _, names2 = A.block_solids(again, "hero", view, kept or None)
            self.assertEqual(A.plan_id("s", again, "hero", 2.0, None, None, view, names2), made, asked)

    def test_the_plan_is_another_when_an_angles_camera_moves(self):
        view = A.view_of("hero")
        rows = self.rows()
        _, _, names = A.block_solids(rows, "hero", view)
        before = A.plan_id("s", rows, "hero", 2.0, None, None, view, names)
        old = A.view_of
        A.view_of = lambda name: dict(old(name), pos=[30, 9, 24]) if name == "combat" else old(name)
        try:
            self.assertNotEqual(A.plan_id("s", rows, "hero", 2.0, None, None, view, names), before)
        finally:
            A.view_of = old
        self.assertEqual(A.plan_id("s", rows, "hero", 2.0, None, None, view, names), before)

    def test_a_solid_is_a_real_shape_in_the_effects_place_and_the_kit_takes_the_preset(self):
        rows = self.rows()
        view = A.view_of("hero")
        _, _, names = A.block_solids(rows, "hero", view)
        preset = A.preset_of("s", rows, "hero", view, 2.0, None, {0: 1.3}, names)
        pillar, slab, card = preset["layers"]
        self.assertEqual((pillar["shape"], slab["shape"], card["shape"]), ("Cylinder", "Block", "disc"))
        self.assertEqual(pillar["point"], [0.0, 0.0, 0.0])                               # on the ground, in the effect's own place
        self.assertNotIn("aim", pillar)                                                  # upright: not turned to any camera
        self.assertIn("aim", card)
        self.assertEqual(card["point"], A.card_point(view))                              # a card stays near the camera
        full = max(k[1][1] for k in pillar["scale"])
        self.assertAlmostEqual(full, 14.0, places=3)                                     # the chart's size: a recording's correction is a card's
        for (u, size), (u2, move) in zip(pillar["scale"], pillar["move"]):
            self.assertEqual(u, u2)
            self.assertAlmostEqual(move[1], size[1] / 2.0, places=3)                     # its underside stays on the ground as it grows
        self.assertEqual(preset["booth"]["views"], ["hero", "combat"])
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "blocking.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(preset, fh)
            self.assertEqual(A.refused(path), [])                                        # the kit's own preset rules take it


class TheFlow(unittest.TestCase):
    """a solid that MOVES over its beat ("to"): every solid is looked at at its start, its middle and its end"""

    def test_a_moving_solid_is_where_its_beat_has_taken_it(self):
        s = B.checked({"form": "ball", "size": 4, "at": [-10, 0], "to": [10, 6]})
        self.assertEqual(B.placed(s, 0)["at"], [-10.0, 0.0])
        self.assertEqual(B.placed(s, 0.5)["at"], [0.0, 3.0])
        self.assertEqual(B.placed(s, 1)["at"], [10.0, 6.0])
        self.assertEqual(B.placed(s, 7)["at"], [10.0, 6.0])              # past its end: where it ended
        self.assertAlmostEqual(B.travel(s), math.hypot(20, 6))
        still = solid("ball", 4)
        self.assertIs(B.placed(still, 0.5), still)                       # one that says no "to" stands
        self.assertEqual(B.travel(still), 0.0)
        self.assertNotIn("to", still)                                    # and its dict is the one it always was (the same plan id)
        with self.assertRaises(ValueError):
            B.checked({"form": "ball", "size": 4, "to": [1]})

    def test_where_a_place_is_in_the_picture(self):
        self.assertEqual(B.project(FRONT, [0, 5, 0]), [0.0, 0.0])        # what the camera looks at: the middle
        right, up = B.project(FRONT, [10, 5, 0]), B.project(FRONT, [0, 15, 0])
        self.assertGreater(right[0], 0.1)
        self.assertEqual(right[1], 0.0)
        self.assertGreater(up[1], 0.1)
        t = math.tan(math.radians(30))
        self.assertAlmostEqual(up[1], 10 / 40 / t, places=3)             # a pinhole camera's own sum
        self.assertIsNone(B.project(FRONT, [0, 5, 80]))                  # behind the camera

    def test_a_solid_that_crosses_the_picture_reports_the_way_it_goes(self):
        rows = [row(0, "wave", B.checked({"form": "ball", "size": 5, "at": [-12, 0], "to": [12, 0]}))]
        report, problems = B.angles(rows, {"front": FRONT, "side": SIDE})
        self.assertEqual(problems, [])
        flow = report["front"][0]["flow"]
        self.assertEqual(flow["travel"], 24.0)
        self.assertLess(flow["from"][0], -0.2)                           # from the left of the picture ...
        self.assertGreater(flow["to"][0], 0.2)                           # ... to the right
        self.assertEqual(len(flow["looks"]), 11)                         # eleven moments, from its start to its end
        self.assertEqual([flow["looks"][k]["at"] for k in (0, 5, 10)], ["at its start", "at its middle", "at its end"])
        self.assertEqual(flow["most"], max(g["share"] for g in flow["looks"]))
        side = report["side"][0]["flow"]
        self.assertAlmostEqual(side["from"][0], 0.0, places=2)           # from the side it comes straight at the camera:
        self.assertAlmostEqual(side["to"][0], 0.0, places=2)             # it does not cross that picture at all

    def test_a_solid_that_leaves_the_picture_on_its_way_is_refused_at_that_moment(self):
        rows = [row(0, "shot", B.checked({"form": "ball", "size": 4, "at": [0, 0], "to": [60, 0]}))]   # in the picture half way, out of it at its end
        _, problems = B.angles(rows, {"front": FRONT})
        self.assertEqual(len(problems), 1)
        self.assertRegex(problems[0], r"\d+ % of its way along|at its end")     # WHERE on its way it is lost, said
        self.assertIn("in the picture", problems[0])
        self.assertNotIn("at its start", problems[0])
        rows[0]["solid"]["to"] = [8, 0]                                  # a shorter way: it stays in the picture
        self.assertEqual(B.angles(rows, {"front": FRONT})[1], [])

    def test_a_moving_solid_is_hidden_only_while_it_is_behind_another(self):
        wall = row(0, "wall", solid("pillar", 40, (0, 12)))
        runner = row(1, "runner", B.checked({"form": "ball", "size": 6, "at": [-30, -6], "to": [30, -6]}))
        report, problems = B.angles([wall, runner], {"front": FRONT})
        looks = {g["at"]: g for g in report["front"][1]["flow"]["looks"]}
        self.assertEqual(looks["at its start"]["hidden"], 0.0)           # beside the wall: seen
        self.assertGreater(looks["at its middle"]["hidden"], 0.9)        # behind it: hidden, and the row says the worst
        self.assertEqual(report["front"][1]["by"], "wall")
        self.assertTrue(any("hidden behind" in p and "beat runner" in p for p in problems))

    def test_what_happens_between_its_start_its_middle_and_its_end_is_seen_too(self):
        # (three looks let both through: a review) a ball that passes a pillar a quarter of its way along
        ball = row(0, "ball", B.checked({"form": "ball", "size": 5, "at": [-20, 0], "to": [20, 0]}))
        post = row(1, "post", solid("pillar", 12, (-10, 0)))
        report, _ = B.angles([ball, post], {"front": FRONT})
        self.assertEqual(report["front"][0]["touches"], ["post"])       # it meets the post on its way
        # ... and one that passes BEHIND a wide pillar between its start and its middle is hidden there
        wall = row(1, "wall", solid("pillar", 40, (-10, 12)))
        runner = row(0, "runner", B.checked({"form": "ball", "size": 6, "at": [-30, -6], "to": [30, -6]}))
        report, problems = B.angles([runner, wall], {"front": FRONT})
        self.assertGreater(report["front"][0]["hidden"], 0.9)
        self.assertTrue(any("hidden behind" in p and "of its way" in p for p in problems))

    def test_a_chart_in_which_nothing_moves_is_checked_as_it_always_was(self):
        rows = [row(0, "strike", solid("pillar", 14)), row(1, "crater", solid("slab", 16))]
        report, problems = B.angles(rows, {"front": FRONT})
        self.assertEqual(problems, [])
        self.assertNotIn("flow", report["front"][0])
        self.assertEqual(sorted(report["front"][0]), ["beat", "by", "grounded", "hidden", "in_frame", "index", "share", "touches"])


class TheDrawing(unittest.TestCase):
    """the solids DRAWN by the same rays: volume, what hides what, the ground they touch (the player's film has none)"""

    def px(self, img, view, point):
        x, y = B.project(view, point)
        h, w = img.shape[:2]
        return img[int(round((1 - y) / 2 * (h - 1))), int(round((x + 1) / 2 * (w - 1)))].astype(int)

    def test_the_nearer_solid_hides_the_farther_one(self):
        near, far = solid("ball", 6, (0, 10)), solid("pillar", 30, (0, -10))
        red, blue = (250, 40, 40), (40, 40, 250)
        img = B.picture(FRONT, [far, near], {0: blue, 1: red})
        at = self.px(img, FRONT, [0, 3, 10])                             # the ball's middle: in front of the pillar
        self.assertGreater(at[0], at[2] + 60)                            # red, though the pillar was drawn first
        img = B.picture(FRONT, [near, far], {0: red, 1: blue})           # the order they are given in does not matter
        self.assertGreater(self.px(img, FRONT, [0, 3, 10])[0], 120)
        above = self.px(img, FRONT, [0, 20, -10])                        # above the ball: the pillar
        self.assertGreater(above[2], above[0] + 60)

    def test_a_solid_has_volume_its_lit_side_is_brighter(self):
        img = B.picture(FRONT, [solid("ball", 12)], {0: (200, 200, 200)}, (480, 270))
        lit = self.px(img, FRONT, [-2.5, 9.5, 3.5])                      # toward the light (it comes from the upper left)
        dark = self.px(img, FRONT, [3.5, 2.5, 3.5])
        self.assertGreater(int(lit.sum()), int(dark.sum()) + 90)         # (the player films this ball as one flat disc)

    def test_the_ground_is_dark_under_what_stands_on_it_and_less_under_what_floats(self):
        beside = [7.0, 0, 0]                                             # on the ground just beside a ball of 12 at the middle
        bare = self.px(B.picture(FRONT, []), FRONT, beside).sum()
        stands = self.px(B.picture(FRONT, [solid("ball", 12)]), FRONT, beside).sum()
        floats = self.px(B.picture(FRONT, [solid("ball", 12, (0, 0), 30)]), FRONT, beside).sum()
        self.assertLess(stands, bare - 15)
        self.assertGreater(floats, stands + 8)

    def test_the_sheet_and_the_film_show_every_solid_beat_from_every_angle(self):
        import tempfile
        from PIL import Image
        rows = [row(0, "strike", solid("pillar", 14), 0.0, 1.0), row(1, "wave", B.checked({"form": "ball", "size": 5, "at": [-10, 4], "to": [10, 4]}), 0.2, 1.0),
                {"index": 2, "beat": "spark", "t": 1.2, "life": 0.3}]
        with tempfile.TemporaryDirectory() as tmp:
            png = B.sheet(rows, {"front": FRONT, "side": SIDE}, os.path.join(tmp, "s.png"), None, (240, 135))
            self.assertEqual(Image.open(png).size, (480, 270))           # two solid beats down, two angles across; the card has no row
            self.assertIsNone(B.sheet([rows[2]], {"front": FRONT}, os.path.join(tmp, "none.png")))
            mp4 = os.path.join(tmp, "a.mp4")
            import shutil
            if shutil.which("ffmpeg"):
                self.assertTrue(B.film(rows, {"front": FRONT, "side": SIDE}, mp4, 1.5, None, 12, (240, 136)))
                self.assertGreater(os.path.getsize(mp4), 2000)
        live = B.alive(rows, 0.7)
        self.assertEqual([r["beat"] for r, _ in live], ["strike", "wave"])
        self.assertAlmostEqual(live[1][1]["at"][0], 0.0, places=6)       # the wave, half way
        self.assertEqual(live[1][1]["at"][1], 4.0)


class TheAnimaticsFlow(unittest.TestCase):
    def test_a_moving_solids_layer_goes_its_way_and_the_plan_is_another(self):
        beats = [{"beat": "wave", "t": 0.2, "len": 1.0, "key": True, "solid": {"form": "ball", "size": 5, "at": [-10, 4], "to": [10, 4]}}]
        rows = A.plan_rows(beats, [None], 2.0)
        view = A.view_of("hero")
        el = A.layer_of(rows[0], view, None)
        first, last = el["move"][0][1], el["move"][-1][1]
        self.assertEqual((first[0], first[2]), (0, 0))                   # it starts where it stands ...
        self.assertAlmostEqual(last[0], 20.0, places=3)                  # ... and has gone 20 studs along x by its end
        there = [k for k in el["move"] if abs(k[1][0] - 20.0) < 1e-3]
        self.assertGreaterEqual(len(there), 2)                           # it is THERE a drawing before the last key (which is never reached)
        self.assertLess(there[0][0], 1.0)
        report, _, _ = A.block_solids(rows, "hero", view, None)
        self.assertEqual(rows[0]["share"], round(max(0.004, min(report["hero"][0]["flow"]["most"], 0.95)), 4))   # the MOST it covers
        self.assertEqual(el["point"][0], -10.0)
        still = [dict(beats[0], solid={"form": "ball", "size": 5, "at": [-10, 4]})]
        srows = A.plan_rows(still, [None], 2.0)
        self.assertNotEqual(A.plan_id("m", rows, "hero", 2.0, None, None, view, ["hero"]), A.plan_id("m", srows, "hero", 2.0, None, None, view, ["hero"]))
        sel = A.layer_of(srows[0], view, None)
        self.assertTrue(all(k[1][0] == 0 and k[1][2] == 0 for k in sel["move"]))   # one that stands does not drift


if __name__ == "__main__":
    unittest.main()
