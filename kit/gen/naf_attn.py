"""naf_attn.py — NAF, the feature upsampler Pixal3D uses, from the kit's vendored copy, with its neighbourhood attention
computed exactly in a fraction of the memory (kit-owned code).

Pixal3D sharpens DINOv3's 16-pixel patch features to pixel resolution with NAF (valeo.ai, Apache-2.0) before it
projects them into its voxel grid. NAF's own loader is torch.hub, which fetches the repository and runs its code at
run time; the kit loads a copy vendored at a pinned commit instead (~/.cache/roblox-kit/src/NAF @ 37f2dfc) and the
checkpoint checked against its pin.

NAF's cross-attention upsamples its keys and values to the output size (nearest) and runs NATTEN's dilated 9 x 9
neighbourhood attention there. In Pixal3D's texture stage that is 1024 x 1024 queries over 1024-channel values: the
upsampled values alone are 4 GiB, more than a 12 GB card has to spare next to everything else. Nearest upsampling by a
whole factor d makes every key in a dilated window the SAME low-resolution key, so the identical attention runs on the
low-resolution keys and values directly: the query at pixel (i, j) attends to the 9 x 9 low-resolution cells around
(i // d, j // d), the window shifted to stay inside the borders as NATTEN does. Same numbers (test_naf_attn.py checks
it against the definition; the install was checked against NATTEN's own Flex kernel), a few rows at a time.

    naf = load_naf(weights_path, device)       # NAF with the kit's attention, weights loaded strictly
    hr = naf(image, lowres_features, (H, W))   # as in Pixal3D: [B, 3, h0, w0], [B, C, h, w] -> [B, C, H, W]
"""

import os
import sys
import types

import torch

NAF_SRC = os.environ.get("KIT_NAF_SRC") or os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "src", "NAF")
NAF_COMMIT = "37f2dfc180f2de53d98bd601109c0da0dd6b0f43"


def _windows(n, k, device):
    """[n, k] indices: the k cells each of n positions attends to (centred, shifted inside the borders)"""
    start = (torch.arange(n, device=device) - k // 2).clamp(0, n - k)
    return start[:, None] + torch.arange(k, device=device)[None]


def lowres_neighbourhood_attention(q, k, v, kernel=(9, 9), scale=None, budget=1 << 29):
    """softmax(q k / sqrt(c)) v over each query's neighbourhood, with keys and values given at LOW resolution.

    q [B, n, c, H, W] at full resolution; k [B, n, c, h, w], v [B, n, cv, h, w] with H = dh * h, W = dw * w.
    Equals NATTEN's na2d(q, up(k), up(v), kernel, dilation=(dh, dw)) where up() is nearest upsampling to (H, W).
    `budget` caps the bytes of one block of output rows -> [B, n, cv, H, W]"""
    B, n, c, H, W = q.shape
    h, w = k.shape[-2:]
    cv = v.shape[2]
    kh, kw = (kernel, kernel) if isinstance(kernel, int) else kernel
    if H % h or W % w:
        raise ValueError(f"lowres attention: {H}x{W} is not a whole multiple of {h}x{w}")
    if h < kh or w < kw:
        raise ValueError(f"lowres attention: a {kh}x{kw} window does not fit in {h}x{w}")
    dh, dw = H // h, W // w
    scale = c ** -0.5 if scale is None else scale
    rows_idx, cols_idx = _windows(h, kh, q.device), _windows(w, kw, q.device)
    out = q.new_empty(B, n, cv, H, W)
    per_row = B * n * w * dh * dw * cv * q.element_size()
    step = max(1, min(h, budget // max(per_row, 1)))
    for p0 in range(0, h, step):
        p1 = min(h, p0 + step)
        P = p1 - p0
        rr = rows_idx[p0:p1]
        # the window of each low-res cell: [B, n, ch, P, kh, w, kw] -> [B, n, P, w, kh * kw, ch]
        kwin = k[:, :, :, rr][..., cols_idx].permute(0, 1, 3, 5, 4, 6, 2).reshape(B, n, P, w, kh * kw, c)
        vwin = v[:, :, :, rr][..., cols_idx].permute(0, 1, 3, 5, 4, 6, 2).reshape(B, n, P, w, kh * kw, cv)
        # the queries of each low-res cell: [B, n, c, P * dh, W] -> [B, n, P, w, dh * dw, c]
        qc = q[:, :, :, p0 * dh:p1 * dh].reshape(B, n, c, P, dh, w, dw).permute(0, 1, 3, 5, 4, 6, 2)
        qc = qc.reshape(B, n, P, w, dh * dw, c)
        att = torch.einsum("bnpwqc,bnpwkc->bnpwqk", qc, kwin).mul_(scale).softmax(-1)
        o = torch.einsum("bnpwqk,bnpwkc->bnpwqc", att, vwin)
        out[:, :, :, p0 * dh:p1 * dh] = o.reshape(B, n, P, w, dh, dw, cv).permute(0, 1, 6, 2, 4, 3, 5).reshape(
            B, n, cv, P * dh, W)
        del kwin, vwin, qc, att, o
    return out


def _kit_forward(original):
    def forward(self, q, k, v, image=None, return_weights=False, **kwargs):
        hq, wq = q.shape[-2:]
        hk, wk = k.shape[-2:]
        if return_weights or hq % hk or wq % wk or hk < self.kernel_size[0] or wk < self.kernel_size[1]:
            return original(self, q, k, v, image=image, return_weights=return_weights, **kwargs)
        B, n = q.shape[0], self.num_heads
        out = lowres_neighbourhood_attention(
            q.reshape(B, n, -1, hq, wq), k.to(q.dtype).reshape(B, n, -1, hk, wk),
            v.to(q.dtype).reshape(B, n, -1, hk, wk), kernel=self.kernel_size, scale=self.scale)
        return out.reshape(B, -1, hq, wq)

    forward._kit = True
    return forward


def vendored_commit(src=NAF_SRC):
    """the commit the vendored copy is checked out at (its .git/HEAD), or None"""
    head = os.path.join(src, ".git", "HEAD")
    if not os.path.isfile(head):
        return None
    with open(head, encoding="utf-8") as fh:
        return fh.read().strip()


def naf_module(src=NAF_SRC):
    """NAF's model module from the vendored copy (its `src` package registered under that name, nothing fetched)"""
    pkg = sys.modules.get("src")
    root = os.path.join(src, "src")
    if pkg is None:
        pkg = types.ModuleType("src")
        pkg.__path__ = [root]
        sys.modules["src"] = pkg
    elif list(getattr(pkg, "__path__", [])) != [root]:
        raise ImportError(f"another package named 'src' is loaded ({getattr(pkg, '__path__', None)})")
    import importlib.util  # noqa: PLC0415

    from src.layers import attentions  # noqa: PLC0415  (imports natten: Flex-only install, no libnatten)

    if not getattr(attentions.CrossAttention.forward, "_kit", False):
        attentions.CrossAttention.forward = _kit_forward(attentions.CrossAttention.forward)
    if "kit_naf_model" not in sys.modules:
        spec = importlib.util.spec_from_file_location("kit_naf_model", os.path.join(root, "model", "naf.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules["kit_naf_model"] = mod
    return sys.modules["kit_naf_model"]


def load_naf(weights, device="cpu", src=NAF_SRC):
    """NAF with its pretrained weights (weights-only load, every key must match) on `device`, in inference mode"""
    commit = vendored_commit(src)
    if commit != NAF_COMMIT:
        raise RuntimeError(f"NAF: the vendored copy in {src} is at {commit}, pinned {NAF_COMMIT}")
    model = naf_module(src).NAF()
    state = torch.load(weights, map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=True)
    model.train(False)
    return model.requires_grad_(False).to(device)
