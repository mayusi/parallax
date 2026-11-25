"""Unit tests of the rule by which a fracture plan's pieces come to rest (kit/vfx/settle.py).
Run: python -m pytest kit/test/python/test_vfx_settle.py -q"""
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
import fracture as FR  # noqa: E402
import methods as M  # noqa: E402
import settle as S  # noqa: E402

G, DT, HY, HW = 120.0, 1 / 60, 0.25, 2.0


def fly(s, steps=600, dt=DT, g=G, floor=0.0, hy=HY, hw=HW):
    trail = [list(s)]
    for _ in range(steps):
        s = S.step(s, dt, g, floor, hy, hw)
        trail.append(s)
    return trail


def run(mod, argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = mod.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


class TheRule(unittest.TestCase):
    def test_a_thrown_piece_lands_slides_and_lies_flat(self):
        end = fly([0, HY, 0, 8, 20, -3, 0, 0, 5, 2, 0])[-1]
        self.assertEqual(end[10], 1)
        self.assertAlmostEqual(end[1], HY)                              # its middle half a thickness above the floor
        self.assertAlmostEqual(end[6] / math.pi, round(end[6] / math.pi))  # flat: a whole number of half turns
        self.assertEqual((end[3], end[4], end[5], end[8], end[9]), (0, 0, 0, 0, 0))
        self.assertGreater(end[0], 2)                                   # it went where it was thrown (8 studs/s for a third of a second in the air)

    def test_it_never_sinks_into_the_floor(self):
        for s in ([0, HY, 0, 8, 20, -3, 0, 0, 5, 2, 0], [0, 6, 0, 0, -30, 0, 0.7, 0, 9, 0, 0], [0, HY, 0, 40, 2, 0, 0, 0, 0, 0, 0]):
            for st in fly(s):
                low = abs(math.cos(st[6])) * HY + abs(math.sin(st[6])) * HW
                self.assertGreaterEqual(st[1], low - 1e-9)

    def test_a_piece_on_its_edge_is_higher_than_one_lying_flat(self):
        st = S.step([0, 5, 0, 0, 0, 0, math.pi / 2, 0, 0, 0, 0], DT, G, 0.0, HY, HW)
        for _ in range(40):                                             # let it fall onto its edge
            st = S.step(st, DT, G, 0.0, HY, HW)
            if st[1] < HW + 0.2:
                break
        self.assertGreater(st[1], HY * 2)

    def test_each_bounce_is_lower_than_the_one_before(self):
        trail = fly([0, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        tops = [b[1] for a, b, c in zip(trail, trail[1:], trail[2:]) if b[1] > a[1] and b[1] >= c[1] and b[1] > HY + 0.01]
        self.assertGreaterEqual(len(tops), 2)
        self.assertTrue(all(y1 < y0 * 0.5 for y0, y1 in zip([8] + tops, tops)), tops)

    def test_at_rest_it_does_not_move_again(self):
        trail = fly([0, HY, 0, 8, 20, -3, 0, 0, 5, 2, 0], steps=900)
        first = next(i for i, st in enumerate(trail) if st[10] == 1)
        self.assertLess(first, 600)
        self.assertTrue(all(st == trail[first] for st in trail[first:]))

    def test_a_piece_that_was_never_pushed_rests_where_it_sat(self):
        end = fly([3, HY, -2, 0, 0, 0, 0, 0, 0, 0, 0], steps=60)[-1]
        self.assertEqual((end[0], end[2], end[10]), (3, -2, 1))
        self.assertAlmostEqual(end[1], HY)

    def test_the_floor_is_where_it_is_said_to_be(self):
        end = fly([0, 10, 0, 2, 0, 0, 0, 0, 1, 0, 0], floor=7.5)[-1]
        self.assertEqual(end[10], 1)
        self.assertAlmostEqual(end[1], 7.5 + HY)

    def test_the_flight_does_not_depend_much_on_the_frame_rate(self):
        ends = [fly([0, HY, 0, 8, 20, -3, 0, 0, 5, 2, 0], steps=int(6 / dt), dt=dt)[-1] for dt in (1 / 30, 1 / 60, 1 / 144)]
        self.assertTrue(all(e[10] == 1 for e in ends))
        self.assertLess(max(e[0] for e in ends) - min(e[0] for e in ends), 1.0)   # within a stud of each other after ~6

    def test_the_input_state_is_not_changed(self):
        s = [0, HY, 0, 8, 20, -3, 0, 0, 5, 2, 0]
        S.step(s, DT, G, 0.0, HY, HW)
        self.assertEqual(s, [0, HY, 0, 8, 20, -3, 0, 0, 5, 2, 0])


class ThePlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        code, _ = run(FR, ["slab", "--size", "12,10,0.5", "--pieces", "14", "--look-dir", tempfile.gettempdir(), "--out-dir", self.tmp.name, "--look-dir", self.tmp.name])
        self.assertEqual(code, 0)
        with open(os.path.join(self.tmp.name, "slab.json"), encoding="utf-8") as fh:
            self.plan = json.load(fh)

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_piece_of_a_plan_comes_to_rest_flat_and_away(self):
        flown = S.fly(self.plan, 2.5)
        self.assertEqual(len(flown), 14)
        self.assertTrue(all(f["rest_at"] is not None and f["flat"] and abs(f["y"] - 0.25) < 1e-9 for f in flown))
        self.assertGreater(max(f["moved"] for f in flown), 2)

    def test_a_piece_waits_for_the_break_to_reach_it(self):
        late = dict(self.plan, pieces=[dict(self.plan["pieces"][0], delay=1.0)])
        self.assertGreater(S.fly(late, 2.5)[0]["rest_at"], 1.0)

    def test_a_layers_speed_scales_the_push(self):
        slow = max(f["moved"] for f in S.fly(self.plan, 4, speed=10))
        fast = max(f["moved"] for f in S.fly(self.plan, 4, speed=60))
        self.assertGreater(fast, slow * 2)

    def test_the_command_says_when_the_last_piece_rests(self):
        code, said = run(S, ["slab", "--plans-dir", self.tmp.name, "--life", "2.5"])
        self.assertEqual((code, said["status"]), (0, "pass"))
        self.assertTrue(0.2 < said["last_rest"] < 2.0)
        self.assertIn('"rest": true', said["next_action"])

    def test_a_life_too_short_is_refused_with_the_life_that_does_do(self):
        # whatever the too-short life was (the first version worked it out from the pieces that HAD landed in it)
        for short in ("0.3", "0.5", "0.6", "0.8", "0.9"):
            code, said = run(S, ["slab", "--plans-dir", self.tmp.name, "--life", short])
            self.assertEqual(code, 1, short)
            self.assertIn("still moving", said["summary"])
            self.assertRegex(said["next_action"], r"a life of \d+\.\d s or more")
            need = said["next_action"].split("a life of ")[1].split(" s")[0]
            self.assertEqual(run(S, ["slab", "--plans-dir", self.tmp.name, "--life", need])[0], 0, (short, need))

    def test_a_slab_up_high_lands_later(self):
        low = run(S, ["slab", "--plans-dir", self.tmp.name, "--life", "4"])[1]["last_rest"]
        high = run(S, ["slab", "--plans-dir", self.tmp.name, "--life", "4", "--height", "8"])[1]["last_rest"]
        self.assertGreater(high, low)                                                   # (the last rest is the last PUSH now, not the last landing)
        fall = [max(f["rest_at"] for f in S.fly(self.plan, 4, height=h, alone=True)) for h in (0, 8)]
        self.assertGreater(fall[1], fall[0] + 0.2)                                      # the landing itself: later by the fall

    def test_pieces_pushed_flat_along_the_ground_still_count_as_flown(self):
        code, _ = run(FR, ["flat", "--size", "12,10,0.5", "--pieces", "14", "--lift", "0", "--look-dir", tempfile.gettempdir(), "--out-dir", self.tmp.name, "--look-dir", self.tmp.name])
        self.assertEqual(code, 0)
        code, said = run(S, ["flat", "--plans-dir", self.tmp.name, "--life", "3"])
        self.assertEqual(code, 0, said["summary"])

    def test_the_side_that_stands_up_when_a_piece_tips_is_its_z(self):
        # a long thin piece: 6 along x, 1 along z. It tips about its own x, so on edge its middle is half a stud up
        long_x = {"points": [[-3, -0.5], [3, -0.5], [3, 0.5], [-3, 0.5]], "centre": [0, 0], "vel": [0, 0, 0], "spin": [0, 0, 0]}
        long_z = {"points": [[-0.5, -3], [0.5, -3], [0.5, 3], [-0.5, 3]], "centre": [0, 0], "vel": [0, 0, 0], "spin": [0, 0, 0]}
        self.assertEqual(S.start(long_x, 0.5)[2], 0.5)
        self.assertEqual(S.start(long_z, 0.5)[2], 3.0)
        on_edge = S.step([0, 5, 0, 0, -1, 0, math.pi / 2, 0, 0, 0, 0], 1 / 60, 120.0, 0.0, 0.25, 3.0)
        for _ in range(30):
            on_edge = S.step(on_edge, 1 / 60, 120.0, 0.0, 0.25, 3.0)
            self.assertGreaterEqual(on_edge[1], abs(math.cos(on_edge[6])) * 0.25 + abs(math.sin(on_edge[6])) * 3.0 - 1e-9)

    def test_wrong_options_and_missing_plans_are_said_in_words(self):
        for argv, word in ((["nope", "--plans-dir", self.tmp.name], "no fracture plan"), (["slab", "--life", "0"], "--life 0.2..30"),
                           (["slab", "--glide", "1"], "not an option"), ([], "name ONE"), (["slab", "--life"], "no value"),
                           (["slab", "--height", "-2"], "--height 0..500")):
            code, said = run(S, argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, said["summary"], argv)


SQ = [-1, -1, 1, -1, 1, 1, -1, 1]      # a square 2 x 2
BIG = [-3, -2, 3, -2, 3, 2, -3, 2]     # a slab 6 x 4


def together(states, shapes, areas=None, steps=360, dt=DT, base=0.0, hw=None, turn=0.0, unit=1.0):
    """-> (the trail of states, the floor under each at the end)"""
    n = len(states)
    hs, ws, areas = [HY] * n, hw or [1.0] * n, areas or [4.0] * n
    trail, floor = [[list(s) for s in states]], [base] * n
    for _ in range(steps):
        states, floor = S.meet(states, shapes, hs, ws, areas, dt, G * unit, base, turn, unit)
        trail.append(states)
    return trail, floor


def deep(states, shapes, i=0, j=1):
    return S.apart(S.lying(states[i], shapes[i]), S.lying(states[j], shapes[j]))[0]


class PiecesMeet(unittest.TestCase):
    """stage 23: pieces on the ground do not lie IN each other, and a piece that lands on another lies ON it"""

    def lying_still(self, x, z, yaw=0.0, y=HY, rest=0):
        return [x, y, z, 0, 0, 0, 0, yaw, 0, 0, rest]

    def test_the_outline_of_a_lying_piece_turns_with_its_yaw_and_mirrors_on_its_other_face(self):
        tri = [0, 0, 2, 0, 0, 1]
        self.assertEqual(S.lying(self.lying_still(5, 7), tri), [5, 7, 7, 7, 5, 8])
        turned = S.lying(self.lying_still(0, 0, yaw=math.pi / 2), tri)           # Roblox's CFrame.Angles(0, yaw, 0): +x goes to -z
        for got, want in zip(turned, [0, 0, 0, -2, 1, 0]):
            self.assertAlmostEqual(got, want)
        over = self.lying_still(0, 0)
        over[6] = math.pi                                                       # on its other face: its z is mirrored
        for got, want in zip(S.lying(over, tri), [0, 0, 2, 0, 0, -1]):
            self.assertAlmostEqual(got, want)

    def test_how_deep_two_outlines_lie_in_each_other(self):
        a = S.lying(self.lying_still(0, 0), SQ)
        self.assertEqual(S.apart(a, S.lying(self.lying_still(2.5, 0), SQ))[0], 0.0)      # apart
        self.assertEqual(S.apart(a, S.lying(self.lying_still(2.0, 0), SQ))[0], 0.0)      # touching: not in each other
        d, nx, nz = S.apart(a, S.lying(self.lying_still(1.5, 0.2), SQ))
        self.assertAlmostEqual(d, 0.5)
        self.assertAlmostEqual(nx, -1.0)                                                # a goes away from b
        self.assertAlmostEqual(nz, 0.0)
        d, nx, nz = S.apart(S.lying(self.lying_still(1.5, 0.2), SQ), a)
        self.assertAlmostEqual(nx, 1.0)
        back = [v for k in range(len(a) - 2, -1, -2) for v in (a[k], a[k + 1])]           # the same outline, the other way round
        self.assertTrue(S.within(a, 0.9, -0.9) and S.within(back, 0.9, -0.9) and not S.within(a, 1.1, 0) and not S.within(back, 1.1, 0))

    def test_two_pieces_in_each_other_on_the_ground_part_and_then_rest(self):
        start = [self.lying_still(0, 0), self.lying_still(0.7, 0.4, yaw=0.6)]
        self.assertGreater(deep(start, [SQ, SQ]), 1.0)
        trail, _ = together(start, [SQ, SQ])
        end = trail[-1]
        self.assertLessEqual(deep(end, [SQ, SQ]), S.SKIN + 1e-6)
        self.assertGreater(deep(end, [SQ, SQ]), 0.0)                                    # they still touch: pushed apart, not thrown
        self.assertEqual([s[10] for s in end], [1, 1])
        self.assertTrue(all(abs(s[1] - HY) < 1e-9 for s in end))
        for a, b in zip(trail, trail[1:]):                                              # a slide, not a jump
            for p, q in zip(a, b):
                self.assertLessEqual(math.hypot(q[0] - p[0], q[2] - p[2]), S.PART * DT + 1e-9)
        self.assertLess(deep(trail[30], [SQ, SQ]), deep(start, [SQ, SQ]) - 1.0)        # and it does slide: most of the way in half a second
        pushing = [n for n, st in enumerate(trail[1:]) if math.hypot(st[0][0] - trail[n][0][0], st[0][2] - trail[n][0][2]) > 1e-12]
        self.assertTrue(pushing and all(trail[n + 1][0][10] == 0 for n in pushing))    # a piece being pushed is not at rest

    def test_the_lighter_piece_gives_way_more(self):
        start = [self.lying_still(0, 0), self.lying_still(0.9, 0)]
        end = together(start, [SQ, SQ], areas=[12.0, 4.0])[0][-1]
        self.assertAlmostEqual(abs(end[1][0] - 0.9) / abs(end[0][0]), 3.0, places=6)

    def test_pieces_that_only_touch_are_left_alone(self):
        start = [self.lying_still(0, 0), self.lying_still(2.0, 0), self.lying_still(0, 2.0)]   # as they sit in a slab
        end = together(start, [SQ, SQ, SQ], steps=120)[0][-1]
        for a, b in zip(start, end):
            self.assertEqual((a[0], a[2]), (b[0], b[2]))
        self.assertEqual([s[10] for s in end], [1, 1, 1])

    def test_pieces_in_the_air_pass_each_other(self):
        start = [[0, 9, 0, 0, 6, 0, 0, 0, 0, 0, 0], [0.5, 9, 0.2, 0, 6, 0, 0, 0, 0, 0, 0]]
        after = together(start, [SQ, SQ], steps=10)[0][-1]
        self.assertEqual((after[0][0], after[1][0]), (0, 0.5))                           # said plainly: they meet on the ground only

    def test_a_piece_dropped_on_a_piece_at_rest_lies_on_it(self):
        start = [self.lying_still(0, 0, rest=1), [0.5, 6, -0.3, 0, 0, 0, 0, 0.3, 0, 1.5, 0]]
        for dt in (1 / 30, 1 / 60, 1 / 144):
            trail, floor = together(start, [BIG, SQ], steps=int(3 / dt), dt=dt, hw=[2.0, 1.0])
            end = trail[-1]
            self.assertAlmostEqual(floor[1], 2 * HY)                                    # the slab's top is its floor
            self.assertAlmostEqual(end[1][1], 3 * HY)
            self.assertEqual(end[1][10], 1)
            self.assertEqual(end[0][:3], start[0][:3])                                  # the slab under it did not move
            self.assertTrue(all(st[1][1] >= 3 * HY - 1e-9 for st in trail))             # it never sank into the slab

    def test_a_fast_falling_piece_does_not_pass_through_the_piece_under_it(self):
        start = [self.lying_still(0, 0, rest=1), [0, 40, 0, 0, -90, 0, 0, 0, 0, 0, 0]]   # 3 studs a step: six times the slab's thickness
        trail, _ = together(start, [BIG, SQ], steps=400, dt=1 / 30, hw=[2.0, 1.0])
        self.assertTrue(all(st[1][1] >= 3 * HY - 1e-9 for st in trail))
        self.assertAlmostEqual(trail[-1][1][1], 3 * HY)

    def test_a_piece_that_lands_beside_the_middle_of_another_ends_on_the_floor_out_of_it(self):
        start = [self.lying_still(0, 0, rest=1), [3.4, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0]]    # its middle is outside the slab's outline
        self.assertGreater(deep([[0, 0, 0] + [0] * 8, [3.4, 0, 0] + [0] * 8], [BIG, SQ]), 0.5)
        end = together(start, [BIG, SQ], areas=[24.0, 4.0], hw=[2.0, 1.0])[0][-1]
        self.assertAlmostEqual(end[1][1], HY)
        self.assertLessEqual(deep(end, [BIG, SQ]), S.SKIN + 1e-6)
        self.assertEqual([s[10] for s in end], [1, 1])

    def test_a_piece_falls_when_what_it_lay_on_is_gone(self):
        on_top = [0.5, 3 * HY, 0, 0, 0, 0, 0, 0, 0, 0, 1]
        held = together([self.lying_still(0, 0, rest=1), on_top], [BIG, SQ], steps=30, hw=[2.0, 1.0])[0][-1]
        self.assertEqual(held[1], on_top)                                               # at rest on the slab: it stays
        fell = together([on_top], [SQ], steps=120)[0]
        self.assertEqual(fell[1][0][10], 0)
        self.assertAlmostEqual(fell[-1][0][1], HY)
        self.assertEqual(fell[-1][0][10], 1)

    def test_six_pieces_dropped_on_one_place_end_as_a_pile_with_nothing_in_anything(self):
        start = [[0.1 * k, 2 + 2.5 * k, 0.07 * k * k, 0.3 * k, 0, -0.2 * k, 0, 0.5 * k, 2.0 - k, 0.7 * k, 0] for k in range(6)]
        shapes = [SQ, BIG, SQ, SQ, BIG, SQ]
        for dt in (1 / 30, 1 / 60, 1 / 144):
            trail, floor = together(start, shapes, areas=[4, 24, 4, 4, 24, 4], steps=int(5 / dt), dt=dt, hw=[1, 2, 1, 1, 2, 1])
            end = trail[-1]
            self.assertEqual([s[10] for s in end], [1] * 6, dt)
            for i in range(6):
                self.assertAlmostEqual(end[i][1], floor[i] + HY)                        # each lies on its floor: the ground or a top
                for j in range(i + 1, 6):
                    if abs(end[i][1] - end[j][1]) < 1e-4:
                        self.assertLessEqual(deep(end, shapes, i, j), S.SKIN + 1e-6, (dt, i, j))

    def test_in_a_turned_frame_a_piece_on_its_other_face_is_mirrored_about_its_own_z(self):
        """the piece is drawn frame x yaw x tilt: mirrored FIRST, turned after (mirroring the world's z was up to 3 studs off)"""
        tri = [0, 0, 3, 0, 0, 0.6]
        over = self.lying_still(0, 0)
        over[6] = math.pi
        for turn in (0.0, math.pi / 6, math.pi / 2, -2.1):
            c, n = math.cos(turn), math.sin(turn)
            want = []
            for k in range(0, 6, 2):
                px, pz = tri[k], -tri[k + 1]
                want += [px * c + pz * n, -px * n + pz * c]
            for got, w in zip(S.lying(over, tri, turn), want):
                self.assertAlmostEqual(got, w)
            yawed = self.lying_still(0, 0, yaw=turn)
            yawed[6] = math.pi
            for got, w in zip(S.lying(yawed, tri), want):                               # a frame's yaw and a piece's own are one turn
                self.assertAlmostEqual(got, w)

    def test_a_play_at_another_scale_is_the_same_flight_larger(self):
        start = [[0.1 * k, 2 + 2.5 * k, 0.07 * k * k, 0.3 * k, 0, -0.2 * k, 0, 0.5 * k, 2.0 - k, 0.7 * k, 0] for k in range(4)]
        shapes = [SQ, BIG, SQ, SQ]
        small = together(start, shapes, areas=[4, 24, 4, 4], steps=300, hw=[1, 2, 1, 1])[0][-1]
        u = 3.0
        big_start = [[s[0] * u, s[1] * u, s[2] * u, s[3] * u, s[4] * u, s[5] * u, *s[6:]] for s in start]
        hs, ws = [HY * u] * 4, [1 * u, 2 * u, 1 * u, 1 * u]
        st = big_start
        for _ in range(300):
            st, _ = S.meet(st, [[v * u for v in sh] for sh in shapes], hs, ws, [4, 24, 4, 4], DT, G * u, 0.0, 0.0, u)
        for a, b in zip(small, st):
            for k in (0, 1, 2):
                self.assertAlmostEqual(a[k] * u, b[k], places=6)
            self.assertEqual(a[10], b[10])

    def test_a_piece_standing_on_its_edge_holds_nothing_up(self):
        plate = [0, 2.0, 0, 0, 0, 0, 1.2, 0, 0, 0, 0]                                    # tipping: its top is high, its real footprint thin
        beside = [0, 6, 1.5, 0, -1, 0, 0, 0, 0, 0, 0]
        _, floor = S.meet([plate, beside], [BIG, SQ], [HY, HY], [2.0, 1.0], [24, 4], DT, G, 0.0)
        self.assertEqual(floor[1], 0.0)

    def test_a_frame_that_hangs_does_not_throw_pieces_apart(self):
        start = [self.lying_still(0, 0), self.lying_still(0.3, 0.0)]
        new, _ = S.meet(start, [SQ, SQ], [HY, HY], [1, 1], [4, 4], 0.25, G, 0.0)         # a quarter of a second in one step
        for a, b in zip(start, new):
            self.assertLessEqual(abs(b[0] - a[0]), S.PART * S.HITCH + 1e-9)

    def test_pushes_that_cancel_leave_a_piece_at_rest(self):
        mid = self.lying_still(0, 0, rest=1)
        left, right = self.lying_still(-1.97, 0, rest=1), self.lying_still(1.97, 0, rest=1)   # each 0.03 deep in the middle one
        new, _ = S.meet([left, mid, right], [SQ, SQ, SQ], [HY] * 3, [1] * 3, [4000, 4, 4000], DT, G, 0.0)
        self.assertEqual((new[1][0], new[1][10]), (0, 1))                                # squeezed from both sides: it does not creep, and it rests

    def test_the_states_given_are_not_changed(self):
        start = [self.lying_still(0, 0), self.lying_still(0.7, 0.4)]
        before = json.dumps(start)
        S.meet(start, [SQ, SQ], [HY, HY], [1, 1], [4, 4], DT, G, 0.0)
        self.assertEqual(json.dumps(start), before)

    def test_one_piece_alone_flies_as_it_always_did(self):
        s = [0, HY, 0, 8, 20, -3, 0, 0, 5, 2, 0]
        for a in fly(s, steps=300)[1:]:
            s = S.meet([s], [SQ], [HY], [HW], [4.0], DT, G, 0.0)[0][0]
            self.assertEqual(s, a)


class ThePlanMeets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.assertEqual(run(FR, ["slab", "--size", "12,10,0.5", "--pieces", "14", "--look-dir", tempfile.gettempdir(), "--out-dir", self.tmp.name, "--look-dir", self.tmp.name])[0], 0)
        with open(os.path.join(self.tmp.name, "slab.json"), encoding="utf-8") as fh:
            self.plan = json.load(fh)

    def tearDown(self):
        self.tmp.cleanup()

    def test_flown_one_by_one_the_pieces_end_in_each_other_and_together_they_do_not(self):
        self.assertGreater(max(f["deep"] for f in S.fly(self.plan, 2.5, alone=True)), 0.5)
        for fps in S.RATES:
            flown = S.fly(self.plan, 2.5, fps=fps)
            self.assertLessEqual(max(f["deep"] for f in flown), S.SKIN + 1e-6, fps)
            self.assertTrue(all(f["rest_at"] is not None for f in flown), fps)
        rows, _ = S.check(S.fly(self.plan, 2.5, alone=True), 2.5)
        self.assertEqual([c["name"] for c in rows if not c["ok"]], ["lies_apart"])

    def test_many_thin_pieces_come_to_rest_and_do_not_creep_for_ever(self):
        """a jammed cluster's pushes cancel: before, 64 thin pieces 'rested' after 12 seconds, or never"""
        tmp = self.tmp.name
        self.assertEqual(run(FR, ["thin", "--size", "20,12,0.1", "--pieces", "64", "--speed", "10", "--lift", "0.8", "--look-dir", tempfile.gettempdir(), "--out-dir", tmp, "--look-dir", tmp])[0], 0)
        with open(os.path.join(tmp, "thin.json"), encoding="utf-8") as fh:
            thin = json.load(fh)
        for fps in S.RATES:
            flown = S.fly(thin, 6.0, fps=fps)
            self.assertTrue(all(f["rest_at"] is not None and f["rest_at"] < 4.0 for f in flown), fps)
            self.assertLessEqual(max(f["deep"] for f in flown), 2 * S.SKIN, fps)

    def test_a_slab_that_only_drops_stays_whole(self):
        still = dict(self.plan, pieces=[dict(p, vel=[0, 0, 0], spin=[0, 0, 0], delay=0) for p in self.plan["pieces"]])
        flown = S.fly(still, 1.0, height=3.0)
        self.assertLess(max(f["moved"] for f in flown), 0.03)                           # cut pieces only touch: nothing pushes them
        self.assertTrue(all(f["rest_at"] is not None for f in flown))

    def test_the_command_tries_three_frame_rates_and_says_so(self):
        code, said = run(S, ["slab", "--plans-dir", self.tmp.name, "--life", "2.5"])
        self.assertEqual(code, 0, said)
        self.assertIn("30, 60, 144 frames a second", said["summary"])
        self.assertIn("no two lie in each other", said["summary"])
        one = run(S, ["slab", "--plans-dir", self.tmp.name, "--life", "2.5", "--fps", "60"])[1]
        self.assertIn("flown at 60 frames a second", one["summary"])
        self.assertGreaterEqual(said["last_rest"], one["last_rest"])                    # the latest of the three


class TheRegister(unittest.TestCase):
    def test_rigid_body_is_the_engines_own_bodies_and_the_kits_rest_where_there_is_no_physics(self):
        _, by = M.load()
        m = by["rigid_body"]
        self.assertEqual(m["state"], "has")                             # "floor": "world" = the engine's own rigid bodies (seen in a play client)
        self.assertIn('"floor": "world"', m["how"])
        self.assertIn("do not meet in the air", m["how"])               # the kit's own rest, and what it is not: still said
        self.assertTrue(M.layer_proves({"kind": "debris", "where": {"floor": ["world"]}}, {"kind": "debris", "floor": "world", "pieces": "x"}, None))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run(FR, ["slab_a", "--size", "12,10,0.5", "--pieces", "14", "--look-dir", tempfile.gettempdir(), "--out-dir", os.path.join(tmp, "fractures"), "--look-dir", tmp])[0], 0)
            with open(os.path.join(tmp, "fractures", "stub.json"), "w", encoding="utf-8") as fh:
                json.dump({"pieces": [{"delay": 0.0}, {"delay": 0.1}]}, fh)   # a plan with nothing to fly

            class Empty:
                def get(self, key):
                    return None

            def proved(layer):
                return M.proved(m, [dict({"kind": "debris", "life": 2}, **layer)], Empty(), tmp, "s") is not None

            self.assertTrue(proved({"pieces": "slab_a", "rest": True}))
            self.assertTrue(proved({"pieces": "slab_a", "rest": True, "life": 2.5, "speed": 30}))
            # stage 23: the layer's own flight is flown - a life too short for the pieces to land and part proves nothing
            self.assertFalse(proved({"pieces": "slab_a", "rest": True, "life": 0.6}))
            self.assertFalse(proved({"pieces": "slab_a", "rest": True, "gravity": 4}))      # so little gravity that they are still up at the fade
            self.assertFalse(proved({"pieces": "stub", "rest": True}))
            self.assertIn("comes to rest before the fade", M.say_proof(m))
            self.assertFalse(proved({"pieces": "slab_a"}))                  # pieces that shrink away in the air
            self.assertFalse(proved({"pieces": "slab_a", "rest": False}))
            self.assertFalse(proved({"pieces": "typo", "rest": True}))
            self.assertFalse(proved({"shape": "rock", "count": 8}))         # thrown rocks


if __name__ == "__main__":
    unittest.main()


def test_a_slower_push_turns_the_pieces_slower_too():
    """a review leftover (stage 23): a layer's speed scaled the plan's push but not its spin - a slab played slow
    still turned its pieces into each other"""
    import settle as S
    piece = {"points": [[-1, -1], [1, -1], [1, 1], [-1, 1]], "centre": [0, 0], "vel": [4, 6, 2], "spin": [3.0, -2.0, 1.0]}
    full = S.start(piece, 1.0, 1.0)[0]
    slow = S.start(piece, 1.0, 0.25)[0]
    assert (full[8], full[9]) == (3.0, -2.0)
    assert (slow[8], slow[9]) == (0.75, -0.5)
    assert slow[3:6] == [1.0, 1.5, 0.5]


def test_the_gate_flies_a_lifted_slab_from_its_height():
    """a review leftover (stage 23): the method gate took every slab to sit ON the floor - a layer whose point lifts it
    lands later, and a life that is long enough on the floor is not long enough from up there"""
    import methods as M
    import settle as S
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "fractures"))
        plan = FR.plan(FR.slab(12, 12), {"pieces": 14, "seed": 3}) if hasattr(FR, "slab") else None
        if plan is None:
            import subprocess
            subprocess.run([sys.executable, os.path.join(HERE, "..", "..", "vfx", "fracture.py"), "lift", "--size", "12,12,1", "--look-dir", tempfile.gettempdir(), "--out-dir",
                            os.path.join(d, "fractures")], capture_output=True, check=True)
        else:
            json.dump(plan, open(os.path.join(d, "fractures", "lift.json"), "w"))
        plan = json.load(open(os.path.join(d, "fractures", "lift.json")))
        ground = max(r["rest_at"] or 99 for r in S.fly(plan, 6.0, 120.0, None, 60, 0.0))
        high = max(r["rest_at"] or 99 for r in S.fly(plan, 6.0, 120.0, None, 60, 60.0))
        assert high > ground + 0.3                                  # from 60 studs up it lands later
        life = (ground + high) / 2 / 0.85                           # long enough on the floor, too short from up there
        on_floor = {"kind": "debris", "pieces": "lift", "rest": True, "life": life, "point": [0, 0, 0]}
        lifted = dict(on_floor, point=[0, 60, 0])
        assert M.plan_rests(on_floor, "pieces", d) is True
        assert M.plan_rests(lifted, "pieces", d) is False


def test_a_still_pile_stays_still_so_the_runtimes_may_stop_stepping_it():
    """the premise of the early stop (a review leftover, stage 23: the rule ran every frame also when all lay still):
    once a step leaves every piece exactly as it was and at rest, a further step - at any frame time - changes nothing"""
    import settle as S
    with tempfile.TemporaryDirectory() as d:
        import subprocess
        subprocess.run([sys.executable, os.path.join(HERE, "..", "..", "vfx", "fracture.py"), "pile", "--size", "12,12,1", "--look-dir", tempfile.gettempdir(), "--out-dir", d],
                       capture_output=True, check=True)
        plan = json.load(open(os.path.join(d, "pile.json")))
    thick = plan["size"][2]
    made = [S.start(pc, thick) for pc in plan["pieces"]]
    st, H, W, shapes = [m[0] for m in made], [m[1] for m in made], [m[2] for m in made], [m[3] for m in made]
    A = [max(float(pc.get("area") or 0), 1e-6) for pc in plan["pieces"]]
    for _ in range(900):
        new, _ = S.meet(st, shapes, H, W, A, 1 / 60, 120.0, 0.0)
        if all(s[10] == 1 for s in new) and new == st:
            break
        st = new
    else:
        raise AssertionError("the pile never lay still")
    for dt in (1 / 30, 1 / 60, 1 / 144, 0.2):
        again, _ = S.meet(new, shapes, H, W, A, dt, 120.0, 0.0)
        assert again == new


def test_a_piece_too_thin_to_be_met_is_refused():
    """a review leftover (stage 23): a piece thinner than the rule's skin lies inside another unparted, and three points
    on a line are 'under' every place on their line - the cut refuses them, and so does the gate on a hand-edited plan"""
    import methods as M
    import settle as S
    assert FR.MEET_WIDE > 2 * S.SKIN
    with tempfile.TemporaryDirectory() as d:
        import subprocess
        tiny = subprocess.run([sys.executable, os.path.join(HERE, "..", "..", "vfx", "fracture.py"), "tiny", "--size", "0.5,0.5", "--pieces", "64",
                               "--look-dir", tempfile.gettempdir(), "--out-dir", d], capture_output=True, text=True)
        said = json.loads(tiny.stdout.strip().splitlines()[-1])
        assert said["status"] == "fail" and "meets" in said["summary"], said["summary"]
        subprocess.run([sys.executable, os.path.join(HERE, "..", "..", "vfx", "fracture.py"), "ok", "--size", "12,12,1", "--look-dir", tempfile.gettempdir(), "--out-dir",
                        os.path.join(d, "fractures")], capture_output=True, check=True)
        plan = json.load(open(os.path.join(d, "fractures", "ok.json")))
        layer = {"kind": "debris", "pieces": "ok", "life": 3, "speed": 30}
        assert M.plan_flies(layer, "pieces", d) is True
        plan["pieces"][0]["points"] = [[0, 0], [1, 0], [2, 0]]          # a line of three points
        json.dump(plan, open(os.path.join(d, "fractures", "ok.json"), "w"))
        assert M.plan_flies(layer, "pieces", d) is False


def test_a_speed_of_0_pushes_nothing_and_a_named_or_far_point_does_not_pass_the_gate():
    """the review of stage 46: settle took a speed of 0 as no speed (a push of 1) where the game and the player push
    nothing; and the gate flew a slab with a named point, or one 600 studs up, as if it sat on the floor"""
    import methods as M
    import settle as S
    piece = {"points": [[-1, -1], [1, -1], [1, 1], [-1, 1]], "centre": [0, 0], "vel": [4, 6, 2], "spin": [3.0, -2.0, 1.0]}
    plan = {"size": [2, 2, 0.5], "made": {"speed": 30}, "pieces": [dict(piece, delay=0)]}
    flown = S.fly(plan, 2.0, 120.0, 0.0, 60)
    assert flown[0]["moved"] == 0 and flown[0]["top"] == 0.25          # no push: it lies where it sat
    with tempfile.TemporaryDirectory() as d:
        import subprocess
        subprocess.run([sys.executable, os.path.join(HERE, "..", "..", "vfx", "fracture.py"), "far", "--size", "12,12,1", "--look-dir", tempfile.gettempdir(), "--out-dir",
                        os.path.join(d, "fractures")], capture_output=True, check=True)
        on_floor = {"kind": "debris", "pieces": "far", "rest": True, "life": 6.0, "point": [0, 0, 0]}
        assert M.plan_rests(on_floor, "pieces", d) is True
        assert M.plan_rests(dict(on_floor, point="top"), "pieces", d) is False
        assert M.plan_rests(dict(on_floor, point=[0, 600, 0]), "pieces", d) is False


def test_a_thin_slanted_piece_is_measured_exactly_and_a_step_of_0_parts_nothing():
    """the review of stage 48: the width was sampled 72 ways (a thin piece between two of them passed), and the early
    stop could be taken from a step of 0 (a hit-stop), in which pieces lying in each other are not parted"""
    import math as m
    import settle as S
    t = m.tan(m.radians(1.25))
    assert FR.measure([[0, 0], [1, t], [3, 3 * t]])[1] < 1e-9           # three points on a slanted line: no width
    sliver = [[0, 0], [5 * m.cos(0.3), 5 * m.sin(0.3)], [5 * m.cos(0.3) - 0.01 * m.sin(0.3), 5 * m.sin(0.3) + 0.01 * m.cos(0.3)],
              [-0.01 * m.sin(0.3), 0.01 * m.cos(0.3)]]
    assert abs(FR.measure(sliver)[1] - 0.01) < 1e-6                    # a 0.01-wide sliver at an angle is 0.01 wide
    assert abs(FR.measure([[0, 0], [2, 0], [2, 1], [0, 1]])[1] - 1.0) < 1e-9
    # two square pieces 0.3 deep in each other, at rest: a step of 0 parts nothing, a frame's step does
    sq = [-1, -1, 1, -1, 1, 1, -1, 1]
    st = [[0.0, 0.25, 0.0, 0, 0, 0, 0, 0, 0, 0, 1], [1.7, 0.25, 0.0, 0, 0, 0, 0, 0, 0, 0, 1]]
    args = ([sq, sq], [0.25, 0.25], [1.0, 1.0], [4.0, 4.0])
    still, _ = S.meet(st, *args, 0.0, 120.0, 0.0)
    assert still == st                                                 # (a step of 0 must not be taken as "still")
    moved, _ = S.meet(st, *args, 1 / 60, 120.0, 0.0)
    assert moved != st


def test_a_dented_or_unpushed_slab_is_judged_as_it_is():
    """the review of stage 48: a hand-edited piece with a DENT hid a thin arm inside its hull, and a speed of 0 failed the
    'flew' check (and the play said its pieces did not come to rest)"""
    import methods as M
    import settle as S
    with tempfile.TemporaryDirectory() as d:
        import subprocess
        subprocess.run([sys.executable, os.path.join(HERE, "..", "..", "vfx", "fracture.py"), "ell", "--size", "12,12,1", "--look-dir", d, "--out-dir",
                        os.path.join(d, "fractures")], capture_output=True, check=True)
        layer = {"kind": "debris", "pieces": "ell", "life": 3, "speed": 30}
        assert M.plan_flies(layer, "pieces", d) is True
        plan = json.load(open(os.path.join(d, "fractures", "ell.json")))
        plan["pieces"][0]["points"] = [[0, 0], [3, 0], [3, 0.01], [0.5, 0.01], [0.5, 1], [0, 1]]   # an L with a 0.01 arm
        json.dump(plan, open(os.path.join(d, "fractures", "ell.json"), "w"))
        assert M.plan_flies(layer, "pieces", d) is False
    piece = {"points": [[-1, -1], [1, -1], [1, 1], [-1, 1]], "centre": [0, 0], "vel": [4, 6, 2], "spin": [3.0, -2.0, 1.0], "delay": 0}
    plan = {"size": [2, 2, 0.5], "made": {"speed": 30}, "pieces": [piece]}
    rows, _ = S.check(S.fly(plan, 2.0, 120.0, 0.0, 60), 2.0, pushed=False)
    assert all(r["ok"] for r in rows), [r for r in rows if not r["ok"]]
    rows, _ = S.check(S.fly(plan, 2.0, 120.0, 0.0, 60), 2.0)
    assert not all(r["ok"] for r in rows)                     # (pushed but nothing flew: still said)


def test_an_outline_goes_round_once_one_way_and_a_speed_of_0_passes_settle():
    """the review of stage 48b: the hull check refused a valid piece with a point on an edge and passed a bowtie; and
    settle's own command with --speed 0 is a pass (nothing is meant to fly)"""
    import methods as M
    assert M.convex_once([[-1, -1], [0, -1], [1, -1], [1, 1], [-1, 1]])            # a point on an edge
    assert M.convex_once([[-1, 1], [1, 1], [1, -1], [-1, -1]])                    # clockwise
    assert not M.convex_once([[-1, -1], [1, 1], [1, -1], [-1, 1]])                # a bowtie
    assert not M.convex_once([[0, 0], [3, 0], [3, 0.01], [0.5, 0.01], [0.5, 1], [0, 1]])   # an L (a dent)
    star = [[m.cos(a), m.sin(a)] for a in [k * 4 * m.pi / 5 for k in range(5)]] if (m := __import__("math")) else []
    assert not M.convex_once(star)                                                # a star turns one way, twice round
    import subprocess
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([sys.executable, os.path.join(HERE, "..", "..", "vfx", "fracture.py"), "zero", "--size", "12,12,1", "--look-dir", d,
                        "--out-dir", d], capture_output=True, check=True)
        r = subprocess.run([sys.executable, os.path.join(HERE, "..", "..", "vfx", "settle.py"), "zero", "--plans-dir", d, "--speed", "0", "--life", "2"],
                           capture_output=True, text=True)
        said = json.loads(r.stdout.strip().splitlines()[-1])
        assert said["status"] == "pass", said["summary"]


def test_baked_means_packed_and_registered():
    import methods as M
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "_textures.json"), "w", encoding="utf-8") as fh:
            json.dump({"up": {"id": "rbxassetid://1"}, "packed": {"id": "", "file": "build/textures/x.png"}}, fh)
        assert M.baked(d, "up") and M.baked(d, "packed")       # registered by the build, uploaded or not
        assert not M.baked(d, "hand_written")                  # a spec never packed
