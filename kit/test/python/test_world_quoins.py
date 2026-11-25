"""test_world_quoins.py - CORNER QUOINS as one instanced strip (kit/world/quoins.py; LIMITATIONS_FIXES_V3.md stage B.1:
"corner quoins as instanced strips - never stripped like gothic_blender.py:551"). Held here: a storey is cut into
whole courses (the first on its foot, the last at its top, a mortar joint between); long and short stones in turn on
each face; every face faces OUT of its stone (a face turned in is not drawn in Roblox); no two faces of the strip
share a plane where they overlap (no flicker inside the strip); it stands PROJ proud of both wall faces and nothing of
it is behind them; it costs a few hundred triangles (one storey of one corner), and the gothic set's recipes ask for
it (gc_house_a/b/c "quoins": "gc_quoin", a gothic_quoin recipe a storey tall).
Not claimed: how it looks - that is the mesh's preview and the built world, looked at."""
import importlib.util
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..", "..")
_spec = importlib.util.spec_from_file_location("kit_world_quoins", os.path.join(HERE, "..", "..", "world", "quoins.py"))
Q = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(Q)


def inside_stone(pt, k, h=14.0):
    """is pt inside course k's stone (the L: front arm + side arm, standing PROJ out of the wall)?"""
    z0, z1 = Q.courses(h)[k]
    lf, ls = (Q.LONG, Q.SHORT) if k % 2 == 0 else (Q.SHORT, Q.LONG)
    x, y, z = pt
    if not (z0 < z < z1):
        return False
    front = -Q.PROJ < x < lf and -Q.PROJ < y < 0
    side = -Q.PROJ < x < 0 and -Q.PROJ < y < ls
    return front or side


class Strip(unittest.TestCase):
    def test_whole_courses_with_joints(self):
        cs = Q.courses(14.0)
        self.assertEqual(len(cs), 10)
        self.assertAlmostEqual(cs[0][0], 0.0)
        self.assertAlmostEqual(cs[-1][1], 14.0)
        for (a0, a1), (b0, b1) in zip(cs, cs[1:]):
            self.assertAlmostEqual(b0 - a1, Q.JOINT)
            self.assertGreater(a1, a0)
        self.assertEqual(len(Q.courses(12.0)), 9)  # (a 12-stud storey: 9 courses of 1.33)

    def test_long_and_short_in_turn(self):
        faces = Q.strip(14.0)
        self.assertEqual(len(faces), 8 * 10 + 2 * 9)  # (8 faces a stone, 2 of mortar a joint)
        fronts = [max(p[0] for p in f[0]) for i, f in enumerate(faces) if i % 8 == 0 and f[3] != "mortar"]
        sides = [max(p[1] for p in f[0]) for i, f in enumerate(faces) if i % 8 == 1 and f[3] != "mortar"]
        self.assertEqual(fronts[:4], [Q.LONG, Q.SHORT, Q.LONG, Q.SHORT])
        self.assertEqual(sides[:4], [Q.SHORT, Q.LONG, Q.SHORT, Q.LONG])

    def test_every_face_faces_out_of_its_stone(self):
        for i, (pts, _, _, role) in enumerate(Q.strip(14.0)):
            if role == "mortar":
                continue  # (the mortar is a single face set back in its joint: held below)
            k = role
            n = Q.normal(pts)
            cx = sum(p[0] for p in pts) / 4
            cy = sum(p[1] for p in pts) / 4
            cz = sum(p[2] for p in pts) / 4
            e = 0.01
            self.assertTrue(inside_stone((cx - n[0] * e, cy - n[1] * e, cz - n[2] * e), k), (i, n))
            self.assertFalse(inside_stone((cx + n[0] * e, cy + n[1] * e, cz + n[2] * e), k), (i, n))

    def test_no_two_faces_overlap_in_one_plane(self):
        faces = Q.strip(14.0)

        def box(pts):
            return [(min(p[a] for p in pts), max(p[a] for p in pts)) for a in range(3)]

        for i in range(len(faces)):
            for j in range(i + 1, len(faces)):
                a, b = box(faces[i][0]), box(faces[j][0])
                # (two flat faces in one plane: the same flat axis at the same place, and an overlap of area)
                for ax in range(3):
                    if a[ax][1] - a[ax][0] < 1e-9 and b[ax][1] - b[ax][0] < 1e-9 and abs(a[ax][0] - b[ax][0]) < 1e-6:
                        others = [o for o in range(3) if o != ax]
                        over = all(min(a[o][1], b[o][1]) - max(a[o][0], b[o][0]) > 1e-6 for o in others)
                        self.assertFalse(over, (i, j))

    def test_proud_of_the_walls_and_nothing_behind_them(self):
        pts = [p for f in Q.strip(14.0) for p in f[0]]
        self.assertAlmostEqual(min(p[0] for p in pts), -Q.PROJ)
        self.assertAlmostEqual(min(p[1] for p in pts), -Q.PROJ)
        # (nothing inside the building: a point with x > 0 and y > 0 at once)
        self.assertFalse(any(p[0] > 1e-9 and p[1] > 1e-9 for p in pts))
        self.assertAlmostEqual(max(p[0] for p in pts), Q.LONG)
        self.assertAlmostEqual(max(p[2] for p in pts), 14.0)

    def test_the_joints_are_filled_so_the_corner_seam_never_shows(self):
        # every joint, at the corner itself, has mortar on both faces facing out, set back from the stones and in
        # front of the wall
        faces = Q.strip(14.0)
        mortar = [f for f in faces if f[3] == "mortar"]
        cs = Q.courses(14.0)
        for k in range(len(cs) - 1):
            z = (cs[k][1] + cs[k + 1][0]) / 2
            front = [f for f in mortar if all(abs(p[1] - f[0][0][1]) < 1e-9 for p in f[0]) and min(p[2] for p in f[0]) < z < max(p[2] for p in f[0])]
            side = [f for f in mortar if all(abs(p[0] - f[0][0][0]) < 1e-9 for p in f[0]) and min(p[2] for p in f[0]) < z < max(p[2] for p in f[0])]
            self.assertEqual((len(front), len(side)), (1, 1), k)
            for f, ax in ((front[0], 1), (side[0], 0)):
                self.assertTrue(-Q.PROJ < f[0][0][ax] < 0)
                self.assertAlmostEqual(min(p[1 - ax] for p in f[0]), f[0][0][ax])  # (it reaches the corner itself)
                n = Q.normal(f[0])
                self.assertLess(n[ax], -0.99)  # (facing out of the wall)

    def test_a_few_hundred_triangles(self):
        self.assertEqual(2 * len(Q.strip(14.0)), 196)

    def test_the_gothic_set_asks_for_it(self):
        if not os.path.isfile(os.path.join(ROOT, "assets", "worlds", "meshes", "gothic.json")):
            self.skipTest("the author's assets/worlds/meshes/gothic.json is not shipped with the kit")
        with open(os.path.join(ROOT, "assets", "worlds", "meshes", "gothic.json"), encoding="utf-8") as f:
            recipes = json.load(f)
        byname = {r["name"]: r for r in recipes}
        for house in ("gc_house_a", "gc_house_b", "gc_house_c"):
            self.assertEqual(byname[house].get("quoins"), "gc_quoin")
            self.assertEqual(float(byname["gc_quoin"]["height"]), float(byname[house]["floorHeight"]))
        self.assertEqual(byname["gc_quoin"]["kind"], "gothic_quoin")


if __name__ == "__main__":
    unittest.main()
