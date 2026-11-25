"""test_world_ribbons.py - RIVERS AS RIBBON MESHES that drain into the land's sinks (kit/world/ribbons.py;
LIMITATIONS_FIXES_V4 5.1 / 13.5: "ribbon river meshes -> --sink"). The rivers were painted Water voxels: flat, and a
river that ran into a closed hollow pooled there unsaid.
Held here on lands made by hand: a bowl whose middle is a recorded --sink drains every river into it; the same bowl
with no sink is a closed hollow (a lake would stand: "pit", the run fails); a land falling to one side drains to the
edge; a ribbon's surface lies under the land along its line and never rises downstream; widths grow downstream; the
strip has 2 vertices a point, 2 triangles a step, u across 0..1 and v rising along it; long rivers are cut into
pieces that share their seam's points; shallow hollows (a raw heightmap's specks) are filled and do not stop water.
Not claimed: the look in Roblox (an uploaded MeshPart with a scrolled texture), or that a land drains well - SampleRegion
as it stands (no sink in its recipe) runs every river into its walled valley (39.9 studs deep at most): measured."""
import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "..", "..", "world", "ribbons.py")
sys.path.insert(0, os.path.join(HERE, "..", "..", "world"))
_spec = importlib.util.spec_from_file_location("kit_world_ribbons", PATH)
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

N, STEP = 81, 4.0
HALF = (N - 1) * STEP / 2


def land(fn, sinks=None):
    hs = []
    for i in range(N):
        for j in range(N):
            hs.append(round(float(fn(i * STEP - HALF, j * STEP - HALF)), 2))
    hm = {"nx": N, "nz": N, "step": STEP, "heights": hs, "options": {}}
    if sinks:
        hm["options"]["sink"] = sinks
    return hm


def bowl(x, z):
    # a bowl falling to its middle, five valleys cut into its sides (the rivers' lines)
    r = math.hypot(x, z)
    a = math.atan2(z, x)
    valley = 6 * (1 - abs(math.cos(2.5 * a))) * min(r / 60, 1)
    return 0.35 * r + valley + 30


def tilted(x, z):
    # falling toward +x, a valley down its middle
    return 80 - 0.3 * x + 0.08 * z * z / 10


class Ribbons(unittest.TestCase):
    def test_a_bowl_with_a_sink_drains_into_it(self):
        ribbons, stats = R.build(land(bowl, ["0,0,24"]), "Bowl")
        self.assertEqual(stats["sinks"], 1)
        self.assertGreaterEqual(len({rb["river"] for rb in ribbons}), 3)
        self.assertTrue(all(rb["drain"] == "sink" for rb in ribbons), {rb["drain"] for rb in ribbons})
        # each river reaches the sink: its last point within the sink's radius and a cell
        for rb in ribbons:
            x, z = rb["points"][-1]
            if rb["joins"] is None:
                self.assertLessEqual(math.hypot(x, z), 24 + STEP * 1.5)

    def test_the_same_bowl_without_a_sink_is_a_pit_and_the_run_fails(self):
        ribbons, _ = R.build(land(bowl), "Bowl")
        self.assertTrue(ribbons)
        self.assertTrue(all(rb["drain"] == "pit" for rb in ribbons))
        d = tempfile.mkdtemp()
        path = os.path.join(d, "Bowl.hm.json")
        json.dump(land(bowl), open(path, "w"))
        r = subprocess.run([sys.executable, PATH, path, "--out", os.path.join(d, "out")], capture_output=True, text=True)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(r.returncode, 1)
        self.assertEqual(out["status"], "fail")
        self.assertIn("--sink", out["next_action"])
        # and with the sink: it passes, one .obj a piece
        json.dump(land(bowl, ["0,0,24"]), open(path, "w"))
        r = subprocess.run([sys.executable, PATH, path, "--out", os.path.join(d, "out2")], capture_output=True, text=True)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["status"], "pass", out)
        objs = [f for f in os.listdir(os.path.join(d, "out2")) if f.endswith(".obj")]
        self.assertEqual(len(objs), out["pieces"])

    def test_a_land_falling_to_one_side_drains_to_the_edge(self):
        ribbons, _ = R.build(land(tilted), "Tilt")
        self.assertTrue(ribbons)
        self.assertTrue(all(rb["drain"] == "edge" for rb in ribbons))

    def test_shallow_hollows_do_not_stop_water(self):
        # the tilted land with specks pressed into it (a raw heightmap's): still to the edge
        def specked(x, z):
            # (2-stud grooves across the whole land every sixth cell: every river must pass them)
            dent = 2.0 if round(x / STEP) % 6 == 3 else 0
            return tilted(x, z) - dent

        ribbons, _ = R.build(land(specked), "Specks")
        self.assertGreaterEqual(len({rb["river"] for rb in ribbons}), 1)
        self.assertTrue(max(len(rb["points"]) for rb in ribbons) > 40)  # (the whole way down, not 4 cells to a groove)
        self.assertTrue(all(rb["drain"] == "edge" for rb in ribbons))

    def test_the_water_lies_in_its_bed_and_never_climbs(self):
        for rb in R.build(land(bowl, ["0,0,24"]), "Bowl")[0] + R.build(land(tilted), "Tilt")[0]:
            s, g = np.array(rb["surface"]), np.array(rb["ground"])
            self.assertTrue(np.all(s <= g - R.DEPTH + 1e-6))
            self.assertTrue(np.all(np.diff(s) <= 1e-9))

    def test_the_strip_and_its_scroll(self):
        rb = max(R.build(land(tilted), "Tilt")[0], key=lambda r: len(r["points"]))
        n = len(rb["points"])
        self.assertEqual(len(rb["verts"]), 2 * n)
        self.assertEqual(len(rb["faces"]), 2 * (n - 1))
        self.assertEqual(rb["tris"], 2 * (n - 1))
        us = sorted({u for u, _ in rb["uvs"]})
        self.assertEqual(us, [0.0, 1.0])
        vs = [v for _, v in rb["uvs"][::2]]
        self.assertTrue(all(b > a for a, b in zip(vs, vs[1:])))
        # its width: the distance between a point's two vertices
        for k in range(n):
            a, b = np.array(rb["verts"][2 * k]), np.array(rb["verts"][2 * k + 1])
            self.assertAlmostEqual(float(np.linalg.norm((a - b)[[0, 2]])), rb["widths"][k], delta=0.006)  # (the record rounds to 0.01)
        # every triangle faces up (seen from above, +y)
        V = np.array(rb["verts"])
        for f in rb["faces"]:
            p, q, r = V[f[0]], V[f[1]], V[f[2]]
            self.assertGreater(float(np.cross(q - p, r - p)[1]), 0)
        # and the widths grow downstream
        self.assertGreaterEqual(rb["widths"][-1], rb["widths"][0])

    def test_long_rivers_come_in_pieces_sharing_their_seams(self):
        old = R.PIECE
        R.PIECE = 60.0
        try:
            ribbons, _ = R.build(land(tilted), "Tilt")
        finally:
            R.PIECE = old
        by = {}
        for rb in ribbons:
            by.setdefault(rb["river"], []).append(rb)
        long = [v for v in by.values() if len(v) > 1]
        self.assertTrue(long)
        for pieces in long:
            pieces.sort(key=lambda r: r["piece"])
            for a, b in zip(pieces, pieces[1:]):
                self.assertEqual(a["points"][-1], b["points"][0])
                self.assertLessEqual(a["length"], 60.0 + 1e-6)


if __name__ == "__main__":
    unittest.main()
