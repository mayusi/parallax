"""kit/tools/cad_run.py (a.cad's runner, in the cad env): a part comes out at the volume worked out by hand, measured
numbers reach the code as P, a failing line and a missing `part` are said plainly. Skipped when the cad env is not
set up (lune run kit tools setup cad)."""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))

import tools  # noqa: E402

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools", "cad_run.py")
PY = tools.env_python("cad")


def run(code, params=None, tol=None, angle=None, fillet=None):
    with tempfile.TemporaryDirectory() as tmp:
        src, out = os.path.join(tmp, "part.py"), os.path.join(tmp, "part.npz")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(code)
        cmd = [PY, RUNNER, src, "--out", out] + (["--params", json.dumps(params)] if params else [])
        cmd += (["--tol", str(tol)] if tol is not None else []) + (["--angle", str(angle)] if angle is not None else [])
        cmd += ["--fillet", str(fillet)] if fillet else []
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        said = json.loads([line for line in r.stdout.splitlines() if line.startswith("{")][-1])
        arrays = None
        if os.path.isfile(out):
            import numpy as np
            with np.load(out) as d:
                arrays = (d["verts"].copy(), d["tris"].copy())
        return r.returncode, said, arrays


class TestFillSmallHoles(unittest.TestCase):
    """the mesher's small holes (a sliver where curved faces meet) fanned shut — plain Python, no cad env"""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(RUNNER))
        import collections  # noqa: PLC0415

        import cad_run  # noqa: PLC0415

        self.cr = cad_run
        P_ = collections.namedtuple("P_", "X Y Z")
        self.verts = [P_(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)]  # a unit cube, its 12 triangles
        quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        self.tris = [t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))]
        self.assertEqual(cad_run.open_edges(self.verts, self.tris), 0)

    def test_a_missing_triangle_is_filled(self):
        tris, filled, left = self.cr.fill_small_holes(self.verts, self.tris[1:])
        self.assertEqual((filled, left), (1, 0))
        self.assertEqual(len(tris), 12)

    def test_a_missing_side_is_filled_and_closed_the_right_way_round(self):
        tris, filled, left = self.cr.fill_small_holes(self.verts, self.tris[2:])   # a 4-edge hole
        self.assertEqual((filled, left), (1, 0))
        directed = {(a, b) for t in tris for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0]))}
        self.assertTrue(all((b, a) in directed for a, b in directed))  # every edge run both ways: one closed winding

    def test_a_long_hole_is_left_alone(self):
        tris, filled, left = self.cr.fill_small_holes(self.verts, self.tris[2:], max_loop=3)
        self.assertEqual((filled, left), (0, 4))


class TestVolumeTruth(unittest.TestCase):
    """a solid that disagrees with its own mesh is named (the Glock's frame: 9.5% off, open edges only after the
    build's import, 2026-10-10) — plain Python, no cad env"""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(RUNNER))
        import cad_run  # noqa: PLC0415

        self.cr = cad_run

    def test_chords_may_lose_area_times_tol(self):
        self.assertAlmostEqual(self.cr.volume_allowed(30000.0, 100000.0, 0.05), 0.015)
        self.assertEqual(self.cr.volume_allowed(10.0, 100000.0, 0.05), 0.005)   # (never under half a percent)

    def test_the_glock_frame_is_named_and_the_rated_one_passes(self):
        said = self.cr.volume_truth(0.0954, 0.014)
        self.assertIn("SOLID is wrong", said)
        self.assertIn("9.5%", said)
        self.assertIsNone(self.cr.volume_truth(0.00376, 0.0149))   # (build 50's frame: the owner's 85)

    def test_a_legit_loft_and_an_open_mesh_are_not_called_wrong(self):
        self.assertIsNone(self.cr.volume_truth(0.0099, 0.0065))    # (the ARP grip: closed, right, a B-spline loft)
        self.assertIsNone(self.cr.volume_truth(0.04, 0.0147))      # (the Glock's frames that built without a tear)
        self.assertIsNone(self.cr.volume_truth(0.5, 0.01, closed=False))   # (off by its holes: said as open edges)
        self.assertIsNotNone(self.cr.volume_truth(1.0, 0.15))      # (a garbage BRep)


@unittest.skipUnless(PY, "the cad env is not set up (lune run kit tools setup cad)")
class TestCadRun(unittest.TestCase):
    def test_a_filleted_box_measures_its_hand_worked_volume_and_size(self):
        code, said, (verts, tris) = run(
            "with BuildPart() as part:\n    Box(P['w'], 30, 20)\n    fillet(part.edges().filter_by(Axis.Z), 3)\n",
            {"w": 40})
        self.assertEqual(code, 0, said)
        want = 40 * 30 * 20 - 4 * (9 - 9 * math.pi / 4) * 20
        self.assertAlmostEqual(said["volume_mm3"], want, delta=0.01)
        self.assertEqual((said["solids"], said["valid"]), (1, True))
        self.assertEqual(said["bbox_mm"], [[-20.0, -15.0, -10.0], [20.0, 15.0, 10.0]])
        self.assertEqual(verts.shape[1], 3)
        self.assertEqual(len(tris), said["triangles"])
        self.assertAlmostEqual(float(verts[:, 0].max()), 20.0, places=6)  # millimetres, the kit's axes

    def test_real_parts_down_to_the_screws(self):
        # an M3 x 10 socket head cap screw (ISO 4762 head 5.68 x 3 mm), a 3 x 20 mm pin, a ground compression spring
        code, said, _ = run("part = screw('M3-0.5', 10)")
        self.assertEqual(code, 0, said)
        self.assertAlmostEqual(said["bbox_mm"][0][2], -10.0, places=3)
        self.assertAlmostEqual(said["bbox_mm"][1][2], 3.0, places=3)
        self.assertAlmostEqual(said["bbox_mm"][1][0] * 2, 5.68, delta=0.05)
        code, said, _ = run("part = pin(3.0, 20, chamfer=0)")
        self.assertAlmostEqual(said["volume_mm3"], math.pi * 1.5 ** 2 * 20, delta=0.05)
        code, said, _ = run("part = spring(8.0, 1.0, 30.0, 8)")
        self.assertEqual((code, said["valid"]), (0, True), said)
        wire = 8 * math.hypot(math.pi * 8.0, 32.0 / 8) * 30 / 32  # the helix inside the ground ends
        self.assertAlmostEqual(said["volume_mm3"], math.pi * 0.5 ** 2 * wire, delta=2.0)
        self.assertEqual([said["bbox_mm"][0][2], said["bbox_mm"][1][2]], [0.0, 30.0])
        code, said, _ = run("part = Cylinder(clearance('M3') / 2, 5)")
        self.assertAlmostEqual(said["volume_mm3"], math.pi * 1.7 ** 2 * 5, delta=0.05)  # ISO 273 normal: 3.4 mm

    def test_hard_edges_finds_the_corners_and_leaves_the_round_seams(self):
        # the count comes back as the size of a box (bbox x): a box has 12 corner edges, a cylinder its 2 rims (not its
        # seam), a cylinder with both rims rounded none (its fillets' edges are tangent), and rounding what hard_edges
        # finds leaves nothing sharp
        for shape, want in (("Box(10, 10, 10)", 12), ("Cylinder(5, 10)", 2),
                            ("fillet(Cylinder(5, 10).edges(), 1.0)", 0)):
            code, said, _ = run(f"n = len(hard_edges({shape}))\npart = Box(max(n, 0.5), 1, 1)\n")
            self.assertEqual(code, 0, said)
            self.assertAlmostEqual(said["bbox_mm"][1][0] * 2, max(want, 0.5), places=3, msg=shape)
        code, said, _ = run("with BuildPart() as part:\n    Box(10, 10, 10)\n    fillet_each(hard_edges(), 1.0)\n"
                            "    n = len(hard_edges())\nassert n == 0, n\n")
        self.assertEqual(code, 0, said)
        self.assertLess(said["volume_mm3"], 1000.0)

    def test_clean_profile_puts_a_refused_outline_back_where_it_was(self):
        # a thin ring (0.8 mm walls) on a SIDE plane: its first rounding (1 mm) eats the walls, so clean_profile puts the
        # outline back and tries smaller — and the solid must still be where it was drawn (f 5..30, h 20..30)
        code, said, _ = run(
            "with BuildPart() as part:\n"
            "    with BuildSketch(Plane.ZY.offset(-2)):\n"
            "        Polygon((-5, 20), (-30, 20), (-30, 30), (-5, 30), align=None)\n"
            "        Polygon((-5.8, 20.8), (-29.2, 20.8), (-29.2, 29.2), (-5.8, 29.2), align=None, mode=Mode.SUBTRACT)\n"
            "        clean_profile(1.0)\n"
            "    extrude(amount=4)\n")
        self.assertEqual(code, 0, said)
        (x0, y0, z0), (x1, y1, z1) = said["bbox_mm"]
        self.assertAlmostEqual(y0, 20.0, delta=0.6)
        self.assertAlmostEqual(y1, 30.0, delta=0.6)
        self.assertAlmostEqual(z0, -30.0, delta=0.6)
        self.assertAlmostEqual(z1, -5.0, delta=0.6)

    def test_a_traced_outline_becomes_smooth_walls_a_fillet_takes(self):
        # a photo's trace: a 40 x 20 block whose top is a bump traced at 1 mm steps with pixel noise. outline() keeps
        # its 4 corners and fits ONE curve along the top (4 edges, not 44), stays where it was traced, and every edge of
        # its extrusion takes the full 1 mm fillet (none reduced)
        code, said, _ = run(
            "import math, random\n"
            "random.seed(3)\n"
            "pts = [(0, 0), (40, 0)] + [(40 - k, 20 + 3 * math.sin(math.pi * (40 - k) / 40) + random.uniform(-0.02, 0.02))"
            " for k in range(41)]\n"
            "face = outline(pts)\n"
            "assert len(face.edges()) == 4, len(face.edges())\n"
            "with BuildPart() as part:\n"
            "    with BuildSketch():\n"
            "        add(face)\n"
            "    extrude(amount=10)\n"
            "    fillet_soft(part.edges(), 1.0)\n")
        self.assertEqual(code, 0, said)
        self.assertNotIn("fillets_reduced", said)
        (x0, y0, z0), (x1, y1, z1) = said["bbox_mm"]
        self.assertAlmostEqual(x0, 0.0, delta=0.05)
        self.assertAlmostEqual(x1, 40.0, delta=0.05)
        self.assertAlmostEqual(y1, 23.0, delta=0.08)

    def test_smooth_profile_refits_a_traced_sketch_with_a_hole(self):
        # the same traced block built the usual way — polygons, a traced round hole cut out — then smooth_profile(): a
        # handful of smooth walls (not ~70 facets), the hole still there, and every edge of the extrusion takes the full
        # fillet. (Not after clean_profile(0.8): a corner rounded tighter in plan than the edge's fillet refuses it —
        # measured here, 1.0 fell to 0.5)
        code, said, _ = run(
            "import math, random\n"
            "random.seed(3)\n"
            "pts = [(0, 0), (40, 0)] + [(40 - k, 20 + 3 * math.sin(math.pi * (40 - k) / 40) + random.uniform(-0.02, 0.02))"
            " for k in range(41)]\n"
            "hole = [(20 + 5 * math.cos(2 * math.pi * k / 24), 9 + 5 * math.sin(2 * math.pi * k / 24)) for k in range(24)]\n"
            "with BuildPart() as part:\n"
            "    with BuildSketch() as sk:\n"
            "        Polygon(*pts, align=None)\n"
            "        Polygon(*hole, align=None, mode=Mode.SUBTRACT)\n"
            "        before = len(sk.sketch.edges())\n"
            "        smooth_profile()\n"
            "        after = len(sk.sketch.edges())\n"
            "    assert after <= 8 < before, (before, after)\n"
            "    assert len(sk.sketch.faces()[0].inner_wires()) == 1\n"
            "    extrude(amount=10)\n"
            "    fillet_soft(part.edges(), 1.0)\n")
        self.assertEqual(code, 0, said)
        self.assertNotIn("fillets_reduced", said)
        (x0, y0, z0), (x1, y1, z1) = said["bbox_mm"]
        self.assertAlmostEqual(x1 - x0, 40.0, delta=0.1)
        self.assertAlmostEqual(y1, 23.0, delta=0.1)
        hole_area = math.pi * 25 * math.sin(math.pi / 24) * math.cos(math.pi / 24) * 24 / math.pi  # (the 24-gon's)
        self.assertLess(said["volume_mm3"], (800 + 240 / math.pi - hole_area) * 10)

    def test_the_mesh_tolerance_is_millimetres(self):
        # a 50 mm radius cylinder meshed to 0.05 mm with no angle limit: its rim needs >= 70 sides to stay within
        # 0.05 mm of the circle (r (1 - cos(pi / n)) <= 0.05). Meshed RELATIVE to the edge's size (build123d's own
        # tessellate), it came out 15-sided — 1.1 mm off
        code, said, (verts, tris) = run("part = Cylinder(50, 10)", tol=0.05, angle=90)
        self.assertEqual(code, 0, said)
        rim = {(round(float(x), 3), round(float(y), 3)) for x, y, z in verts if abs(float(z) - 5.0) < 1e-6}
        self.assertGreaterEqual(len(rim), 60, len(rim))
        self.assertEqual(said["tol_mm"], 0.05)

    def test_fine_fillets_mesh_without_needle_triangles(self):
        # a traced block (smooth walls) with 0.4 mm fillets along both sides, meshed to 0.04 mm: next to no triangle
        # under the validator's zero-area line (7.8e-5 mm2 — 1e-9 square studs). Left free, the mesher strewed 2,344
        # needles along the fillets (cleaned on import, they tore the Glock frame open: 791 open edges); with a minimum
        # element size only the 8 corners' own poles are left
        import numpy as np
        code, said, (verts, tris) = run(
            "import math, random\n"
            "random.seed(3)\n"
            "pts = [(0, 0), (40, 0)] + [(40 - k, 20 + 3 * math.sin(math.pi * (40 - k) / 40) + random.uniform(-0.02, 0.02))"
            " for k in range(41)]\n"
            "with BuildPart() as part:\n"
            "    with BuildSketch():\n"
            "        add(outline(pts))\n"
            "    extrude(amount=10)\n"
            "    fillet(part.edges().filter_by(Axis.Z, reverse=True), 0.4)\n", tol=0.04, angle=4)
        self.assertEqual(code, 0, said)
        v, t = np.asarray(verts), np.asarray(tris)
        area = 0.5 * np.linalg.norm(np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]]), axis=1)
        self.assertLessEqual(int((area < 7.8e-5).sum()), 16)
        self.assertEqual(said["open_edges"], 0)

    def test_the_mesh_encloses_the_solids_own_volume(self):
        # every mesh is checked against the solid it came from: a traced, filleted block with a round hole through it
        # meshes within 0.5% of its true volume, closed (the Glock grip's side once came out in chords 2 mm inside the
        # true surface — 79.6 cm3 for a 94.8 cm3 solid — and passed every other check)
        code, said, (verts, tris) = run(
            "import math, random\n"
            "random.seed(3)\n"
            "pts = [(0, 0), (40, 0)] + [(40 - k, 20 + 3 * math.sin(math.pi * (40 - k) / 40) + random.uniform(-0.02, 0.02))"
            " for k in range(41)]\n"
            "with BuildPart() as part:\n"
            "    with BuildSketch():\n"
            "        add(outline(pts))\n"
            "    extrude(amount=10)\n"
            "    fillet(part.edges().filter_by(Axis.Z, reverse=True), 0.4)\n"
            "    with Locations((20, 9, 5)):\n"
            "        Cylinder(4, 20, mode=Mode.SUBTRACT)\n", tol=0.04, angle=5)
        self.assertEqual(code, 0, said)
        self.assertLessEqual(said["mesh_volume_error"], 0.005)
        self.assertEqual(said["open_edges"], 0)
        import numpy as np
        v, t = np.asarray(verts), np.asarray(tris)
        vol = float(np.einsum("ij,ij->i", v[t[:, 0]], np.cross(v[t[:, 1]], v[t[:, 2]])).sum() / 6.0)
        self.assertAlmostEqual(vol, said["volume_mm3"], delta=0.005 * said["volume_mm3"])

    def test_an_inlay_wraps_a_tube_instead_of_floating(self):
        # a 6 x 20 mm strip pushed through a 10 mm round tube: what is left hugs the tube from 0.3 under to 0.85 over
        code, said, _ = run("host = Cylinder(10, 40)\npart = inlay(Box(30, 6, 20), host)")
        self.assertEqual((code, said["valid"]), (0, True), said)
        self.assertAlmostEqual(said["bbox_mm"][1][0], 10.85, delta=0.05)   # (its outer face 0.85 mm off the tube)
        self.assertAlmostEqual(said["bbox_mm"][0][0], -10.85, delta=0.05)  # (both sides)
        arc = 2 * 2 * math.asin(3.0 / 10.425) * 10.425                      # (two curved strips ~6 mm wide at r 10.4)
        self.assertAlmostEqual(said["volume_mm3"], arc * 1.15 * 20, delta=0.08 * arc * 1.15 * 20)

    def test_a_rounded_ring_and_a_domed_coin(self):
        # a 10-14 mm ring 3 mm high, a half-round top (round=1): exact size, lighter than the square-edged washer
        code, said, _ = run("part = ring(10, 14, 3)")
        self.assertEqual((code, said["valid"]), (0, True), said)
        self.assertAlmostEqual(said["bbox_mm"][1][0], 14.0, delta=0.02)
        self.assertAlmostEqual(said["bbox_mm"][1][2], 3.0, delta=0.02)
        washer = math.pi * (14 ** 2 - 10 ** 2) * 3
        self.assertLess(said["volume_mm3"], washer * 0.95)
        self.assertGreater(said["volume_mm3"], washer * 0.7)
        code, said, _ = run("part = ring(0, 8, 1.5, round=1)")                 # (a domed coin: a medallion)
        self.assertEqual((code, said["valid"]), (0, True), said)
        self.assertAlmostEqual(said["bbox_mm"][1][0], 8.0, delta=0.02)
        self.assertLess(said["volume_mm3"], math.pi * 64 * 1.5)

    def test_a_turned_profile_of_many_samples_is_a_valid_solid(self):
        # 1,201 samples of a terraced face (flat steps + half-round ridges): revolved as they are, OpenCASCADE calls
        # the solid invalid (the Tide Shield, 2026-10-25); turned() drops the nearly-collinear ones -> valid, same size
        code, said, _ = run(
            "import math\n"
            "def z(r):\n"
            "    v = sum(3.5 / (1 + math.exp((r - c) / 1.2)) for c in (40.0, 70.0, 95.0))\n"
            "    for c in (46.0, 76.0, 101.0):\n"
            "        if abs(r - c) < 4.0:\n"
            "            v += 3.0 * math.sqrt(1 - ((r - c) / 4.0) ** 2)\n"
            "    return v\n"
            "rs = [120.0 * k / 1200 for k in range(1201)]\n"
            "part = turned([(r, z(r)) for r in rs], [(r, -4.0) for r in reversed(rs)])\n")
        self.assertEqual((code, said["valid"]), (0, True), said)
        self.assertAlmostEqual(said["bbox_mm"][1][0], 120.0, delta=0.05)
        self.assertAlmostEqual(said["bbox_mm"][0][2], -4.0, delta=0.05)

    def test_a_lobed_rosette_domed(self):
        # a 10-lobed rosette (r 30, dips 1.4 deep) domed 3.4 high on a 3.2 mm shoulder: a valid solid, as wide as its
        # lobes, as high as its dome, and well under the flat plate of that outline (convex, not a slab)
        code, said, _ = run("part = dome(lobed(30, 10, 1.4), 3.4, 3.2)")
        self.assertEqual((code, said["valid"]), (0, True), said)
        self.assertAlmostEqual(said["bbox_mm"][1][0], 30.0, delta=0.15)
        self.assertAlmostEqual(said["bbox_mm"][1][2], 3.4, delta=0.05)
        plate = math.pi * 30 ** 2 * 3.4
        self.assertLess(said["volume_mm3"], plate * 0.95)
        self.assertGreater(said["volume_mm3"], plate * 0.75)

    def test_a_redrawn_trace_takes_a_fillet(self):
        # a noisy traced rounded rectangle (40 x 20, 5 mm rounds) redrawn as lines + arcs, extruded, its whole top
        # edge loop filleted 1 mm: a fitted-spline wall refused fillets (the Glock frame); lines + arcs take them
        code, said, _ = run(
            "import math\nimport numpy as np\n"
            "rng = np.random.default_rng(1)\n"
            "pts = []\n"
            "for k, (cx, cy, a0) in enumerate([(15, -5, -90), (15, 5, 0), (-15, 5, 90), (-15, -5, 180)]):\n"
            "    for t in np.linspace(math.radians(a0), math.radians(a0 + 90), 20, endpoint=False):\n"
            "        pts.append((cx + 5 * math.cos(t), cy + 5 * math.sin(t)))\n"
            "    nx, ny = [(20, -5), (15, 10), (-20, 5), (-15, -10)][k]\n"
            "    ex, ey = [(20, 5), (-15, 10), (-20, -5), (15, -10)][k]\n"
            "    for f in np.linspace(0, 1, 30, endpoint=False):\n"
            "        pts.append((nx + (ex - nx) * f, ny + (ey - ny) * f))\n"
            "pts = [(x + rng.normal(0, 0.03), y + rng.normal(0, 0.03)) for x, y in pts]\n"
            "part = extrude(redraw(pts, tol=0.12), 6)\n"
            "part = fillet(part.edges().group_by(Axis.Z)[-1], 1.0)")
        self.assertEqual((code, said["valid"]), (0, True), said)
        box = (40 * 20 - (4 - math.pi) * 25) * 6
        self.assertLess(said["volume_mm3"], box)                              # (the fillet took material off)
        self.assertGreater(said["volume_mm3"], box - 40)

    def test_fillet_auto_rounds_every_edge_as_far_as_it_fits(self):
        # a plain box: every one of its 12 edges takes the asked 2 mm at once
        code, said, _ = run("part = Box(40, 20, 10)", fillet=2.0)
        self.assertEqual((code, said["valid"]), (0, True), said)
        self.assertEqual(said["fillet_auto"], {"2.0": 12})
        # a FIN 1 mm thick on its top: the fin's edges cannot take 2 mm (two rounds 1 mm apart) — they get their own
        # smaller round, the box the full 2 mm, nothing lost (Blender's clamp_overlap had cut EVERY edge to the fin's)
        code, said, _ = run("part = Box(40, 20, 10) + Pos(0, 12, 0) * Box(30, 4, 1)", fillet=2.0)
        self.assertEqual((code, said["valid"]), (0, True), said)
        got = {float(k): v for k, v in said["fillet_auto"].items()}
        self.assertIn(2.0, got, got)
        self.assertLess(min(got), 2.0, got)
        self.assertGreater(got[2.0], 8, got)

    def test_a_bead_is_a_swept_half_round(self):
        # a 1.5 x 0.7 half-round bead round a 10 mm circle: 2 pi 10 x (pi / 4 x 1.5 x 0.7) = 51.8 mm3
        code, said, _ = run("import math\npts = [(10 * math.cos(t), 10 * math.sin(t)) for t in [i * 2 * math.pi / 24 "
                            "for i in range(25)]]\npart = bead(pts, 1.5, 0.7)")
        self.assertEqual((code, said["valid"]), (0, True), said)
        self.assertAlmostEqual(said["volume_mm3"], 2 * math.pi * 10 * math.pi / 4 * 1.5 * 0.7, delta=1.0)
        self.assertAlmostEqual(said["bbox_mm"][1][2], 0.7, delta=0.02)
        code, said, _ = run("part = bead([(0, 0), (10, 3), (20, 0), (30, -3)], 2.0, 1.0)")   # (domed open ends)
        self.assertEqual((code, said["valid"], said["solids"]), (0, True, 1), said)
        self.assertLess(said["bbox_mm"][0][0], -0.9)                          # (the dome rounds past the path's end)

    def test_a_setting_holds_the_stone_under_its_lip(self):
        # a 10 mm stone's bezel: material INSIDE the stone's radius above the girdle (the lip that holds it) and
        # below it (the seat), none in between (the stone's room)
        for prongs in (0, 4):
            code, said, _ = run(
                f"part = setting(10.0, prongs={prongs})\n"
                "lip = part & Pos(0, 0, 1.4) * Cylinder(4.9, 0.3)\n"
                "seat = part & Pos(0, 0, 0.5) * Cylinder(4.9, 0.3)\n"
                "room = part & Pos(0, 0, 1.15) * Cylinder(4.9, 0.2)\n"
                "assert lip.volume > 0.1 and seat.volume > 0.1, (lip.volume, seat.volume)\n"
                "assert room.volume < 1e-6, room.volume")
            self.assertEqual((code, said["valid"]), (0, True), said)
            self.assertAlmostEqual(said["bbox_mm"][1][0], 6.0, delta=0.02)

    def test_a_grip_section_can_be_boxy_at_the_front(self):
        # a loft through sections round at the back (2) and boxy at the front (6): at 80% of the way to the front it is
        # wider than at 80% of the way to the back, and its middle of mass sits forward of its centre
        code, said, _ = run(
            "f = section(20, 30, 2.0, squareness_front=6.0)\n"
            "def width_at(y):\n"
            "    cut = f & Pos(0, y, 0) * Rectangle(100, 0.01)\n"
            "    bb = cut.bounding_box()\n"
            "    return bb.max.X - bb.min.X\n"
            "assert width_at(12.0) > width_at(-12.0) + 4.0, (width_at(12.0), width_at(-12.0))\n"
            "assert f.center().Y > 0.3, f.center()\n"
            "part = loft_sections([{'at': 0, 'width': 20, 'depth': 30, 'squareness': 2, 'squareness_front': 6},\n"
            "                      {'at': 10, 'width': 20, 'depth': 30, 'squareness': 2, 'squareness_front': 6}])\n")
        self.assertEqual(code, 0, said)
        self.assertEqual(said["solids"], 1)

    def test_a_failing_line_is_named(self):
        code, said, _ = run("part = Box(10, 10, 10)\nraise ValueError('boom')\n")
        self.assertEqual(code, 1)
        self.assertIn("line 2", said["summary"])
        self.assertIn("boom", said["summary"])

    def test_code_that_leaves_no_part_is_said_plainly(self):
        code, said, arrays = run("x = Box(10, 10, 10)\n")
        self.assertEqual(code, 1)
        self.assertIn("no `part`", said["summary"])
        self.assertIsNone(arrays)

    def test_a_surface_is_not_a_solid(self):  # (the cad_solid gate reads these facts)
        code, said, _ = run("with BuildSketch() as sk:\n    Rectangle(10, 10)\npart = sk.sketch\n")
        self.assertEqual(code, 0, said)
        self.assertEqual(said["solids"], 0)
        self.assertEqual(said["volume_mm3"], 0.0)


if __name__ == "__main__":
    unittest.main()
