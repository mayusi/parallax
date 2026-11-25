"""Unit tests of liquid solved and baked into a flipbook (kit/vfx/liquid.py): FLIP and a particle fluid, held to what
physics says - never to a real scene (none was read).
Run: python -m pytest kit/test/python/test_vfx_liquid.py -q"""
import contextlib
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
import liquid as L  # noqa: E402
import methods as M  # noqa: E402

G = 4.0


def pool(depth=0.3):
    step = 1.0 / (L.NX * L.PER)
    xs = (np.arange(L.NX * L.PER) + 0.5) * step
    x, y = np.meshgrid(xs, xs)
    keep = y.reshape(-1) < depth
    return np.stack([x.reshape(-1)[keep], y.reshape(-1)[keep]], -1)


def blob(y=0.6, r=0.1):
    p = pool(1.0)
    return p[(p[:, 0] - 0.5) ** 2 + (p[:, 1] - y) ** 2 < r * r]


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = L.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


class Flip(unittest.TestCase):
    def test_a_still_pool_stays_still_and_its_pressure_is_gravity_times_depth(self):
        pos = pool()
        vel = pos * 0
        dt = 1.0 / L.rate_of(G)
        start = pos.copy()
        for _ in range(60):
            pos, vel, p, wet = L.flip_step(pos, vel, dt, G)
        self.assertLess(float(np.abs(pos - start).max()), 1e-6)
        self.assertLess(float(np.abs(vel).max()), 1e-6)
        rows = int(wet[:, 0].sum())                                                       # wet cells in a column
        self.assertAlmostEqual(float(p[0].mean()), G * rows / L.NX, delta=1e-4)          # at the bed: the weight of the water over it
        self.assertAlmostEqual(float(p[rows - 1].mean()), G * 1 / L.NX, delta=1e-4)      # under the surface: one cell's

    def test_a_body_in_the_air_falls_as_gravity_says(self):
        pos = blob()
        vel = pos * 0
        dt = 1.0 / L.rate_of(G)
        y0 = float(pos[:, 1].mean())
        for _ in range(60):
            pos, vel, _, _ = L.flip_step(pos, vel, dt, G)
        t = 60 * dt
        self.assertAlmostEqual(float(pos[:, 1].mean()), y0 - 0.5 * G * t * t, delta=0.004)
        self.assertAlmostEqual(float(vel[:, 1].mean()), -G * t, delta=0.01)
        self.assertLess(float(np.abs(vel[:, 0]).max()), 0.05)                              # and does not spread: nothing pushes it

    def test_the_pressure_solve_leaves_no_cell_filling_or_emptying(self):
        rng = np.random.default_rng(3)
        pos = L.body("drop")
        vel = rng.normal(0, 0.5, pos.shape)
        u0, v0, wet = L.to_grid(pos, vel, L.NX)
        before = float(np.abs(np.where(wet, L.divergence(u0, v0, L.NX), 0)).max())
        u, v, _ = L.project(u0, v0, wet, 0.004, L.NX, tol=1e-9, most=2000)
        after = float(np.abs(np.where(wet, L.divergence(u, v, L.NX), 0)).max())
        self.assertGreater(before, 1.0)
        self.assertLess(after, 1e-5 * before)
        # ... and with a RUN's own settings (tol 1e-6, 400 rounds), not only the test's tighter ones (a review leftover)
        u2, v2, _ = L.project(u0, v0, wet, 0.004, L.NX)
        self.assertLess(float(np.abs(np.where(wet, L.divergence(u2, v2, L.NX), 0)).max()), 1e-5 * before)
        self.assertEqual((float(np.abs(u[:, 0]).max()), float(np.abs(u[:, -1]).max()), float(np.abs(v[0]).max())), (0.0, 0.0, 0.0))   # nothing through a wall

    def test_the_grid_and_the_particles_agree_on_a_steady_flow(self):
        pos = pool(0.5)
        vel = np.tile([0.3, -0.2], (len(pos), 1))
        u, v, _ = L.to_grid(pos, vel, L.NX)
        inner = pos[(pos[:, 0] > 0.2) & (pos[:, 0] < 0.8) & (pos[:, 1] > 0.1) & (pos[:, 1] < 0.4)]
        got = L.from_grid(inner, u, v, L.NX)
        self.assertLess(float(np.abs(got - [0.3, -0.2]).max()), 1e-9)


class ParticleFluid(unittest.TestCase):
    def test_a_pool_settles_and_is_nowhere_much_denser_than_at_rest(self):
        pos = pool()
        vel = pos * 0
        rho0, h = L.rest_density()
        dt = 1.0 / L.rate_of(G)
        top = float(pos[:, 1].max())
        for _ in range(120):
            pos, vel, rho = L.pbf_step(pos, vel, dt, G, rho0, h)
        self.assertLess(float((rho / rho0).max()), 1.08)
        self.assertLess(abs(float(pos[:, 1].max()) - top), 0.03)                           # the surface is where it was (it sags a little: said on the page)
        self.assertLess(float(np.sqrt((vel ** 2).sum(-1)).mean()), 0.05 * math.sqrt(G))

    def test_a_body_in_the_air_falls_as_gravity_says(self):
        pos = blob()
        vel = pos * 0
        rho0, h = L.rest_density()
        dt = 1.0 / L.rate_of(G)
        y0 = float(pos[:, 1].mean())
        for _ in range(60):
            pos, vel, _ = L.pbf_step(pos, vel, dt, G, rho0, h)
        t = 60 * dt
        self.assertAlmostEqual(float(pos[:, 1].mean()), y0 - 0.5 * G * t * t, delta=0.004)

    def test_the_rest_density_is_a_lattices(self):
        rho0, h = L.rest_density()
        p = pool(0.5)
        i, j = L.pairs_of(p, h)
        deep = (p[:, 0] > 0.2) & (p[:, 0] < 0.8) & (p[:, 1] > 0.1) & (p[:, 1] < 0.4)
        self.assertLess(float(np.abs(L.density(p, h, i, j)[deep] / rho0 - 1).max()), 1e-9)


class TheRun(unittest.TestCase):
    def test_no_liquid_is_made_or_lost_and_its_energy_does_not_rise(self):
        for solver, scene, frames in (("flip", "dam", 30), ("flip", "drop", 24), ("pbf", "dam", 12)):
            seen = []
            a = {"solver": solver, "scene": scene, "gravity": G, "frames": frames, "fps": 24}
            out = L.simulate(a, keep=lambda s, p, v, x: seen.append((len(p), float(p.min()), float(p.max()), L.energy(p, v, G))))
            n = {s[0] for s in seen}
            self.assertEqual(len(n), 1, solver)
            self.assertTrue(all(0 <= s[1] and s[2] <= 1 for s in seen), solver)
            e = np.array([s[3] for s in seen])
            self.assertLess(float(np.diff(e).max()), L.RISE * G, (solver, scene))
            self.assertLess(e[-1], e[0], (solver, scene))                                 # it has fallen and splashed: lower than it began
            self.assertEqual(len(out), frames)

    def test_a_dams_front_runs_no_faster_than_shallow_water_theory_allows(self):
        """Ritter: a dam of height h on a dry bed runs out at 2 x sqrt(g h) at the very most"""
        a = {"solver": "flip", "scene": "dam", "gravity": G, "frames": 13, "fps": 24}
        out = L.simulate(a)
        h = 0.9 * 0.4
        front = [float(f[0][:, 0].max()) for f in out]
        fastest = max((b - x) * 24 for x, b in zip(front, front[1:]))
        self.assertLess(fastest, 2 * math.sqrt(G * h))
        self.assertGreater(front[12] - front[0], 0.3)                                     # and it does run out

    def test_frame_f_is_the_liquid_at_f_over_fps(self):
        slow = L.simulate({"solver": "flip", "scene": "dam", "gravity": G, "frames": 4, "fps": 12})
        fast = L.simulate({"solver": "flip", "scene": "dam", "gravity": G, "frames": 10, "fps": 36})
        self.assertLess(float(np.abs(slow[3][0] - fast[9][0]).max()), 1e-9)                # solved at one rate, whatever the frames

    def test_spray_is_liquid_that_has_left_the_body_and_a_slosh_makes_little_foam(self):
        out = L.simulate({"solver": "flip", "scene": "dam", "gravity": G, "frames": 40, "fps": 24})
        most = max(out, key=lambda f: int(f[3].sum()))
        if most[3].any():
            from scipy.spatial import cKDTree
            near = np.array([len(x) - 1 for x in cKDTree(most[0]).query_ball_point(most[0][most[3]], 1.5 / L.NX)])
            self.assertTrue((near < L.SPRAY_NEAR).all())
        wild = max(float((f[2] > 0.3).mean()) for f in out)
        calm = max(float((f[2] > 0.3).mean()) for f in L.simulate({"solver": "flip", "scene": "slosh", "gravity": G, "frames": 20, "fps": 24}))
        self.assertGreater(wild, 5 * max(calm, 1e-4))
        self.assertTrue(all((f[2] >= 0).all() and (f[2] <= 1).all() for f in out))

    def whites(self, cell):
        drawn = cell[..., 3] > 0.3
        return float(((cell[..., 0] / np.maximum(cell[..., 3], 1e-6) > 0.75) & drawn).sum() / max(int(drawn.sum()), 1))

    def test_foam_is_seen_in_the_picture_and_calm_liquid_shows_none(self):
        """the check counted particles while the picture showed almost no white; the particle fluid's settling was read as foam"""
        dam = L.simulate({"solver": "flip", "scene": "dam", "gravity": G, "frames": 40, "fps": 24})
        self.assertGreater(max(self.whites(L.render(f, 128)) for f in dam), 0.05)
        old = L.body
        L.body = lambda scene, n=L.NX, per=L.PER, fill=0.4, seed=1: pool() + np.random.default_rng(seed).uniform(-0.25, 0.25, pool().shape) / (n * per)
        try:
            for solver, most in (("flip", 0.0), ("pbf", L.WHITE / 2)):
                still = L.simulate({"solver": solver, "scene": "dam", "gravity": G, "frames": 16, "fps": 24})
                self.assertLessEqual(max(self.whites(L.render(f, 128)) for f in still), most, solver)
                self.assertEqual(max(int(f[3].sum()) for f in still), 0, solver)
        finally:
            L.body = old

    def test_with_no_foam_the_body_is_drawn_alone(self):
        a = {"solver": "pbf", "scene": "dam", "gravity": G, "fill": 0.4, "seed": 1, "fps": 24, "foam": False, "frames": 16, "grid": 4, "cell": 64}
        _, cells, rows = L.solve(a)
        self.assertEqual(max(self.whites(c) for c in cells), 0.0)                          # spray was still drawn as bright mist
        self.assertNotIn("foam or spray is made", [r["name"] for r in rows])

    def test_flip_keeps_its_liquid(self):
        """bunched particles fill fewer cells: a dam lost 14 % of its wet cells and an eighth of its picture"""
        out = L.simulate({"solver": "flip", "scene": "dam", "gravity": G, "frames": 64, "fps": 24})
        wet = [len(set(map(tuple, (f[0] * L.NX).astype(int)))) for f in out]
        self.assertGreater(min(wet), 0.93 * wet[0])
        area = [float(L.render(f, 128)[..., 3].sum()) for f in out]
        self.assertLess(max(abs(x - area[0]) for x in area) / area[0], 0.08)

    def test_the_energy_is_watched_from_the_first_step(self):
        seen = []
        L.simulate({"solver": "flip", "scene": "dam", "gravity": G, "frames": 2, "fps": 24}, keep=lambda s, p, v, x: seen.append(s))
        self.assertEqual(seen[:2], [0, 1])

    def test_the_picture_is_premultiplied_and_holds_the_liquid(self):
        out = L.simulate({"solver": "flip", "scene": "dam", "gravity": G, "frames": 2, "fps": 24})
        c = L.render(out[0], 128)
        self.assertEqual(c.shape, (128, 128, 4))
        self.assertTrue((c[..., :3] <= c[..., 3:] + 1e-9).all() and c.min() >= 0 and c.max() <= 1)
        area = float(c[..., 3].mean())
        self.assertAlmostEqual(area, 0.3 * 0.36, delta=0.02)                              # the block is 0.3 wide and 0.36 tall
        self.assertEqual(float(c[:40, 80:, 3].max()), 0.0)                                # and the air is clear


class TheCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dirs = ["--specs-dir", os.path.join(self.tmp.name, "specs"), "--frames-dir", os.path.join(self.tmp.name, "frames"), "--look-dir", os.path.join(self.tmp.name, "look")]

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_sheet_is_baked_with_its_spec_and_its_picture(self):
        code, said = run(["spill", "--grid", "4", "--cell", "64", *self.dirs])
        self.assertEqual(code, 0, said)
        with open(os.path.join(self.tmp.name, "specs", "spill.json"), encoding="utf-8") as fh:
            spec = json.load(fh)
        self.assertEqual((spec["recipe"], spec["frames"], spec["grid"], spec["cell"], spec["liquid"]["solver"]), ("liquid", 16, 4, 64, "flip"))
        self.assertIn("Never matched to a real scene", spec["about"])
        frames = sorted(f for f in os.listdir(os.path.join(self.tmp.name, "frames", "spill")) if f.endswith(".npy"))
        self.assertEqual(len(frames), 16)
        self.assertEqual(np.load(os.path.join(self.tmp.name, "frames", "spill", frames[0])).shape, (64, 64, 4))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, "look", "spill.png")))
        # the build step: current frames are left, a changed spec is baked again
        step = ["--specs", os.path.join(self.tmp.name, "specs"), "--out", os.path.join(self.tmp.name, "frames")]
        self.assertIn("current", run(step)[1]["summary"])
        spec["liquid"]["seed"] = 5
        with open(os.path.join(self.tmp.name, "specs", "spill.json"), "w", encoding="utf-8") as fh:
            json.dump(spec, fh)
        code, said = run(step)
        self.assertEqual((code, len(said["baked"])), (0, 1))
        spec["liquid"]["solver"] = "sph"
        with open(os.path.join(self.tmp.name, "specs", "spill.json"), "w", encoding="utf-8") as fh:
            json.dump(spec, fh)
        code, said = run(step)
        self.assertEqual(code, 1)
        self.assertIn('"solver" is one of', said["summary"])
        # a sheet whose bake failed has NO frames: the old ones were another spec's, and the packer would pack them as this one's
        self.assertEqual([f for f in os.listdir(os.path.join(self.tmp.name, "frames", "spill")) if f.endswith(".npy") or f == "frames.json"], [])
        spec["liquid"]["solver"] = "flip"
        with open(os.path.join(self.tmp.name, "specs", "spill.json"), "w", encoding="utf-8") as fh:
            json.dump(spec, fh)
        self.assertEqual(run(step)[0], 0)
        meta = os.path.join(self.tmp.name, "frames", "spill", "frames.json")
        with open(meta, encoding="utf-8") as fh:
            made = json.load(fh)
        self.assertEqual(made["code"], L.code_id())
        with open(meta, "w", encoding="utf-8") as fh:
            json.dump(dict(made, code="an older solver"), fh)
        self.assertEqual(len(run(step)[1]["baked"]), 1)                                    # frames another version of the solver made are baked again

    def test_asks_that_cannot_work_are_said_in_words_and_nothing_is_written(self):
        for argv, word in ((["Spill"], "not a texture key"), (["s", "--solver", "sph"], '"solver" is one of'), (["s", "--scene", "river"], '"scene" is one of'),
                           (["s", "--grid", "6"], '"grid" is 4 or 8'), (["s", "--grid", "4", "--cell", "100"], "256, 512 or 1024"), (["s", "--gravity", "40"], '"gravity" is a number'),
                           (["s", "--gravity", "18", "--fps", "12"], "a fifth of the tank a frame"), (["s", "--fill", "0.9"], '"fill" is a number'),
                           (["s", "--glow", "1"], "not one of its options"), (["s", "--fps"], "no value"), (["s", "--fps", "fast"], "is a number"),
                           (["s", "--grid", "nan"], "is a number"), (["s", "--fill", "inf"], "is a number"), (["s", "--grid", "1e400"], "is a number"),
                           (["s", "--scene", "--fps", "24"], "--scene has no value"), (["s", "--scene", "dam", "--fill", "0.5"], "at most for a dam")):
            code, said = run(argv[:1] + self.dirs + argv[1:])
            self.assertEqual(code, 1, argv)
            self.assertIn(word, said["summary"], argv)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "specs")))

    def test_another_recipes_sheet_of_the_name_is_not_written_over(self):
        os.makedirs(os.path.join(self.tmp.name, "specs"))
        with open(os.path.join(self.tmp.name, "specs", "smoke.json"), "w", encoding="utf-8") as fh:
            json.dump({"engine": "fx", "recipe": "burst"}, fh)
        code, said = run(["smoke", "--grid", "4", "--cell", "64", *self.dirs])
        self.assertEqual(code, 1)
        self.assertIn("is not a liquid spec", said["summary"])


class TheRegister(unittest.TestCase):
    def test_each_solver_proves_its_own_method(self):
        by = M.load()[1]
        for m in ("liquid_sim", "flip_fluid", "particle_fluid", "foam_spray"):
            self.assertEqual(by[m]["state"], "has")
            self.assertIn("NEVER matched to a real scene", by[m]["how"])

        def proves(method, block):
            spec = {"engine": "fx", "recipe": "liquid", "frames": 64, "grid": 8, "cell": 128, "liquid": block}
            return any(M.texture_proves(alt["texture"], spec) for alt in by[method]["proof"])

        self.assertTrue(proves("flip_fluid", {"solver": "flip"}) and proves("flip_fluid", {}))            # flip is what a spec with no solver gets
        self.assertFalse(proves("flip_fluid", {"solver": "pbf"}))
        self.assertTrue(proves("particle_fluid", {"solver": "pbf"}))
        self.assertFalse(proves("particle_fluid", {"solver": "flip"}) or proves("particle_fluid", {}))
        self.assertTrue(proves("liquid_sim", {"solver": "pbf"}) and proves("liquid_sim", {"solver": "flip"}))
        self.assertTrue(proves("foam_spray", {"scene": "dam"}) and proves("foam_spray", {"scene": "drop", "foam": True}))
        self.assertFalse(proves("foam_spray", {"scene": "dam", "foam": False}) or proves("foam_spray", {"scene": "slosh"}))
        for m in ("liquid_sim", "flip_fluid", "particle_fluid", "foam_spray"):
            self.assertFalse(any(M.texture_proves(alt["texture"], {"engine": "fx", "recipe": "wave"}) for alt in by[m]["proof"]))
        self.assertEqual(L.checked(L.new_spec("flip", "dam"))["solver"], "flip")
        # a spec kit vfx would never bake proves nothing: another engine, no block, a block the solver refuses
        for bad in ({"engine": "blender", "recipe": "liquid", "liquid": {}}, {"engine": "fx", "recipe": "liquid"},
                    {"engine": "fx", "recipe": "liquid", "liquid": {"foam": 1}}, {"engine": "fx", "recipe": "liquid", "grid": 6, "liquid": {}},
                    {"engine": "fx", "recipe": "liquid", "liquid": {"scene": "dam", "fill": 0.5}}):
            for m in ("liquid_sim", "flip_fluid", "foam_spray"):
                self.assertFalse(any(M.texture_proves(alt["texture"], bad) for alt in by[m]["proof"]), (m, bad))


if __name__ == "__main__":
    unittest.main()
