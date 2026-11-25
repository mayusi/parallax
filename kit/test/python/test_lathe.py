"""kit/blender/rbx_lathe.py: a generated ROUND body made truly round, its colour bands read from the view (owner
2026-10-16, batch 2 "still bad": the extinguisher's body streaked and its dome chrome, the barrel's hoops in patches).
A lumpy cylinder is trued, a square prism and an appendage stay; a hoop row is a band at any light."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
import rbx_lathe as L  # noqa: E402


def cylinder(r=0.3, h=1.0, rings=240, around=96, lump=0.04, seed=0):
    rng = np.random.default_rng(seed)
    z = np.repeat(np.linspace(0, h, rings), around)
    a = np.tile(np.linspace(0, 2 * np.pi, around, endpoint=False), rings)
    rr = r * (1 + lump * rng.uniform(-1, 1, len(z)))
    return np.column_stack([rr * np.cos(a), rr * np.sin(a), z])


class TrueRound(unittest.TestCase):
    def test_a_lumpy_cylinder_comes_out_round(self):
        V = cylinder()
        out, facts = L.true_round(V)
        self.assertGreater(facts["round_share"], 0.9)
        rho0 = np.hypot(V[:, 0], V[:, 1])
        rho1 = np.hypot(out[:, 0], out[:, 1])
        mid = (V[:, 2] > 0.1) & (V[:, 2] < 0.9)
        self.assertLess(rho1[mid].std() / rho1[mid].mean(), 0.25 * rho0[mid].std() / rho0[mid].mean())
        self.assertTrue(np.allclose(out[:, 2], V[:, 2]))   # (radial only: the heights stay)

    def test_a_square_prism_is_not_round_and_stays(self):
        rings, side = 40, 25
        z = np.repeat(np.linspace(0, 1, rings), 4 * side)
        s = np.linspace(-0.3, 0.3, side, endpoint=False)
        ring = np.concatenate([np.column_stack([s, np.full(side, -0.3)]), np.column_stack([np.full(side, 0.3), s]),
                               np.column_stack([-s, np.full(side, 0.3)]), np.column_stack([np.full(side, -0.3), -s])])
        V = np.column_stack([np.tile(ring, (rings, 1)), z])
        out, facts = L.true_round(V)
        self.assertEqual(facts["round_share"], 0.0)
        self.assertTrue(np.allclose(out, V))

    def test_an_appendage_keeps_its_place(self):
        V = cylinder(lump=0.03)
        bracket = np.column_stack([np.full(50, 0.42), np.linspace(-0.02, 0.02, 50), np.linspace(0.4, 0.6, 50)])
        out, _f = L.true_round(np.vstack([V, bracket]))
        self.assertTrue(np.allclose(out[-50:], bracket))


class Bands(unittest.TestCase):
    def test_a_hoop_row_is_steel_at_any_light(self):
        # a barrel lit from above: wood and grey hoops both darker at the bottom (the concept's own light)
        h, w = 200, 120
        img = np.zeros((h, w, 4), np.uint8)
        img[20:180, 20:100, 3] = 255
        for y in range(20, 180):
            light = 1.0 - 0.65 * (y - 20) / 160
            hoop = (28 <= y < 45) or (155 <= y < 173)   # (each two slices tall)
            c = np.array([190, 190, 190] if hoop else [205, 165, 120], float) * light
            img[y, 20:100, :3] = c.clip(0, 255).astype(np.uint8)
        wood = [(141, 116, 82), (84, 67, 49), (172, 153, 123)]
        steel = [(125, 122, 115)]
        lab = L.bands(img, n=20, families=[wood, steel])
        self.assertEqual(lab[1], 1)    # (the bottom hoop: dark grey, still steel)
        self.assertEqual(lab[18], 1)   # (the top hoop: pale grey)
        self.assertEqual(lab[10], 0)

    def test_a_mixed_row_is_no_band(self):
        img = np.zeros((100, 100, 4), np.uint8)
        img[10:90, 10:90, 3] = 255
        img[10:90, 10:90, :3] = 25
        img[10:90, 30:70:2, :3] = 225   # (a lantern's panes between its bars: half and half)
        lab = L.bands(img, n=10, families=[[(28, 28, 27)], [(224, 226, 227)]])
        self.assertTrue(all(x is None for x in lab))


class Staves(unittest.TestCase):
    def test_grooves_at_equal_angles_on_the_skin_only(self):
        V = cylinder(lump=0.0, around=360)
        out, facts = L.true_round(V)
        lid = np.column_stack([np.linspace(-0.1, 0.1, 30), np.zeros(30), np.full(30, 1.0)])   # (inside: never grooved)
        allv = np.vstack([out, lid])
        g, moved = L.staves(allv, facts["profile"], n=30)
        self.assertGreater(moved, 0)
        self.assertTrue(np.allclose(g[-30:], lid))
        rho = np.hypot(g[:-30, 0], g[:-30, 1])
        ang = np.degrees(np.arctan2(g[:-30, 1], g[:-30, 0])) % 12   # (30 staves: a groove every 12 degrees)
        on = (ang < 0.5) | (ang > 11.5)
        mid = np.abs(ang - 6) < 1
        self.assertLess(rho[on].mean(), rho[mid].mean() * 0.997)   # (the grooves dip in)
        self.assertTrue(np.allclose(rho[mid], rho[mid].mean(), rtol=1e-3))   # (between them: the skin as it was)


if __name__ == "__main__":
    unittest.main()
