"""A mesh that is not closed, READ (kit/blender/rbx_repair.py; the owner's method lists, 2026-11-13: "non-manifold
cleanup"; the 3D methods audit, M7): a seam never welded, a flat hole, an open rim and the border of a surface with
no thickness are told apart, each with what closes it."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_repair as R  # noqa: E402

CUBE = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]   # outward


def mesh(faces):
    corner = [v for f in faces for v in f]
    total = [len(f) for f in faces]
    start = np.cumsum([0] + total[:-1])
    return np.array(corner), np.array(start), np.array(total)


def tube(n=16, r=0.5, h=2.0):
    ring = [(r * np.cos(2 * np.pi * i / n), r * np.sin(2 * np.pi * i / n)) for i in range(n)]
    verts = [(x, y, 0.0) for x, y in ring] + [(x, y, h) for x, y in ring]
    faces = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    return verts, faces


def probe():
    """kit/selftest/blender/check_repair_cases.py run once in Blender -> its answers (None without Blender)"""
    import json  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
    import cad_check  # noqa: PLC0415

    blender = cad_check.blender()
    if not blender or not os.path.isfile(blender):
        return None
    if not hasattr(probe, "answers"):
        e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_repair"))
        r = subprocess.run([blender, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                            os.path.join(ROOT, "kit", "selftest", "blender", "check_repair_cases.py"), "--",
                            "--no-preview"], cwd=ROOT, capture_output=True, text=True, timeout=900, env=e,
                           encoding="utf-8", errors="replace")
        line = next((x for x in r.stdout.splitlines() if x.startswith("REPAIR_CASES ")), None)
        assert r.returncode == 0 and line, (r.stderr or r.stdout)[-800:]
        probe.answers = json.loads(line.split(" ", 1)[1])
    return probe.answers


class Faults(unittest.TestCase):
    def test_a_closed_box_has_none(self):
        t = R.edge_table(*mesh(FACES))
        self.assertEqual(R.faults(t), {"open": 0, "fins": 0, "flipped": 0})
        self.assertEqual(R.open_loops(t), [])
        found = R.read(CUBE, *mesh(FACES))
        self.assertEqual((found["twins"], found["loops"], R.said(found)), (0, [], ""))

    def test_a_face_wound_against_its_neighbours(self):
        faces = [FACES[0][::-1]] + FACES[1:]
        self.assertEqual(R.faults(R.edge_table(*mesh(faces))), {"open": 0, "fins": 0, "flipped": 4})
        self.assertIn("4 edges between faces wound against each other", R.said(R.read(CUBE, *mesh(faces))))

    def test_an_edge_three_faces_share(self):
        verts = [(0, 0, 0), (0, 0, 1), (1, 0, 0), (1, 0, 1), (0, 1, 0), (0, 1, 1), (-1, 0, 0), (-1, 0, 1)]
        faces = [(0, 2, 3, 1), (0, 1, 5, 4), (0, 6, 7, 1)]                # three walls on the edge 0-1
        t = R.edge_table(*mesh(faces))
        self.assertEqual(R.faults(t)["fins"], 1)
        self.assertIn("1 edge shared by three or more faces", R.said(R.read(verts, *mesh(faces))))

    def test_face_normals(self):
        n = R.face_normals(CUBE, *mesh(FACES))
        self.assertTrue(np.allclose(n, [(0, 0, -1), (0, 0, 1), (0, -1, 0), (1, 0, 0), (0, 1, 0), (-1, 0, 0)]))


class Kinds(unittest.TestCase):
    def test_a_missing_face_is_a_flat_hole(self):
        found = R.read(CUBE, *mesh(FACES[:1] + FACES[2:]))                # the top is gone
        self.assertEqual(found["faults"]["open"], 4)
        self.assertEqual(len(found["loops"]), 1)
        d = found["loops"][0]
        self.assertEqual((d["kind"], d["n"]), ("hole", 4))
        self.assertAlmostEqual(d["area"], 1.0, places=5)
        self.assertAlmostEqual(d["size"], np.sqrt(2), places=4)
        self.assertEqual(d["centre"], (0.5, 0.5, 1.0))
        self.assertEqual(sorted(d["verts"].tolist()), [4, 5, 6, 7])
        self.assertEqual(R.said(found), "1 flat hole (1.41 studs across)")

    def test_a_tube_without_its_ends_is_two_holes(self):
        verts, faces = tube()
        found = R.read(verts, *mesh(faces))
        self.assertEqual([d["kind"] for d in found["loops"]], ["hole", "hole"])
        self.assertEqual(sorted(d["centre"][2] for d in found["loops"]), [0.0, 2.0])
        self.assertIn("2 flat holes (1, 1 studs across)", R.said(found))

    def test_a_flat_surface_with_no_thickness_is_not_a_hole(self):
        verts = [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)]
        found = R.read(verts, *mesh([(0, 1, 2, 3)]))
        self.assertEqual([d["kind"] for d in found["loops"]], ["sheet"])   # a cap would lie ON the face
        self.assertIn("border of a surface with no thickness", R.said(found))

    def test_a_torn_patch_that_is_not_flat_is_a_rim(self):
        verts, faces = tube(n=16)
        verts = verts + [(0.0, 0.0, 0.0), (0.0, 0.0, 2.0)]
        caps = [(i, 32, (i + 1) % 16) for i in range(16)] + [(16 + i, 16 + (i + 1) % 16, 33) for i in range(16)]
        torn = [f for k, f in enumerate(faces) if k not in (0, 1, 2)] + caps   # three wall panels torn out
        found = R.read(verts, *mesh(torn))
        self.assertEqual([d["kind"] for d in found["loops"]], ["rim"])     # round the bend: no flat cap fits
        self.assertGreater(found["loops"][0]["off"], 0.02)

    def test_a_crack_whose_points_do_not_match_is_a_slit(self):
        # a box whose top face's front edge has a point in its middle that the front wall does not have
        verts = CUBE + [(0.5, 0.0, 1.0)]
        faces = [FACES[0], (4, 8, 5, 6, 7)] + FACES[2:]
        found = R.read(verts, *mesh(faces))
        self.assertEqual(found["faults"]["open"], 3)
        self.assertEqual([d["kind"] for d in found["loops"]], ["slit"])
        self.assertIn("1 slit", R.said(found))


class Seams(unittest.TestCase):
    def apart(self, noise=0.0):
        """the cube as six faces that share no point: a seam at every edge"""
        rng = np.random.default_rng(5)
        verts, faces = [], []
        for f in FACES:
            faces.append(tuple(range(len(verts), len(verts) + 4)))
            verts += [tuple(np.array(CUBE[v], float) + rng.uniform(-noise, noise, 3)) for v in f]
        return verts, faces

    def test_a_seam_never_welded_is_found_and_welding_closes_it(self):
        verts, faces = self.apart(noise=2e-7)
        found = R.read(verts, *mesh(faces), weld=1e-5)
        self.assertEqual(found["faults"]["open"], 24)
        self.assertEqual(found["twins"], 24)                               # three points at each of 8 corners
        self.assertEqual(found["after_weld"], {"open": 0, "fins": 0, "flipped": 0})
        self.assertEqual(found["loops"], [])
        self.assertEqual(len(found["weld"]), 16)                           # 24 points become 8
        self.assertEqual(R.said(found), "a seam of 24 point pairs never welded")

    def test_points_a_modelling_distance_apart_are_not_a_seam(self):
        verts, faces = self.apart(noise=2e-3)
        found = R.read(verts, *mesh(faces), weld=1e-5)
        self.assertEqual(found["twins"], 0)
        self.assertEqual(len(found["loops"]), 6)

    def test_two_ends_of_one_short_edge_are_not_twins(self):
        verts = [(0, 0, 0), (1e-6, 0, 0), (0, 1, 0)]                       # a sliver triangle: its short edge
        t = R.edge_table(*mesh([(0, 1, 2)]))
        self.assertEqual(len(R.twins(verts, t, 1e-5)), 0)

    def test_the_weld_map_takes_every_group_to_its_smallest(self):
        m = R.weld_map(np.array([(3, 7), (7, 9), (2, 5)]))
        self.assertEqual(m, {7: 3, 9: 3, 5: 2})
        self.assertTrue(np.array_equal(R.welded(np.array([9, 5, 1, 7]), m), [3, 2, 1, 3]))


class Touching(unittest.TestCase):
    def test_a_loop_that_passes_a_point_twice_is_split_there(self):
        # a 2 x 2 grid of squares with two diagonal ones missing: the two holes share the middle point (4)
        verts = [(x, y, 0.0) for y in range(3) for x in range(3)]
        faces = [(1, 2, 5, 4), (3, 4, 7, 6)]                               # the other two squares
        found = R.read(verts, *mesh(faces))
        loops = sorted(sorted(d["verts"].tolist()) for d in found["loops"])
        self.assertEqual(loops, [[1, 2, 4, 5], [3, 4, 6, 7]])              # each square's own border: two loops
        self.assertEqual(R._simple([0, 1, 2, 0, 3, 4], list("abcdef")),
                         [([0, 1, 2], ["a", "b", "c"]), ([0, 3, 4], ["d", "e", "f"])])


class Loops(unittest.TestCase):
    def test_a_loop_is_walked_in_order_and_knows_its_corners(self):
        corner, start, total = mesh(FACES[:1] + FACES[2:])
        t = R.edge_table(corner, start, total)
        (loop, closed, corners), = R.open_loops(t)
        self.assertTrue(closed)
        self.assertEqual(len(loop), 4)
        for v, c in zip(loop.tolist(), corners.tolist(), strict=True):
            self.assertEqual(int(corner[c]), v)                            # each edge starts at its corner
        ring = loop.tolist() + [loop[0]]
        want = {(4, 5), (5, 6), (6, 7), (7, 4)}
        self.assertTrue(all((min(a, b), max(a, b)) in {(min(x, y), max(x, y)) for x, y in want}
                            for a, b in zip(ring, ring[1:], strict=False)))

    def test_a_chain_that_cannot_close(self):
        d = R.describe([(0, 0, 0), (1, 0, 0), (2, 0, 0)], [0, 1, 2], closed=False)
        self.assertEqual((d["kind"], d["n"]), ("chain", 2))


class Build(unittest.TestCase):
    """a.repair on real parts (state: open edges, faces of no area, points, faces)"""

    def setUp(self):
        self.d = probe()
        if self.d is None:
            self.skipTest("Blender not found")

    def test_a_ring_shaped_opening_is_one_face_with_its_hole(self):
        before, after, doubled, volume = self.d["ring"]
        self.assertEqual((before[0], after[0], after[1]), (32, 0, 0))     # the thick pipe's open end, closed
        self.assertEqual(doubled, 0)                                       # ... and no face lying on another
        self.assertAlmostEqual(volume, 3.14159 * (0.3 ** 2 - 0.2 ** 2) * 0.8, delta=0.012)   # 16-sided: a little less

    def test_a_weld_that_would_make_an_edge_three_faces_share_is_not_kept(self):
        self.assertEqual(self.d["cards"], {"welded": 0, "open": [12, 12], "fins": [0, 0]})

    def test_two_holes_that_share_one_point_are_two_holes(self):
        before, after = self.d["twin"]
        self.assertEqual((before[0], after[0]), (8, 0))

    def test_a_flat_hole_is_capped(self):
        self.assertEqual(self.d["bin"], [[4, 0, 8, 5], [0, 0, 8, 6]])     # the sixth face, on the same eight points

    def test_a_seam_never_welded_is_welded(self):
        self.assertEqual(self.d["shell"], [[24, 0, 24, 6], [0, 0, 8, 6]])  # 24 points become 8, nothing added

    def test_a_copy_is_repaired_with_its_part(self):
        before, after = self.d["pipe"]
        self.assertEqual(before, [32, 0, 32, 16])
        self.assertEqual(after, [[0, 0, 32, 18], [0, 0, 32, 18]])         # the part and its mirror: both ends

    def test_what_no_repair_closes_is_refused_and_left_as_it_was(self):
        for case, word in (("sheet", "border of a surface with no thickness"), ("torn", "1 open rim"),
                           ("uncapped", "1 flat hole")):
            got = self.d[case]
            self.assertIn("cannot be closed by a repair", got["said"], case)
            self.assertIn(word, got["said"], case)
            self.assertTrue(got["unchanged"], case)
        self.assertIn("cap=False: flat holes were left", self.d["uncapped"]["said"])

    def test_a_weld_of_a_modelling_distance_is_refused(self):
        self.assertIn("never a modelling distance", self.d["far"]["said"])
        self.assertTrue(self.d["far"]["unchanged"])

    def test_a_closed_part_is_left_alone_and_nothing_is_said_of_it(self):
        self.assertEqual(self.d["block"][0], self.d["block"][1])
        self.assertEqual([(r["part"], r["said"]) for r in self.d["repaired"]],
                         [("Bin", "1 hole capped"), ("Shell", "16 seam points welded"), ("Pipe", "2 holes capped"),
                          ("Ring", "2 holes capped"), ("Twin", "2 holes capped")])


if __name__ == "__main__":
    unittest.main()
