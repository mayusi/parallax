"""kit/gen/uvraster.py: the nvdiffrast subset TRELLIS.2's GLB export uses (rasterize in UV space + interpolate),
with nvdiffrast's conventions — pixel centres, row 0 at clip y = -1, barycentrics of the first two corners, the
triangle index + 1 in the last channel — so the export runs without nvdiffrast's non-commercial licence."""

import os
import sys
import unittest

try:
    import torch
except ImportError:  # (the kit's tests run without torch on a machine with no vision stack)
    torch = None

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gen"))


def clip(uv):
    """UVs in [0, 1] -> the clip-space positions the TRELLIS.2 export hands the rasterizer"""
    return torch.cat([uv * 2 - 1, torch.zeros_like(uv[:, :1]), torch.ones_like(uv[:, :1])], dim=-1).unsqueeze(0)


@unittest.skipIf(torch is None, "torch is not installed")
class TestUVRaster(unittest.TestCase):
    def setUp(self):
        import uvraster  # noqa: PLC0415

        self.R = uvraster
        self.ctx = uvraster.RasterizeCudaContext()
        self.uv = torch.tensor([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
        self.quad = torch.tensor([[0, 1, 2], [0, 2, 3]], dtype=torch.int32)

    def test_a_quad_covers_every_texel_once(self):
        rast, _ = self.R.rasterize(self.ctx, clip(self.uv), self.quad, resolution=[8, 8])
        self.assertEqual(tuple(rast.shape), (1, 8, 8, 4))
        ids = rast[0, ..., 3]
        self.assertTrue(bool((ids >= 1).all()))
        self.assertEqual(set(ids.unique().tolist()), {1.0, 2.0})

    def test_interpolation_puts_each_texel_at_its_centre_with_row_zero_at_the_bottom(self):
        H, W = 6, 10
        rast, _ = self.R.rasterize(self.ctx, clip(self.uv), self.quad, resolution=[H, W])
        out, _ = self.R.interpolate(self.uv.unsqueeze(0), rast, self.quad)
        rows = (torch.arange(H).float() + 0.5) / H
        cols = (torch.arange(W).float() + 0.5) / W
        self.assertTrue(torch.allclose(out[0, :, :, 0], cols.expand(H, W), atol=1e-5))  # u along the columns
        self.assertTrue(torch.allclose(out[0, :, :, 1], rows.unsqueeze(1).expand(H, W), atol=1e-5))  # v up the rows

    def test_a_half_triangle_covers_about_half_and_nothing_outside(self):
        tri = torch.tensor([[0, 1, 2]], dtype=torch.int32)  # the lower-right half of the square (u >= v)
        rast, _ = self.R.rasterize(self.ctx, clip(self.uv), tri, resolution=[64, 64])
        mask = rast[0, ..., 3] > 0
        self.assertAlmostEqual(mask.float().mean().item(), 0.5, delta=0.02)
        out, _ = self.R.interpolate(self.uv.unsqueeze(0), rast, tri)
        u, v = out[0, ..., 0][mask], out[0, ..., 1][mask]
        self.assertTrue(bool((u >= v - 1e-5).all()))

    def test_chunking_and_the_exports_face_offsets_agree(self):
        full, _ = self.R.rasterize(self.ctx, clip(self.uv), self.quad, resolution=[16, 16])
        tiny, _ = self.R.rasterize(self.ctx, clip(self.uv), self.quad, resolution=[16, 16], chunk=7)
        self.assertTrue(torch.equal(full, tiny))
        # the export rasterizes faces in slices, shifts each slice's ids by its start, and merges by coverage
        rast = torch.zeros_like(full)
        for i in range(2):
            part, _ = self.R.rasterize(self.ctx, clip(self.uv), self.quad[i:i + 1], resolution=[16, 16])
            m = part[..., 3:4] > 0
            part[..., 3:4] += i
            rast = torch.where(m, part, rast)
        self.assertTrue(torch.equal(rast[..., 3], full[..., 3]))

    def test_degenerate_and_offscreen_triangles_cover_nothing(self):
        uv = torch.tensor([[0.2, 0.2], [0.4, 0.4], [0.6, 0.6], [1.5, 1.5], [1.7, 1.5], [1.6, 1.8]])
        tri = torch.tensor([[0, 1, 2], [3, 4, 5]], dtype=torch.int32)
        rast, _ = self.R.rasterize(self.ctx, clip(uv), tri, resolution=[32, 32])
        self.assertEqual(int((rast[0, ..., 3] > 0).sum()), 0)


if __name__ == "__main__":
    unittest.main()
