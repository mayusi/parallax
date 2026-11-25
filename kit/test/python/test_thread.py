"""rbx_parts.thread_mesh: a screw thread as light game geometry (rework 6ebz, the car rim's lug holes) — closed (every
edge on two faces), wound outward (positive volume, every edge walked once each way), on its radii, its UV strips
never turned over, ~6 triangles a facet."""

import math
import os
import sys
import unittest
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_parts as P  # noqa: E402  (no bpy at import)


def _volume(v, f):
    vol = 0.0
    for x in f:
        p0 = v[x[0]]
        for k in range(1, len(x) - 1):
            p1, p2 = v[x[k]], v[x[k + 1]]
            vol += (p0[0] * (p1[1] * p2[2] - p1[2] * p2[1]) - p0[1] * (p1[0] * p2[2] - p1[2] * p2[0])
                    + p0[2] * (p1[0] * p2[1] - p1[1] * p2[0])) / 6.0
    return vol


class TestThreadMesh(unittest.TestCase):
    def check(self, internal):
        v, f, uv = P.thread_mesh(14.2, 1.5, 10.0, internal=internal, segments=12)
        tris = sum(len(x) - 2 for x in f)
        self.assertEqual(tris, 482)   # (80 facets x 3 quads x 2 + 2 caps)
        walked = Counter()
        for x in f:
            for k in range(len(x)):
                walked[(x[k], x[(k + 1) % len(x)])] += 1
        for (a, b), n in walked.items():
            self.assertEqual(n, 1)
            self.assertEqual(walked.get((b, a), 0), 1, "an edge without its twin: not closed, or wound both ways")
        self.assertGreater(_volume(v, f), 0.0)   # (outward)
        self.assertTrue(all(P._area2(q) > 0 for q in uv), "a UV island turned over")
        return v

    def test_internal_ridge_stands_in_from_the_hole_wall(self):
        v = self.check(True)
        r = [math.hypot(p[0], p[1]) for p in v]
        self.assertAlmostEqual(max(r), 7.1, places=6)                      # (the base on the major radius)
        self.assertAlmostEqual(min(r), 7.1 - 0.625 * 0.8660254 * 1.5, places=6)   # (the crest 5/8 H in)

    def test_external_ridge_stands_out_from_the_rod(self):
        v = self.check(False)
        r = [math.hypot(p[0], p[1]) for p in v]
        self.assertAlmostEqual(max(r), 7.1, places=6)                      # (the crest on the major radius)

    def test_faded_in_at_the_start(self):
        v, f, _uv = P.thread_mesh(14.2, 1.5, 10.0, segments=12, fade_turns=0.5)
        depth = [7.1 - math.hypot(p[0], p[1]) for p in v]
        self.assertLess(max(depth[:3]), 0.1 * max(depth))                  # (the first ring: barely a ridge)


if __name__ == "__main__":
    unittest.main()
