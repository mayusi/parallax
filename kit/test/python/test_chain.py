"""rbx_parts.chain_layout — a hanging chain whose every piece is threaded through the next (the owner, 2026-10-21:
"the chains under the gun arent even connected to the gun"): the loop seated in the host, each link's lower wire
inside the next link's hole and the next link's upper wire inside its hole, the ring through the last, the bail round
the ring's lower wire."""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
for _m in ("bpy", "mathutils", "bmesh"):   # (rbx_parts' pure helpers need no Blender)
    sys.modules.setdefault(_m, types.ModuleType(_m))
import rbx_parts as P  # noqa: E402


class ChainLayout(unittest.TestCase):
    def check(self, **kw):
        L = kw.get("link_mm", (11.0, 16.0))[1]
        band = kw.get("band_mm", 2.9)
        r_l, w_l = kw.get("loop_mm", (3.6, 1.3))
        r_r, w_r = kw.get("ring_mm", (5.0, 1.1))
        r_b, w_b = kw.get("bail_mm", (2.6, 0.9))
        lay = P.chain_layout(100.0, **kw)
        half_hole, wire = lay["hole"] / 2, L / 2 - band / 2   # (a link's hole half-height, its wire's offset)
        self.assertGreater(lay["loop"] + r_l + w_l, 100.0)                       # the loop reaches into the host
        self.assertLess(abs((lay["loop"] - r_l) - lay["links"][0]), half_hole)   # its lower wire in link 0's hole
        for up, dn in zip(lay["links"], lay["links"][1:]):
            self.assertLess(abs((up - wire) - dn), half_hole)                   # a lower wire in the next hole
            self.assertLess(abs((dn + wire) - up), half_hole)                   # the next upper wire in this hole
        self.assertLess(abs((lay["ring"] + r_r) - lay["links"][-1]), half_hole)  # the ring through the last link
        self.assertLess(abs((lay["links"][-1] - wire) - lay["ring"]), r_r - w_r)  # ...and that link's wire in the ring
        self.assertLess(abs((lay["ring"] - r_r) - lay["bail"]), r_b - w_b)       # the ring's wire through the bail
        self.assertLess(lay["pendant_top"], lay["bail"])
        return lay

    def test_default_chain_threads_through(self):
        lay = self.check()
        self.assertEqual(len(lay["links"]), 3)

    def test_other_sizes_thread_too(self):
        self.check(links=5, link_mm=(8.0, 12.0), band_mm=2.0, ring_mm=(4.0, 0.9))
        self.check(links=1, link_mm=(14.0, 22.0), band_mm=3.5, loop_mm=(5.0, 1.6))


if __name__ == "__main__":
    unittest.main()
