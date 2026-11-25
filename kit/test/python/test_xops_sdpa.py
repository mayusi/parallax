"""kit/gen/xops_sdpa.py: TRELLIS.2's two xformers calls on PyTorch attention — packed sequences of different lengths
attend only within themselves, exactly like softmax(q k^T / sqrt(C)) v per sequence."""

import os
import sys
import unittest

try:
    import torch
except ImportError:
    torch = None

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gen"))


def reference(q, k, v, qs, ks):
    """plain attention, one sequence at a time ([M, H, C] packed)"""
    outs, qa, ka = [], 0, 0
    for lq, lk in zip(qs, ks):
        qi, ki, vi = q[qa:qa + lq], k[ka:ka + lk], v[ka:ka + lk]  # [L, H, C]
        w = torch.einsum("qhc,khc->hqk", qi, ki) / qi.shape[-1] ** 0.5
        outs.append(torch.einsum("hqk,khc->qhc", w.softmax(-1), vi))
        qa, ka = qa + lq, ka + lk
    return torch.cat(outs, 0)


@unittest.skipIf(torch is None, "torch is not installed")
class TestXopsSdpa(unittest.TestCase):
    def setUp(self):
        import xops_sdpa  # noqa: PLC0415

        self.X = xops_sdpa
        self.g = torch.Generator().manual_seed(0)

    def rand(self, m, h=2, c=8):
        return torch.randn(m, h, c, generator=self.g)

    def check(self, qs, ks):
        q, k, v = self.rand(sum(qs)), self.rand(sum(ks)), self.rand(sum(ks))
        mask = self.X.fmha.BlockDiagonalMask.from_seqlens(qs, ks if ks != qs else None)
        out = self.X.memory_efficient_attention(q[None], k[None], v[None], attn_bias=mask)[0]
        self.assertEqual(tuple(out.shape), tuple(q.shape))
        self.assertTrue(torch.allclose(out, reference(q, k, v, qs, ks), atol=1e-5))

    def test_mixed_lengths_attend_only_within_each_sequence(self):
        self.check([3, 5, 2], [3, 5, 2])

    def test_cross_attention_with_other_key_lengths(self):
        self.check([4, 1, 6], [7, 2, 3])

    def test_equal_lengths_take_the_batched_path(self):
        self.check([4, 4, 4], [4, 4, 4])

    def test_the_per_sequence_fallback_agrees(self):
        self.X._nested_ok[0] = False
        try:
            self.check([3, 5, 2], [6, 1, 4])
        finally:
            self.X._nested_ok[0] = True

    def test_no_mask_is_plain_batched_attention(self):
        q, k, v = (torch.randn(2, 5, 2, 8, generator=self.g) for _ in range(3))
        out = self.X.memory_efficient_attention(q, k, v)
        want = torch.stack([reference(q[b], k[b], v[b], [5], [5]) for b in range(2)])
        self.assertTrue(torch.allclose(out, want, atol=1e-5))

    def test_lengths_that_do_not_add_up_are_refused(self):
        q = self.rand(5)
        with self.assertRaises(ValueError):
            self.X.memory_efficient_attention(q[None], q[None], q[None],
                                              attn_bias=self.X.fmha.BlockDiagonalMask.from_seqlens([2, 2]))


if __name__ == "__main__":
    unittest.main()
