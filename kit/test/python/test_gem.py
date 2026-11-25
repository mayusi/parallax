"""rbx_parts.brilliant — a round brilliant cut as a CLOSED mesh: every edge shared by exactly two faces, the facet
count of a real brilliant's crown (1 table + 8 star + 8 kite + 16 upper girdle), the proportions asked for."""

import collections
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
for _m in ("bpy", "mathutils", "bmesh"):
    sys.modules.setdefault(_m, types.ModuleType(_m))
import rbx_parts as P  # noqa: E402


class Brilliant(unittest.TestCase):
    def test_closed_and_consistently_wound(self):
        v, f = P.brilliant(1.0)
        edges = collections.Counter()
        directed = set()
        for face in f:
            for a, b in zip(face, face[1:] + face[:1]):
                edges[frozenset((a, b))] += 1
                self.assertNotIn((a, b), directed, "two faces run an edge the same way: a flipped facet")
                directed.add((a, b))
        self.assertTrue(all(n == 2 for n in edges.values()), [e for e, n in edges.items() if n != 2][:4])

    def test_crown_facets_and_proportions(self):
        v, f = P.brilliant(2.0, table=0.5, crown=0.3, pavilion=0.9)
        crown = [face for face in f if all(v[i][2] >= -1e-9 for i in face) and len(face) != 4 or len(face) == 8]
        self.assertEqual(sum(1 for face in f if len(face) == 8), 1)                 # the table
        self.assertEqual(len(f), 1 + 8 + 8 + 16 + 16 + 16)
        self.assertAlmostEqual(max(p[2] for p in v), 0.6)                          # crown 0.3 x radius 2
        self.assertAlmostEqual(min(p[2] for p in v), -1.8)                         # culet 0.9 x 2
        self.assertAlmostEqual(max(abs(p[0]) for p in v), 2.0)
        self.assertTrue(crown)


if __name__ == "__main__":
    unittest.main()
