"""xops_sdpa.py — the two xformers.ops calls TRELLIS.2 makes, on PyTorch's own attention (kit-owned code).

TRELLIS.2's sparse transformers pack many sequences of different lengths into one tensor and attend within each
(`xformers.ops.fmha.BlockDiagonalMask.from_seqlens` + `xformers.ops.memory_efficient_attention`). xformers'
Windows wheel has no attention kernel for compute capability 12.0 (RTX 50-series: "too new" / "not built",
measured 2026-10-06 with xformers 0.0.35), while PyTorch's scaled_dot_product_attention runs there. This module is
installed as `xformers.ops` by the runner (kit/gen/trellis2_run.py) and gives the same results:

    mask = fmha.BlockDiagonalMask.from_seqlens(q_seqlen, kv_seqlen)   # kv_seqlen defaults to q_seqlen
    out = memory_efficient_attention(q, k, v, attn_bias=mask)         # q [1, sum(q_seqlen), H, C] -> same layout

Equal-length sequences go through one batched call; mixed lengths through PyTorch's nested (jagged) tensors, or
one call per sequence if those are unavailable. No mask: plain batched attention ([B, L, H, C]).
"""

import types
from itertools import accumulate

import torch
import torch.nn.functional as F


class BlockDiagonalMask:
    """which rows attend to which: sequence i's queries see only sequence i's keys"""

    def __init__(self, q_seqlen, kv_seqlen=None):
        self.q_seqlen = [int(n) for n in q_seqlen]
        self.kv_seqlen = [int(n) for n in (kv_seqlen if kv_seqlen is not None else q_seqlen)]
        if len(self.q_seqlen) != len(self.kv_seqlen):
            raise ValueError("q and kv must have the same number of sequences")

    @classmethod
    def from_seqlens(cls, q_seqlen, kv_seqlen=None):
        return cls(q_seqlen, kv_seqlen)


fmha = types.SimpleNamespace(BlockDiagonalMask=BlockDiagonalMask)
_nested_ok = [True]


def _bhlc(q, k, v, scale):
    """[B, L, H, C] in and out"""
    out = F.scaled_dot_product_attention(q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2), scale=scale)
    return out.transpose(1, 2)


def _varlen(q, k, v, qs, ks, scale):
    """packed [M, H, C] sequences -> packed [Mq, H, Co]"""
    if len(set(qs)) == 1 and len(set(ks)) == 1:  # equal lengths: one batched call
        n = len(qs)
        out = _bhlc(q.reshape(n, qs[0], *q.shape[1:]), k.reshape(n, ks[0], *k.shape[1:]),
                    v.reshape(n, ks[0], *v.shape[1:]), scale)
        return out.reshape(-1, *out.shape[2:])
    if _nested_ok[0]:
        try:
            qo = torch.tensor([0, *accumulate(qs)], device=q.device, dtype=torch.int64)
            ko = torch.tensor([0, *accumulate(ks)], device=q.device, dtype=torch.int64)
            qn = torch.nested.nested_tensor_from_jagged(q, qo)
            kn = torch.nested.nested_tensor_from_jagged(k, ko)
            vn = torch.nested.nested_tensor_from_jagged(v, ko)
            out = F.scaled_dot_product_attention(qn.transpose(1, 2), kn.transpose(1, 2), vn.transpose(1, 2),
                                                 scale=scale)
            return out.transpose(1, 2).values()
        except (RuntimeError, NotImplementedError, TypeError, ValueError):
            _nested_ok[0] = False  # (this build cannot: one call per sequence from now on)
    outs, qa, ka = [], 0, 0
    for lq, lk in zip(qs, ks):
        outs.append(_bhlc(q[qa:qa + lq][None], k[ka:ka + lk][None], v[ka:ka + lk][None], scale)[0])
        qa, ka = qa + lq, ka + lk
    return torch.cat(outs, 0)


def memory_efficient_attention(query, key, value, attn_bias=None, p=0.0, scale=None, op=None, **_):
    """xformers' memory_efficient_attention for the inputs TRELLIS.2 gives it ([B, L, H, C]; no dropout)"""
    if p:
        raise NotImplementedError("xops_sdpa: dropout is not used at inference")
    if attn_bias is None:
        return _bhlc(query, key, value, scale)
    if not isinstance(attn_bias, BlockDiagonalMask) or query.shape[0] != 1:
        raise NotImplementedError("xops_sdpa: only a BlockDiagonalMask over one packed batch row")
    if sum(attn_bias.q_seqlen) != query.shape[1] or sum(attn_bias.kv_seqlen) != key.shape[1]:
        raise ValueError("xops_sdpa: the sequence lengths do not add up to the packed lengths")
    return _varlen(query[0], key[0], value[0], attn_bias.q_seqlen, attn_bias.kv_seqlen, scale)[None]
