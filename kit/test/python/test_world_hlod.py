"""test_world_hlod.py - the far ranges as HLOD proxies (kit/world/hlod.py; LIMITATIONS_FIXES_V3.md stage F.2: "batch
far blocks into <= 2k-tri HLOD proxy clusters replacing the cardboard wedges").
Held here: each of a ring's four quarters is under 2000 triangles and inside a MeshPart's 2048 studs; a ring too big
for one is refused, said; every triangle faces up (Roblox draws one side); the quarters share their seams vertex for
vertex (no crack in the skyline); the ring's feet lie on the far land (y 0) and its crests reach the asked heights;
the same recipe makes the same ring. Not claimed: that it reads as mountains - the built world, looked at."""
import importlib.util
import math
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_world_hlod", os.path.join(HERE, "..", "..", "world", "hlod.py"))
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)

SPEC = {"radius": 1500, "count": 24, "height": [200, 500], "seed": 1}


def up(v, t):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = v[t[0]], v[t[1]], v[t[2]]
    ux, uy, uz = bx - ax, by - ay, bz - az
    wx, wy, wz = cx - ax, cy - ay, cz - az
    return uz * wx - ux * wz  # (the normal's y)


class Ring(unittest.TestCase):
    def test_four_quarters_each_inside_the_budgets(self):
        for q in (1, 2, 3, 4):
            v, t = H.ring(SPEC, q)
            self.assertLessEqual(len(t), H.MAX_TRIS)
            lo, hi = H.bounds(v)
            for k in range(3):
                self.assertLessEqual(hi[k] - lo[k], H.MAX_SIDE)

    def test_a_ring_too_big_for_a_meshpart_is_refused(self):
        with self.assertRaises(ValueError) as e:
            H.ring(dict(SPEC, radius=1800), 1)
        self.assertIn("2048", str(e.exception))

    def test_every_triangle_faces_up(self):
        for q in (1, 2, 3, 4):
            v, t = H.ring(SPEC, q)
            self.assertTrue(all(up(v, tri) > 0 for tri in t), q)

    def test_the_quarters_share_their_seams(self):
        rings = [H.ring(SPEC, q)[0] for q in (1, 2, 3, 4)]
        W = H.STEPS_R + 1
        for q in range(4):
            last = rings[q][-W:]
            first = rings[(q + 1) % 4][:W]
            for a, b in zip(last, first):
                self.assertLess(math.dist(a, b), 1e-6)

    def test_feet_on_the_far_land_crests_at_height(self):
        v, _ = H.ring(SPEC, 1)
        W = H.STEPS_R + 1
        for i in range(H.STEPS_A + 1):
            self.assertEqual(v[i * W][1], 0.0)
            self.assertEqual(v[i * W + W - 1][1], 0.0)
        top = max(max(p[1] for p in H.ring(SPEC, q)[0]) for q in (1, 2, 3, 4))
        self.assertGreater(top, 300)
        self.assertLessEqual(top, 500 + 1e-6)

    def test_the_skyline_never_drops_to_the_ground_between_massifs(self):
        # on the ring's middle line, every angle stands at least the foothills' least height
        W = H.STEPS_R + 1
        mid = H.STEPS_R // 2
        floor = 200 * H.FOOTHILL * 0.5
        for q in (1, 2, 3, 4):
            v, _ = H.ring(SPEC, q)
            for i in range(H.STEPS_A + 1):
                self.assertGreater(v[i * W + mid][1], floor)

    def test_the_same_recipe_the_same_ring(self):
        self.assertEqual(H.ring(SPEC, 2), H.ring(dict(SPEC), 2))
        self.assertNotEqual(H.ring(SPEC, 2)[0], H.ring(dict(SPEC, seed=2), 2)[0])


if __name__ == "__main__":
    unittest.main()
