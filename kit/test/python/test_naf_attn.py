"""kit/gen/naf_attn.py: NAF's dilated neighbourhood attention over nearest-upsampled keys/values, computed on the
low-resolution keys/values directly — must equal the definition: upsample k and v to full resolution exactly as NAF does
(F.interpolate nearest-exact), then let each query attend to its k x k dilated neighbourhood (NATTEN's rule: the
positions of its dilation group, a window of k centred on it and shifted to stay inside the group)."""

import os
import sys
import unittest

try:
    import torch
    import torch.nn.functional as F
except ImportError:
    torch = None

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gen"))


def window(i, d, length, k):
    """NATTEN's dilated neighbourhood of position i on an axis of `length`: k positions of i's dilation group"""
    a, p = i % d, i // d
    group = len(range(a, length, d))
    start = min(max(p - k // 2, 0), group - k)
    return [a + d * (start + t) for t in range(k)]


def reference(q, k_low, v_low, kernel):
    """q [B, n, c, H, W]; k_low/v_low [B, n, *, h, w] -> brute force [B, n, cv, H, W]"""
    B, n, c, H, W = q.shape
    h, w = k_low.shape[-2:]
    dh, dw = H // h, W // w
    up = lambda x: F.interpolate(x.reshape(B, -1, h, w), size=(H, W), mode="nearest-exact").reshape(  # noqa: E731
        B, n, -1, H, W)
    k, v = up(k_low), up(v_low)
    out = torch.zeros(B, n, v.shape[2], H, W, dtype=q.dtype)
    for i in range(H):
        rows = window(i, dh, H, kernel[0])
        for j in range(W):
            cols = window(j, dw, W, kernel[1])
            kk = k[:, :, :, rows][..., cols].reshape(B, n, c, -1)  # [B, n, c, kh*kw]
            vv = v[:, :, :, rows][..., cols].reshape(B, n, v.shape[2], -1)
            att = (torch.einsum("bnc,bnck->bnk", q[..., i, j], kk) * c ** -0.5).softmax(-1)
            out[..., i, j] = torch.einsum("bnk,bnck->bnc", att, vv)
    return out


@unittest.skipIf(torch is None, "torch is not installed")
class TestNafAttention(unittest.TestCase):
    def setUp(self):
        import naf_attn  # noqa: PLC0415

        self.A = naf_attn
        self.g = torch.Generator().manual_seed(0)

    def check(self, H, W, h, w, kernel, budget=1 << 29):
        B, n, c, cv = 1, 2, 4, 6
        q = torch.randn(B, n, c, H, W, generator=self.g, dtype=torch.float64)
        k = torch.randn(B, n, c, h, w, generator=self.g, dtype=torch.float64)
        v = torch.randn(B, n, cv, h, w, generator=self.g, dtype=torch.float64)
        got = self.A.lowres_neighbourhood_attention(q, k, v, kernel=kernel, budget=budget)
        want = reference(q, k, v, kernel)
        self.assertEqual(tuple(got.shape), (B, n, cv, H, W))
        self.assertLess(float((got - want).abs().max()), 1e-10)

    def test_square_dilated_windows_shift_at_every_border(self):
        self.check(H=20, W=20, h=5, w=5, kernel=(3, 3))

    def test_different_factors_per_axis(self):
        self.check(H=12, W=24, h=6, w=4, kernel=(5, 3))

    def test_a_window_as_big_as_the_grid(self):
        self.check(H=9, W=9, h=3, w=3, kernel=(3, 3))

    def test_row_blocks_give_the_same_answer(self):
        self.check(H=20, W=20, h=5, w=5, kernel=(3, 3), budget=1)

    def test_shapes_that_do_not_divide_are_refused(self):
        q = torch.zeros(1, 1, 2, 10, 10)
        with self.assertRaises(ValueError):
            self.A.lowres_neighbourhood_attention(q, torch.zeros(1, 1, 2, 3, 3), torch.zeros(1, 1, 2, 3, 3), (3, 3))


if __name__ == "__main__":
    unittest.main()
