"""Unit tests of water as a height field (kit/vfx/water.py): the wave equation and the shallow-water equations, held
to what the mathematics says - never to a real scene (none was read).
Run: python -m pytest kit/test/python/test_vfx_water.py -q"""
import contextlib
import copy
import io
import json
import math
import os
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import methods as M  # noqa: E402
import water as W  # noqa: E402


def asks(**k):
    return W.arguments({"--" + a.replace("_", "-"): str(b) for a, b in k.items()})


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = W.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def failed(d, **kw):
    return [c["name"] for c in W.check(d, **kw) if not c["ok"]]


class TheWaveEquation(unittest.TestCase):
    def test_no_wave_runs_faster_than_the_speed_said_and_one_does_run_that_fast(self):
        for speed in (0.4, 0.8):
            a = asks(recipe="drop", damp=0, frames=13, fps=24, speed=speed, width=0.045, cols=24, rows=24)
            first, last = W.waves(a)[0], W.waves(a)[12]
            c = W.centres(W.N)
            r = np.hypot(c[None, :], c[:, None])
            far = speed * 0.5                                                        # how far a wave has run in 12 frames
            amp = float(np.abs(first).max())
            self.assertLess(float(np.abs(last[r > far + 5 * 0.045]).max()), 0.02 * amp, speed)   # nothing has outrun it
            ring = r[np.abs(last) > 0.05 * amp]
            self.assertGreater(float(ring.max()), far - 0.03, speed)                 # and its front is out there

    def test_two_waves_pass_through_each_other_and_add(self):
        one, two = asks(recipe="drop", at="-0.2,0.1", frames=20), asks(recipe="drop", at="0.15,-0.2", frames=20)
        n = W.N
        rate = W.rate_of(one["speed"], n)
        e = one["amount"] * one["depth"] * (W.stamp(n, -0.2, 0.1, one["width"]) + W.stamp(n, 0.15, -0.2, one["width"]))
        v = e * 0
        for _ in range(round(19 / 24 * rate)):
            v += (one["speed"] ** 2 * W.lap(e, 1 / n) - one["damp"] * v) / rate
            e = e + v / rate
        self.assertLess(float(np.abs(e - (W.waves(one)[19] + W.waves(two)[19])).max()), 1e-12)

    def test_no_water_is_made_or_lost_by_drops_rain_or_walls(self):
        for a in (asks(recipe="drop", at="0.35,0.35", frames=64), asks(recipe="rain", drops=12, frames=64), asks(recipe="slosh", frames=40)):
            self.assertLess(max(abs(float(f.mean())) for f in W.waves(a)), 1e-12, a["recipe"])

    def test_a_standing_wave_rocks_at_the_period_the_tank_gives_it(self):
        # a tank 1 wide: its m'th standing wave comes round every 2 / (m x speed) seconds
        for mode, speed in ((1, 0.75), (2, 0.5)):
            a = asks(recipe="slosh", mode=mode, speed=speed, frames=64, fps=24, cols=24, rows=24)
            left = np.array([f[W.N // 2, 0] for f in W.waves(a)])
            turns = [k for k in range(1, 63) if left[k] < left[k - 1] and left[k] <= left[k + 1]]   # at its lowest: half way round
            self.assertTrue(turns, mode)
            self.assertAlmostEqual(turns[0] / 24, 1 / (mode * speed), delta=1.01 / 24)
            self.assertAlmostEqual(float(left[turns[0]]), -float(left[0]), delta=0.01 * abs(left[0]))    # as far down as it was up: nothing is lost

    def test_a_loop_moves_the_speed_so_the_rocking_comes_round(self):
        a = asks(recipe="slosh", frames=64, speed=0.74, loop=1)
        self.assertAlmostEqual(a["speed"], 0.75, places=3)
        self.assertEqual(a["times"], 1)
        f = W.waves(a)
        steps = max(float(np.abs(x - y).max()) for x, y in zip(f, f[1:]))
        self.assertLess(float(np.abs(f[0] - f[-1]).max()), 1.2 * steps)                    # the last frame steps into the first
        with self.assertRaisesRegex(ValueError, "far from the 0.6 asked"):
            asks(recipe="slosh", frames=48, loop=1)

    def test_damping_takes_the_waves_down(self):
        loud = max(float(np.abs(f).max()) for f in W.waves(asks(recipe="drop", damp=0, frames=48))[24:])
        soft = max(float(np.abs(f).max()) for f in W.waves(asks(recipe="drop", damp=3, frames=48))[24:])
        self.assertLess(soft, 0.5 * loud)

    def test_the_frames_do_not_depend_on_the_frames_a_second(self):
        a12, a48 = asks(recipe="rain", frames=13, fps=12), asks(recipe="rain", frames=49, fps=48)
        self.assertEqual(W.rate_of(a12["speed"], W.N), W.rate_of(a48["speed"], W.N))        # solved at one rate, whatever the frames
        slow, fast = W.waves(dict(a12, drops=1)), W.waves(dict(a48, drops=1))                # (one drop, at the start: rain's moments are drawn from the run's length)
        self.assertLess(float(np.abs(slow[12] - fast[48]).max()), 1e-9)


class TheShallowWaterEquations(unittest.TestCase):
    def test_a_dam_break_is_stokers(self):
        """water twice as deep on one side: a shelf runs out behind a bore; its height and the bore's speed are known exactly"""
        for amount in (1.0, 2.0):
            a = asks(recipe="dam", amount=amount, at="-0.2,0", frames=13, fps=24)
            d = a["depth"]
            g = a["speed"] ** 2 / d
            shelf, flow, bore = W.stoker(d * (1 + amount), d, g)
            self.assertAlmostEqual(flow + 2 * math.sqrt(g * shelf), 2 * math.sqrt(g * d * (1 + amount)))     # the two conditions it solves
            self.assertAlmostEqual(bore * (shelf - d), shelf * flow)
            mid = W.shallow(a)[12][W.N // 2] + d
            c = W.centres(W.N)
            wall = c[c < -0.2].max() + 0.5 / W.N                                             # the cell edge the dam stood on
            front = c[np.where(mid > (shelf + d) / 2)[0].max()]
            self.assertAlmostEqual(front, wall + bore * 0.5, delta=1.5 / W.N, msg=amount)   # where the bore is after half a second
            flat = mid[(c > wall + bore * 0.5 - 0.2) & (c < wall + bore * 0.5 - 0.08)]      # behind the bore, clear of the fan the shelf runs out of
            self.assertGreater(len(flat), 5)
            self.assertLess(float(np.abs(flat - shelf).max()), 0.015 * shelf, amount)        # the shelf's height, to 1.5 %

    def test_a_high_wave_outruns_a_low_one(self):
        """the wave equation cannot do this: there every wave has one speed"""
        def front(amount):
            a = asks(recipe="dam", amount=amount, at="-0.2,0", frames=13, fps=24)
            d = a["depth"]
            shelf = W.stoker(d * (1 + amount), d, a["speed"] ** 2 / d)[0]
            mid = W.shallow(a)[12][W.N // 2]
            return W.centres(W.N)[np.where(mid > (shelf - d) / 2)[0].max()]                 # half way up its front

        low, high = front(0.05), front(2.0)
        self.assertAlmostEqual(low, -0.2 + 0.6 * 0.5, delta=0.03)                           # a small step runs at the speed said (0.6)
        self.assertGreater(high, low + 0.08)

    def test_no_water_is_made_or_lost_and_none_crosses_a_wall(self):
        for a in (asks(recipe="dam", amount=3, frames=64), asks(recipe="surge", at="0.3,-0.3", amount=4, frames=64)):
            frames = W.shallow(a)
            self.assertLess(max(abs(float(f.mean() - frames[0].mean())) for f in frames), 1e-12, a["recipe"])
            self.assertGreater(min(float(f.min()) for f in frames), -a["depth"])            # the bed is never laid bare

    def test_a_surge_in_the_middle_stays_the_same_all_four_ways(self):
        for f in W.shallow(asks(recipe="surge", frames=30)):
            self.assertLess(float(np.abs(f - f.T).max() + np.abs(f - f[::-1]).max() + np.abs(f - f[:, ::-1]).max()), 1e-9)

    def test_still_water_stays_still(self):
        a = asks(recipe="dam", amount=0.05, frames=5)
        h = np.full((W.N, W.N), a["depth"])
        h2, hu, hv = W.shallow_step(h, h * 0, h * 0, 3.6, 1 / W.N, 0.002)
        self.assertEqual((float(np.abs(h2 - h).max()), float(np.abs(hu).max()), float(np.abs(hv).max())), (0.0, 0.0, 0.0))

    def test_the_frames_hardly_depend_on_the_frames_a_second(self):
        slow, fast = W.shallow(asks(recipe="dam", frames=7, fps=12)), W.shallow(asks(recipe="dam", frames=25, fps=48))
        self.assertLess(float(np.abs(slow[6] - fast[24]).max()), 0.02 * 0.1)                # (a frame's moment cuts a step short: a fiftieth of the depth)


class TheMesh(unittest.TestCase):
    def test_the_points_are_rows_of_columns_over_the_tank(self):
        e = np.fromfunction(lambda j, i: i * 0.001 + j * 0.01, (W.N, W.N))
        p = W.to_points(e, 12, 10)
        self.assertEqual(p.shape, (11, 13, 3))
        self.assertEqual((p[0, 0, 0], p[0, -1, 0], p[0, 0, 2], p[-1, 0, 2]), (-0.5, 0.5, -0.5, 0.5))
        self.assertGreater(p[0, 5, 1], p[0, 4, 1])                                           # along a row: x
        self.assertGreater(p[5, 0, 1], p[4, 0, 1] + 5 * (p[0, 5, 1] - p[0, 4, 1]))           # from row to row: z

    def test_a_points_share_of_the_tank(self):
        self.assertAlmostEqual(float(W.volume(np.full((9, 9), 0.25))), 0.25)
        tilt = np.linspace(-1, 1, 9)[None, :] * np.ones((9, 1))
        self.assertAlmostEqual(float(W.volume(tilt)), 0.0)


class TheCommandAndTheChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def bake(self, name, *argv):
        code, said = run([name, *argv, "--out-dir", self.tmp.name, "--look-dir", self.tmp.name])
        self.assertEqual(code, 0, said)
        with open(os.path.join(self.tmp.name, f"{name}.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_every_recipe_bakes_and_its_file_passes_its_own_checks(self):
        for name, argv in (("drop", []), ("rain", ["--recipe", "rain"]), ("rock", ["--recipe", "slosh", "--frames", "64", "--speed", "0.75", "--loop"]),
                           ("dam", ["--recipe", "dam"]), ("surge", ["--recipe", "surge"])):
            d = self.bake(name, *argv)
            self.assertEqual(failed(d), [], name)
            self.assertEqual(len(d["frames"][0]), 21 * 21 * 3)
            self.assertIn("Never matched to a real scene", d["about"])
            self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, f"{name}.png")))
        self.assertEqual(failed(self.bake("rock", "--recipe", "slosh", "--frames", "64", "--speed", "0.75", "--loop"), loop=True), [])
        self.assertEqual(failed(self.bake("drop"), loop=True), ["the loop's seam"])
        self.assertEqual(failed(self.bake("rock", "--recipe", "slosh"), loop=True), ["the loop's seam"])       # a slosh baked without --loop
        self.assertEqual(failed(self.bake("drop"), play=4), ["it is played at its own speed"])

    def test_a_file_changed_by_hand_is_not_what_its_asks_solve_to(self):
        good = self.bake("drop")

        def spoilt(fn):
            d = copy.deepcopy(good)
            fn(d)
            return failed(d)

        def taller(d):
            d["frames"] = [[v * 1.5 if k % 3 == 1 else v for k, v in enumerate(f)] for f in d["frames"]]

        self.assertIn("the frames are what its asks solve to", spoilt(taller))
        self.assertIn("the frames are what its asks solve to", spoilt(lambda d: d.update(frames=d["frames"][::-1])))
        self.assertIn("the frames are what its asks solve to", spoilt(lambda d: d["frames"][7].__setitem__(1 + 3 * 200, 0.05)))

        def a_tenth_taller(d):
            d["frames"] = [[round(v * 1.1, 4) if k % 3 == 1 else v for k, v in enumerate(f)] for f in d["frames"]]

        self.assertIn("the frames are what its asks solve to", spoilt(a_tenth_taller))       # (0.004 of the tank let this through)
        self.assertIn("the frames are what its asks solve to", spoilt(lambda d: d["frames"][5].__setitem__(1 + 3 * 220, d["frames"][5][1 + 3 * 220] + 0.002)))
        self.assertEqual(spoilt(lambda d: d["frames"][5].__setitem__(1, "0.0")), ["a water bake"])    # a number written as text
        for spoil in (lambda d: d.update(recipe="sand"), lambda d: d["args"].update(speed=0.9), lambda d: d["asks"].update({"--amount": "0.5"}), lambda d: d.pop("asks"),
                      lambda d: d["asks"].update({"--glow": "1"}), lambda d: d["frames"][3].pop(), lambda d: d.update(frames=d["frames"][:10]), lambda d: d.update(strips=2),
                      lambda d: d["frames"][2].__setitem__(0, 0.1), lambda d: d["frames"][2].__setitem__(4, float("nan")), lambda d: d.update(cols=True),
                      lambda d: d["args"].update(recipe="dam")):
            self.assertEqual(spoilt(spoil), ["a water bake"])

    def test_asks_that_cannot_work_are_said_in_words(self):
        for argv, word in ((["Wave"], "lowercase"), (["w", "--recipe", "river"], "--recipe is one of"), (["w", "--speed", "9"], "--speed is a number"),
                           (["w", "--recipe", "dam", "--loop"], "--loop is for a slosh"), (["w", "--width", "0.03"], "under one cell of the mesh"),
                           (["w", "--speed", "3", "--fps", "12"], "flip from frame to frame"), (["w", "--speed", "1.9", "--fps", "24", "--width", "0.08"], "flip from frame to frame"),
                           (["w", "--recipe", "dam", "--speed", "2", "--fps", "8", "--amount", "4"], "points of the mesh a frame"),
                           (["w", "--recipe", "surge", "--fps", "12", "--amount", "4", "--speed", "1"], "points of the mesh a frame"),
                           (["w", "--recipe", "slosh", "--depth", "0.02", "--amount", "0.04", "--speed", "1.5"], "high enough to see"),
                           (["w", "--recipe", "slosh", "--loop"], "far from the 0.6 asked"), (["w", "--recipe", "slosh", "--mode", "4"], "under 12 points a wave"),
                           (["w", "--recipe", "slosh", "--speed", "4", "--fps", "8"], "under 8"), (["w", "--at", "0.9,0"], "--at is x,z"),
                           (["w", "--amount", "0.95"], "--amount is a number"), (["w", "--glow", "1"], "not an option"), (["w", "--frames"], "no value"),
                           (["w", "--recipe", "rain", "--drops", "1"], "--drops is a whole number")):
            code, said = run(["--out-dir", self.tmp.name, "--look-dir", self.tmp.name] + argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, said["summary"], argv)
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_a_dam_bakes_wherever_its_wall_stands_and_however_coarse_its_mesh(self):
        """the coarse mesh cannot weigh a sharp step: 79 of 289 honest dams were refused for water 'made or lost'"""
        for at in ("-0.3", "-0.05", "0.078", "0.25"):
            for cols in ("8", "9", "12", "24"):
                code, said = run(["dam", "--recipe", "dam", "--at", at, "--cols", cols, "--rows", cols, "--frames", "12", "--out-dir", self.tmp.name, "--look-dir", self.tmp.name])
                self.assertEqual(code, 0, (at, cols, said["summary"][:200]))

    def test_a_bake_too_large_leaves_an_earlier_one_alone(self):
        self.bake("drop", "--frames", "12")
        before = os.path.getsize(os.path.join(self.tmp.name, "drop.json"))
        code, said = run(["drop", "--frames", "64", "--cols", "24", "--rows", "24", "--out-dir", self.tmp.name, "--look-dir", self.tmp.name])
        if code == 1:                                                                        # (64 frames of 25 x 25 points: over the 600 KB a bake may be)
            self.assertIn("KB of frames", said["summary"])
            self.assertEqual(os.path.getsize(os.path.join(self.tmp.name, "drop.json")), before)


class TheRegister(unittest.TestCase):
    def test_waves_and_shallow_water_each_prove_their_own_method(self):
        by = M.load()[1]
        self.assertEqual((by["wave_sim"]["state"], by["shallow_water"]["state"]), ("has", "has"))
        for m in ("wave_sim", "shallow_water"):
            self.assertIn("NEVER matched to a real scene", by[m]["how"])

        class Empty:
            def get(self, key):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            seq = os.path.join(tmp, "seq")
            for name, argv in (("drop", []), ("dam", ["--recipe", "dam"]), ("rock", ["--recipe", "slosh", "--frames", "64", "--speed", "0.75", "--loop"])):
                self.assertEqual(run([name, *argv, "--out-dir", seq, "--look-dir", tmp])[0], 0)
            with open(os.path.join(seq, "drop.json"), encoding="utf-8") as fh:
                drop = json.load(fh)
            with open(os.path.join(seq, "tall.json"), "w", encoding="utf-8") as fh:
                json.dump(dict(drop, frames=[[v * 1.5 if k % 3 == 1 else v for k, v in enumerate(f)] for f in drop["frames"]]), fh)

            def proved(method, layer):
                return M.proved(by[method], [dict({"kind": "mesh", "pivot": "origin", "shape": "seq", "life": 3}, **layer)], Empty(), tmp, "s") is not None

            self.assertTrue(proved("wave_sim", {"params": {"seq": "drop"}}))
            self.assertTrue(proved("wave_sim", {"params": {"seq": "rock", "loop": True}}))
            self.assertTrue(proved("shallow_water", {"params": {"seq": "dam"}}))
            self.assertFalse(proved("shallow_water", {"params": {"seq": "drop"}}))        # every wave at one speed: no bore
            self.assertFalse(proved("wave_sim", {"params": {"seq": "dam"}}))
            self.assertFalse(proved("wave_sim", {"params": {"seq": "drop", "loop": True}}))
            self.assertFalse(proved("wave_sim", {"params": {"seq": "tall"}}))             # changed by hand
            self.assertFalse(proved("wave_sim", {"params": {"seq": "nothing"}}))
            self.assertFalse(proved("wave_sim", {"life": 0.3, "params": {"seq": "drop"}}))
            self.assertFalse(proved("wave_sim", {"shape": "billow", "params": {"seq": "drop"}}))
            # stage 26: centred on its first frame's box the water is not at the level its layer's point says
            self.assertFalse(proved("wave_sim", {"pivot": "center", "params": {"seq": "drop"}}))
            self.assertFalse(proved("shallow_water", {"pivot": None, "params": {"seq": "dam"}}))
            self.assertIn('"pivot": "origin"', M.say_proof(by["wave_sim"]))
            self.assertIn("--recipe dam|surge", M.say_proof(by["shallow_water"]))


class TheStandIns(unittest.TestCase):
    """stage 26: the rows Roblox has only a stand-in for prove their method by what is SEEN"""

    def proved(self, method, layer, effects=None):
        class Empty:
            def get(self, key):
                return None

        return M.proved(M.load()[1][method], [layer], Empty(), effects, "s") is not None

    def test_many_copies_are_many(self):
        self.assertTrue(self.proved("instanced", {"kind": "swarm", "count": 40}))
        self.assertTrue(self.proved("instanced", {"kind": "swarm"}))                       # the game's own count is 40
        self.assertFalse(self.proved("instanced", {"kind": "swarm", "count": 3}))
        self.assertFalse(self.proved("instanced", {"kind": "swarm", "count": "many"}))
        self.assertFalse(self.proved("instanced", {"kind": "swarm", "count": 11.99}))
        self.assertIn('"count" of 12 or more', M.say_proof(M.load()[1]["instanced"]))

    def test_the_screen_is_proved_by_what_works_on_the_screen(self):
        self.assertTrue(self.proved("screen_space", {"kind": "world", "sunRays": 0.4}))
        self.assertTrue(self.proved("screen_space", {"kind": "world", "exposure": [[0, 0], [1, -1.5]]}))
        self.assertTrue(self.proved("screen_space", {"kind": "screen", "blur": [[0, 0], [1, 12]]}))
        self.assertTrue(self.proved("screen_space", {"kind": "screen", "saturation": -0.6}))
        self.assertFalse(self.proved("screen_space", {"kind": "screen"}))                   # a screen layer that does nothing
        self.assertFalse(self.proved("screen_space", {"kind": "screen", "tint": [255, 255, 255], "blur": 0}))
        self.assertTrue(self.proved("screen_space", {"kind": "lens"}))
        self.assertFalse(self.proved("screen_space", {"kind": "world", "fog": 4, "sky": [10, 10, 30]}))   # the world's, not the screen's
        self.assertFalse(self.proved("screen_space", {"kind": "world", "sunRays": 0, "exposure": 0}))

    def test_a_haze_of_no_strength_bends_nothing(self):
        for m in ("refraction", "heat_distortion"):
            self.assertTrue(self.proved(m, {"kind": "mesh", "haze": {"scale": 1.2}}))      # (its strength is 0.5 unless said)
            self.assertTrue(self.proved(m, {"kind": "mesh", "haze": {"strength": 0.3}}))
            self.assertTrue(self.proved(m, {"kind": "mesh", "haze": {"strength": "0"}}))   # (not a number: the game takes its own 0.5)
            self.assertFalse(self.proved(m, {"kind": "mesh", "haze": {"strength": 0}}))
            self.assertFalse(self.proved(m, {"kind": "mesh", "haze": {"strength": -0.5}}))  # the game clamps it to 0: nothing is drawn
            self.assertFalse(self.proved(m, {"kind": "mesh", "haze": {"strength": 1e-9}}))
            self.assertFalse(self.proved(m, {"kind": "mesh"}))

    def test_a_replayed_sequence_is_one_that_is_there(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "seq"))
            with open(os.path.join(tmp, "seq", "billow_a.json"), "w", encoding="utf-8") as fh:
                json.dump({"cols": 1, "rows": 1, "frames": [[0] * 12, [0] * 12]}, fh)
            self.assertTrue(self.proved("vertex_anim_texture", {"kind": "mesh", "shape": "seq", "params": {"seq": "billow_a"}}, tmp))
            self.assertFalse(self.proved("vertex_anim_texture", {"kind": "mesh", "shape": "seq", "params": {"seq": "bilow_a"}}, tmp))
            self.assertFalse(self.proved("vertex_anim_texture", {"kind": "mesh", "shape": "seq"}, tmp))


if __name__ == "__main__":
    unittest.main()


def test_review_leftovers_rain_is_the_same_rain_and_a_wide_drop_does_not_lower_the_far_water():
    """stage 24's review leftovers: rain's moments were drawn over 0.7 of the run (other --frames, other rain); a wide
    drop's mark was balanced by lowering the WHOLE tank"""
    import numpy as np
    import water as WA
    short = WA.arguments({"--recipe": "rain", "--frames": "30", "--seed": "4"})
    long_ = WA.arguments({"--recipe": "rain", "--frames": "48", "--seed": "4"})
    a, b = WA.waves(short), WA.waves(long_)
    for f in range(30):                                   # the frames both runs have are the same rain
        assert np.allclose(a[f], b[f])
    # a drop near one wall, cut by it: what is left over is taken off NEAR it, not off the far corner of the tank
    n, x, z, w = 20, -0.4, -0.4, 0.15
    s = WA.stamp(n, x, z, w)
    assert abs(float(s.sum())) < 1e-9                     # it still holds no water in all
    c = WA.centres(n)
    r2 = ((c[None, :] - x) ** 2 + (c[:, None] - z) ** 2) / (w * w)
    raw = (1 - r2 / 2) * np.exp(-r2 / 2)
    old = raw - raw.mean()                                # the old balance: the same taken off every cell
    assert abs(float(old[-1, -1])) > 1e-3                 # it lowered the far corner
    assert abs(float(s[-1, -1])) < abs(float(old[-1, -1])) / 100
