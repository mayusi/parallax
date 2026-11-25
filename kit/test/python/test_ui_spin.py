"""kit ui spin: a piece's opaque silhouette becomes closed polygons (outer outline + holes) in image pixels"""
import importlib.util
import os
import unittest

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_spin", os.path.join(HERE, "..", "..", "ui", "spin.py"))
spin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spin)


class TestSpin(unittest.TestCase):
    def test_a_ring_gives_an_outline_and_a_hole(self):
        im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse([10, 10, 190, 190], fill=(200, 160, 60, 255))
        d.ellipse([60, 60, 140, 140], fill=(0, 0, 0, 0))
        polys = spin.silhouette_polys(im)
        self.assertEqual(len(polys), 2)
        xs = [x for p in polys for x, _ in p]
        self.assertLess(min(xs), 20)
        self.assertGreater(max(xs), 180)

    def test_a_relief_raises_the_bright_part_a_step_above_the_base(self):
        im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([10, 10, 190, 190], fill=(60, 50, 40, 255))   # a dark plate
        d.ellipse([60, 60, 140, 140], fill=(250, 230, 160, 255))  # a bright boss on it
        base = spin.silhouette_polys(im)
        layers = spin.relief_layers(im, base, 2, 0.12, bevel=0.03)
        self.assertEqual(len(layers), 2)
        boss = layers[1]
        xs = [x for p in boss["polys"] for x, _ in p]
        self.assertGreater(min(xs), 50)  # only the boss, not the plate
        self.assertLess(max(xs), 150)
        # its front stands proud of the base's front INCLUDING the base's bevel (a bevel bigger than a step once buried it)
        self.assertGreater(boss["z"] + boss["depth"] / 2, 0.12 / 2 + 0.03)

    def test_slivers_are_dropped_and_shapes_kept(self):
        hair = [(0, 100), (120, 101), (120, 102), (0, 101.5)]
        disc = [(100 + 40 * __import__("math").cos(t / 10), 100 + 40 * __import__("math").sin(t / 10)) for t in range(63)]
        self.assertTrue(spin.sliver(hair, (200, 200)))
        self.assertFalse(spin.sliver(disc, (200, 200)))

    def test_a_thin_counter_stays_a_hole_in_the_relief(self):
        im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([10, 10, 190, 190], fill=(60, 50, 40, 255))      # the dark plate
        d.rectangle([60, 20, 140, 180], fill=(250, 230, 160, 255))   # a bright "O"...
        d.rectangle([99, 30, 100, 170], fill=(60, 50, 40, 255))      # ...with a 2 px counter (a sliver by shape: once dropped)
        layers = spin.relief_layers(im, spin.silhouette_polys(im), 2, 0.12)
        areas = [spin.signed_area(p) for p in layers[1]["polys"]]
        self.assertTrue(any(a > 0 for a in areas) and any(a < 0 for a in areas), areas)  # outline AND its hole

    def test_a_depth_relief_peaks_inside_and_meets_the_base_at_the_edge(self):
        import numpy as np
        yy, xx = np.mgrid[0:200, 0:200]
        r = np.hypot(xx - 100, yy - 100)
        mask = r < 80                                  # a disc
        depth = np.clip(1 - r / 80, 0, 1)              # a dome: nearest in the middle
        z = spin.grid_from_depth(depth, mask, cells=50)
        self.assertEqual(z.shape, (50, 50))
        self.assertTrue(np.isnan(z[0, 0]))             # outside the piece: no relief
        self.assertGreater(np.nanmax(z[20:30, 20:30]), 0.6)   # the middle stands high
        ring = [z[25, 6], z[6, 25], z[25, 44], z[44, 25]]     # just inside the edge
        self.assertTrue(all(v < 0.15 for v in ring), ring)    # eased down to the base

    def test_a_relief_touching_the_border_still_eases_down(self):
        import numpy as np
        z = spin.grid_from_depth(np.full((100, 100), 0.8, np.float32) + np.random.default_rng(1).random((100, 100)).astype(np.float32) * 0.2,
                                 np.ones((100, 100), bool), cells=50)
        self.assertLess(float(np.nanmax(z[0, :])), 0.2)   # (no cliff at the image edge)

    def test_motions_are_data_frame_by_frame(self):
        import math
        spin_ = spin.rotations("spin", 4)
        self.assertEqual([round(math.degrees(r[1])) for r in spin_], [0, 90, 180, 270])
        flip = spin.rotations("flip", 10)
        self.assertAlmostEqual(flip[0][1], math.pi)          # a flip starts on the BACK
        land = spin.rotations("land", 30)
        self.assertGreater(land[0][1], 5 * math.pi)          # a land starts spinning fast...
        self.assertLess(land[-1][1], 0.05)                    # ...and ends face-on
        own = spin.rotations(n=4, curve={"y": [[0, 0], [0.5, 90], [1, 90]], "x": [[0, 10], [1, 10]]})
        self.assertEqual([round(math.degrees(r[1])) for r in own], [0, 45, 90, 90])
        self.assertTrue(all(round(math.degrees(r[0])) == 10 for r in own))

    def test_parallax_cards_split_the_piece_by_depth_with_nothing_lost(self):
        import numpy as np
        im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle([10, 10, 89, 89], fill=(200, 100, 50, 255))
        d = np.tile(np.linspace(0, 1, 100, dtype=np.float32), (100, 1))  # nearer to the right
        layers = spin.depth_layers(im, d, 3)
        counts = [int((np.array(L)[:, :, 3] > 0).sum()) for L in layers]
        self.assertEqual(sum(counts), 80 * 80)                 # every opaque pixel lands on exactly one card
        self.assertTrue(all(c > 0 for c in counts))
        a0, a2 = np.array(layers[0])[:, :, 3], np.array(layers[2])[:, :, 3]
        self.assertGreater(np.nonzero(a2)[1].mean(), np.nonzero(a0)[1].mean())   # the near card holds the right side

    def test_an_empty_piece_has_no_silhouette(self):
        self.assertEqual(spin.silhouette_polys(Image.new("RGBA", (64, 64), (0, 0, 0, 0))), [])


if __name__ == "__main__":
    unittest.main()
